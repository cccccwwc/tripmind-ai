"""Durable LangGraph orchestration for TripMind's hybrid planning workflow."""

from __future__ import annotations

import json
import operator
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..models.schemas import TripPlan, TripRequest, WeatherInfo
from ..services.poi_reliability_service import POIReliabilityService


def _merge_dicts(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    return {**(left or {}), **(right or {})}


class TripPlanningState(TypedDict, total=False):
    request: dict[str, Any]
    workflow_id: str
    approved: bool
    status: str
    attraction_response: str
    weather_response: str
    weather_data: list[dict[str, Any]]
    hotel_response: str
    hotel_candidates: list[dict[str, Any]]
    attraction_candidates: list[dict[str, Any]]
    attraction_round: int
    research_issues: list[str]
    retry_attractions: bool
    force_fallback: bool
    plan_needs_retry: bool
    plan_needs_fallback: bool
    poi_validation_report: dict[str, Any]
    rejected_attractions: list[dict[str, Any]]
    plan_revision: int
    trip_plan: dict[str, Any]
    raw_trip_plan: dict[str, Any]
    errors: Annotated[dict[str, str], _merge_dicts]
    events: Annotated[list[dict[str, Any]], operator.add]


class AgentExecutionError(RuntimeError):
    """A transient model or tool failure that LangGraph should retry."""


class WorkflowCancelledError(RuntimeError):
    """Raised at a safe graph boundary after the user cancels a job."""


class TripPlanningGraph:
    """Run deterministic data nodes, then one planning model, with checkpoints."""

    MAX_ATTRACTION_ROUNDS = 2
    MAX_AGENT_ATTEMPTS = 2

    def __init__(self, planner: Any, checkpoint_path: str | Path | None = None, checkpointer=None):
        self.planner = planner
        self._agent_locks = {
            "planner": threading.Lock(),
        }
        self._cancelled_workflows: set[str] = set()
        self._cancel_lock = threading.Lock()
        self._checkpoint_connection: sqlite3.Connection | None = None
        if checkpointer is None:
            backend_root = Path(__file__).resolve().parents[2]
            path = Path(checkpoint_path) if checkpoint_path else backend_root / "data" / "langgraph_checkpoints.db"
            if not path.is_absolute():
                path = backend_root / path
            path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_connection = sqlite3.connect(path, check_same_thread=False)
            checkpointer = SqliteSaver(self._checkpoint_connection)
            checkpointer.setup()
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    @classmethod
    def in_memory(cls, planner: Any) -> "TripPlanningGraph":
        """Build an isolated graph for tests without touching the project database."""
        return cls(planner, checkpointer=InMemorySaver())

    @staticmethod
    def _event(
        node: str,
        status: str,
        message: str,
        *,
        tool_name: str = "",
        tool_arguments: dict[str, Any] | None = None,
        attempts: int | None = None,
    ) -> list[dict[str, Any]]:
        event = {
            "node": node,
            "status": status,
            "message": message,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if tool_name:
            event["tool_name"] = tool_name
        if tool_arguments is not None:
            event["tool_arguments"] = tool_arguments
        if attempts is not None:
            event["attempts"] = attempts
        return [event]

    @staticmethod
    def _request(state: TripPlanningState) -> TripRequest:
        return TripRequest.model_validate(state["request"])

    @staticmethod
    def _response_failed(response: Any) -> bool:
        text = str(response or "").strip()
        if not text:
            return True
        failure_markers = (
            "connection error",
            "调用llm api时发生错误",
            "调用语言模型服务时出错",
            "调用超时",
            "未找到工具",
            "工具调用错误",
            "mcp 操作失败",
            "异步操作失败",
            "error calling tool",
            "工具执行失败",
        )
        normalized = text.casefold()
        return any(marker in normalized for marker in failure_markers)

    def _run_agent(self, role: str, agent: Any, prompt: str, **kwargs) -> str:
        # SimpleAgent keeps mutable history. A per-role lock makes the process-wide
        # planner safe when several HTTP requests arrive at the same time.
        with self._agent_locks[role]:
            agent.clear_history()
            response = agent.run(prompt, **kwargs)
        if self._response_failed(response):
            raise AgentExecutionError(f"{role} Agent 返回失败结果: {str(response)[:240]}")
        return str(response)

    def request_cancel(self, workflow_id: str) -> None:
        """Request cooperative cancellation for a running workflow."""
        with self._cancel_lock:
            self._cancelled_workflows.add(workflow_id)

    def clear_cancel(self, workflow_id: str) -> None:
        with self._cancel_lock:
            self._cancelled_workflows.discard(workflow_id)

    def _ensure_not_cancelled(self, state_or_id: TripPlanningState | str) -> None:
        workflow_id = (
            state_or_id
            if isinstance(state_or_id, str)
            else str(state_or_id.get("workflow_id", ""))
        )
        with self._cancel_lock:
            cancelled = workflow_id in self._cancelled_workflows
        if cancelled:
            raise WorkflowCancelledError("旅行规划已由用户取消")

    def _run_agent_with_retry(
        self,
        role: str,
        agent: Any,
        prompt: str,
        *,
        workflow_id: str = "",
        **kwargs,
    ) -> tuple[str, int]:
        """Retry route-planning model failures inside one durable graph node.

        LangGraph's node ``error_handler`` in the currently pinned release can
        execute after a parallel-branch failure while the sync runner still
        re-raises the original exception. Keeping the retry and typed fallback
        inside the node makes fan-in deterministic and persists only the final
        outcome of that node.
        """
        last_error: Exception | None = None
        for attempt in range(1, self.MAX_AGENT_ATTEMPTS + 1):
            try:
                self._ensure_not_cancelled(workflow_id)
                result = self._run_agent(role, agent, prompt, **kwargs)
                self._ensure_not_cancelled(workflow_id)
                return result, attempt
            except WorkflowCancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self.MAX_AGENT_ATTEMPTS:
                    time.sleep(0.5 * attempt)
        assert last_error is not None
        raise last_error

    def _run_operation_with_retry(
        self,
        operation,
        *,
        workflow_id: str,
        accept_empty: bool = False,
    ) -> tuple[Any, int]:
        """Retry deterministic HTTP/data operations without invoking an LLM."""
        last_error: Exception | None = None
        for attempt in range(1, self.MAX_AGENT_ATTEMPTS + 1):
            try:
                self._ensure_not_cancelled(workflow_id)
                result = operation()
                if not accept_empty and not result:
                    raise AgentExecutionError("确定性数据接口没有返回可用结果")
                self._ensure_not_cancelled(workflow_id)
                return result, attempt
            except WorkflowCancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self.MAX_AGENT_ATTEMPTS:
                    time.sleep(0.5 * attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _target_attraction_count(request: TripRequest) -> int:
        return min(12, max(2, request.travel_days * 2, len(request.selected_recommendations)))

    def _collect_verified_attractions(
        self,
        request: TripRequest,
        round_index: int,
        excluded_names: set[str] | None = None,
        excluded_poi_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        service = self.planner.poi_location_service
        reliability_service = getattr(self.planner, "poi_reliability_service", None)
        if reliability_service is None:
            reliability_service = POIReliabilityService()
            self.planner.poi_reliability_service = reliability_service
        target = self._target_attraction_count(request)
        collected: list[Any] = []
        seen: set[str] = set()
        excluded_names = {
            service._normalize(item) for item in (excluded_names or set()) if item
        }
        excluded_poi_ids = excluded_poi_ids or set()

        def append(poi: Any) -> None:
            if poi is None:
                return
            key = str(getattr(poi, "poi_id", "") or service._normalize(poi.name))
            normalized_name = service._normalize(poi.name)
            if (
                not key
                or key in seen
                or key in excluded_poi_ids
                or normalized_name in excluded_names
            ):
                return
            seen.add(key)
            collected.append(poi)

        for item in request.selected_recommendations:
            append(service.resolve(item.name, request.city))

        if round_index == 0:
            queries = [*(request.preferences[:1] or []), "旅游景点"]
        else:
            queries = [
                *request.preferences,
                "旅游景点",
                "历史文化",
                "博物馆",
                "公园",
                "文化场馆",
                "名胜古迹",
            ]

        for query in dict.fromkeys(item for item in queries if item):
            for poi in service.search(query, request.city, 25):
                append(poi)
                if len(collected) >= target:
                    break
            if len(collected) >= target:
                break

        collected = reliability_service.order_by_proximity(
            reliability_service.filter_spatial_outliers(collected)
        )
        return [
            {
                "poi_id": poi.poi_id,
                "name": poi.name,
                "address": poi.address,
                "city": poi.city or request.city,
                "district": poi.district,
                "poi_type": poi.poi_type,
                "poi_typecode": poi.poi_typecode,
                "location": {
                    "longitude": poi.longitude,
                    "latitude": poi.latitude,
                },
                "operational_status": poi.operational_status,
                "data_source": poi.data_source or "amap",
                "verified_at": poi.verified_at,
                "verification_confidence": poi.confidence,
            }
            for poi in collected[:target]
        ]

    def _merge_candidates(
        self,
        existing: list[dict[str, Any]],
        replacements: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keep prior valid POIs, remove rejected ones, then append replacements."""
        service = self.planner.poi_location_service
        rejected_ids = {str(item.get("poi_id") or "") for item in rejected if item.get("poi_id")}
        rejected_names = {
            service._normalize(item.get("name")) for item in rejected if item.get("name")
        }
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*existing, *replacements]:
            poi_id = str(item.get("poi_id") or "")
            normalized_name = service._normalize(item.get("name"))
            key = poi_id or normalized_name
            if (
                not key
                or key in seen
                or poi_id in rejected_ids
                or normalized_name in rejected_names
            ):
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _fallback_attraction_text(self, candidates: list[dict[str, Any]]) -> str:
        if not candidates:
            return "高德未返回可核验景点"
        return "高德校验后的景点候选：\n" + json.dumps(candidates, ensure_ascii=False)

    def _collect_verified_hotels(self, request: TripRequest) -> list[dict[str, Any]]:
        hotels = self.planner.poi_location_service.search(request.accommodation or "酒店", request.city, 8)
        if not hotels:
            hotels = self.planner.poi_location_service.search("酒店", request.city, 8)
        return [
            {
                "poi_id": item.poi_id,
                "name": item.name,
                "address": item.address,
                "city": item.city or request.city,
                "district": item.district,
                "poi_type": item.poi_type,
                "poi_typecode": item.poi_typecode,
                "location": {"longitude": item.longitude, "latitude": item.latitude},
                "operational_status": item.operational_status,
                "data_source": item.data_source or "amap",
                "verified_at": item.verified_at,
                "verification_confidence": item.confidence,
            }
            for item in hotels[:5]
        ]

    def _fallback_hotel_text(self, request: TripRequest) -> str:
        data = self._collect_verified_hotels(request)
        return "高德校验后的酒店候选：\n" + json.dumps(data, ensure_ascii=False)

    def _approval_node(self, state: TripPlanningState) -> dict[str, Any]:
        if state.get("approved") is True:
            return {
                "status": "approved",
                "events": self._event("approval", "completed", "用户已确认 Planning Brief"),
            }
        decision = interrupt({
            "type": "trip_planning_approval",
            "question": "是否确认这份 Planning Brief 并启动正式规划？",
            "planning_brief": state["request"],
        })
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        return {
            "approved": approved,
            "status": "approved" if approved else "rejected",
            "events": self._event(
                "approval",
                "completed" if approved else "rejected",
                "用户确认启动规划" if approved else "用户拒绝启动规划",
            ),
        }

    @staticmethod
    def _after_approval(state: TripPlanningState) -> str:
        return "prepare" if state.get("approved") else END

    def _prepare_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        return {
            "status": "researching",
            "attraction_round": 0,
            "plan_revision": 0,
            "rejected_attractions": [],
            "poi_validation_report": {},
            "errors": {},
            "events": self._event("prepare", "completed", "开始并行查询景点、天气和酒店"),
        }

    def _attraction_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        try:
            candidates, attempts = self._run_operation_with_retry(
                lambda: self._collect_verified_attractions(request, 0),
                workflow_id=state["workflow_id"],
            )
        except WorkflowCancelledError:
            raise
        except Exception as error:
            return self._attraction_error(state, error, round_index=0)
        return {
            "attraction_response": self._fallback_attraction_text(candidates),
            "attraction_candidates": candidates,
            "attraction_round": 0,
            "events": self._event(
                "attractions",
                "retried" if attempts > 1 else "completed",
                f"高德景点接口第 {attempts} 次请求成功，获得 {len(candidates)} 个可核验景点",
                tool_name="amap.poi.search",
                tool_arguments={
                    "city": request.city,
                    "preferences": request.preferences,
                    "selected_places": [item.name for item in request.selected_recommendations],
                },
                attempts=attempts,
            ),
        }

    def _weather_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        try:
            weather_items, attempts = self._run_operation_with_retry(
                lambda: self.planner.weather_service.get_forecast(
                    request.city,
                    request.start_date,
                    request.end_date,
                ),
                workflow_id=state["workflow_id"],
                # A future trip outside AMap's forecast window legitimately
                # returns an empty list and must not be treated as an outage.
                accept_empty=True,
            )
        except WorkflowCancelledError:
            raise
        except Exception as error:
            return self._weather_error(state, error)
        weather_data = [item.model_dump(mode="json") for item in weather_items]
        response = (
            "高德逐日天气数据：\n" + json.dumps(weather_data, ensure_ascii=False)
            if weather_data
            else "所选日期超出高德逐日天气预报窗口，不得编造天气；请在临近出发时更新。"
        )
        return {
            "weather_response": response,
            "weather_data": weather_data,
            "events": self._event(
                "weather",
                "retried" if attempts > 1 else "completed",
                f"高德天气接口第 {attempts} 次请求完成，返回 {len(weather_data)} 天预报",
                tool_name="amap.weather.forecast",
                tool_arguments={
                    "city": request.city,
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                },
                attempts=attempts,
            ),
        }

    def _hotel_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        try:
            hotels, attempts = self._run_operation_with_retry(
                lambda: self._collect_verified_hotels(request),
                workflow_id=state["workflow_id"],
            )
        except WorkflowCancelledError:
            raise
        except Exception as error:
            return self._hotel_error(state, error)
        return {
            "hotel_response": "高德校验后的酒店候选：\n" + json.dumps(hotels, ensure_ascii=False),
            "hotel_candidates": hotels,
            "events": self._event(
                "hotel",
                "retried" if attempts > 1 else "completed",
                f"高德酒店接口第 {attempts} 次请求成功，获得 {len(hotels)} 个候选",
                tool_name="amap.hotel.search",
                tool_arguments={"city": request.city, "accommodation": request.accommodation},
                attempts=attempts,
            ),
        }

    def _attraction_error(
        self,
        state: TripPlanningState,
        error: Exception,
        *,
        round_index: int,
    ) -> dict[str, Any]:
        request = self._request(state)
        rejected = state.get("rejected_attractions", [])
        candidates = self._merge_candidates(
            state.get("attraction_candidates", []),
            [],
            rejected,
        )[: self._target_attraction_count(request)]
        return {
            "attraction_response": self._fallback_attraction_text(candidates),
            "attraction_candidates": candidates,
            "attraction_round": round_index,
            "errors": {"attractions": str(error)},
            "events": self._event("attractions", "fallback", "高德景点接口重试失败，未获得足够候选"),
        }

    def _weather_error(self, state: TripPlanningState, error: Exception) -> dict[str, Any]:
        return {
            "weather_response": "天气服务暂不可用，行程需在出发前再次核对实时天气。",
            "weather_data": [],
            "errors": {"weather": str(error)},
            "events": self._event("weather", "fallback", "高德天气接口重试失败，已使用显式降级说明"),
        }

    def _hotel_error(self, state: TripPlanningState, error: Exception) -> dict[str, Any]:
        return {
            "hotel_response": "高德酒店服务暂不可用，行程暂不指定酒店，请稍后重试。",
            "hotel_candidates": [],
            "errors": {"hotel": str(error)},
            "events": self._event("hotel", "fallback", "高德酒店接口重试失败，行程将不指定酒店"),
        }

    def _validate_research_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        candidates = state.get("attraction_candidates", [])
        target = self._target_attraction_count(request)
        valid_candidates = [item for item in candidates if item.get("location")]
        issues: list[str] = []
        if len(valid_candidates) < target:
            issues.append(f"可核验景点不足：需要 {target} 个，当前 {len(valid_candidates)} 个")
        if not state.get("weather_response"):
            issues.append("天气结果缺失")
        if not state.get("hotel_response"):
            issues.append("酒店结果缺失")

        attraction_round = int(state.get("attraction_round", 0))
        should_retry = len(valid_candidates) < target and attraction_round < self.MAX_ATTRACTION_ROUNDS
        return {
            "status": "retrying_attractions" if should_retry else "planning",
            "research_issues": issues,
            "retry_attractions": should_retry,
            "force_fallback": len(valid_candidates) == 0 and not should_retry,
            "events": self._event(
                "validate_research",
                "retry" if should_retry else "completed",
                "；".join(issues) if issues else "景点、天气和酒店数据已汇合并通过校验",
            ),
        }

    @staticmethod
    def _after_research_validation(state: TripPlanningState) -> str:
        return "retry_attractions" if state.get("retry_attractions") else "plan"

    def _retry_attractions_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        round_index = int(state.get("attraction_round", 0)) + 1
        rejected = state.get("rejected_attractions", [])
        rejected_names = {str(item.get("name") or "") for item in rejected}
        rejected_ids = {
            str(item.get("poi_id") or "") for item in rejected if item.get("poi_id")
        }
        try:
            replacements, attempts = self._run_operation_with_retry(
                lambda: self._collect_verified_attractions(
                    request,
                    round_index,
                    excluded_names=rejected_names,
                    excluded_poi_ids=rejected_ids,
                ),
                workflow_id=state["workflow_id"],
            )
        except WorkflowCancelledError:
            raise
        except Exception as error:
            return self._attraction_error(state, error, round_index=round_index)
        candidates = self._merge_candidates(
            state.get("attraction_candidates", []),
            replacements,
            rejected,
        )[: self._target_attraction_count(request)]
        return {
            # Only this deterministic whitelist reaches the planner. The
            # natural-language agent response may still mention a rejected POI.
            "attraction_response": self._fallback_attraction_text(candidates),
            "attraction_candidates": candidates,
            "attraction_round": round_index,
            "retry_attractions": False,
            "events": self._event(
                "retry_attractions",
                "retried" if attempts > 1 else "completed",
                f"高德补搜第 {attempts} 次请求成功，排除 {len(rejected)} 个问题地点后共有 {len(candidates)} 个可核验景点",
                tool_name="amap.poi.search",
                tool_arguments={
                    "city": request.city,
                    "preferences": request.preferences,
                    "excluded_poi_ids": sorted(rejected_ids),
                },
                attempts=attempts,
            ),
        }

    def _planner_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        if state.get("force_fallback"):
            plan = self.planner._create_fallback_plan(request)
            raw_plan = None
            response = ""
            mode = "fallback"
            validation_report = self.planner._validate_attraction_reliability(plan, request.city)
        else:
            verified_context = self._fallback_attraction_text(state.get("attraction_candidates", []))
            prompt = self.planner._build_planner_query(
                request,
                f"{state.get('attraction_response', '')}\n\n{verified_context}",
                state.get("weather_response", ""),
                state.get("hotel_response", ""),
            )
            try:
                response, attempts = self._run_agent_with_retry(
                    "planner",
                    self.planner.planner_agent,
                    prompt,
                    workflow_id=state["workflow_id"],
                    temperature=0.2,
                    max_tokens=8192,
                )
            except WorkflowCancelledError:
                raise
            except Exception as error:
                return self._planner_error(state, error)
            raw_plan, plan = self.planner._parse_response_stages(response, request)
            mode = "retried" if attempts > 1 else "completed"
            self.planner._apply_verified_hotels(
                plan,
                state.get("hotel_candidates", []),
                request.accommodation,
            )
            validation_report = self.planner._verify_attraction_locations(plan, request.city)

        plan.weather_info = [
            WeatherInfo.model_validate(item) for item in state.get("weather_data", [])
        ]

        return {
            "trip_plan": plan.model_dump(mode="json"),
            "raw_trip_plan": raw_plan.model_dump(mode="json") if raw_plan else {},
            "poi_validation_report": validation_report.to_dict(),
            "plan_revision": int(state.get("plan_revision", 0)) + 1,
            "status": "validating_plan",
            "events": self._event(
                "plan",
                mode,
                "已生成结构化行程，正在校验地点与时间轴",
                tool_name="llm.trip_plan",
                tool_arguments={"city": request.city, "travel_days": request.travel_days},
                attempts=attempts if not state.get("force_fallback") else 0,
            ),
        }

    def _planner_error(self, state: TripPlanningState, error: Exception) -> dict[str, Any]:
        request = self._request(state)
        plan = self.planner._create_fallback_plan(request)
        plan.weather_info = [
            WeatherInfo.model_validate(item) for item in state.get("weather_data", [])
        ]
        validation_report = self.planner._validate_attraction_reliability(plan, request.city)
        return {
            "trip_plan": plan.model_dump(mode="json"),
            "raw_trip_plan": {},
            "poi_validation_report": validation_report.to_dict(),
            "plan_revision": int(state.get("plan_revision", 0)) + 1,
            "errors": {"planner": str(error)},
            "status": "validating_plan",
            "events": self._event("plan", "fallback", "规划 Agent 失败，已使用真实 POI 生成确定性行程"),
        }

    def _validate_plan_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        plan = TripPlan.model_validate(state["trip_plan"])
        attractions = [item for day in plan.days for item in day.attractions]
        verified = [item for item in attractions if item.location is not None]
        unique_verified = {self.planner.poi_location_service._normalize(item.name) for item in verified}
        available = len(state.get("attraction_candidates", []))
        expected = min(self._target_attraction_count(request), max(1, available))
        schedules_valid = all(
            day.schedule and self.planner._schedule_has_no_overlap(day.schedule)
            for day in plan.days
        )
        reliability_report = state.get("poi_validation_report", {})
        reliability_issues = list(reliability_report.get("issues") or [])
        reliability_failed = not bool(reliability_report.get("is_valid", False))
        rejected = list(state.get("rejected_attractions", []))
        known_rejections = {
            (str(item.get("poi_id") or ""), str(item.get("name") or ""), str(item.get("code") or ""))
            for item in rejected
        }
        for issue in reliability_issues:
            key = (
                str(issue.get("poi_id") or ""),
                str(issue.get("name") or ""),
                str(issue.get("code") or ""),
            )
            if key not in known_rejections:
                rejected.append(issue)
                known_rejections.add(key)
        plan_invalid = len(unique_verified) < expected or not schedules_valid or reliability_failed
        needs_retry = plan_invalid and int(state.get("attraction_round", 0)) < self.MAX_ATTRACTION_ROUNDS
        needs_fallback = plan_invalid and not needs_retry
        issues = []
        if len(unique_verified) < expected:
            issues.append(f"最终行程仅有 {len(unique_verified)}/{expected} 个可核验景点")
        if not schedules_valid:
            issues.append("最终行程存在空白或冲突时间轴")
        if reliability_issues:
            issues.extend(
                f"{item.get('name')}：{item.get('reason')}" for item in reliability_issues[:5]
            )
        return {
            "status": "retrying_attractions" if needs_retry else "fallback" if needs_fallback else "completed",
            "plan_needs_retry": needs_retry,
            "plan_needs_fallback": needs_fallback,
            "rejected_attractions": rejected,
            "events": self._event(
                "validate_plan",
                "retry" if needs_retry else "fallback" if needs_fallback else "completed",
                "；".join(issues) if issues else "地点坐标和每日时间轴校验通过",
            ),
        }

    @staticmethod
    def _after_plan_validation(state: TripPlanningState) -> str:
        if state.get("plan_needs_retry"):
            return "retry_attractions"
        if state.get("plan_needs_fallback"):
            return "fallback_plan"
        return END

    def _fallback_plan_node(self, state: TripPlanningState) -> dict[str, Any]:
        self._ensure_not_cancelled(state)
        request = self._request(state)
        plan = self.planner._create_fallback_plan(request)
        plan.weather_info = [
            WeatherInfo.model_validate(item) for item in state.get("weather_data", [])
        ]
        validation_report = self.planner._validate_attraction_reliability(plan, request.city)
        if not validation_report.is_valid:
            reasons = "；".join(issue.reason for issue in validation_report.issues[:5])
            raise RuntimeError(f"高德确定性行程仍未通过可靠性校验：{reasons}")
        return {
            "trip_plan": plan.model_dump(mode="json"),
            "poi_validation_report": validation_report.to_dict(),
            "status": "completed",
            "plan_needs_fallback": False,
            "events": self._event("fallback_plan", "completed", "已用高德真实 POI 重建可用行程"),
        }

    def _build_graph(self):
        builder = StateGraph(TripPlanningState)
        builder.add_node("approval", self._approval_node)
        builder.add_node("prepare", self._prepare_node)
        builder.add_node("attractions", self._attraction_node)
        builder.add_node("weather", self._weather_node)
        builder.add_node("hotel", self._hotel_node)
        builder.add_node("validate_research", self._validate_research_node)
        builder.add_node("retry_attractions", self._retry_attractions_node)
        builder.add_node("plan", self._planner_node)
        builder.add_node("validate_plan", self._validate_plan_node)
        builder.add_node("fallback_plan", self._fallback_plan_node)

        builder.add_edge(START, "approval")
        builder.add_conditional_edges("approval", self._after_approval, {"prepare": "prepare", END: END})
        builder.add_edge("prepare", "attractions")
        builder.add_edge("prepare", "weather")
        builder.add_edge("prepare", "hotel")
        builder.add_edge(["attractions", "weather", "hotel"], "validate_research")
        builder.add_conditional_edges(
            "validate_research",
            self._after_research_validation,
            {"retry_attractions": "retry_attractions", "plan": "plan"},
        )
        builder.add_edge("retry_attractions", "validate_research")
        builder.add_edge("plan", "validate_plan")
        builder.add_conditional_edges(
            "validate_plan",
            self._after_plan_validation,
            {"retry_attractions": "retry_attractions", "fallback_plan": "fallback_plan", END: END},
        )
        builder.add_edge("fallback_plan", END)
        return builder.compile(checkpointer=self.checkpointer)

    @staticmethod
    def _config(workflow_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": workflow_id}, "recursion_limit": 30}

    @staticmethod
    def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
        interrupts = result.get("__interrupt__", [])
        if not interrupts:
            return None
        value = getattr(interrupts[0], "value", None)
        return value if isinstance(value, dict) else {"question": str(value)}

    def start(self, request: TripRequest, *, require_approval: bool, workflow_id: str | None = None) -> dict[str, Any]:
        workflow_id = workflow_id or f"trip-{uuid4().hex}"
        self.clear_cancel(workflow_id)
        existing = self.graph.get_state(self._config(workflow_id))
        if existing.values:
            raise ValueError(f"工作流 {workflow_id} 已存在，请恢复原工作流或使用新的 workflow_id")
        initial: TripPlanningState = {
            "request": request.model_dump(mode="json"),
            "workflow_id": workflow_id,
            "approved": not require_approval,
            "status": "awaiting_approval" if require_approval else "approved",
            "attraction_round": 0,
            "errors": {},
            "events": [],
        }
        result = self.graph.invoke(initial, config=self._config(workflow_id))
        return self._to_result(workflow_id, result)

    def resume(self, workflow_id: str, approved: bool | None = None) -> dict[str, Any]:
        config = self._config(workflow_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            raise KeyError(workflow_id)
        graph_input: Any = Command(resume=approved) if approved is not None else None
        result = self.graph.invoke(graph_input, config=config)
        return self._to_result(workflow_id, result)

    def status(self, workflow_id: str) -> dict[str, Any]:
        snapshot = self.graph.get_state(self._config(workflow_id))
        if not snapshot.values:
            raise KeyError(workflow_id)
        values = dict(snapshot.values)
        if snapshot.interrupts:
            values["__interrupt__"] = snapshot.interrupts
        return self._to_result(workflow_id, values)

    def run(self, request: TripRequest, workflow_id: str | None = None) -> TripPlan:
        result = self.start(request, require_approval=False, workflow_id=workflow_id)
        if not result.get("trip_plan"):
            raise RuntimeError("LangGraph 工作流未生成旅行计划")
        return TripPlan.model_validate(result["trip_plan"])

    def _to_result(self, workflow_id: str, values: dict[str, Any]) -> dict[str, Any]:
        approval_prompt = self._interrupt_payload(values)
        status = "awaiting_approval" if approval_prompt else values.get("status", "unknown")
        return {
            "workflow_id": workflow_id,
            "status": status,
            "approval_prompt": approval_prompt,
            "trip_plan": values.get("trip_plan"),
            "raw_trip_plan": values.get("raw_trip_plan"),
            "poi_validation_report": values.get("poi_validation_report", {}),
            "errors": values.get("errors", {}),
            "events": values.get("events", []),
        }
