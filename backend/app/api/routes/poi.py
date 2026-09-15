"""POI相关API路由"""

from fastapi import APIRouter, HTTPException, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import List, Optional
from ...services.amap_service import get_amap_service
from ...services.unsplash_service import get_unsplash_service
from ...services.poi_location_service import POILocationService

router = APIRouter(prefix="/poi", tags=["POI"])


class POIDetailResponse(BaseModel):
    """POI详情响应"""
    success: bool
    message: str
    data: Optional[dict] = None


class PhotoPrepareRequest(BaseModel):
    """一次性准备当前行程所需的景点图片。"""
    city: str = Field(default="", max_length=50)
    names: List[str] = Field(default_factory=list, max_length=18)


class PlaceLocationRequest(BaseModel):
    """需要重新核验坐标的行程地点。"""
    name: str = Field(..., min_length=1, max_length=100)
    address: str = Field(default="", max_length=300)


class LocationResolveRequest(BaseModel):
    """批量核验旧行程里的景点坐标。"""
    city: str = Field(..., min_length=1, max_length=50)
    places: List[PlaceLocationRequest] = Field(default_factory=list, max_length=60)


@router.post(
    "/locations/resolve",
    summary="校准景点坐标",
    description="按城市和景点名称重新匹配高德官方 POI，供旧行程修复地图坐标",
)
async def resolve_place_locations(payload: LocationResolveRequest):
    service = POILocationService()

    def resolve_all():
        resolved_places = []
        seen = set()
        for place in payload.places:
            cache_key = (place.name.strip(), place.address.strip())
            if cache_key in seen:
                continue
            seen.add(cache_key)
            result = service.resolve(place.name, payload.city, place.address)
            if result is None:
                resolved_places.append({
                    "query_name": place.name,
                    "matched": False,
                })
                continue
            resolved_places.append({
                "query_name": place.name,
                "matched": True,
                "poi_id": result.poi_id,
                "name": result.name,
                "address": result.address,
                "location": {
                    "longitude": result.longitude,
                    "latitude": result.latitude,
                },
                "confidence": round(result.confidence, 3),
            })
        return resolved_places

    data = await run_in_threadpool(resolve_all)
    matched = sum(1 for item in data if item.get("matched"))
    return {
        "success": True,
        "message": f"已校准 {matched} 个景点",
        "data": data,
    }


@router.get(
    "/detail/{poi_id}",
    response_model=POIDetailResponse,
    summary="获取POI详情",
    description="根据POI ID获取详细信息,包括图片"
)
async def get_poi_detail(poi_id: str):
    """
    获取POI详情
    
    Args:
        poi_id: POI ID
        
    Returns:
        POI详情响应
    """
    try:
        amap_service = get_amap_service()
        
        # 调用高德地图POI详情API
        result = amap_service.get_poi_detail(poi_id)
        
        return POIDetailResponse(
            success=True,
            message="获取POI详情成功",
            data=result
        )
        
    except Exception as e:
        print(f"❌ 获取POI详情失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取POI详情失败: {str(e)}"
        )


@router.get(
    "/search",
    summary="搜索POI",
    description="根据关键词搜索POI"
)
async def search_poi(keywords: str, city: str = "北京"):
    """
    搜索POI

    Args:
        keywords: 搜索关键词
        city: 城市名称

    Returns:
        搜索结果
    """
    try:
        amap_service = get_amap_service()
        result = amap_service.search_poi(keywords, city)

        return {
            "success": True,
            "message": "搜索成功",
            "data": result
        }

    except Exception as e:
        print(f"❌ 搜索POI失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"搜索POI失败: {str(e)}"
        )


@router.get(
    "/photo",
    summary="获取景点图片",
    description="根据景点名称从Unsplash获取图片"
)
async def get_attraction_photo(name: str):
    """
    获取景点图片

    Args:
        name: 景点名称

    Returns:
        图片URL
    """
    try:
        unsplash_service = get_unsplash_service()

        # 搜索景点图片
        photo_url = unsplash_service.get_photo_url(f"{name} China landmark")

        if not photo_url:
            # 如果没找到,尝试只用景点名称搜索
            photo_url = unsplash_service.get_photo_url(name)

        return {
            "success": True,
            "message": "获取图片成功",
            "data": {
                "name": name,
                "photo_url": photo_url
            }
        }

    except Exception as e:
        print(f"❌ 获取景点图片失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取景点图片失败: {str(e)}"
        )


@router.post(
    "/photos/prepare",
    summary="批量准备景点图片",
    description="一次搜索并按图片描述核验多个景点，减少请求数量与错误匹配",
)
async def prepare_attraction_photos(payload: PhotoPrepareRequest):
    try:
        unsplash_service = get_unsplash_service()
        prepared = await run_in_threadpool(
            unsplash_service.prepare_attraction_photos,
            payload.names,
            payload.city,
        )
        return {"success": True, "prepared": prepared}
    except Exception as e:
        # 预热失败不会阻止页面使用高德图片或本地占位图。
        print(f"⚠️ 批量准备景点图片失败: {str(e)}")
        return {"success": False, "prepared": 0}


@router.get(
    "/photo/image",
    summary="代理景点图片",
    description="根据景点名称搜索图片并由后端直接返回图片内容"
)
async def proxy_attraction_photo(name: str, city: str = "", address: str = "", index: int = 0):
    """精确匹配景点图片，并转换为同源后端资源。"""
    try:
        unsplash_service = get_unsplash_service()
        result = await run_in_threadpool(
            unsplash_service.get_attraction_photo,
            name,
            city,
            address,
            index,
        )
        if not result:
            raise HTTPException(status_code=404, detail="未找到可用的景点图片")

        content, content_type = result
        return Response(
            content=content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=604800, immutable"},
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 代理景点图片失败: {str(e)}")
        raise HTTPException(status_code=502, detail="景点图片加载失败")
