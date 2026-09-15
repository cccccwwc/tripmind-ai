import json
import threading

from app.agents.trip_planner_agent import MultiAgentTripPlanner
from app.agents.trip_planner_graph import TripPlanningGraph
from app.models.schemas import TripRequest, WeatherInfo
from app.services.poi_reliability_service import POIReliabilityService
from test_agent_parser import FakeFallbackPOIService, make_plan_data


def request() -> TripRequest:
    return TripRequest(
        city="开封",
        start_date="2026-09-13",
        end_date="2026-09-13",
        travel_days=1,
        transportation="公共交通",
        accommodation="舒适型酒店",
    )


class FakeAgent:
    def __init__(self, response, barrier=None):
        self.response = response
        self.barrier = barrier
        self.calls = 0
        self.cleared = 0

    def clear_history(self):
        self.cleared += 1

    def run(self, input_text, **kwargs):
        self.calls += 1
        if self.barrier:
            self.barrier.wait(timeout=2)
        if isinstance(self.response, list):
            return self.response[min(self.calls - 1, len(self.response) - 1)]
        return self.response


class TrackingPOIService(FakeFallbackPOIService):
    def __init__(self, barrier=None):
        self.barrier = barrier
        self.calls = []
        self._waited_groups = set()
        self._lock = threading.Lock()

    def search(self, keywords, city, limit=20):
        self.calls.append(keywords)
        group = "attractions" if keywords == "旅游景点" else "hotel" if keywords == "舒适型酒店" else ""
        if self.barrier and group:
            with self._lock:
                should_wait = group not in self._waited_groups
                self._waited_groups.add(group)
            if should_wait:
                self.barrier.wait(timeout=2)
        return super().search(keywords, city, limit)


class FakeWeatherService:
    def __init__(self, barrier=None, error=None, items=None):
        self.barrier = barrier
        self.error = error
        self.items = items or []
        self.calls = 0

    def get_forecast(self, city, start_date, end_date):
        self.calls += 1
        if self.barrier and self.calls == 1:
            self.barrier.wait(timeout=2)
        if self.error:
            raise self.error
        return self.items


def planner_with_services(*, barrier=None):
    planner = MultiAgentTripPlanner.__new__(MultiAgentTripPlanner)
    planner.planner_agent = FakeAgent(json.dumps(make_plan_data([
        {"start_time": "09:00", "end_time": "11:00", "item_type": "attraction", "title": "清明上河园"},
    ]), ensure_ascii=False))
    planner.poi_location_service = TrackingPOIService(barrier)
    planner.poi_reliability_service = POIReliabilityService()
    planner.weather_service = FakeWeatherService(barrier)
    planner.workflow = TripPlanningGraph.in_memory(planner)
    return planner


def test_deterministic_research_nodes_are_fanned_out_in_parallel():
    # A serial implementation deadlocks on this barrier; all three research
    # nodes must be active in the same LangGraph superstep to pass it.
    planner = planner_with_services(barrier=threading.Barrier(3))

    plan = planner.plan_trip(request())

    assert plan.city == "开封"
    assert "旅游景点" in planner.poi_location_service.calls
    assert "舒适型酒店" in planner.poi_location_service.calls
    assert planner.weather_service.calls == 1


def test_workflow_events_expose_sanitized_tool_contract_for_evaluation():
    planner = planner_with_services()

    result = planner.workflow.start(
        request(),
        require_approval=False,
        workflow_id="evaluation-trace-test",
    )
    calls = {
        event.get("tool_name"): event
        for event in result["events"]
        if event.get("tool_name")
    }

    assert calls["amap.poi.search"]["tool_arguments"]["city"] == "开封"
    assert calls["amap.weather.forecast"]["tool_arguments"]["start_date"] == "2026-09-13"
    assert calls["amap.hotel.search"]["tool_arguments"]["accommodation"] == "舒适型酒店"
    assert calls["llm.trip_plan"]["tool_arguments"]["travel_days"] == 1
    assert all("api_key" not in json.dumps(event).casefold() for event in calls.values())


def test_transient_amap_failure_is_retried_before_fallback():
    class FlakyPOIService(TrackingPOIService):
        def __init__(self):
            super().__init__()
            self.attraction_attempts = 0

        def search(self, keywords, city, limit=20):
            if keywords == "旅游景点":
                self.attraction_attempts += 1
                if self.attraction_attempts == 1:
                    return ()
            return super().search(keywords, city, limit)

    planner = planner_with_services()
    planner.poi_location_service = FlakyPOIService()
    planner.workflow = TripPlanningGraph.in_memory(planner)

    result = planner.workflow.start(request(), require_approval=False, workflow_id="retry-test")

    assert result["status"] == "completed"
    assert planner.poi_location_service.attraction_attempts >= 2
    assert not result["errors"].get("attractions")


def test_failed_weather_api_uses_role_specific_fallback():
    planner = planner_with_services()
    planner.weather_service = FakeWeatherService(error=TimeoutError("调用超时"))
    planner.workflow = TripPlanningGraph.in_memory(planner)

    result = planner.workflow.start(request(), require_approval=False, workflow_id="fallback-test")

    assert result["status"] == "completed"
    assert planner.weather_service.calls == 2
    assert "weather" in result["errors"]
    assert any(
        event["node"] == "weather" and event["status"] == "fallback"
        for event in result["events"]
    )


def test_workflow_interrupts_for_approval_and_resumes_from_checkpoint():
    planner = planner_with_services()

    waiting = planner.workflow.start(
        request(),
        require_approval=True,
        workflow_id="approval-test",
    )
    assert waiting["status"] == "awaiting_approval"
    assert waiting["approval_prompt"]["type"] == "trip_planning_approval"
    assert planner.poi_location_service.calls == []

    completed = planner.workflow.resume("approval-test", approved=True)
    assert completed["status"] == "completed"
    assert completed["trip_plan"]["city"] == "开封"
    assert "旅游景点" in planner.poi_location_service.calls


def test_workflow_can_be_rejected_without_running_research_nodes():
    planner = planner_with_services()
    planner.workflow.start(request(), require_approval=True, workflow_id="reject-test")

    rejected = planner.workflow.resume("reject-test", approved=False)

    assert rejected["status"] == "rejected"
    assert rejected["trip_plan"] is None
    assert planner.poi_location_service.calls == []


def test_sqlite_checkpoint_can_resume_after_graph_is_recreated(tmp_path):
    planner = planner_with_services()
    database = tmp_path / "workflow.db"
    first_graph = TripPlanningGraph(planner, checkpoint_path=database)
    waiting = first_graph.start(
        request(),
        require_approval=True,
        workflow_id="durable-test",
    )
    assert waiting["status"] == "awaiting_approval"
    first_graph._checkpoint_connection.close()

    recreated_graph = TripPlanningGraph(planner, checkpoint_path=database)
    completed = recreated_graph.resume("durable-test", approved=True)

    assert completed["status"] == "completed"
    assert completed["trip_plan"]["city"] == "开封"


def test_start_rejects_duplicate_workflow_id():
    planner = planner_with_services()
    planner.workflow.start(request(), require_approval=True, workflow_id="duplicate")

    try:
        planner.workflow.start(request(), require_approval=True, workflow_id="duplicate")
    except ValueError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("重复 workflow_id 应被拒绝，避免历史状态污染新请求")


def test_invalid_poi_returns_to_search_and_rebuilds_plan():
    planner = planner_with_services()
    invalid = make_plan_data([
        {"start_time": "09:00", "end_time": "11:00", "item_type": "attraction", "title": "不存在景点"},
    ])
    invalid["days"][0]["attractions"][0]["name"] = "不存在景点"
    valid = make_plan_data([
        {"start_time": "09:00", "end_time": "11:00", "item_type": "attraction", "title": "清明上河园"},
        {"start_time": "13:00", "end_time": "15:00", "item_type": "attraction", "title": "龙亭公园"},
    ])
    valid["days"][0]["attractions"].append({
        "name": "龙亭公园",
        "address": "开封市龙亭区",
        "location": {"longitude": 114.35113, "latitude": 34.811187},
        "visit_duration": 120,
        "description": "皇家园林",
    })
    planner.planner_agent = FakeAgent([
        json.dumps(invalid, ensure_ascii=False),
        json.dumps(valid, ensure_ascii=False),
    ])
    planner.workflow = TripPlanningGraph.in_memory(planner)

    result = planner.workflow.start(request(), require_approval=False, workflow_id="poi-loop-test")

    assert result["status"] == "completed"
    assert planner.planner_agent.calls >= 2
    assert any(
        event["node"] == "validate_plan" and event["status"] == "retry"
        for event in result["events"]
    )
    assert result["poi_validation_report"]["is_valid"] is True
    names = [item["name"] for item in result["trip_plan"]["days"][0]["attractions"]]
    assert "不存在景点" not in names
    assert all(item["poi_id"] for item in result["trip_plan"]["days"][0]["attractions"])


def test_deterministic_weather_overrides_model_weather():
    planner = planner_with_services()
    planner.weather_service = FakeWeatherService(items=[WeatherInfo(
        date="2026-09-13",
        day_weather="晴",
        night_weather="多云",
        day_temp=26,
        night_temp=17,
        wind_direction="东",
        wind_power="1-3",
    )])
    planner.workflow = TripPlanningGraph.in_memory(planner)

    result = planner.workflow.start(request(), require_approval=False, workflow_id="weather-source-test")

    weather = result["trip_plan"]["weather_info"]
    assert weather == [{
        "date": "2026-09-13",
        "day_weather": "晴",
        "night_weather": "多云",
        "day_temp": 26,
        "night_temp": 17,
        "wind_direction": "东",
        "wind_power": "1-3",
    }]
