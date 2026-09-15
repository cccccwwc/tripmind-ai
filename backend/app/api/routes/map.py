"""地图服务API路由"""

import requests
from fastapi import APIRouter, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool
from typing import Optional
from ...config import get_settings
from ...models.schemas import (
    POISearchRequest,
    POISearchResponse,
    RouteRequest,
    RouteResponse,
    WeatherResponse
)
from ...services.amap_service import get_amap_service

router = APIRouter(prefix="/map", tags=["地图服务"])


def _fetch_static_map(points: list[tuple[float, float]]) -> tuple[bytes, str]:
    """使用后端 Web 服务 Key 请求高德静态地图，避免在前端暴露 Key。"""
    key = get_settings().amap_api_key
    if not key:
        raise RuntimeError("AMAP_API_KEY 未配置")

    marker_groups = []
    for index, (longitude, latitude) in enumerate(points, start=1):
        marker_groups.append(
            f"mid,0x438CF4,{index % 10}:{longitude:.6f},{latitude:.6f}"
        )

    params = {
        "key": key,
        "size": "700*600",
        "scale": 1,
        "markers": "|".join(marker_groups),
    }
    if len(points) > 1:
        coordinates = ";".join(f"{lng:.6f},{lat:.6f}" for lng, lat in points)
        params["paths"] = f"4,0x438CF4,0.85,,:{coordinates}"

    response = requests.get(
        "https://restapi.amap.com/v3/staticmap",
        params=params,
        timeout=(5, 20),
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0]
    if not content_type.startswith("image/"):
        detail = response.text[:200]
        raise RuntimeError(f"高德静态地图返回异常: {detail}")
    return response.content, content_type


@router.get(
    "/static",
    summary="获取高德静态地图",
    description="根据景点坐标生成包含标记和连线的高德静态地图"
)
async def get_static_map(points: str = Query(..., description="以分号分隔的经纬度坐标")):
    parsed_points: list[tuple[float, float]] = []
    try:
        for item in points.split(";")[:10]:
            longitude_text, latitude_text = item.split(",", 1)
            longitude = float(longitude_text)
            latitude = float(latitude_text)
            if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                raise ValueError("坐标超出范围")
            parsed_points.append((longitude, latitude))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"坐标格式错误: {exc}") from exc

    if not parsed_points:
        raise HTTPException(status_code=400, detail="至少需要一个景点坐标")

    try:
        content, content_type = await run_in_threadpool(_fetch_static_map, parsed_points)
        return Response(
            content=content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"高德静态地图请求失败: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/poi",
    response_model=POISearchResponse,
    summary="搜索POI",
    description="根据关键词搜索POI(兴趣点)"
)
async def search_poi(
    keywords: str = Query(..., description="搜索关键词", example="故宫"),
    city: str = Query(..., description="城市", example="北京"),
    citylimit: bool = Query(True, description="是否限制在城市范围内")
):
    """
    搜索POI
    
    Args:
        keywords: 搜索关键词
        city: 城市
        citylimit: 是否限制在城市范围内
        
    Returns:
        POI搜索结果
    """
    try:
        # 获取服务实例
        service = get_amap_service()
        
        # 搜索POI
        pois = service.search_poi(keywords, city, citylimit)
        
        return POISearchResponse(
            success=True,
            message="POI搜索成功",
            data=pois
        )
        
    except Exception as e:
        print(f"❌ POI搜索失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"POI搜索失败: {str(e)}"
        )


@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="查询天气",
    description="查询指定城市的天气信息"
)
async def get_weather(
    city: str = Query(..., description="城市名称", example="北京")
):
    """
    查询天气
    
    Args:
        city: 城市名称
        
    Returns:
        天气信息
    """
    try:
        # 获取服务实例
        service = get_amap_service()
        
        # 查询天气
        weather_info = service.get_weather(city)
        
        return WeatherResponse(
            success=True,
            message="天气查询成功",
            data=weather_info
        )
        
    except Exception as e:
        print(f"❌ 天气查询失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"天气查询失败: {str(e)}"
        )


@router.post(
    "/route",
    response_model=RouteResponse,
    summary="规划路线",
    description="规划两点之间的路线"
)
async def plan_route(request: RouteRequest):
    """
    规划路线
    
    Args:
        request: 路线规划请求
        
    Returns:
        路线信息
    """
    try:
        # 获取服务实例
        service = get_amap_service()
        
        # 规划路线
        route_info = service.plan_route(
            origin_address=request.origin_address,
            destination_address=request.destination_address,
            origin_city=request.origin_city,
            destination_city=request.destination_city,
            route_type=request.route_type
        )
        
        return RouteResponse(
            success=True,
            message="路线规划成功",
            data=route_info
        )
        
    except Exception as e:
        print(f"❌ 路线规划失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"路线规划失败: {str(e)}"
        )


@router.get(
    "/health",
    summary="健康检查",
    description="检查地图服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        # 检查服务是否可用
        service = get_amap_service()
        
        return {
            "status": "healthy",
            "service": "map-service",
            "mcp_tools_count": len(service.mcp_tool._available_tools)
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
