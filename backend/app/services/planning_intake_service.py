"""Conversation-first travel requirement collection."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from ..models.schemas import (
    PlanningBrief,
    PlanningIntakeRequest,
    PlanningIntakeResponse,
    ProjectedLongTermMemory,
)
from .llm_service import get_llm


SYSTEM_PROMPT = """你是 TripMind 的旅行需求顾问。你当前只负责多轮澄清和整理 Planning Brief，绝不能生成正式行程、景点列表或路线。

请阅读已有简报和对话，只提取用户明确表达的信息。不要猜测目的地或日期。相对日期必须结合今天转换为 YYYY-MM-DD。
每轮最多追问一个最重要的问题，语气自然、简短。目的地、开始日期、结束日期是启动前必填项；交通、住宿有默认值，偏好可以为空。

只返回以下 JSON，不要使用 Markdown：
{
  "assistant_message": "给用户的简短回复或下一个问题",
  "brief": {
    "city": null,
    "start_date": null,
    "end_date": null,
    "requested_days": null,
    "transportation": "公共交通",
    "accommodation": "舒适型酒店",
    "preferences": [],
    "free_text_input": ""
  }
}

规则：
1. brief 只填写用户已明确提供或已有简报中的内容。
2. 用户修改信息时采用最新表达。
3. 日期跨度不得超过 30 天。
4. 信息齐全时，assistant_message 请概括并提示用户检查右侧 Planning Brief 后明确确认。
5. 即使用户在消息中说“确认”，也只更新简报，不启动正式规划。
6. requested_days 只记录用户明确说出的“玩4天”“九天”等时长；不能根据起止日期推测或覆盖它。
7. 如果已有 requested_days，而用户本轮只提供日期，必须原样保留 requested_days。
"""

INTAKE_UNAVAILABLE_MESSAGE = "我暂时没有正确整理这条信息，请换一种说法再试一次。"


class PlanningIntakeUnavailableError(RuntimeError):
    """The model did not produce a usable structured intake response."""


class PlanningIntakeService:
    required_fields = ("city", "start_date", "end_date")
    field_labels = {
        "city": "目的地",
        "start_date": "出发日期",
        "end_date": "返程日期",
        "duration_conflict": "旅行天数冲突",
    }

    chinese_digits = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9,
    }

    @staticmethod
    def _extract_json(text: str | None) -> dict[str, Any]:
        """Extract the first complete JSON object from a model response.

        OpenAI-compatible providers may wrap JSON in Markdown or add a short
        sentence before it.  ``raw_decode`` lets us accept those harmless
        wrappers while still rejecting truncated or malformed JSON.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("模型返回了空内容")

        cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "").strip()
        decoder = json.JSONDecoder()
        last_error: json.JSONDecodeError | None = None

        for match in re.finditer(r"\{", cleaned):
            try:
                data, _ = decoder.raw_decode(cleaned[match.start():])
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if isinstance(data, dict) and ({"assistant_message", "brief"} & data.keys()):
                return data

        if last_error is not None:
            raise last_error
        raise ValueError("需求 Agent 未返回 JSON 对象")

    @staticmethod
    def _messages_for_attempt(prompt: str, invalid_response: str | None = None) -> list[dict[str, str]]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        if invalid_response is not None:
            # Keep the broken response bounded so a provider error page or a
            # runaway answer cannot consume the second request's context.
            messages.extend([
                {"role": "assistant", "content": invalid_response[:3000]},
                {
                    "role": "user",
                    "content": (
                        "上一条回复不是完整、合法的 JSON。请根据原始对话重新输出一次；"
                        "只允许输出一个 JSON 对象，不要 Markdown、解释或省略号。"
                    ),
                },
            ])
        return messages

    @classmethod
    def _missing_fields(cls, brief: PlanningBrief) -> list[str]:
        return [field for field in cls.required_fields if not getattr(brief, field)]

    @classmethod
    def _extract_requested_days(cls, text: str) -> int | None:
        """Read an explicitly stated duration such as ``4天`` or ``九天``."""
        arabic = re.search(r"(?<!\d)([1-9]|[12]\d|30)\s*天", text)
        if arabic:
            return int(arabic.group(1))

        chinese = re.search(r"([一二两三四五六七八九十]{1,3})\s*天", text)
        if not chinese:
            return None
        value = chinese.group(1)
        if value == "十":
            return 10
        if "十" in value:
            tens, ones = value.split("十", 1)
            result = (cls.chinese_digits.get(tens, 1) if tens else 1) * 10
            result += cls.chinese_digits.get(ones, 0) if ones else 0
            return result if 1 <= result <= 30 else None
        return cls.chinese_digits.get(value)

    @staticmethod
    def _has_duration_conflict(brief: PlanningBrief) -> bool:
        return bool(
            brief.requested_days
            and brief.travel_days
            and brief.requested_days != brief.travel_days
        )

    @staticmethod
    def _project_memory(request: PlanningIntakeRequest, brief: PlanningBrief) -> None:
        normalized_city = (brief.city or "").strip().lower()
        brief.memory_projection.visited_places = list(dict.fromkeys(
            item.name for item in request.travel_memory
            if normalized_city and item.city.strip().lower() == normalized_city
        ))
        brief.memory_projection.carryover_places = list(dict.fromkeys(request.carryover_places))
        applicable = [
            item for item in request.long_term_memory
            if not item.scope_city.strip()
            or not normalized_city
            or item.scope_city.strip().lower() == normalized_city
        ]
        brief.memory_projection.applied_preferences = [
            ProjectedLongTermMemory(
                id=item.id,
                content=item.content,
                evidence=item.evidence,
                source_conversation_id=item.source_conversation_id,
            )
            for item in applicable if item.kind == "preference"
        ]
        brief.memory_projection.applied_avoidances = [
            ProjectedLongTermMemory(
                id=item.id,
                content=item.content,
                evidence=item.evidence,
                source_conversation_id=item.source_conversation_id,
            )
            for item in applicable if item.kind == "avoidance"
        ]

    def refine(self, request: PlanningIntakeRequest) -> PlanningIntakeResponse:
        current = request.brief.model_dump(exclude={"memory_projection"})
        # Compatibility with briefs created before requested_days existed.
        if (
            not current.get("requested_days")
            and current.get("travel_days")
            and not (current.get("start_date") and current.get("end_date"))
        ):
            current["requested_days"] = current["travel_days"]
        conversation = "\n".join(
            f"{message.role}: {message.content}" for message in request.messages[-12:]
        )
        prompt = (
            f"今天是 {date.today().isoformat()}。\n"
            f"已有 Planning Brief：{json.dumps(current, ensure_ascii=False)}\n"
            "用户已审批且本次启用的长期旅行记忆："
            f"{json.dumps([item.model_dump() for item in request.long_term_memory], ensure_ascii=False)}\n"
            "长期记忆只作为上下文；用户本轮明确表达与记忆冲突时，以本轮表达为准。\n"
            f"对话记录：\n{conversation}"
        )

        llm = get_llm()
        parsed: dict[str, Any] | None = None
        invalid_response: str | None = None
        last_error: Exception | None = None

        # A single provider response can occasionally be empty, truncated, or
        # contain invalid JSON. Retry once with an explicit repair instruction.
        for attempt in range(2):
            raw: str | None = None
            try:
                raw = llm.invoke(
                    self._messages_for_attempt(prompt, invalid_response if attempt else None),
                    temperature=0,
                    max_tokens=1200,
                )
                parsed = self._extract_json(raw)
                break
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                last_error = exc
                invalid_response = raw if isinstance(raw, str) else ""
                print(f"⚠️ 需求 Agent 第 {attempt + 1} 次返回无法解析: {exc}")

        if parsed is None:
            print(f"❌ 需求 Agent 连续返回无效 JSON: {last_error}")
            raise PlanningIntakeUnavailableError(INTAKE_UNAVAILABLE_MESSAGE) from last_error

        update = parsed.get("brief") if isinstance(parsed.get("brief"), dict) else {}

        # Duration is extracted deterministically from the latest user turn.
        # This prevents the model from silently replacing “4天” with a 9-day
        # date span merely because the next message contains 10.1-10.9.
        latest_user_message = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        explicit_days = self._extract_requested_days(latest_user_message)
        if explicit_days is not None:
            update["requested_days"] = explicit_days
        elif re.search(r"(?:按|以).{0,4}日期|日期.{0,3}为准", latest_user_message):
            if current.get("travel_days"):
                update["requested_days"] = current["travel_days"]
            else:
                update.pop("requested_days", None)
        else:
            # A duration not explicitly mentioned in this user turn must not
            # be invented or overwritten by the model.
            update.pop("requested_days", None)

        # Merge with the existing brief so a later short answer such as “高铁”
        # cannot erase facts collected in earlier turns.
        merged = dict(current)
        for key in current:
            if key in update and update[key] is not None:
                merged[key] = update[key]
        brief = PlanningBrief(**merged)
        self._project_memory(request, brief)
        missing = self._missing_fields(brief)
        duration_conflict = self._has_duration_conflict(brief)
        if duration_conflict:
            missing.append("duration_conflict")

        assistant_message = str(parsed.get("assistant_message") or "").strip()
        if duration_conflict:
            assistant_message = (
                f"你之前计划玩 {brief.requested_days} 天，但 "
                f"{brief.start_date} 至 {brief.end_date} 按首尾日期计算共 {brief.travel_days} 天。"
                f"请确认按 {brief.travel_days} 天，或者提供新的 {brief.requested_days} 天日期。"
            )
        elif not assistant_message:
            if missing:
                assistant_message = f"请告诉我{self.field_labels[missing[0]]}。"
            else:
                assistant_message = "信息已经整理好了，请检查右侧 Planning Brief，确认后我再开始正式规划。"

        return PlanningIntakeResponse(
            assistant_message=assistant_message,
            brief=brief,
            missing_fields=missing,
            ready_to_confirm=not missing,
        )


_planning_intake_service: PlanningIntakeService | None = None


def get_planning_intake_service() -> PlanningIntakeService:
    global _planning_intake_service
    if _planning_intake_service is None:
        _planning_intake_service = PlanningIntakeService()
    return _planning_intake_service
