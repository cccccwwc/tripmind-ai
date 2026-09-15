from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes import poi as poi_route
from app.api.routes import trip as trip_route
from app.api.routes import intake as intake_route
from app.api.routes import memory as memory_route
from app.models.schemas import LongTermMemoryRecord, PlanningBrief, PlanningIntakeResponse, TripPlan
from app.services.poi_location_service import ResolvedPOI
from app.services.planning_intake_service import PlanningIntakeUnavailableError


client = TestClient(app, raise_server_exceptions=False)


def request_payload():
    return {
        "city": "开封",
        "start_date": "2026-09-13",
        "end_date": "2026-09-13",
        "travel_days": 1,
        "transportation": "公共交通",
        "accommodation": "舒适型酒店",
        "preferences": ["历史文化"],
    }


def minimal_plan():
    return TripPlan(
        city="开封",
        start_date="2026-09-13",
        end_date="2026-09-13",
        days=[],
        overall_suggestions="测试行程",
    )


def job_payload(status="queued", data=None):
    return {
        "id": "job-1",
        "workflow_id": "trip-1",
        "parent_job_id": None,
        "request": request_payload(),
        "status": status,
        "progress": 100 if status == "completed" else 2,
        "current_step": status,
        "message": "旅行计划生成完成" if status == "completed" else "任务已提交",
        "data": data,
        "error": None,
        "cancel_requested": False,
        "can_cancel": status in {"queued", "running", "cancelling"},
        "can_retry": status in {"failed", "cancelled", "interrupted"},
        "can_resume": status in {"failed", "cancelled", "interrupted"},
        "created_at": "2026-09-14T00:00:00+00:00",
        "updated_at": "2026-09-14T00:00:00+00:00",
    }


def test_health_endpoint_success():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_trip_plan_endpoint_success(monkeypatch):
    class FakePlanner:
        def plan_trip(self, request):
            assert request.city == "开封"
            return minimal_plan()

    monkeypatch.setattr(trip_route, "get_trip_planner_agent", lambda: FakePlanner())

    response = client.post("/api/trip/plan", json=request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["city"] == "开封"


def test_trip_plan_endpoint_returns_500_when_planner_fails(monkeypatch):
    class BrokenPlanner:
        def plan_trip(self, request):
            raise RuntimeError("planner unavailable")

    monkeypatch.setattr(trip_route, "get_trip_planner_agent", lambda: BrokenPlanner())

    response = client.post("/api/trip/plan", json=request_payload())

    assert response.status_code == 500
    assert "planner unavailable" in response.json()["detail"]


def test_trip_job_endpoint_returns_202_immediately(monkeypatch):
    class FakeManager:
        def create_job(self, request):
            assert request.city == "开封"
            return job_payload()

    monkeypatch.setattr(trip_route, "get_trip_job_manager", lambda: FakeManager())
    response = client.post("/api/trip/jobs", json=request_payload())

    assert response.status_code == 202
    assert response.json()["job_id"] == "job-1"
    assert response.json()["status"] == "queued"


def test_trip_job_sse_streams_persisted_progress_and_result(monkeypatch):
    plan = minimal_plan().model_dump(mode="json")

    class FakeManager:
        def get_job(self, job_id):
            assert job_id == "job-1"
            return job_payload("completed", plan)

        def list_events(self, job_id, after_id=0):
            return [{
                "id": 7,
                "job_id": job_id,
                "type": "completed",
                "status": "completed",
                "progress": 100,
                "current_step": "completed",
                "message": "旅行计划生成完成",
                "data": plan,
            }] if after_id < 7 else []

    monkeypatch.setattr(trip_route, "get_trip_job_manager", lambda: FakeManager())
    response = client.get("/api/trip/jobs/job-1/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: completed" in response.text
    assert '"city":"开封"' in response.text


def test_workflow_api_supports_approval_and_resume(monkeypatch):
    class FakePlanner:
        def start_workflow(self, request, *, require_approval, workflow_id=None):
            assert request.city == "开封"
            assert require_approval is True
            return {
                "workflow_id": workflow_id or "workflow-1",
                "status": "awaiting_approval",
                "approval_prompt": {"question": "是否确认？"},
                "trip_plan": None,
                "errors": {},
                "events": [],
            }

        def resume_workflow(self, workflow_id, approved=None):
            assert workflow_id == "workflow-1"
            assert approved is True
            return {
                "workflow_id": workflow_id,
                "status": "completed",
                "approval_prompt": None,
                "trip_plan": minimal_plan().model_dump(mode="json"),
                "errors": {},
                "events": [],
            }

        def get_workflow_status(self, workflow_id):
            assert workflow_id == "workflow-1"
            return {
                "workflow_id": workflow_id,
                "status": "awaiting_approval",
                "approval_prompt": {"question": "是否确认？"},
                "trip_plan": None,
                "errors": {},
                "events": [{"node": "approval", "status": "waiting"}],
            }

    monkeypatch.setattr(trip_route, "get_trip_planner_agent", lambda: FakePlanner())
    started = client.post("/api/trip/workflows", json={
        "trip": request_payload(),
        "require_approval": True,
        "workflow_id": "workflow-1",
    })
    assert started.status_code == 200
    assert started.json()["status"] == "awaiting_approval"
    assert started.json()["data"] is None

    resumed = client.post(
        "/api/trip/workflows/workflow-1/resume",
        json={"approved": True},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["data"]["city"] == "开封"

    status = client.get("/api/trip/workflows/workflow-1")
    assert status.status_code == 200
    assert status.json()["status"] == "awaiting_approval"
    assert status.json()["events"][0]["node"] == "approval"


def test_location_resolve_endpoint_handles_matches_and_misses(monkeypatch):
    class FakeResolver:
        def resolve(self, name, city, address=""):
            if name == "清明上河园":
                return ResolvedPOI(
                    poi_id="poi-1",
                    name=name,
                    address="开封市龙亭区",
                    longitude=114.340685,
                    latitude=34.809044,
                    confidence=0.95,
                )
            return None

    monkeypatch.setattr(poi_route, "POILocationService", FakeResolver)
    response = client.post("/api/poi/locations/resolve", json={
        "city": "开封",
        "places": [{"name": "清明上河园"}, {"name": "未知地点"}],
    })

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "已校准 1 个景点"
    assert body["data"][0]["location"] == {
        "longitude": 114.340685,
        "latitude": 34.809044,
    }
    assert body["data"][1]["matched"] is False


def test_planning_intake_endpoint_returns_brief_without_starting_planner(monkeypatch):
    class FakeIntakeService:
        def refine(self, request):
            assert request.messages[-1].content == "9月20日到23日去杭州"
            return PlanningIntakeResponse(
                assistant_message="信息已齐，请确认简报。",
                brief=PlanningBrief(
                    city="杭州",
                    start_date="2026-09-20",
                    end_date="2026-09-23",
                ),
                missing_fields=[],
                ready_to_confirm=True,
            )

    monkeypatch.setattr(intake_route, "get_planning_intake_service", lambda: FakeIntakeService())
    response = client.post("/api/trip/intake", json={
        "messages": [{"role": "user", "content": "9月20日到23日去杭州"}],
        "brief": {},
        "travel_memory": [],
        "carryover_places": [],
    })

    assert response.status_code == 200
    body = response.json()
    assert body["ready_to_confirm"] is True
    assert body["brief"]["city"] == "杭州"
    assert body["brief"]["travel_days"] == 4


def test_planning_intake_endpoint_maps_agent_failure_to_502(monkeypatch):
    class BrokenIntakeService:
        def refine(self, request):
            raise RuntimeError("llm unavailable")

    monkeypatch.setattr(intake_route, "get_planning_intake_service", lambda: BrokenIntakeService())
    response = client.post("/api/trip/intake", json={
        "messages": [{"role": "user", "content": "我想去旅行"}],
        "brief": {},
    })

    assert response.status_code == 502
    assert "需求顾问暂时无法回复" in response.json()["detail"]


def test_planning_intake_endpoint_does_not_expose_json_parser_errors(monkeypatch):
    class InvalidResponseIntakeService:
        def refine(self, request):
            raise PlanningIntakeUnavailableError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(intake_route, "get_planning_intake_service", lambda: InvalidResponseIntakeService())
    response = client.post("/api/trip/intake", json={
        "messages": [{"role": "user", "content": "只去成都"}],
        "brief": {"city": "成都、杭州"},
    })

    assert response.status_code == 502
    assert response.json()["detail"] == "我暂时没有正确整理这条信息，请换一种说法再试一次。"
    assert "Expecting" not in response.text


def test_long_term_memory_api_supports_extract_approve_and_forget(monkeypatch):
    record = LongTermMemoryRecord(
        id="memory-1",
        user_id="local-user",
        kind="avoidance",
        content="避免红眼航班",
        scope_city="",
        status="pending",
        source_conversation_id="archive-1",
        source_message_ids=["u1"],
        evidence="我不坐红眼航班",
        created_at="2026-09-13T00:00:00+00:00",
        updated_at="2026-09-13T00:00:00+00:00",
    )

    class FakeMemoryService:
        def extract_and_store(self, request):
            return "archive-1", [record]

        def list_memories(self, user_id, status=""):
            return [record]

        def update_memory(self, memory_id, update):
            return record.model_copy(update={"status": update.status or record.status})

        def forget_memory(self, memory_id, user_id):
            return True

    monkeypatch.setattr(memory_route, "get_long_term_memory_service", lambda: FakeMemoryService())
    extraction = client.post("/api/memory/extract", json={
        "messages": [{"id": "u1", "role": "user", "content": "我不坐红眼航班"}]
    })
    assert extraction.status_code == 200
    assert extraction.json()["memories"][0]["status"] == "pending"

    listing = client.get("/api/memory")
    assert listing.status_code == 200
    assert listing.json()["memories"][0]["evidence"] == "我不坐红眼航班"

    approval = client.patch("/api/memory/memory-1", json={"status": "approved"})
    assert approval.status_code == 200
    assert approval.json()["status"] == "approved"

    forgotten = client.delete("/api/memory/memory-1")
    assert forgotten.status_code == 200
    assert forgotten.json()["success"] is True
