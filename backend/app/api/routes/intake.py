"""多轮旅行需求澄清 API。"""

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ...models.schemas import PlanningIntakeRequest, PlanningIntakeResponse
from ...services.planning_intake_service import (
    INTAKE_UNAVAILABLE_MESSAGE,
    PlanningIntakeUnavailableError,
    get_planning_intake_service,
)


router = APIRouter(prefix="/trip", tags=["旅行需求澄清"])


@router.post("/intake", response_model=PlanningIntakeResponse)
async def refine_planning_brief(request: PlanningIntakeRequest) -> PlanningIntakeResponse:
    """通过多轮对话补齐旅行信息，但不启动正式规划。"""
    try:
        return await run_in_threadpool(get_planning_intake_service().refine, request)
    except PlanningIntakeUnavailableError as exc:
        print(f"❌ 旅行需求结构化失败: {exc}")
        raise HTTPException(status_code=502, detail=INTAKE_UNAVAILABLE_MESSAGE) from exc
    except ValueError as exc:
        print(f"❌ 旅行需求参数无效: {exc}")
        raise HTTPException(status_code=422, detail="旅行信息格式无效，请检查后重试") from exc
    except Exception as exc:
        print(f"❌ 旅行需求澄清失败: {exc}")
        raise HTTPException(status_code=502, detail="需求顾问暂时无法回复，请稍后重试") from exc
