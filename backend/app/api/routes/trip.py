"""旅行规划 API 路由。"""

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from ...models.schemas import (
    TripJobResponse,
    TripRequest,
    TripPlanResponse,
    TripWorkflowResumeRequest,
    TripWorkflowResponse,
    TripWorkflowStartRequest,
)
from ...agents.trip_planner_agent import get_trip_planner_agent
from ...services.trip_job_service import (
    TERMINAL_STATUSES,
    TripJobConflictError,
    TripJobNotFoundError,
    get_trip_job_manager,
)

router = APIRouter(prefix="/trip", tags=["旅行规划"])


def _job_response(job: dict) -> TripJobResponse:
    return TripJobResponse(
        job_id=job["id"],
        workflow_id=job["workflow_id"],
        parent_job_id=job.get("parent_job_id"),
        status=job["status"],
        progress=job["progress"],
        current_step=job["current_step"],
        message=job["message"],
        can_cancel=job["can_cancel"],
        can_retry=job["can_retry"],
        can_resume=job["can_resume"],
        data=job.get("data"),
        error=job.get("error"),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


@router.post(
    "/jobs",
    response_model=TripJobResponse,
    status_code=202,
    summary="提交后台旅行规划任务",
)
async def create_trip_job(payload: TripRequest):
    """Return immediately; LangGraph continues in a worker thread."""
    try:
        return _job_response(get_trip_job_manager().create_job(payload))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建后台任务失败: {exc}") from exc


@router.get("/jobs/{job_id}", response_model=TripJobResponse, summary="查询后台任务状态")
async def get_trip_job(job_id: str):
    try:
        return _job_response(get_trip_job_manager().get_job(job_id))
    except TripJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到该旅行规划任务") from exc


@router.post("/jobs/{job_id}/cancel", response_model=TripJobResponse, summary="取消后台任务")
async def cancel_trip_job(job_id: str):
    try:
        return _job_response(get_trip_job_manager().cancel_job(job_id))
    except TripJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到该旅行规划任务") from exc


@router.post("/jobs/{job_id}/retry", response_model=TripJobResponse, status_code=202, summary="重试后台任务")
async def retry_trip_job(job_id: str):
    try:
        return _job_response(get_trip_job_manager().retry_job(job_id))
    except TripJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到该旅行规划任务") from exc
    except TripJobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/resume", response_model=TripJobResponse, status_code=202, summary="从检查点继续后台任务")
async def resume_trip_job(job_id: str):
    try:
        return _job_response(get_trip_job_manager().resume_job(job_id))
    except TripJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到该旅行规划任务") from exc
    except TripJobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/events", summary="订阅后台任务实时进度（SSE）")
async def stream_trip_job_events(
    job_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    manager = get_trip_job_manager()
    try:
        manager.get_job(job_id)
    except TripJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到该旅行规划任务") from exc

    try:
        cursor = max(after, int(last_event_id or 0))
    except ValueError:
        cursor = after

    async def generate():
        nonlocal cursor
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                return
            events = await run_in_threadpool(manager.list_events, job_id, cursor)
            for event in events:
                cursor = int(event["id"])
                event_name = event.get("type", "progress")
                data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {cursor}\nevent: {event_name}\ndata: {data}\n\n"
            job = await run_in_threadpool(manager.get_job, job_id)
            if job["status"] in TERMINAL_STATUSES:
                if not events:
                    data = json.dumps({
                        "job_id": job_id,
                        "type": job["status"],
                        "status": job["status"],
                        "progress": job["progress"],
                        "current_step": job["current_step"],
                        "message": job["message"],
                        "data": job.get("data"),
                        "error": job.get("error"),
                    }, ensure_ascii=False, separators=(",", ":"))
                    yield f"event: {job['status']}\ndata: {data}\n\n"
                return
            idle_ticks += 1
            if idle_ticks % 20 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应
    """
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'='*60}\n")

        # 获取混合规划器实例
        print("🔄 获取混合旅行规划系统实例...")
        agent = get_trip_planner_agent()

        # 生成旅行计划
        print("🚀 开始生成旅行计划...")
        # Agent/MCP clients are synchronous. Keep the FastAPI event loop free so
        # other requests and workflow status polling remain responsive.
        trip_plan = await run_in_threadpool(agent.plan_trip, request)

        print("✅ 旅行计划生成成功,准备返回响应\n")

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan
        )
    except Exception as e:
        print(f"❌ 生成旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}"
        )


def _workflow_response(result: dict) -> TripWorkflowResponse:
    return TripWorkflowResponse(
        workflow_id=result["workflow_id"],
        status=result["status"],
        message={
            "awaiting_approval": "等待用户确认 Planning Brief",
            "rejected": "用户已取消本次规划",
            "completed": "旅行计划生成成功",
        }.get(result["status"], "工作流状态已更新"),
        approval_prompt=result.get("approval_prompt"),
        data=result.get("trip_plan"),
        poi_validation_report=result.get("poi_validation_report", {}),
        errors=result.get("errors", {}),
        events=result.get("events", []),
    )


@router.post("/workflows", response_model=TripWorkflowResponse, summary="创建可恢复旅行规划工作流")
async def start_trip_workflow(payload: TripWorkflowStartRequest):
    try:
        agent = get_trip_planner_agent()
        result = await run_in_threadpool(
            agent.start_workflow,
            payload.trip,
            require_approval=payload.require_approval,
            workflow_id=payload.workflow_id,
        )
        return _workflow_response(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建工作流失败: {exc}") from exc


@router.post(
    "/workflows/{workflow_id}/resume",
    response_model=TripWorkflowResponse,
    summary="审批或恢复旅行规划工作流",
)
async def resume_trip_workflow(workflow_id: str, payload: TripWorkflowResumeRequest):
    try:
        agent = get_trip_planner_agent()
        result = await run_in_threadpool(
            agent.resume_workflow,
            workflow_id,
            payload.approved,
        )
        return _workflow_response(result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未找到该旅行规划工作流") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"恢复工作流失败: {exc}") from exc


@router.get(
    "/workflows/{workflow_id}",
    response_model=TripWorkflowResponse,
    summary="查询旅行规划工作流状态",
)
async def get_trip_workflow(workflow_id: str):
    try:
        agent = get_trip_planner_agent()
        result = await run_in_threadpool(agent.get_workflow_status, workflow_id)
        return _workflow_response(result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未找到该旅行规划工作流") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"查询工作流失败: {exc}") from exc

@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        # 初始化规划器并报告当前混合编排结构。
        agent = get_trip_planner_agent()
        
        return {
            "status": "healthy",
            "service": "trip-planner",
            "orchestrator": "langgraph",
            "architecture": {
                "deterministic_nodes": ["amap_attractions", "amap_weather", "amap_hotels"],
                "model_nodes": ["route_planner"],
            },
            "planner_tools": len(agent.planner_agent.list_tools()),
            "persistence": "sqlite",
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
