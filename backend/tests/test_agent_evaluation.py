import json
from pathlib import Path

from evals.metrics import evaluate_case, summarize_results, threshold_failures
from evals.runner import (
    DEFAULT_DATASET,
    DEFAULT_THRESHOLDS,
    RELEASE_THRESHOLDS,
    HARD_TAGS,
    collect_route_checks,
    load_jsonl,
    main,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "evals" / "data"


def test_evaluation_dataset_has_30_unique_well_formed_cases():
    cases = load_jsonl(DEFAULT_DATASET)

    assert 30 <= len(cases) <= 50
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case.get("messages") for case in cases)
    assert all("expected_brief" in case for case in cases)
    assert all("expected_tools" in case for case in cases)
    assert any(not case.get("should_plan", True) for case in cases)
    assert any(case.get("selected_places") for case in cases)
    assert all(
        case.get("avoid_terms")
        for case in cases
        if "avoidance" in case.get("tags", [])
    )
    by_id = {case["id"]: case for case in cases}
    assert all(
        HARD_TAGS.intersection(by_id[f"TM-{number:03d}"]["tags"])
        for number in range(26, 31)
    )


def test_recorded_good_run_passes_all_rule_metrics():
    case = {item["id"]: item for item in load_jsonl(DEFAULT_DATASET)}["TM-001"]
    run = {item["case_id"]: item for item in load_jsonl(DATA_DIR / "sample_runs.jsonl")}["TM-001"]

    result = evaluate_case(case, run)

    assert result["brief"]["score"] == 1
    assert result["tools"]["selection_f1"] == 1
    assert result["tools"]["argument_accuracy"] == 1
    assert result["pois"]["combined_pass_rate"] == 1
    assert result["schedule"]["conflict_rate"] == 0
    assert result["selected_places"]["coverage_rate"] == 1
    assert result["rule_score"] == 1


def test_bad_run_exposes_tool_poi_schedule_selection_and_fallback_failures():
    case = {item["id"]: item for item in load_jsonl(DEFAULT_DATASET)}["TM-001"]
    bad_run = {
        "case_id": "TM-001",
        "planning_brief": {
            "city": "上海",
            "start_date": "2027-04-02",
            "end_date": "2027-04-04",
            "travel_days": 3,
            "transportation": "公共交通",
            "accommodation": "舒适型酒店",
            "preferences": [],
        },
        "tool_calls": [{"name": "amap.hotel.search", "arguments": {"city": "上海"}}],
        "trip_plan": {
            "days": [{
                "date": "2027-04-02",
                "attractions": [{
                    "name": "北京景点1",
                    "address": "上海市",
                    "city": "上海市",
                    "poi_id": "",
                    "location": {"longitude": 0, "latitude": 0},
                    "operational_status": "unknown",
                }],
                "schedule": [
                    {"start_time": "09:00", "end_time": "11:00", "item_type": "attraction", "title": "北京景点1"},
                    {"start_time": "10:00", "end_time": "12:00", "item_type": "meal", "title": "午餐"},
                ],
            }],
        },
        "events": [{"node": "hotel", "status": "fallback"}],
    }

    result = evaluate_case(case, bad_run)

    assert result["brief"]["score"] < 1
    assert result["tools"]["selection_f1"] < 1
    assert result["tools"]["argument_accuracy"] < 1
    assert result["pois"]["combined_pass_rate"] == 0
    assert result["schedule"]["conflict_rate"] > 0
    assert result["selected_places"]["coverage_rate"] == 0
    assert result["fallback_triggered"] is True
    assert result["rule_score"] < 0.5


def test_unknown_open_status_is_reported_as_uncovered_not_failed():
    case = {item["id"]: item for item in load_jsonl(DEFAULT_DATASET)}["TM-001"]
    run = {item["case_id"]: item for item in load_jsonl(DATA_DIR / "sample_runs.jsonl")}["TM-001"]
    for day in run["trip_plan"]["days"]:
        for poi in day.get("attractions", []):
            poi["operational_status"] = "unknown"

    result = evaluate_case(case, run)

    assert result["pois"]["open_status_coverage_rate"] == 0
    assert result["pois"]["combined_pass_rate"] == 1
    assert result["rule_score"] == 1


def test_summary_tracks_latency_tokens_cost_and_threshold_failures():
    cases = {item["id"]: item for item in load_jsonl(DEFAULT_DATASET)}
    runs = {item["case_id"]: item for item in load_jsonl(DATA_DIR / "sample_runs.jsonl")}
    results = [evaluate_case(cases[case_id], run) for case_id, run in runs.items()]

    summary = summarize_results(results)

    assert summary["case_count"] == 2
    assert summary["total_input_tokens"] == 4890
    assert summary["total_output_tokens"] == 2230
    assert summary["total_api_cost_usd"] == 0.00345
    assert threshold_failures(summary, DEFAULT_THRESHOLDS) == []


def test_cli_writes_json_markdown_and_human_review_template(tmp_path):
    exit_code = main([
        "--runs", str(DATA_DIR / "sample_runs.jsonl"),
        "--output-dir", str(tmp_path),
    ])

    assert exit_code == 0
    assert len(list(tmp_path.glob("evaluation-*.json"))) == 1
    markdown = next(tmp_path.glob("evaluation-*.md")).read_text(encoding="utf-8")
    assert "Planning Brief 准确率" in markdown
    template = next(tmp_path.glob("human-review-*.jsonl"))
    first = json.loads(template.read_text(encoding="utf-8").splitlines()[0])
    assert first["case_id"] == "TM-001"
    assert first["scores"]["correctness"] is None


def test_live_mode_requires_explicit_cost_confirmation():
    assert main(["--live", "--limit", "1"]) == 2


def test_raw_and_repaired_outputs_are_scored_separately():
    case = {item["id"]: item for item in load_jsonl(DEFAULT_DATASET)}["TM-001"]
    final_run = {item["case_id"]: item for item in load_jsonl(DATA_DIR / "sample_runs.jsonl")}["TM-001"]
    raw_plan = json.loads(json.dumps(final_run["trip_plan"], ensure_ascii=False))
    raw_plan["days"][0]["schedule"].append({
        "start_time": "09:30",
        "end_time": "10:30",
        "item_type": "activity",
        "title": "重叠的活动",
    })
    run = {**final_run, "raw_trip_plan": raw_plan}

    result = evaluate_case(case, run)

    assert result["stages"]["raw"]["observed"] is True
    assert result["stages"]["raw"]["schedule"]["conflict_rate"] > 0
    assert result["stages"]["final"]["schedule"]["conflict_rate"] == 0
    assert result["stages"]["raw"]["score"] < result["stages"]["final"]["score"]


def test_semantically_bad_poi_no_longer_gets_perfect_stage_score():
    case = {
        "id": "AUDIT",
        "expected_brief": {"city": "深圳"},
        "selected_places": [],
        "avoid_terms": ["火锅"],
        "should_plan": True,
    }
    plan = {
        "city": "深圳",
        "days": [{
            "date": "2027-03-08",
            "attractions": [{
                "name": "福田公交站",
                "city": "深圳市",
                "poi_id": "nonempty",
                "poi_type": "交通设施服务;公交车站",
                "location": {"longitude": 114.05, "latitude": 22.54},
                "operational_status": "unknown",
            }],
            "meals": [{"name": "火锅晚餐"}],
            "schedule": [{
                "start_time": "09:00",
                "end_time": "10:00",
                "item_type": "attraction",
                "title": "福田公交站",
                "description": "火锅体验",
            }],
        }],
    }
    result = evaluate_case(case, {
        "planning_brief": {"city": "深圳"},
        "tool_calls": [],
        "raw_trip_plan": plan,
        "trip_plan": plan,
    })

    final = result["stages"]["final"]
    assert final["poi_types"]["pass_rate"] == 0
    assert final["avoidance"]["pass_rate"] == 0
    assert final["score"] < 1


def test_empty_raw_plan_is_not_counted_as_captured():
    case = {item["id"]: item for item in load_jsonl(DEFAULT_DATASET)}["TM-001"]
    final_run = {item["case_id"]: item for item in load_jsonl(DATA_DIR / "sample_runs.jsonl")}["TM-001"]

    result = evaluate_case(case, {**final_run, "raw_trip_plan": {}})
    summary = summarize_results([result])

    assert result["stages"]["raw"]["observed"] is False
    assert summary["raw_capture_coverage_rate"] == 0
    assert summary["raw_output_coverage_rate"] == 0


def test_release_gate_requires_human_reviews_and_new_quality_metrics():
    summary = {
        **{metric: 1.0 for metric in RELEASE_THRESHOLDS},
        "human_score": None,
        "human_review_coverage_rate": 0.0,
    }

    failures = threshold_failures(summary, RELEASE_THRESHOLDS, require_present=True)

    assert any("human_score" in item for item in failures)
    assert any("human_review_coverage_rate" in item for item in failures)


def test_route_checks_use_real_duration_for_resolved_transport(monkeypatch):
    monkeypatch.setenv("AMAP_API_KEY", "test-key")
    monkeypatch.setattr(
        "evals.runner._amap_route_truth",
        lambda *args, **kwargs: {
            "actual_distance_meters": 8200,
            "actual_duration_seconds": 2700,
        },
    )
    plan = {
        "city": "北京",
        "days": [{
            "date": "2027-04-02",
            "attractions": [
                {"name": "故宫", "address": "故宫", "location": {"longitude": 116.397, "latitude": 39.916}},
                {"name": "天坛", "address": "天坛", "location": {"longitude": 116.410, "latitude": 39.882}},
            ],
            "schedule": [{
                "item_type": "transport",
                "from_location": "故宫",
                "to_location": "天坛",
                "transport_mode": "地铁",
                "duration_minutes": 30,
            }],
        }],
    }

    checks = collect_route_checks(plan, maximum_checks=3)

    assert checks[0]["success"] is True
    assert checks[0]["actual_duration_seconds"] == 2700
