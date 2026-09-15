"""Tavily 实时旅行推荐 API。"""

import httpx
from fastapi import APIRouter, HTTPException

from ...models.schemas import RecommendationRequest, RecommendationResponse
from ...services.tavily_service import get_tavily_recommendation_service


router = APIRouter(prefix="/recommendations", tags=["实时推荐"])


@router.post("/discover", response_model=RecommendationResponse)
async def discover_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    """聚合公开网页攻略并返回带来源的推荐候选。"""
    try:
        query, recommendations = await get_tavily_recommendation_service().discover(
            city=request.city.strip(),
            preferences=request.preferences,
            limit=request.limit,
        )
        return RecommendationResponse(
            success=True,
            message=f"已找到 {len(recommendations)} 条有来源的实时推荐",
            query=query,
            data=recommendations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = "Tavily 鉴权失败，请检查 API Key" if status in {401, 403} else "Tavily 搜索服务暂时不可用"
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="无法连接 Tavily 搜索服务，请稍后重试") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        print(f"❌ 获取实时推荐失败: {exc}")
        raise HTTPException(status_code=500, detail="生成实时推荐榜单失败") from exc
