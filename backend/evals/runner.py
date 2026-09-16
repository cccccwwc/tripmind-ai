"""Command line runner for TripMind offline regression and live API evaluation.

Examples:
    python -m evals.runner --runs evals/data/sample_runs.jsonl
    python -m evals.runner --live --confirm-live --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .metrics import evaluate_case, summarize_results, threshold_failures


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "data" / "trip_eval_dataset.jsonl"
DEFAULT_REPORTS = ROOT / "reports"
DEFAULT_THRESHOLDS = {
    "brief_accuracy": 0.90,
    "tool_selection_f1": 0.95,
    "tool_argument_accuracy": 0.95,
    "poi_city_pass_rate": 0.98,
    "poi_coordinate_pass_rate": 0.98,
    "poi_identity_pass_rate": 0.98,
    "poi_combined_pass_rate": 0.88,
    "selected_place_coverage_rate": 0.90,
    "completion_rate": 0.95,
}
DEFAULT_MAXIMUMS = {
    "schedule_conflict_rate": 0.0,
    "fallback_rate": 0.20,
}
RELEASE_THRESHOLDS = {
    "raw_capture_coverage_rate": 0.95,
    "raw_output_coverage_rate": 0.80,
    "raw_stage_score": 0.65,
    "final_stage_score": 0.80,
    "final_poi_type_coverage_rate": 0.95,
    "final_poi_type_pass_rate": 0.95,
    "final_route_distance_pass_rate": 0.95,
    "final_commute_coverage_rate": 0.60,
    "final_commute_duration_pass_rate": 0.85,
    "final_avoidance_pass_rate": 1.0,
    "human_review_coverage_rate": 1.0,
    "human_score": 0.80,
}
HARD_TAGS = {
    "avoidance",
    "accessibility",
    "intake-only",
    "missing-date",
    "missing-city",
    "multi-turn",
    "partial-day",
    "winter",
    "pace-limit",
    "constraint",
    "duration-conflict",
    "correction",
    "memory-override",
    "regression",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number} 不是合法 JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{number} 必须是 JSON 对象")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            payload = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _estimated_tokens(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    non_cjk = re.sub(r"[\u3400-\u9fff]", "", text)
    return max(1, int(cjk * 1.15 + len(non_cjk) / 4))


def _tool_calls_from_events(
    events: list[dict[str, Any]],
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    mapping = {
        "attractions": ("amap.poi.search", {
            "city": request["city"],
            "preferences": request.get("preferences") or [],
        }),
        "weather": ("amap.weather.forecast", {
            "city": request["city"],
            "start_date": request["start_date"],
            "end_date": request["end_date"],
        }),
        "hotel": ("amap.hotel.search", {
            "city": request["city"],
            "accommodation": request["accommodation"],
        }),
        "plan": ("llm.trip_plan", {
            "city": request["city"],
            "travel_days": request["travel_days"],
        }),
    }
    calls: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        node = str(event.get("node") or "")
        if node not in mapping or node in seen:
            continue
        seen.add(node)
        name, fallback_arguments = mapping[node]
        calls.append({
            "name": event.get("tool_name") or name,
            "arguments": event.get("tool_arguments") or fallback_arguments,
            "success": str(event.get("node_status") or event.get("status") or "").casefold() != "fallback",
        })
    return calls


def _normal(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(value or "").casefold())


def _route_mode(value: Any) -> str:
    text = _normal(value)
    if any(token in text for token in ("自驾", "打车", "包车", "租车", "出租", "网约")):
        return "driving"
    if any(token in text for token in ("公交", "地铁", "轨道", "公共交通")):
        return "transit"
    return "walking"


def _location_index(day: dict[str, Any]) -> dict[str, tuple[float, float]]:
    index: dict[str, tuple[float, float]] = {}

    def add(item: dict[str, Any] | None) -> None:
        if not item or not isinstance(item.get("location"), dict):
            return
        try:
            point = (float(item["location"]["longitude"]), float(item["location"]["latitude"]))
        except (KeyError, TypeError, ValueError):
            return
        for value in (item.get("name"), item.get("address")):
            key = _normal(value)
            if key:
                index[key] = point

    for item in day.get("attractions") or []:
        add(item)
    for item in day.get("meals") or []:
        add(item)
    add(day.get("hotel"))
    return index


def _match_point(value: Any, index: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    key = _normal(value)
    if not key:
        return None
    if key in index:
        return index[key]
    matches = [point for label, point in index.items() if len(label) >= 3 and (label in key or key in label)]
    return matches[0] if matches else None


def _amap_route_truth(
    client: httpx.Client,
    api_key: str,
    origin: tuple[float, float],
    destination: tuple[float, float],
    mode: str,
    city: str,
) -> dict[str, Any]:
    endpoint = {
        "driving": "https://restapi.amap.com/v3/direction/driving",
        "transit": "https://restapi.amap.com/v3/direction/transit/integrated",
        "walking": "https://restapi.amap.com/v3/direction/walking",
    }[mode]
    params = {
        "key": api_key,
        "origin": f"{origin[0]:.6f},{origin[1]:.6f}",
        "destination": f"{destination[0]:.6f},{destination[1]:.6f}",
    }
    if mode == "transit":
        params.update({"city": city, "cityd": city})
    response = client.get(endpoint, params=params)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "1":
        raise RuntimeError(str(payload.get("info") or "AMap route error"))
    route = payload.get("route") or {}
    candidates = route.get("transits") if mode == "transit" else route.get("paths")
    first = (candidates or [None])[0]
    if not isinstance(first, dict):
        raise RuntimeError("AMap route has no path")
    return {
        "actual_distance_meters": float(first.get("distance") or 0),
        "actual_duration_seconds": float(first.get("duration") or 0),
    }


def collect_route_checks(plan: dict[str, Any], *, maximum_checks: int = 12) -> list[dict[str, Any]]:
    api_key = (os.getenv("AMAP_API_KEY") or "").strip()
    if not api_key or not plan:
        return []
    checks: list[dict[str, Any]] = []
    with httpx.Client(timeout=25) as route_client:
        for day in plan.get("days") or []:
            index = _location_index(day)
            for item in day.get("schedule") or []:
                if item.get("item_type") != "transport" or len(checks) >= maximum_checks:
                    continue
                origin = _match_point(item.get("from_location"), index)
                destination = _match_point(item.get("to_location"), index)
                check = {
                    "date": day.get("date"),
                    "from": item.get("from_location"),
                    "to": item.get("to_location"),
                    "mode": _route_mode(item.get("transport_mode")),
                    "planned_duration_minutes": float(item.get("duration_minutes") or 0),
                    "success": False,
                }
                if origin is None or destination is None:
                    check["error"] = "unresolved_endpoint"
                    checks.append(check)
                    continue
                try:
                    truth = _amap_route_truth(
                        route_client,
                        api_key,
                        origin,
                        destination,
                        check["mode"],
                        str(plan.get("city") or ""),
                    )
                    check.update(truth)
                    check["success"] = bool(truth["actual_duration_seconds"])
                except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
                    check["error"] = str(exc)[:160]
                checks.append(check)
            if len(checks) >= maximum_checks:
                break
    return checks


def _trip_request(brief: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    return {
        "city": brief["city"],
        "start_date": brief["start_date"],
        "end_date": brief["end_date"],
        "travel_days": brief["travel_days"],
        "transportation": brief.get("transportation") or "公共交通",
        "accommodation": brief.get("accommodation") or "舒适型酒店",
        "preferences": brief.get("preferences") or [],
        "free_text_input": brief.get("free_text_input") or "",
        "selected_recommendations": [
            {"name": name, "category": "景点", "reason": "评测数据集指定", "source_url": ""}
            for name in case.get("selected_places") or []
        ],
    }


def collect_live_run(
    client: httpx.Client,
    base_url: str,
    case: dict[str, Any],
    *,
    timeout_seconds: float,
    input_cost_per_million: float,
    output_cost_per_million: float,
    maximum_route_checks: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    record: dict[str, Any] = {"case_id": case["id"], "source": "live-api"}
    intake_payload = {
        "messages": case["messages"],
        "brief": {},
        "travel_memory": case.get("travel_memory", []),
        "carryover_places": case.get("carryover_places", []),
        "long_term_memory": case.get("long_term_memory", []),
    }
    try:
        intake_response = client.post(f"{base_url}/api/trip/intake", json=intake_payload)
        intake_response.raise_for_status()
        intake = intake_response.json()
        record["planning_brief"] = intake.get("brief") or {}
        if not case.get("should_plan", True):
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            record["tool_calls"] = []
            return record
        if not intake.get("ready_to_confirm"):
            raise RuntimeError(f"Planning Brief 未就绪: {intake.get('missing_fields')}")

        request = _trip_request(record["planning_brief"], case)
        job_response = client.post(f"{base_url}/api/trip/jobs", json=request)
        job_response.raise_for_status()
        job = job_response.json()
        deadline = time.monotonic() + timeout_seconds
        while job.get("status") not in {"completed", "failed", "cancelled", "interrupted"}:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"任务 {job.get('job_id')} 超过 {timeout_seconds:.0f} 秒")
            time.sleep(1)
            response = client.get(f"{base_url}/api/trip/jobs/{job['job_id']}")
            response.raise_for_status()
            job = response.json()
        event_response = client.get(f"{base_url}/api/trip/jobs/{job['job_id']}/events")
        event_response.raise_for_status()
        events = _parse_sse(event_response.text)
        raw_trip_plan = next(
            (event.get("raw_data") for event in reversed(events) if "raw_data" in event),
            None,
        )
        record.update({
            "trip_plan": job.get("data"),
            "raw_trip_plan": raw_trip_plan or {},
            "events": events,
            "errors": ({"job": job.get("error")} if job.get("error") else {}),
            "tool_calls": _tool_calls_from_events(events, request),
            "error": job.get("error"),
        })
        record["route_checks"] = collect_route_checks(
            record.get("trip_plan") or {},
            maximum_checks=maximum_route_checks,
        )
    except Exception as exc:
        record["error"] = str(exc)
        record.setdefault("planning_brief", {})
        record.setdefault("tool_calls", [])
        record.setdefault("events", [])
    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    input_tokens = _estimated_tokens(intake_payload)
    output_tokens = _estimated_tokens({
        "planning_brief": record.get("planning_brief"),
        "trip_plan": record.get("trip_plan"),
    })
    record["usage"] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "api_cost_usd": round(
            input_tokens * input_cost_per_million / 1_000_000
            + output_tokens * output_cost_per_million / 1_000_000,
            6,
        ),
        "estimated": True,
    }
    return record


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "")
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("LLM judge 没有返回 JSON 对象")


def judge_run(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model = os.getenv("LLM_MODEL_ID") or "deepseek-chat"
    if not api_key:
        raise RuntimeError("运行 LLM-as-judge 前必须配置 LLM_API_KEY 或 DEEPSEEK_API_KEY")
    prompt = {
        "task": "请评估旅行规划质量。不要奖励文风，只依据参考需求与结构化行程。",
        "rubric": {
            "correctness": "城市、日期和地点是否正确，1-5",
            "route_practicality": "时间和地理路线是否可执行，1-5",
            "preference_alignment": "是否满足偏好、避雷和用户选择，1-5",
            "explanation_quality": "建议是否具体、清楚且不编造，1-5",
        },
        "required_output": {
            "correctness": 1,
            "route_practicality": 1,
            "preference_alignment": 1,
            "explanation_quality": 1,
            "reason": "100字以内证据",
        },
        "case": case,
        "run": {
            "planning_brief": run.get("planning_brief"),
            "trip_plan": run.get("trip_plan"),
            "error": run.get("error"),
        },
    }
    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": "你是严格的旅行 Agent 评测员，只输出一个 JSON 对象。"},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
    judged = _extract_json_object(payload["choices"][0]["message"]["content"])
    usage = payload.get("usage") or {}
    judged["usage"] = {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }
    return judged


def _index(rows: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("case_id") or row.get("id") or "")
        if not key:
            raise ValueError(f"{name} 中存在没有 case_id/id 的记录")
        if key in indexed:
            raise ValueError(f"{name} 中 case_id 重复: {key}")
        indexed[key] = row
    return indexed


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    percent_metrics = [
        ("规则总分", "rule_score"),
        ("Planning Brief 准确率", "brief_accuracy"),
        ("工具选择 F1", "tool_selection_f1"),
        ("工具参数准确率", "tool_argument_accuracy"),
        ("POI 城市通过率", "poi_city_pass_rate"),
        ("POI 坐标通过率", "poi_coordinate_pass_rate"),
        ("POI 身份通过率", "poi_identity_pass_rate"),
        ("POI 综合通过率", "poi_combined_pass_rate"),
        ("POI 营业状态数据覆盖率", "poi_open_status_coverage_rate"),
        ("行程时间冲突率", "schedule_conflict_rate"),
        ("用户选择地点覆盖率", "selected_place_coverage_rate"),
        ("降级触发率", "fallback_rate"),
        ("任务完成率", "completion_rate"),
    ]
    lines = [
        "# TripMind Agent 评测报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 数据集：`{report['dataset']}`",
        f"- 运行来源：`{report['run_source']}`",
        f"- 样本数：{summary['case_count']}（需要正式规划 {summary['planned_case_count']}）",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {label} | {summary[key] * 100:.2f}% |" for label, key in percent_metrics)
    lines.extend([
        f"| 平均耗时 | {summary['average_latency_ms'] / 1000:.2f}s |",
        f"| 输入 Token | {summary['total_input_tokens']} |",
        f"| 输出 Token | {summary['total_output_tokens']} |",
        f"| API 成本 | ${summary['total_api_cost_usd']:.6f} |",
    ])
    if summary.get("human_score") is not None:
        lines.append(f"| 人工评分 | {summary['human_score'] * 100:.2f}% |")
    if summary.get("llm_judge_score") is not None:
        lines.append(f"| LLM-as-judge 抽检分 | {summary['llm_judge_score'] * 100:.2f}% |")
    lines.extend([
        "",
        "## 原始输出 vs 修复后输出",
        "",
        "| 阶段 | 捕获/输出覆盖 | 质量分 | POI 类型 | 路线距离 | 避雷约束 | 真实通勤时间 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| 原始模型输出 | {summary['raw_capture_coverage_rate'] * 100:.2f}% | "
            f"{summary['raw_stage_score'] * 100:.2f}% | {summary['raw_poi_type_pass_rate'] * 100:.2f}% | "
            f"{summary['raw_route_distance_pass_rate'] * 100:.2f}% | {summary['raw_avoidance_pass_rate'] * 100:.2f}% | 不调用外部路线 |"
        ),
        (
            f"| 修复后最终输出 | {summary['final_output_coverage_rate'] * 100:.2f}% | "
            f"{summary['final_stage_score'] * 100:.2f}% | {summary['final_poi_type_pass_rate'] * 100:.2f}% | "
            f"{summary['final_route_distance_pass_rate'] * 100:.2f}% | {summary['final_avoidance_pass_rate'] * 100:.2f}% | "
            f"{summary['final_commute_duration_pass_rate'] * 100:.2f}% |"
        ),
    ])
    hard = report.get("hard_set") or {}
    hard_summary = hard.get("summary") or {}
    if hard_summary:
        lines.extend([
            "",
            "## Hard-set",
            "",
            f"- 样本数：{hard_summary['case_count']}",
            f"- 规则总分：{hard_summary['rule_score'] * 100:.2f}%",
            f"- 原始输出质量：{hard_summary['raw_stage_score'] * 100:.2f}%",
            f"- 修复后输出质量：{hard_summary['final_stage_score'] * 100:.2f}%",
            f"- 人工评分覆盖：{hard_summary['human_review_coverage_rate'] * 100:.2f}%",
        ])
    lines.extend([
        "",
        "## 门禁结果",
        "",
        "通过" if not report["threshold_failures"] else "未通过：",
    ])
    lines.extend(f"- {item}" for item in report["threshold_failures"])
    lines.extend([
        "",
        "## 失败样本（按规则分从低到高）",
        "",
        "| case_id | 规则分 | Brief | 工具F1 | POI | 冲突率 | 选择覆盖 | 降级 | 错误 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ])
    for item in sorted(report["results"], key=lambda row: row["rule_score"])[:15]:
        poi = item.get("pois") or {"combined_pass_rate": 1.0}
        schedule = item.get("schedule") or {"conflict_rate": 0.0}
        selected = item.get("selected_places") or {"coverage_rate": 1.0}
        error = str(item.get("error") or "").replace("|", "/")[:80]
        lines.append(
            f"| {item['case_id']} | {item['rule_score']:.3f} | {item['brief']['score']:.3f} | "
            f"{item['tools']['selection_f1']:.3f} | {poi['combined_pass_rate']:.3f} | "
            f"{schedule['conflict_rate']:.3f} | {selected['coverage_rate']:.3f} | "
            f"{'是' if item['fallback_triggered'] else '否'} | {error} |"
        )
    lines.extend([
        "",
        "> Token 在现有业务 API 未返回 usage 时为估算值；接入供应商 usage 后，运行记录中的精确值会优先参与汇总。",
        "> 高德地点文本检索不提供实时营业状态；该字段单独报告数据覆盖率，不把 `unknown` 误判为关闭，也不纳入发布门禁。",
        "",
    ])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TripMind Agent 规则、人工与 LLM 评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--runs", type=Path, help="离线运行记录 JSONL")
    source.add_argument("--live", action="store_true", help="调用本地 API 生成真实运行记录，会消耗 API")
    parser.add_argument("--confirm-live", action="store_true", help="确认允许真实 API 调用")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--human-reviews", type=Path)
    parser.add_argument("--judge-sample", type=int, default=0, help="使用 LLM 评审前 N 个样本")
    parser.add_argument("--max-route-checks", type=int, default=12, help="每条样本最多调用的真实路线核验数")
    parser.add_argument(
        "--hard-tags",
        default=",".join(sorted(HARD_TAGS)),
        help="逗号分隔的 hard-set 标签",
    )
    parser.add_argument("--input-cost-per-million", type=float, default=0.0)
    parser.add_argument("--output-cost-per-million", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--fail-on-threshold", action="store_true")
    parser.add_argument(
        "--release-gate",
        action="store_true",
        help="启用原始/修复输出、路线、POI 类型、避雷和人工评分严格发布门禁",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = load_jsonl(args.dataset)
    if args.limit:
        cases = cases[: args.limit]
    case_index = _index(cases, "数据集")

    if args.live:
        if not args.confirm_live:
            print("拒绝执行：--live 会调用真实模型和地图 API，请同时传入 --confirm-live。", file=sys.stderr)
            return 2
        runs = []
        with httpx.Client(timeout=30) as client:
            for position, case in enumerate(cases, 1):
                print(f"[{position}/{len(cases)}] {case['id']} {case.get('description', '')}")
                runs.append(collect_live_run(
                    client,
                    args.base_url.rstrip("/"),
                    case,
                    timeout_seconds=args.timeout,
                    input_cost_per_million=args.input_cost_per_million,
                    output_cost_per_million=args.output_cost_per_million,
                    maximum_route_checks=args.max_route_checks,
                ))
        run_source = f"live:{args.base_url}"
    else:
        runs = load_jsonl(args.runs)
        run_source = str(args.runs)
    run_index = _index(runs, "运行记录")
    selected_cases = [case for case in cases if case["id"] in run_index]
    if not selected_cases:
        raise ValueError("运行记录与评测数据集没有相同的 case_id")

    reviews = _index(load_jsonl(args.human_reviews), "人工评分") if args.human_reviews else {}
    judgments: dict[str, dict[str, Any]] = {}
    if args.judge_sample:
        for case in selected_cases[: args.judge_sample]:
            judgments[case["id"]] = judge_run(case, run_index[case["id"]])

    results = [
        evaluate_case(
            case,
            run_index[case["id"]],
            reviews.get(case["id"]),
            judgments.get(case["id"]),
        )
        for case in selected_cases
    ]
    summary = summarize_results(results)
    failures = threshold_failures(summary, DEFAULT_THRESHOLDS, DEFAULT_MAXIMUMS)
    hard_tags = {item.strip() for item in args.hard_tags.split(",") if item.strip()}
    hard_results = [
        item for item in results if hard_tags.intersection(item.get("tags") or [])
    ]
    hard_summary = summarize_results(hard_results) if hard_results else {}
    if hard_summary:
        hard_minimums = dict(DEFAULT_THRESHOLDS)
        hard_maximums = dict(DEFAULT_MAXIMUMS)
        if not hard_summary["planned_case_count"]:
            for metric in list(hard_minimums):
                if metric.startswith("poi_") or metric == "selected_place_coverage_rate":
                    hard_minimums.pop(metric)
            hard_maximums.pop("schedule_conflict_rate", None)
            hard_maximums.pop("fallback_rate", None)
        failures.extend(
            f"hard-set {item}"
            for item in threshold_failures(hard_summary, hard_minimums, hard_maximums)
        )
    if args.release_gate:
        failures.extend(
            f"release {item}"
            for item in threshold_failures(
                summary,
                RELEASE_THRESHOLDS,
                require_present=True,
            )
        )
        if hard_summary:
            failures.extend(
                f"hard-set release {item}"
                for item in threshold_failures(
                    hard_summary,
                    RELEASE_THRESHOLDS,
                    require_present=True,
                )
            )
    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": generated_at,
        "dataset": str(args.dataset),
        "run_source": run_source,
        "summary": summary,
        "hard_set": {
            "tags": sorted(hard_tags),
            "case_ids": [item["case_id"] for item in hard_results],
            "summary": hard_summary,
        },
        "thresholds": {
            "minimums": DEFAULT_THRESHOLDS,
            "maximums": DEFAULT_MAXIMUMS,
            "release_minimums": RELEASE_THRESHOLDS,
        },
        "threshold_failures": failures,
        "results": results,
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"evaluation-{stamp}.json"
    markdown_path = args.output_dir / f"evaluation-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    human_template = args.output_dir / f"human-review-{stamp}.jsonl"
    write_jsonl(human_template, [{
        "case_id": case["id"],
        "scores": {
            "correctness": None,
            "route_practicality": None,
            "preference_alignment": None,
            "explanation_quality": None,
        },
        "comments": "",
        "reviewer": "",
    } for case in selected_cases])
    if args.live:
        write_jsonl(args.output_dir / f"live-runs-{stamp}.jsonl", runs)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"JSON 报告: {json_path}")
    print(f"Markdown 报告: {markdown_path}")
    print(f"人工评分模板: {human_template}")
    if failures:
        print("门禁未通过: " + "；".join(failures))
    return 1 if failures and (args.fail_on_threshold or args.release_gate) else 0


if __name__ == "__main__":
    raise SystemExit(main())
