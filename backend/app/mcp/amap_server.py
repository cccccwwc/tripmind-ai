"""稳定的高德地图 MCP 服务。

第三方 amap-mcp-server 0.1.11 使用没有超时的 ``requests.get``。
在部分 macOS 网络环境里 Python 会优先尝试不可用的 IPv6 TLS 链路，
导致 MCP ``CallToolRequest`` 一直等待。本服务保留标准 MCP 接口，同时：

1. 强制高德 HTTP 请求使用 IPv4；
2. 为连接和读取分别设置超时；
3. 返回景点坐标，供最终行程和前端地图使用。
"""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP
from urllib3.util import connection


# 必须在第一次 requests 调用之前设置。
connection.allowed_gai_family = lambda: socket.AF_INET

AMAP_BASE_URL = "https://restapi.amap.com"
CONNECT_TIMEOUT = float(os.getenv("AMAP_HTTP_CONNECT_TIMEOUT", "6"))
READ_TIMEOUT = float(os.getenv("AMAP_HTTP_READ_TIMEOUT", "15"))

mcp = FastMCP("hello-agents-amap")


def _api_key() -> str:
    key = os.getenv("AMAP_MAPS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AMAP_MAPS_API_KEY 未配置")
    return key


def _get(path: str, **params: Any) -> dict[str, Any]:
    response = requests.get(
        f"{AMAP_BASE_URL}{path}",
        params={"key": _api_key(), **params},
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "1":
        info = data.get("info") or "UNKNOWN_ERROR"
        infocode = data.get("infocode") or ""
        raise RuntimeError(f"高德 API 返回错误: {info} ({infocode})")
    return data


def _location(value: Any) -> dict[str, float] | None:
    if not isinstance(value, str) or "," not in value:
        return None
    longitude, latitude = value.split(",", 1)
    try:
        return {"longitude": float(longitude), "latitude": float(latitude)}
    except ValueError:
        return None


@mcp.tool()
def maps_text_search(
    keywords: str,
    city: str = "",
    citylimit: str = "true",
) -> dict[str, Any]:
    """在指定城市搜索景点、酒店等 POI，并返回名称、地址和真实坐标。"""
    try:
        data = _get(
            "/v3/place/text",
            keywords=keywords,
            city=city,
            citylimit=citylimit,
            offset=20,
            page=1,
            extensions="all",
        )
        pois = []
        for poi in data.get("pois", []):
            name = str(poi.get("name") or "")
            unavailable = any(
                marker in name
                for marker in ("不对外开放", "暂停开放", "停止开放", "永久关闭", "暂不开放", "闭园")
            )
            pois.append(
                {
                    "id": poi.get("id"),
                    "name": name,
                    "address": poi.get("address"),
                    "province": poi.get("pname"),
                    "city": poi.get("cityname") or city,
                    "district": poi.get("adname"),
                    "adcode": poi.get("adcode"),
                    "type": poi.get("type"),
                    "typecode": poi.get("typecode"),
                    "location": _location(poi.get("location")),
                    "tel": poi.get("tel"),
                    "operational_status": "unavailable" if unavailable else "unknown",
                    "data_source": "amap",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "verification_confidence": 1.0,
                }
            )
        return {"city": city, "keywords": keywords, "count": len(pois), "pois": pois}
    except requests.RequestException as exc:
        return {"error": f"高德网络请求失败: {exc}"}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def maps_weather(city: str) -> dict[str, Any]:
    """查询指定城市或 adcode 的高德天气预报。"""
    try:
        data = _get(
            "/v3/weather/weatherInfo",
            city=city,
            extensions="all",
        )
        forecasts = data.get("forecasts", [])
        if not forecasts:
            return {"error": "高德没有返回天气预报", "city": city}
        forecast = forecasts[0]
        return {
            "city": forecast.get("city") or city,
            "province": forecast.get("province"),
            "adcode": forecast.get("adcode"),
            "reporttime": forecast.get("reporttime"),
            "forecasts": forecast.get("casts", []),
        }
    except requests.RequestException as exc:
        return {"error": f"高德网络请求失败: {exc}"}
    except Exception as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
