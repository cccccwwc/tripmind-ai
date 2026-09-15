import json
from pathlib import Path

from evals.metrics import evaluate_case, summarize_results, threshold_failures
from evals.runner import DEFAULT_DATASET, DEFAULT_THRESHOLDS, load_jsonl, main


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
