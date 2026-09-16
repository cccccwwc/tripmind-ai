"""Resolve itinerary place names to verified AMap POIs.

The planner model is useful for arranging an itinerary, but it must not be the
source of truth for map coordinates.  This service performs an exact, city
restricted POI lookup and only returns coordinates when the match is strong
enough.
"""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

import requests
from urllib3.util import connection

from ..config import get_settings


# Avoid the IPv6 TLS stalls that can occur on some macOS networks.
connection.allowed_gai_family = lambda: socket.AF_INET


@dataclass(frozen=True)
class ResolvedPOI:
    poi_id: str
    name: str
    address: str
    longitude: float
    latitude: float
    confidence: float
    city: str = ""
    district: str = ""
    poi_type: str = ""
    poi_typecode: str = ""
    operational_status: str = "unknown"
    data_source: str = "amap"
    verified_at: str = ""


class POILocationService:
    """Resolve an attraction against AMap instead of trusting LLM coordinates."""

    endpoint = "https://restapi.amap.com/v3/place/text"
    unavailable_name_pattern = re.compile(
        r"不对外开放|暂停开放|停止开放|永久关闭|暂不开放|闭园"
    )

    def __init__(self) -> None:
        self.api_key = get_settings().amap_api_key.strip()
        self.session = requests.Session()

    @staticmethod
    def _poi_city_text(poi: dict[str, Any]) -> str:
        return "".join(
            str(poi.get(key) or "")
            for key in ("pname", "cityname", "adname", "address")
        )

    @staticmethod
    def _to_resolved_poi(poi: dict[str, Any], confidence: float = 1.0) -> Optional[ResolvedPOI]:
        poi_name = str(poi.get("name") or "").strip()
        # AMap sometimes returns an exact coordinate for a place that cannot be
        # visited. It is geographically valid but invalid as an itinerary POI.
        if POILocationService.unavailable_name_pattern.search(poi_name):
            return None
        location = str(poi.get("location") or "")
        if "," not in location:
            return None
        try:
            longitude_text, latitude_text = location.split(",", 1)
            longitude, latitude = float(longitude_text), float(latitude_text)
        except (TypeError, ValueError):
            return None
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            return None

        address = poi.get("address")
        if isinstance(address, list):
            address = "".join(str(part) for part in address)
        return ResolvedPOI(
            poi_id=str(poi.get("id") or ""),
            name=poi_name,
            address=str(address or "").strip(),
            longitude=longitude,
            latitude=latitude,
            confidence=confidence,
            city=str(poi.get("cityname") or "").strip(),
            district=str(poi.get("adname") or "").strip(),
            poi_type=str(poi.get("type") or "").strip(),
            poi_typecode=str(poi.get("typecode") or "").strip(),
            # AMap place/text confirms the POI identity, not live opening
            # status. Explicit closure markers are rejected above; all other
            # places remain unknown until a dedicated opening-hours source is used.
            operational_status="unknown",
            data_source="amap",
            verified_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _normalize(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[（(].*?[）)]", "", text)
        text = re.sub(
            r"(?:景区|风景区|旅游区|公园|博物馆|纪念馆|遗址|故居|寺|街区|广场)$",
            "",
            text,
        )
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", text)

    @classmethod
    def _score(cls, query: str, poi: dict[str, Any], city: str, address: str) -> float:
        query_name = cls._normalize(query)
        poi_name = cls._normalize(poi.get("name"))
        if not query_name or not poi_name:
            return 0.0

        if query_name == poi_name:
            name_score = 1.0
        elif query_name in poi_name or poi_name in query_name:
            name_score = 0.86
        else:
            name_score = SequenceMatcher(None, query_name, poi_name).ratio()

        city_text = cls._poi_city_text(poi)
        city_score = 1.0 if city and cls._normalize(city) in cls._normalize(city_text) else 0.0

        address_score = 0.0
        normalized_address = cls._normalize(address)
        normalized_poi_address = cls._normalize(poi.get("address"))
        if normalized_address and normalized_poi_address:
            address_score = SequenceMatcher(
                None, normalized_address, normalized_poi_address
            ).ratio()

        return name_score * 0.78 + city_score * 0.17 + address_score * 0.05

    def resolve(self, name: str, city: str, address: str = "") -> Optional[ResolvedPOI]:
        if not self.api_key or not name.strip() or not city.strip():
            return None

        try:
            response = self.session.get(
                self.endpoint,
                params={
                    "key": self.api_key,
                    "keywords": name.strip(),
                    "city": city.strip(),
                    "citylimit": "true",
                    "offset": 10,
                    "page": 1,
                    "extensions": "all",
                },
                timeout=(6, 15),
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "1":
                return None

            candidates: list[tuple[float, dict[str, Any]]] = []
            for poi in payload.get("pois") or []:
                location = str(poi.get("location") or "")
                if "," not in location:
                    continue
                city_text = self._poi_city_text(poi)
                # 高德偶尔会返回外地同名景点；有明确城市信息时必须匹配。
                if city_text and self._normalize(city) not in self._normalize(city_text):
                    continue
                candidates.append((self._score(name, poi, city, address), poi))

            if not candidates:
                return None

            confidence, poi = max(candidates, key=lambda item: item[0])
            # A loose search hit in the correct city is still not enough for a
            # map marker.  A wrong marker is worse than an omitted marker.
            if confidence < 0.72:
                return None

            result = self._to_resolved_poi(poi, confidence)
            if result is None:
                return None
            return ResolvedPOI(
                poi_id=result.poi_id,
                name=result.name or name,
                address=result.address or address or city,
                longitude=result.longitude,
                latitude=result.latitude,
                confidence=result.confidence,
                city=result.city or city,
                district=result.district,
                poi_type=result.poi_type,
                poi_typecode=result.poi_typecode,
                operational_status=result.operational_status,
                data_source=result.data_source,
                verified_at=result.verified_at,
            )
        except (requests.RequestException, ValueError, TypeError):
            return None

    def search(self, keywords: str, city: str, limit: int = 20) -> tuple[ResolvedPOI, ...]:
        """Return real, city-restricted AMap POIs for resilient plan recovery.

        Unlike ``resolve``, this method intentionally accepts multiple different
        names because it is used for category searches such as “旅游景点” or
        “餐厅”. Every returned item still has an official AMap id and coordinate.
        """
        if not self.api_key or not keywords.strip() or not city.strip():
            return ()
        try:
            response = self.session.get(
                self.endpoint,
                params={
                    "key": self.api_key,
                    "keywords": keywords.strip(),
                    "city": city.strip(),
                    "citylimit": "true",
                    "offset": max(1, min(int(limit), 25)),
                    "page": 1,
                    "extensions": "all",
                },
                timeout=(6, 15),
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "1":
                return ()

            resolved: list[ResolvedPOI] = []
            seen: set[str] = set()
            normalized_city = self._normalize(city)
            for poi in payload.get("pois") or []:
                city_text = self._poi_city_text(poi)
                if city_text and normalized_city not in self._normalize(city_text):
                    continue
                item = self._to_resolved_poi(poi)
                key = item.poi_id if item else ""
                if item is None or not item.name or not key or key in seen:
                    continue
                seen.add(key)
                resolved.append(item)
            return tuple(resolved)
        except (requests.RequestException, ValueError, TypeError):
            return ()
