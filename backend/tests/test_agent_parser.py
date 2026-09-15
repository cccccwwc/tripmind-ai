import json

from app.agents.trip_planner_agent import MultiAgentTripPlanner
from app.agents.trip_planner_graph import TripPlanningGraph
from app.models.schemas import TimelineItem, TripRequest
from app.services.poi_location_service import ResolvedPOI
from app.services.poi_reliability_service import POIReliabilityService


def make_request() -> TripRequest:
    return TripRequest(
        city="开封",
        start_date="2026-09-13",
        end_date="2026-09-13",
        travel_days=1,
        transportation="公共交通",
        accommodation="舒适型酒店",
    )


def make_plan_data(schedule):
    return {
        "city": "开封",
        "start_date": "2026-09-13",
        "end_date": "2026-09-13",
        "days": [{
            "date": "2026-09-13",
            "day_index": 0,
            "description": "开封一日游",
            "transportation": "公共交通",
            "accommodation": "舒适型酒店",
            "attractions": [{
                "name": "清明上河园",
                "address": "开封市龙亭区",
                "location": {"longitude": 114.340685, "latitude": 34.809044},
                "visit_duration": 120,
                "description": "宋文化主题景区",
            }],
            "meals": [],
            "schedule": schedule,
        }],
        "weather_info": [],
        "overall_suggestions": "提前预约",
    }


def parser_without_external_agents() -> MultiAgentTripPlanner:
    return MultiAgentTripPlanner.__new__(MultiAgentTripPlanner)


def test_parse_json_code_block_and_sort_schedule():
    schedule = [
        {"start_time": "11:00", "end_time": "12:00", "item_type": "meal", "title": "午餐"},
        {"start_time": "09:00", "end_time": "10:30", "item_type": "attraction", "title": "清明上河园"},
    ]
    response = f"规划如下：\n```json\n{json.dumps(make_plan_data(schedule), ensure_ascii=False)}\n```"

    plan = parser_without_external_agents()._parse_response(response, make_request())

    assert plan.city == "开封"
    assert plan.days[0].attractions[0].name == "清明上河园"
    assert [item.start_time for item in plan.days[0].schedule] == ["09:00", "11:00"]


def test_overlapping_schedule_is_rebuilt():
    overlapping = [
        {"start_time": "09:00", "end_time": "11:00", "item_type": "attraction", "title": "清明上河园"},
        {"start_time": "10:30", "end_time": "12:00", "item_type": "meal", "title": "午餐"},
    ]
    response = json.dumps(make_plan_data(overlapping), ensure_ascii=False)

    plan = parser_without_external_agents()._parse_response(response, make_request())

    assert MultiAgentTripPlanner._schedule_has_no_overlap(plan.days[0].schedule)
    assert [item.title for item in plan.days[0].schedule] != ["清明上河园", "午餐"]


def test_schedule_overlap_validator_rejects_invalid_ranges():
    valid = [
        TimelineItem(start_time="09:00", end_time="10:00", item_type="activity", title="A"),
        TimelineItem(start_time="10:00", end_time="11:00", item_type="activity", title="B"),
    ]
    overlap = [
        *valid,
        TimelineItem(start_time="10:30", end_time="12:00", item_type="activity", title="C"),
    ]
    invalid = [TimelineItem(start_time="25:00", end_time="26:00", item_type="activity", title="D")]

    assert MultiAgentTripPlanner._schedule_has_no_overlap(valid)
    assert not MultiAgentTripPlanner._schedule_has_no_overlap(overlap)
    assert not MultiAgentTripPlanner._schedule_has_no_overlap(invalid)


class FakeFallbackPOIService:
    @staticmethod
    def _normalize(value):
        return str(value).replace("景区", "").replace("公园", "")

    def resolve(self, name, city, address=""):
        matches = {
            "清明上河园": ResolvedPOI("a1", "清明上河园", "龙亭西路", 114.340685, 34.809044, 1),
            "龙亭公园": ResolvedPOI("a2", "龙亭景区", "龙亭北路", 114.35113, 34.811187, 1),
        }
        return matches.get(name)

    def search(self, keywords, city, limit=20):
        data = {
            "旅游景点": (
                ResolvedPOI("a3", "铁塔公园", "北门大街", 114.3656, 34.8162, 1),
                ResolvedPOI("a4", "大相国寺", "自由路西段", 114.3474, 34.7938, 1),
            ),
            "博物馆": (
                ResolvedPOI("a5", "开封博物馆", "郑开大道", 114.2453, 34.7761, 1),
            ),
            "酒店": (
                ResolvedPOI("h1", "开封建业铂尔曼酒店", "龙亭北路", 114.347, 34.817, 1),
            ),
            "餐厅": tuple(
                ResolvedPOI(f"r{i}", f"开封餐厅{i}", f"鼓楼街{i}号", 114.34 + i / 1000, 34.79, 1)
                for i in range(1, 10)
            ),
        }
        return data.get(keywords, ())


def test_fallback_plan_uses_selected_and_verified_real_pois():
    planner = parser_without_external_agents()
    planner.poi_location_service = FakeFallbackPOIService()
    request = TripRequest(
        city="开封",
        start_date="2026-09-13",
        end_date="2026-09-15",
        travel_days=3,
        transportation="公共交通",
        accommodation="舒适型酒店",
        selected_recommendations=[
            {"name": "清明上河园", "category": "历史文化", "reason": "用户主动选择"},
            {"name": "龙亭公园", "category": "历史文化", "reason": "用户主动选择"},
        ],
    )

    plan = planner._create_fallback_plan(request)
    names = [attraction.name for day in plan.days for attraction in day.attractions]

    assert "清明上河园" in names
    assert "龙亭景区" in names
    assert all("景点1" not in name and "景点2" not in name for name in names)
    assert all(attraction.location for day in plan.days for attraction in day.attractions)
    assert all(day.hotel and day.hotel.name == "开封建业铂尔曼酒店" for day in plan.days)
    assert all(not meal.name.startswith("第") for day in plan.days for meal in day.meals)
    assert plan.budget and plan.budget.total > 0


def test_fallback_plan_fails_instead_of_returning_fake_places():
    class EmptyPOIService(FakeFallbackPOIService):
        def resolve(self, name, city, address=""):
            return None

        def search(self, keywords, city, limit=20):
            return ()

    planner = parser_without_external_agents()
    planner.poi_location_service = EmptyPOIService()

    try:
        planner._create_fallback_plan(make_request())
    except RuntimeError as exc:
        assert "可核验的景点" in str(exc)
    else:
        raise AssertionError("应拒绝返回虚构占位地点")


def test_plan_trip_only_runs_the_route_planning_agent():
    class FakeAgent:
        def __init__(self, response):
            self.response = response
            self.cleared = 0
            self.last_kwargs = {}

        def clear_history(self):
            self.cleared += 1

        def run(self, input_text, **kwargs):
            self.last_kwargs = kwargs
            return self.response

    planner = parser_without_external_agents()
    planner.planner_agent = FakeAgent(json.dumps(make_plan_data([
        {"start_time": "09:00", "end_time": "11:00", "item_type": "attraction", "title": "清明上河园"},
    ]), ensure_ascii=False))
    planner.poi_location_service = FakeFallbackPOIService()
    planner.poi_reliability_service = POIReliabilityService()
    planner.weather_service = type(
        "FakeWeatherService",
        (),
        {"get_forecast": lambda self, city, start_date, end_date: []},
    )()
    planner.workflow = TripPlanningGraph.in_memory(planner)

    plan = planner.plan_trip(make_request())

    assert plan.city == "开封"
    assert planner.planner_agent.cleared >= 1
    assert planner.planner_agent.last_kwargs["max_tokens"] == 8192
