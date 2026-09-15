"""Deterministic evaluators for TripMind traces and structured outputs."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from statistics import mean
from typing import Any, Iterable


PLACEHOLDER_RE = re.compile(r"(?:景点|酒店|餐厅|饭店)\s*[一二三四五六七八九十\d]+$|^第\s*\d+\s*天")


def _normalize(value: Any) -> str:
    text = re.sub(r"[\s·•（）()\[\]【】,，。/\\\-_]", "", str(value or "")).casefold()
    for suffix in ("旅游景区", "风景名胜区", "景区", "公园"):
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
    return text


def _ratio(passed: int, total: int, *, empty: float = 1.0) -> float:
    return round(passed / total, 4) if total else empty


def _set_similarity(expected: Iterable[Any], actual: Iterable[Any]) -> float:
    left = {_normalize(item) for item in expected if _normalize(item)}
    right = {_normalize(item) for item in actual if _normalize(item)}
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def evaluate_brief(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected_brief") or {}
    actual = run.get("planning_brief") or {}
    scores: dict[str, float] = {}
    for field, expected_value in expected.items():
        if field == "preferences":
            scores[field] = _set_similarity(expected_value or [], actual.get(field) or [])
        elif field == "free_text_input":
            expected_text = _normalize(expected_value)
            actual_text = _normalize(actual.get(field))
            scores[field] = float(
                not expected_text
                or expected_text in actual_text
                or actual_text in expected_text
            )
        else:
            scores[field] = float(_normalize(expected_value) == _normalize(actual.get(field)))
    return {
        "score": round(mean(scores.values()), 4) if scores else 1.0,
        "fields": scores,
        "missing_actual_fields": [field for field in expected if actual.get(field) in (None, "", [])],
    }


def evaluate_tools(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected_tools") or []
    actual = run.get("tool_calls") or []
    expected_names = [item["name"] for item in expected]
    actual_names = [str(item.get("name") or "") for item in actual]
    expected_counter = Counter(expected_names)
    actual_counter = Counter(actual_names)
    true_positive = sum((expected_counter & actual_counter).values())
    precision = _ratio(true_positive, sum(actual_counter.values()), empty=float(not expected_names))
    recall = _ratio(true_positive, sum(expected_counter.values()), empty=1.0)
    selection_f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if precision + recall
        else 0.0
    )

    argument_scores: list[float] = []
    argument_details: list[dict[str, Any]] = []
    used_indexes: set[int] = set()
    for expected_call in expected:
        matched_index = next(
            (
                index
                for index, call in enumerate(actual)
                if index not in used_indexes and call.get("name") == expected_call["name"]
            ),
            None,
        )
        expected_args = expected_call.get("arguments") or {}
        if matched_index is None:
            argument_scores.append(0.0)
            argument_details.append({"name": expected_call["name"], "score": 0.0, "missing": True})
            continue
        used_indexes.add(matched_index)
        actual_args = actual[matched_index].get("arguments") or {}
        field_scores = {
            key: (
                _set_similarity(value, actual_args.get(key) or [])
                if isinstance(value, list)
                else float(_normalize(value) == _normalize(actual_args.get(key)))
            )
            for key, value in expected_args.items()
        }
        score = mean(field_scores.values()) if field_scores else 1.0
        argument_scores.append(score)
        argument_details.append({
            "name": expected_call["name"],
            "score": round(score, 4),
            "fields": field_scores,
            "success": bool(actual[matched_index].get("success", True)),
        })

    return {
        "selection_precision": precision,
        "selection_recall": recall,
        "selection_f1": selection_f1,
        "argument_accuracy": round(mean(argument_scores), 4) if argument_scores else 1.0,
        "arguments": argument_details,
        "unexpected_tools": list((actual_counter - expected_counter).elements()),
        "missing_tools": list((expected_counter - actual_counter).elements()),
    }


def _iter_attractions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        attraction
        for day in plan.get("days") or []
        for attraction in day.get("attractions") or []
        if isinstance(attraction, dict)
    ]


def _valid_coordinate(location: Any) -> bool:
    if not isinstance(location, dict):
        return False
    try:
        longitude = float(location["longitude"])
        latitude = float(location["latitude"])
    except (KeyError, TypeError, ValueError):
        return False
    return 73.0 <= longitude <= 136.0 and 3.0 <= latitude <= 54.0


def evaluate_pois(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    plan = run.get("trip_plan") or {}
    expected_city = _normalize((case.get("expected_brief") or {}).get("city"))
    pois = _iter_attractions(plan)
    city_pass = coordinate_pass = open_pass = identity_pass = combined_pass = 0
    failures: list[dict[str, Any]] = []
    for poi in pois:
        name = str(poi.get("name") or "").strip()
        city_ok = bool(expected_city and expected_city in _normalize(poi.get("city") or poi.get("address")))
        coordinate_ok = _valid_coordinate(poi.get("location"))
        operational_ok = str(poi.get("operational_status") or "").casefold() == "available"
        identity_ok = bool(str(poi.get("poi_id") or "").strip()) and bool(name) and not PLACEHOLDER_RE.search(name)
        city_pass += city_ok
        coordinate_pass += coordinate_ok
        open_pass += operational_ok
        identity_pass += identity_ok
        combined_pass += city_ok and coordinate_ok and operational_ok and identity_ok
        if not all((city_ok, coordinate_ok, operational_ok, identity_ok)):
            failures.append({
                "name": name,
                "city": city_ok,
                "coordinate": coordinate_ok,
                "operational_status": operational_ok,
                "poi_identity": identity_ok,
            })
    total = len(pois)
    return {
        "count": total,
        "city_pass_rate": _ratio(city_pass, total, empty=0.0),
        "coordinate_pass_rate": _ratio(coordinate_pass, total, empty=0.0),
        "open_status_pass_rate": _ratio(open_pass, total, empty=0.0),
        "identity_pass_rate": _ratio(identity_pass, total, empty=0.0),
        "combined_pass_rate": _ratio(combined_pass, total, empty=0.0),
        "failures": failures[:10],
    }


def _minutes(value: Any) -> int | None:
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", str(value or ""))
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def evaluate_schedule(run: dict[str, Any]) -> dict[str, Any]:
    days = (run.get("trip_plan") or {}).get("days") or []
    comparisons = conflicts = invalid_items = 0
    empty_days = 0
    details: list[dict[str, Any]] = []
    for day in days:
        schedule = day.get("schedule") or []
        if not schedule:
            empty_days += 1
            details.append({"date": day.get("date"), "reason": "empty_schedule"})
            continue
        intervals: list[tuple[int, int, str]] = []
        for item in schedule:
            start = _minutes(item.get("start_time"))
            end = _minutes(item.get("end_time"))
            if start is None or end is None or start >= end:
                invalid_items += 1
                details.append({"date": day.get("date"), "title": item.get("title"), "reason": "invalid_time"})
                continue
            intervals.append((start, end, str(item.get("title") or "")))
        intervals.sort()
        for previous, current in zip(intervals, intervals[1:]):
            comparisons += 1
            if current[0] < previous[1]:
                conflicts += 1
                details.append({
                    "date": day.get("date"),
                    "reason": "overlap",
                    "items": [previous[2], current[2]],
                })
    denominator = comparisons + invalid_items + empty_days
    return {
        "conflict_rate": _ratio(conflicts + invalid_items + empty_days, denominator, empty=0.0),
        "conflicts": conflicts,
        "invalid_items": invalid_items,
        "empty_days": empty_days,
        "details": details[:10],
    }


def _place_matches(expected: str, actual: str) -> bool:
    left, right = _normalize(expected), _normalize(actual)
    return bool(left and right and (left == right or left in right or right in left))


def evaluate_selected_place_coverage(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    expected = [str(item) for item in case.get("selected_places") or []]
    plan = run.get("trip_plan") or {}
    actual = [poi.get("name", "") for poi in _iter_attractions(plan)]
    actual.extend(
        item.get("title", "")
        for day in plan.get("days") or []
        for item in day.get("schedule") or []
        if item.get("item_type") == "attraction"
    )
    covered = [place for place in expected if any(_place_matches(place, item) for item in actual)]
    missing = [place for place in expected if place not in covered]
    return {
        "coverage_rate": _ratio(len(covered), len(expected)),
        "covered": covered,
        "missing": missing,
    }


def _fallback_triggered(run: dict[str, Any]) -> bool:
    return bool(
        run.get("error")
        or run.get("errors")
        or any(
            str(event.get("status") or event.get("node_status") or "").casefold() == "fallback"
            or str(event.get("node") or "") == "fallback_plan"
            for event in run.get("events") or []
        )
    )


def evaluate_case(
    case: dict[str, Any],
    run: dict[str, Any],
    human_review: dict[str, Any] | None = None,
    llm_judgment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    brief = evaluate_brief(case, run)
    tools = evaluate_tools(case, run)
    should_plan = bool(case.get("should_plan", True))
    pois = evaluate_pois(case, run) if should_plan else None
    schedule = evaluate_schedule(run) if should_plan else None
    selected = evaluate_selected_place_coverage(case, run) if should_plan else None
    fallback = _fallback_triggered(run)
    completed = bool(run.get("trip_plan")) if should_plan else not bool(run.get("trip_plan"))

    if should_plan:
        weighted = {
            "brief": (brief["score"], 0.20),
            "tool_selection": (tools["selection_f1"], 0.10),
            "tool_arguments": (tools["argument_accuracy"], 0.10),
            "poi_reliability": (pois["combined_pass_rate"], 0.25),
            "schedule": (1 - schedule["conflict_rate"], 0.15),
            "selected_coverage": (selected["coverage_rate"], 0.15),
            "completed": (float(completed), 0.05),
        }
    else:
        weighted = {
            "brief": (brief["score"], 0.80),
            "tool_selection": (tools["selection_f1"], 0.15),
            "not_started": (float(completed), 0.05),
        }
    rule_score = round(sum(score * weight for score, weight in weighted.values()), 4)
    result = {
        "case_id": case["id"],
        "description": case.get("description", ""),
        "tags": case.get("tags", []),
        "should_plan": should_plan,
        "completed": completed,
        "rule_score": rule_score,
        "brief": brief,
        "tools": tools,
        "pois": pois,
        "schedule": schedule,
        "selected_places": selected,
        "fallback_triggered": fallback,
        "latency_ms": float(run.get("latency_ms") or 0),
        "usage": run.get("usage") or {},
        "error": run.get("error"),
    }
    if human_review:
        scores = [
            float(value)
            for value in (human_review.get("scores") or {}).values()
            if isinstance(value, (int, float))
        ]
        result["human_review"] = {
            **human_review,
            "normalized_score": round(mean(scores) / 5, 4) if scores else None,
        }
    if llm_judgment:
        numeric = [
            float(llm_judgment.get(field))
            for field in ("correctness", "route_practicality", "preference_alignment", "explanation_quality")
            if isinstance(llm_judgment.get(field), (int, float))
        ]
        result["llm_judgment"] = {
            **llm_judgment,
            "normalized_score": round(mean(numeric) / 5, 4) if numeric else None,
        }
    return result


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    planned = [item for item in results if item["should_plan"]]
    values = lambda key, rows=results: [float(row[key]) for row in rows]
    usage = [item.get("usage") or {} for item in results]
    summary = {
        "case_count": len(results),
        "planned_case_count": len(planned),
        "rule_score": round(mean(values("rule_score")), 4) if results else 0.0,
        "brief_accuracy": round(mean(item["brief"]["score"] for item in results), 4) if results else 0.0,
        "tool_selection_f1": round(mean(item["tools"]["selection_f1"] for item in results), 4) if results else 0.0,
        "tool_argument_accuracy": round(mean(item["tools"]["argument_accuracy"] for item in results), 4) if results else 0.0,
        "poi_city_pass_rate": round(mean(item["pois"]["city_pass_rate"] for item in planned), 4) if planned else 0.0,
        "poi_coordinate_pass_rate": round(mean(item["pois"]["coordinate_pass_rate"] for item in planned), 4) if planned else 0.0,
        "poi_open_status_pass_rate": round(mean(item["pois"]["open_status_pass_rate"] for item in planned), 4) if planned else 0.0,
        "poi_combined_pass_rate": round(mean(item["pois"]["combined_pass_rate"] for item in planned), 4) if planned else 0.0,
        "schedule_conflict_rate": round(mean(item["schedule"]["conflict_rate"] for item in planned), 4) if planned else 0.0,
        "selected_place_coverage_rate": round(mean(item["selected_places"]["coverage_rate"] for item in planned), 4) if planned else 0.0,
        "fallback_rate": _ratio(sum(item["fallback_triggered"] for item in planned), len(planned), empty=0.0),
        "completion_rate": _ratio(sum(item["completed"] for item in results), len(results), empty=0.0),
        "average_latency_ms": round(mean(item["latency_ms"] for item in results), 2) if results else 0.0,
        "total_input_tokens": sum(int(item.get("input_tokens") or 0) for item in usage),
        "total_output_tokens": sum(int(item.get("output_tokens") or 0) for item in usage),
        "total_api_cost_usd": round(sum(float(item.get("api_cost_usd") or 0) for item in usage), 6),
    }
    human = [item["human_review"]["normalized_score"] for item in results if item.get("human_review", {}).get("normalized_score") is not None]
    judges = [item["llm_judgment"]["normalized_score"] for item in results if item.get("llm_judgment", {}).get("normalized_score") is not None]
    summary["human_score"] = round(mean(human), 4) if human else None
    summary["llm_judge_score"] = round(mean(judges), 4) if judges else None
    return summary


def threshold_failures(
    summary: dict[str, Any],
    minimums: dict[str, float],
    maximums: dict[str, float] | None = None,
) -> list[str]:
    failures = []
    for metric, threshold in minimums.items():
        value = summary.get(metric)
        if isinstance(value, (int, float)) and value < threshold:
            failures.append(f"{metric}: {value:.4f} < {threshold:.4f}")
    for metric, threshold in (maximums or {}).items():
        value = summary.get(metric)
        if isinstance(value, (int, float)) and value > threshold:
            failures.append(f"{metric}: {value:.4f} > {threshold:.4f}")
    return failures
