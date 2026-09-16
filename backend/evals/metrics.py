"""Deterministic evaluators for TripMind traces and structured outputs."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from statistics import mean
from typing import Any, Iterable


PLACEHOLDER_RE = re.compile(r"(?:景点|酒店|餐厅|饭店)\s*[一二三四五六七八九十\d]+$|^第\s*\d+\s*天")
BLOCKED_POI_TYPE_RE = re.compile(
    r"公交|地铁站|停车场|寄存|售票处|卫生间|厕所|出入口|"
    r"公司|房地产|住宅区|施工|建设中|客运站|服务区"
)


def _normalize(value: Any) -> str:
    text = re.sub(r"[\s·•（）()\[\]【】,，。/\\\-_]", "", str(value or "")).casefold()
    for suffix in ("旅游景区", "风景名胜区", "景区", "公园"):
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
    return text


def _ratio(passed: int, total: int, *, empty: float = 1.0) -> float:
    return round(passed / total, 4) if total else empty


def _canonical_transport(value: Any) -> str:
    text = _normalize(value)
    if any(token in text for token in ("公共交通", "地铁", "公交")):
        return "公共交通"
    if any(token in text for token in ("打车", "出租车", "网约车")):
        return "打车"
    if "自驾" in text:
        return "自驾"
    if "步行" in text:
        return "步行"
    return text


def _canonical_preference(value: Any) -> str:
    text = _normalize(value)
    if any(token in text for token in ("亲子", "孩子", "小孩", "儿童")):
        return "亲子"
    if any(token in text for token in ("海滨", "海边", "看海", "海岸", "海景")):
        return "海滨"
    if "海鲜" in text:
        return "海鲜"
    return text


def _expected_preference_coverage(expected: Iterable[Any], actual: Iterable[Any]) -> float:
    """Measure whether required preferences were captured.

    Extra values often contain avoidance constraints, pacing requirements or a
    selected POI. They are useful rather than hallucinated, so they must not
    reduce recall of the expected preferences.
    """
    left = {_canonical_preference(item) for item in expected if _canonical_preference(item)}
    right = {_canonical_preference(item) for item in actual if _canonical_preference(item)}
    if not left:
        return 1.0
    return round(len(left & right) / len(left), 4)


def _brief_field_matches(field: str, expected: Any, actual: Any) -> bool:
    if field == "transportation":
        return _canonical_transport(expected) == _canonical_transport(actual)
    if field == "accommodation":
        left, right = _normalize(expected), _normalize(actual)
        return bool(left and right and (left == right or left in right or right in left))
    return _normalize(expected) == _normalize(actual)


def evaluate_brief(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected_brief") or {}
    actual = run.get("planning_brief") or {}
    scores: dict[str, float] = {}
    for field, expected_value in expected.items():
        if field == "preferences":
            scores[field] = _expected_preference_coverage(expected_value or [], actual.get(field) or [])
        elif field == "free_text_input":
            expected_text = _normalize(expected_value)
            actual_text = _normalize(actual.get(field))
            scores[field] = float(
                not expected_text
                or expected_text in actual_text
                or actual_text in expected_text
            )
        else:
            actual_value = actual.get(field)
            if field == "requested_days" and actual_value in (None, ""):
                actual_value = actual.get("travel_days")
            scores[field] = float(_brief_field_matches(field, expected_value, actual_value))
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
                _expected_preference_coverage(value, actual_args.get(key) or [])
                if key == "preferences" and isinstance(value, list)
                else float(_brief_field_matches(key, value, actual_args.get(key)))
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


def _distance_km(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    try:
        lon_a, lat_a = float(left["longitude"]), float(left["latitude"])
        lon_b, lat_b = float(right["longitude"]), float(right["latitude"])
    except (KeyError, TypeError, ValueError):
        return None
    lat_a_rad, lat_b_rad = radians(lat_a), radians(lat_b)
    delta_lat = lat_b_rad - lat_a_rad
    delta_lon = radians(lon_b - lon_a)
    value = sin(delta_lat / 2) ** 2 + cos(lat_a_rad) * cos(lat_b_rad) * sin(delta_lon / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(value))


def evaluate_poi_types(run: dict[str, Any]) -> dict[str, Any]:
    pois = _iter_attractions(run.get("trip_plan") or {})
    known = passed = 0
    failures: list[dict[str, str]] = []
    for poi in pois:
        poi_type = str(poi.get("poi_type") or poi.get("category") or "").strip()
        typecode = str(poi.get("poi_typecode") or "").strip()
        # Generic model labels are not independent evidence of a visitable type.
        type_known = bool(poi_type and poi_type not in {"景点", "景点类别", "景区"})
        type_ok = type_known and not BLOCKED_POI_TYPE_RE.search(
            " ".join((poi_type, typecode, str(poi.get("name") or "")))
        )
        known += type_known
        passed += type_ok
        if not type_ok:
            failures.append({"name": str(poi.get("name") or ""), "poi_type": poi_type})
    return {
        "count": len(pois),
        "coverage_rate": _ratio(known, len(pois), empty=0.0),
        "pass_rate": _ratio(passed, len(pois), empty=0.0),
        "failures": failures[:10],
    }


def evaluate_route_distances(run: dict[str, Any], *, maximum_leg_km: float = 60.0) -> dict[str, Any]:
    plan = run.get("trip_plan") or {}
    distances: list[float] = []
    failures: list[dict[str, Any]] = []
    for day in plan.get("days") or []:
        attractions = [item for item in day.get("attractions") or [] if isinstance(item, dict)]
        for left, right in zip(attractions, attractions[1:]):
            distance = _distance_km(left.get("location") or {}, right.get("location") or {})
            if distance is None:
                continue
            distances.append(distance)
            if distance > maximum_leg_km:
                failures.append({
                    "date": day.get("date"),
                    "from": left.get("name"),
                    "to": right.get("name"),
                    "distance_km": round(distance, 2),
                })
    return {
        "checked_legs": len(distances),
        "pass_rate": _ratio(len(distances) - len(failures), len(distances), empty=1.0),
        "average_leg_km": round(mean(distances), 2) if distances else None,
        "maximum_leg_km": round(max(distances), 2) if distances else None,
        "failures": failures[:10],
    }


def evaluate_commute_truth(run: dict[str, Any]) -> dict[str, Any]:
    checks = [item for item in run.get("route_checks") or [] if isinstance(item, dict)]
    successful = [item for item in checks if item.get("success")]
    duration_passes = 0
    for item in successful:
        planned = float(item.get("planned_duration_minutes") or 0)
        actual = float(item.get("actual_duration_seconds") or 0) / 60
        # Permit a small planning tolerance but catch systematic 30-minute fiction.
        if planned + 10 >= actual and planned >= actual * 0.8:
            duration_passes += 1
    return {
        "requested_legs": len(checks),
        "verified_legs": len(successful),
        "coverage_rate": _ratio(len(successful), len(checks), empty=0.0),
        "duration_pass_rate": _ratio(duration_passes, len(successful), empty=0.0),
        "failures": [item for item in successful if not (
            float(item.get("planned_duration_minutes") or 0) + 10
            >= float(item.get("actual_duration_seconds") or 0) / 60
            and float(item.get("planned_duration_minutes") or 0)
            >= float(item.get("actual_duration_seconds") or 0) / 60 * 0.8
        )][:10],
    }


def evaluate_avoidance(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    terms = [str(item).strip() for item in case.get("avoid_terms") or [] if str(item).strip()]
    plan = run.get("trip_plan") or {}
    scheduled_texts: list[str] = []
    for day in plan.get("days") or []:
        for item in day.get("attractions") or []:
            scheduled_texts.extend((str(item.get("name") or ""), str(item.get("description") or "")))
        for item in day.get("meals") or []:
            scheduled_texts.extend((str(item.get("name") or ""), str(item.get("description") or "")))
        for item in day.get("schedule") or []:
            scheduled_texts.extend((str(item.get("title") or ""), str(item.get("description") or "")))
    scheduled_texts.append(str(plan.get("overall_suggestions") or ""))

    def violates(term: str) -> bool:
        needle = _normalize(term)
        for text in scheduled_texts:
            normalized = _normalize(text)
            position = normalized.find(needle)
            if position < 0:
                continue
            prefix = normalized[max(0, position - 6):position]
            if not any(marker in prefix for marker in ("不吃", "不要", "不安排", "避开", "避免", "非")):
                return True
        return False

    violations = [term for term in terms if violates(term)]
    return {
        "applicable": bool(terms),
        "terms": terms,
        "violations": violations,
        "pass_rate": _ratio(len(terms) - len(violations), len(terms)),
    }


def evaluate_plan_stage(
    case: dict[str, Any],
    run: dict[str, Any],
    plan_key: str,
    *,
    include_route_truth: bool,
) -> dict[str, Any]:
    plan = run.get(plan_key) or {}
    stage_run = {**run, "trip_plan": plan}
    present = bool(plan)
    pois = evaluate_pois(case, stage_run) if present else None
    poi_types = evaluate_poi_types(stage_run) if present else None
    schedule = evaluate_schedule(stage_run) if present else None
    selected = evaluate_selected_place_coverage(case, stage_run) if present else None
    route_distance = evaluate_route_distances(stage_run) if present else None
    commute = evaluate_commute_truth(stage_run) if include_route_truth and present else None
    avoidance = evaluate_avoidance(case, stage_run) if present else None
    components: list[tuple[float, float]] = []
    if present:
        components.extend([
            (pois["combined_pass_rate"], 0.25),
            (poi_types["pass_rate"], 0.10),
            (1 - schedule["conflict_rate"], 0.15),
            (route_distance["pass_rate"], 0.10),
        ])
        if case.get("selected_places"):
            components.append((selected["coverage_rate"], 0.15))
        if avoidance["applicable"]:
            components.append((avoidance["pass_rate"], 0.15))
        if commute and commute["requested_legs"]:
            components.append((commute["duration_pass_rate"], 0.10))
    denominator = sum(weight for _, weight in components)
    score = sum(value * weight for value, weight in components) / denominator if denominator else 0.0
    return {
        "present": present,
        "score": round(score, 4),
        "pois": pois,
        "poi_types": poi_types,
        "schedule": schedule,
        "selected_places": selected,
        "route_distance": route_distance,
        "commute": commute,
        "avoidance": avoidance,
    }


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
    city_pass = coordinate_pass = open_pass = open_known = identity_pass = combined_pass = 0
    failures: list[dict[str, Any]] = []
    for poi in pois:
        name = str(poi.get("name") or "").strip()
        city_ok = bool(expected_city and expected_city in _normalize(poi.get("city") or poi.get("address")))
        coordinate_ok = _valid_coordinate(poi.get("location"))
        operational_status = str(poi.get("operational_status") or "unknown").casefold()
        operational_known = operational_status in {"available", "unavailable"}
        operational_ok = operational_status != "unavailable"
        identity_ok = bool(str(poi.get("poi_id") or "").strip()) and bool(name) and not PLACEHOLDER_RE.search(name)
        city_pass += city_ok
        coordinate_pass += coordinate_ok
        open_pass += operational_status == "available"
        open_known += operational_known
        identity_pass += identity_ok
        combined_pass += city_ok and coordinate_ok and operational_ok and identity_ok
        if not all((city_ok, coordinate_ok, operational_ok, identity_ok)):
            failures.append({
                "name": name,
                "city": city_ok,
                "coordinate": coordinate_ok,
                "operational_status": operational_status,
                "not_known_closed": operational_ok,
                "poi_identity": identity_ok,
            })
    total = len(pois)
    return {
        "count": total,
        "city_pass_rate": _ratio(city_pass, total, empty=0.0),
        "coordinate_pass_rate": _ratio(coordinate_pass, total, empty=0.0),
        "open_status_pass_rate": _ratio(open_pass, total, empty=0.0),
        "open_status_coverage_rate": _ratio(open_known, total, empty=0.0),
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
    raw_observed = bool(run.get("raw_trip_plan"))
    raw_run = run if "raw_trip_plan" in run else {**run, "raw_trip_plan": run.get("trip_plan")}
    raw_stage = evaluate_plan_stage(
        case,
        raw_run,
        "raw_trip_plan",
        include_route_truth=False,
    ) if should_plan else None
    if raw_stage is not None:
        raw_stage["observed"] = raw_observed
    final_stage = evaluate_plan_stage(
        case,
        run,
        "trip_plan",
        include_route_truth=True,
    ) if should_plan else None
    pois = final_stage["pois"] if final_stage else None
    schedule = final_stage["schedule"] if final_stage else None
    selected = final_stage["selected_places"] if final_stage else None
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
        "stages": {"raw": raw_stage, "final": final_stage},
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
        "poi_open_status_coverage_rate": round(mean(item["pois"]["open_status_coverage_rate"] for item in planned), 4) if planned else 0.0,
        "poi_identity_pass_rate": round(mean(item["pois"]["identity_pass_rate"] for item in planned), 4) if planned else 0.0,
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
    for stage_name in ("raw", "final"):
        stages = [item["stages"][stage_name] for item in planned]
        present = [stage for stage in stages if stage.get("present")]
        prefix = f"{stage_name}_"
        summary[prefix + "output_coverage_rate"] = _ratio(len(present), len(stages), empty=0.0)
        summary[prefix + "stage_score"] = round(mean(stage["score"] for stage in stages), 4) if stages else 0.0
        summary[prefix + "poi_type_coverage_rate"] = round(mean(
            stage["poi_types"]["coverage_rate"] for stage in present
        ), 4) if present else 0.0
        summary[prefix + "poi_type_pass_rate"] = round(mean(
            stage["poi_types"]["pass_rate"] for stage in present
        ), 4) if present else 0.0
        route_stages = [stage for stage in present if stage["route_distance"]["checked_legs"]]
        summary[prefix + "route_distance_pass_rate"] = round(mean(
            stage["route_distance"]["pass_rate"] for stage in route_stages
        ), 4) if route_stages else 0.0
        avoidance_stages = [stage for stage in present if stage["avoidance"]["applicable"]]
        summary[prefix + "avoidance_pass_rate"] = round(mean(
            stage["avoidance"]["pass_rate"] for stage in avoidance_stages
        ), 4) if avoidance_stages else 1.0
        commute_stages = [stage for stage in present if stage.get("commute") and stage["commute"]["requested_legs"]]
        summary[prefix + "commute_coverage_rate"] = round(mean(
            stage["commute"]["coverage_rate"] for stage in commute_stages
        ), 4) if commute_stages else 0.0
        summary[prefix + "commute_duration_pass_rate"] = round(mean(
            stage["commute"]["duration_pass_rate"] for stage in commute_stages
        ), 4) if commute_stages else 0.0
    raw_observed = [stage for item in planned if (stage := item["stages"]["raw"]).get("observed")]
    summary["raw_capture_coverage_rate"] = _ratio(len(raw_observed), len(planned), empty=0.0)
    human = [item["human_review"]["normalized_score"] for item in results if item.get("human_review", {}).get("normalized_score") is not None]
    judges = [item["llm_judgment"]["normalized_score"] for item in results if item.get("llm_judgment", {}).get("normalized_score") is not None]
    summary["human_score"] = round(mean(human), 4) if human else None
    summary["human_review_coverage_rate"] = _ratio(len(human), len(results), empty=0.0)
    summary["llm_judge_score"] = round(mean(judges), 4) if judges else None
    return summary


def threshold_failures(
    summary: dict[str, Any],
    minimums: dict[str, float],
    maximums: dict[str, float] | None = None,
    *,
    require_present: bool = False,
) -> list[str]:
    failures = []
    for metric, threshold in minimums.items():
        value = summary.get(metric)
        if require_present and not isinstance(value, (int, float)):
            failures.append(f"{metric}: missing < {threshold:.4f}")
        elif isinstance(value, (int, float)) and value < threshold:
            failures.append(f"{metric}: {value:.4f} < {threshold:.4f}")
    for metric, threshold in (maximums or {}).items():
        value = summary.get(metric)
        if require_present and not isinstance(value, (int, float)):
            failures.append(f"{metric}: missing > {threshold:.4f}")
        elif isinstance(value, (int, float)) and value > threshold:
            failures.append(f"{metric}: {value:.4f} > {threshold:.4f}")
    return failures
