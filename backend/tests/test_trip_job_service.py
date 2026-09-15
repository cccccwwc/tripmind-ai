import time

from app.models.schemas import TripPlan, TripRequest
from app.services.trip_job_service import TripJobManager


def request_payload():
    return TripRequest(
        city="开封",
        start_date="2026-09-14",
        end_date="2026-09-14",
        travel_days=1,
        transportation="公共交通",
        accommodation="舒适型酒店",
    )


def plan_payload():
    return TripPlan(
        city="开封",
        start_date="2026-09-14",
        end_date="2026-09-14",
        days=[],
        overall_suggestions="测试",
    ).model_dump(mode="json")


class FakeWorkflow:
    def __init__(self):
        self.results = {}

    def clear_cancel(self, workflow_id):
        return None

    def request_cancel(self, workflow_id):
        return None

    def start(self, request, *, require_approval, workflow_id):
        assert require_approval is False
        self.results[workflow_id] = {
            "workflow_id": workflow_id,
            "status": "completed",
            "trip_plan": plan_payload(),
            "events": [
                {"node": "prepare", "status": "completed", "message": "开始并行查询", "at": "1"},
                {"node": "attractions", "status": "completed", "message": "获得 2 个景点", "at": "2"},
                {"node": "validate_plan", "status": "completed", "message": "校验通过", "at": "3"},
            ],
        }
        return self.results[workflow_id]

    def status(self, workflow_id):
        if workflow_id not in self.results:
            raise KeyError(workflow_id)
        return self.results[workflow_id]


class FakePlanner:
    def __init__(self):
        self.workflow = FakeWorkflow()

    def _get_workflow(self):
        return self.workflow


def test_background_job_persists_progress_and_result(tmp_path):
    planner = FakePlanner()
    manager = TripJobManager(
        tmp_path / "jobs.db",
        planner_factory=lambda: planner,
        max_workers=1,
    )
    try:
        created = manager.create_job(request_payload())
        assert created["status"] in {"queued", "running", "completed"}

        deadline = time.time() + 3
        job = created
        while time.time() < deadline:
            job = manager.get_job(created["id"])
            if job["status"] == "completed":
                break
            time.sleep(0.02)

        assert job["status"] == "completed"
        assert job["progress"] == 100
        assert job["data"]["city"] == "开封"
        events = manager.list_events(created["id"])
        assert events[0]["type"] == "queued"
        assert any(event["type"] == "completed" for event in events)
        assert any(event.get("node") == "attractions" for event in events)
    finally:
        manager.close()
