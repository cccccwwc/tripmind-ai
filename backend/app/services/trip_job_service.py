"""Persistent background jobs and realtime progress for trip planning."""

from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from ..agents.trip_planner_agent import get_trip_planner_agent
from ..agents.trip_planner_graph import WorkflowCancelledError
from ..models.schemas import TripRequest


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class TripJobNotFoundError(KeyError):
    pass


class TripJobConflictError(RuntimeError):
    pass


class TripJobManager:
    """Run LangGraph workflows off the request thread and persist job events."""

    _NODE_PROGRESS = {
        "approval": 7,
        "prepare": 12,
        "attractions": 34,
        "weather": 44,
        "hotel": 54,
        "validate_research": 64,
        "retry_attractions": 70,
        "plan": 86,
        "validate_plan": 96,
        "fallback_plan": 98,
    }

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        planner_factory: Callable[[], Any] = get_trip_planner_agent,
        max_workers: int = 4,
    ):
        backend_root = Path(__file__).resolve().parents[2]
        self.database_path = Path(database_path) if database_path else backend_root / "data" / "trip_jobs.db"
        if not self.database_path.is_absolute():
            self.database_path = backend_root / self.database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.planner_factory = planner_factory
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="trip-job")
        self._closed = False
        self._init_database()
        self._mark_orphaned_jobs()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _init_database(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trip_jobs (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    parent_job_id TEXT,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    result_json TEXT,
                    error TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trip_job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES trip_jobs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_trip_job_events_job
                    ON trip_job_events(job_id, id);
                """
            )

    def _mark_orphaned_jobs(self) -> None:
        """A process restart cannot leave jobs pretending to still be running."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM trip_jobs WHERE status IN ('queued', 'running', 'cancelling')"
            ).fetchall()
            now = self._now()
            for row in rows:
                connection.execute(
                    "UPDATE trip_jobs SET status='interrupted', message=?, updated_at=? WHERE id=?",
                    ("服务曾重启，可点击继续任务", now, row["id"]),
                )
                self._insert_event(
                    connection,
                    row["id"],
                    "interrupted",
                    {"message": "服务曾重启，可从 LangGraph 检查点继续", "status": "interrupted"},
                    now,
                )

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> int:
        cursor = connection.execute(
            "INSERT INTO trip_job_events(job_id, event_type, data_json, created_at) VALUES (?, ?, ?, ?)",
            (job_id, event_type, json.dumps(payload, ensure_ascii=False), created_at),
        )
        return int(cursor.lastrowid)

    def _append_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        *,
        progress: int | None = None,
        current_step: str | None = None,
        status: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int:
        now = self._now()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM trip_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise TripJobNotFoundError(job_id)
            next_progress = int(row["progress"] if progress is None else max(row["progress"], progress))
            next_step = current_step if current_step is not None else row["current_step"]
            next_status = status or row["status"]
            connection.execute(
                """UPDATE trip_jobs
                   SET status=?, progress=?, current_step=?, message=?, updated_at=?
                   WHERE id=?""",
                (next_status, next_progress, next_step, message, now, job_id),
            )
            payload = {
                "job_id": job_id,
                "type": event_type,
                "status": next_status,
                "progress": next_progress,
                "current_step": next_step,
                "message": message,
                **(extra or {}),
            }
            return self._insert_event(connection, job_id, event_type, payload, now)

    def create_job(self, request: TripRequest, *, parent_job_id: str | None = None) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("后台任务服务已关闭")
        job_id = f"job-{uuid4().hex}"
        workflow_id = f"trip-{uuid4().hex}"
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO trip_jobs(
                       id, workflow_id, parent_job_id, request_json, status, progress,
                       current_step, message, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, 'queued', 2, 'queued', ?, ?, ?)""",
                (
                    job_id,
                    workflow_id,
                    parent_job_id,
                    request.model_dump_json(),
                    "任务已提交，等待后台执行",
                    now,
                    now,
                ),
            )
            self._insert_event(
                connection,
                job_id,
                "queued",
                {
                    "job_id": job_id,
                    "type": "queued",
                    "status": "queued",
                    "progress": 2,
                    "current_step": "queued",
                    "message": "任务已提交，等待后台执行",
                },
                now,
            )
        self.executor.submit(self._run_job, job_id, False)
        return self.get_job(job_id)

    def _monitor_graph(self, job_id: str, workflow: Any, workflow_id: str, stop: threading.Event) -> None:
        seen: set[tuple[str, str, str]] = {
            (str(event.get("node", "")), str(event.get("node_status", "")), str(event.get("message", "")))
            for event in self.list_events(job_id, 0)
            if event.get("type") == "progress"
        }
        while not stop.wait(0.25):
            try:
                result = workflow.status(workflow_id)
            except (KeyError, sqlite3.Error):
                continue
            except Exception:
                continue
            for event in result.get("events", []):
                signature = (
                    str(event.get("node", "")),
                    str(event.get("status", "")),
                    str(event.get("message", "")),
                )
                if signature in seen:
                    continue
                seen.add(signature)
                node = signature[0]
                self._append_event(
                    job_id,
                    "progress",
                    signature[2] or "工作流状态已更新",
                    progress=self._NODE_PROGRESS.get(node, 10),
                    current_step=node,
                    status="running",
                    extra={
                        "node": node,
                        "node_status": signature[1],
                        **{
                            key: event[key]
                            for key in ("tool_name", "tool_arguments", "attempts")
                            if key in event
                        },
                    },
                )

    def _run_job(self, job_id: str, resume: bool) -> None:
        job = self.get_job(job_id)
        planner = self.planner_factory()
        workflow = planner._get_workflow()
        workflow_id = job["workflow_id"]
        if job["cancel_requested"]:
            self._finish_cancelled(job_id)
            return
        workflow.clear_cancel(workflow_id)
        self._append_event(
            job_id,
            "started" if not resume else "resumed",
            "已理解旅行需求，正在启动混合规划工作流" if not resume else "正在从上次检查点继续",
            progress=6,
            current_step="approval",
            status="running",
        )
        stop_monitor = threading.Event()
        monitor = threading.Thread(
            target=self._monitor_graph,
            args=(job_id, workflow, workflow_id, stop_monitor),
            daemon=True,
            name=f"trip-monitor-{job_id[-8:]}",
        )
        monitor.start()
        try:
            if resume:
                try:
                    result = workflow.resume(workflow_id, approved=None)
                except KeyError:
                    request = TripRequest.model_validate(job["request"])
                    result = workflow.start(request, require_approval=False, workflow_id=workflow_id)
            else:
                request = TripRequest.model_validate(job["request"])
                result = workflow.start(request, require_approval=False, workflow_id=workflow_id)
            stop_monitor.set()
            monitor.join(timeout=1)
            self._sync_graph_events(job_id, workflow, workflow_id)
            if self.get_job(job_id)["cancel_requested"]:
                self._finish_cancelled(job_id)
                return
            trip_plan = result.get("trip_plan")
            if not trip_plan:
                raise RuntimeError("工作流结束但没有生成旅行计划")
            now = self._now()
            with self._connect() as connection:
                connection.execute(
                    """UPDATE trip_jobs SET status='completed', progress=100,
                       current_step='completed', message='旅行计划生成完成', result_json=?,
                       error=NULL, updated_at=? WHERE id=?""",
                    (json.dumps(trip_plan, ensure_ascii=False), now, job_id),
                )
            self._append_event(
                job_id,
                "completed",
                "旅行计划生成完成",
                progress=100,
                current_step="completed",
                status="completed",
                extra={
                    "data": trip_plan,
                    "poi_validation_report": result.get("poi_validation_report", {}),
                },
            )
        except WorkflowCancelledError:
            self._finish_cancelled(job_id)
        except Exception as exc:
            if self.get_job(job_id)["cancel_requested"]:
                self._finish_cancelled(job_id)
            else:
                now = self._now()
                with self._connect() as connection:
                    connection.execute(
                        "UPDATE trip_jobs SET status='failed', message=?, error=?, updated_at=? WHERE id=?",
                        ("旅行规划失败，可以重试或从检查点继续", str(exc), now, job_id),
                    )
                self._append_event(
                    job_id,
                    "failed",
                    "旅行规划失败，可以重试或从检查点继续",
                    status="failed",
                    extra={"error": str(exc)},
                )
        finally:
            stop_monitor.set()
            monitor.join(timeout=1)

    def _sync_graph_events(self, job_id: str, workflow: Any, workflow_id: str) -> None:
        """Capture the final checkpoint even if it was written between monitor polls."""
        self._monitor_graph_once(job_id, workflow, workflow_id)

    def _monitor_graph_once(self, job_id: str, workflow: Any, workflow_id: str) -> None:
        try:
            result = workflow.status(workflow_id)
        except Exception:
            return
        existing = {
            (event.get("node"), event.get("node_status"), event.get("message"))
            for event in self.list_events(job_id, 0)
            if event.get("type") == "progress"
        }
        for event in result.get("events", []):
            signature = (event.get("node"), event.get("status"), event.get("message"))
            if signature in existing:
                continue
            node = str(event.get("node", ""))
            self._append_event(
                job_id,
                "progress",
                str(event.get("message") or "工作流状态已更新"),
                progress=self._NODE_PROGRESS.get(node, 10),
                current_step=node,
                status="running",
                extra={
                    "node": node,
                    "node_status": str(event.get("status", "")),
                    **{
                        key: event[key]
                        for key in ("tool_name", "tool_arguments", "attempts")
                        if key in event
                    },
                },
            )

    def _finish_cancelled(self, job_id: str) -> None:
        self._append_event(
            job_id,
            "cancelled",
            "旅行规划已取消，已完成的步骤仍保留在检查点中",
            current_step="cancelled",
            status="cancelled",
        )

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] in TERMINAL_STATUSES:
            return job
        with self._connect() as connection:
            connection.execute(
                "UPDATE trip_jobs SET cancel_requested=1, status='cancelling', message=?, updated_at=? WHERE id=?",
                ("正在安全停止当前任务", self._now(), job_id),
            )
        try:
            self.planner_factory()._get_workflow().request_cancel(job["workflow_id"])
        except Exception:
            pass
        self._append_event(
            job_id,
            "cancelling",
            "已收到取消请求，将在当前外部调用结束后停止",
            status="cancelling",
        )
        return self.get_job(job_id)

    def retry_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] not in {"failed", "cancelled", "interrupted"}:
            raise TripJobConflictError("只有失败、取消或中断的任务可以重试")
        return self.create_job(TripRequest.model_validate(job["request"]), parent_job_id=job_id)

    def resume_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] not in {"failed", "cancelled", "interrupted"}:
            raise TripJobConflictError("当前任务不需要继续")
        with self._connect() as connection:
            connection.execute(
                """UPDATE trip_jobs SET status='queued', cancel_requested=0, error=NULL,
                   message='任务已排队，准备从检查点继续', updated_at=? WHERE id=?""",
                (self._now(), job_id),
            )
        self.executor.submit(self._run_job, job_id, True)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM trip_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise TripJobNotFoundError(job_id)
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"))
        result_json = result.pop("result_json")
        result["data"] = json.loads(result_json) if result_json else None
        result["cancel_requested"] = bool(result["cancel_requested"])
        result["can_cancel"] = result["status"] in {"queued", "running"}
        result["can_retry"] = result["status"] in {"failed", "cancelled", "interrupted"}
        result["can_resume"] = result["status"] in {"failed", "cancelled", "interrupted"}
        return result

    def list_events(self, job_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        self.get_job(job_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, event_type, data_json, created_at FROM trip_job_events WHERE job_id=? AND id>? ORDER BY id",
                (job_id, after_id),
            ).fetchall()
        events = []
        for row in rows:
            payload = json.loads(row["data_json"])
            payload.update({"id": row["id"], "type": row["event_type"], "created_at": row["created_at"]})
            events.append(payload)
        return events

    def close(self) -> None:
        self._closed = True
        self.executor.shutdown(wait=False, cancel_futures=False)


_manager: TripJobManager | None = None
_manager_lock = threading.Lock()


def get_trip_job_manager() -> TripJobManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = TripJobManager()
    return _manager


def close_trip_job_manager() -> None:
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.close()
            _manager = None
