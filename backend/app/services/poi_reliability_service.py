"""Deterministic reliability checks for itinerary attractions.

The language model arranges a trip, but AMap remains the source of truth for
place identity.  This module deliberately contains no model calls: every
failure is structured so LangGraph can decide whether to search again.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import asin, cos, radians, sin, sqrt
from statistics import median
from typing import Any, Iterable

from ..models.schemas import TripPlan


@dataclass(frozen=True)
class POIValidationIssue:
    code: str
    reason: str
    name: str
    day_index: int
    poi_id: str = ""


@dataclass(frozen=True)
class POIValidationReport:
    is_valid: bool
    total: int
    valid: int
    issues: list[POIValidationIssue]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total": self.total,
            "valid": self.valid,
            "issues": [asdict(issue) for issue in self.issues],
            "warnings": list(self.warnings),
        }


class POIReliabilityService:
    """Validate identity, location, availability and route plausibility."""

    MIN_CONFIDENCE = 0.72
    MAX_CLUSTER_DISTANCE_KM = 90.0
    MAX_DAY_LEG_DISTANCE_KM = 80.0
    INVALID_STATUSES = {"unavailable", "closed", "permanently_closed"}

    @staticmethod
    def _normalize(value: Any) -> str:
        return "".join(str(value or "").casefold().replace("市", "").split())

    @staticmethod
    def distance_km(longitude_a: float, latitude_a: float, longitude_b: float, latitude_b: float) -> float:
        """Return great-circle distance between two WGS-like coordinates."""
        earth_radius_km = 6371.0088
        lat_a, lat_b = radians(latitude_a), radians(latitude_b)
        delta_lat = lat_b - lat_a
        delta_lon = radians(longitude_b - longitude_a)
        value = sin(delta_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
        return 2 * earth_radius_km * asin(sqrt(value))

    def filter_spatial_outliers(self, pois: Iterable[Any]) -> list[Any]:
        """Remove category-search hits far outside the dominant city cluster."""
        items = list(pois)
        if len(items) < 3:
            return items
        center_longitude = median(float(item.longitude) for item in items)
        center_latitude = median(float(item.latitude) for item in items)
        return [
            item for item in items
            if self.distance_km(
                center_longitude,
                center_latitude,
                float(item.longitude),
                float(item.latitude),
            ) <= self.MAX_CLUSTER_DISTANCE_KM
        ]

    def order_by_proximity(self, pois: Iterable[Any]) -> list[Any]:
        """Create a deterministic nearest-neighbour order for daily grouping."""
        remaining = list(pois)
        if len(remaining) < 2:
            return remaining
        ordered = [remaining.pop(0)]
        while remaining:
            previous = ordered[-1]
            next_index = min(
                range(len(remaining)),
                key=lambda index: self.distance_km(
                    float(previous.longitude),
                    float(previous.latitude),
                    float(remaining[index].longitude),
                    float(remaining[index].latitude),
                ),
            )
            ordered.append(remaining.pop(next_index))
        return ordered

    def validate_plan(self, plan: TripPlan, requested_city: str) -> POIValidationReport:
        issues: list[POIValidationIssue] = []
        warnings: list[str] = []
        coordinates: list[tuple[int, Any, float, float]] = []
        requested_city_normalized = self._normalize(requested_city)

        def add_issue(code: str, reason: str, attraction: Any, day_index: int) -> None:
            issues.append(POIValidationIssue(
                code=code,
                reason=reason,
                name=str(attraction.name),
                day_index=day_index,
                poi_id=str(attraction.poi_id or ""),
            ))

        total = 0
        for day in plan.days:
            day_coordinates: list[tuple[Any, float, float]] = []
            for attraction in day.attractions:
                total += 1
                if not attraction.poi_id:
                    add_issue("missing_poi_id", "缺少高德 POI ID", attraction, day.day_index)
                if attraction.location is None:
                    add_issue("missing_location", "高德未匹配到可信坐标", attraction, day.day_index)
                    continue

                longitude = float(attraction.location.longitude)
                latitude = float(attraction.location.latitude)
                if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                    add_issue("invalid_coordinate", "经纬度超出合法范围", attraction, day.day_index)
                    continue

                city_normalized = self._normalize(attraction.city)
                if not city_normalized or requested_city_normalized not in city_normalized:
                    add_issue("wrong_city", f"高德城市不是 {requested_city}", attraction, day.day_index)
                if str(attraction.operational_status).casefold() in self.INVALID_STATUSES:
                    add_issue("unavailable", "地点当前不可作为可游览景点", attraction, day.day_index)
                if attraction.data_source != "amap":
                    add_issue("untrusted_source", "地点不是由高德数据核验", attraction, day.day_index)
                if not attraction.verified_at:
                    add_issue("missing_verified_at", "缺少地点核验时间", attraction, day.day_index)
                if attraction.verification_confidence < self.MIN_CONFIDENCE:
                    add_issue(
                        "low_confidence",
                        f"地点匹配置信度低于 {self.MIN_CONFIDENCE:.2f}",
                        attraction,
                        day.day_index,
                    )
                if not attraction.district:
                    warnings.append(f"{attraction.name} 缺少行政区信息")

                coordinates.append((day.day_index, attraction, longitude, latitude))
                day_coordinates.append((attraction, longitude, latitude))

            for previous, current in zip(day_coordinates, day_coordinates[1:]):
                distance = self.distance_km(previous[1], previous[2], current[1], current[2])
                if distance > self.MAX_DAY_LEG_DISTANCE_KM:
                    add_issue(
                        "day_route_too_far",
                        f"与上一景点相距 {distance:.1f} 公里，不适合排在同一天",
                        current[0],
                        day.day_index,
                    )

        if len(coordinates) >= 3:
            center_longitude = median(item[2] for item in coordinates)
            center_latitude = median(item[3] for item in coordinates)
            for day_index, attraction, longitude, latitude in coordinates:
                distance = self.distance_km(center_longitude, center_latitude, longitude, latitude)
                if distance > self.MAX_CLUSTER_DISTANCE_KM:
                    add_issue(
                        "spatial_outlier",
                        f"距离本次行程主要地点群 {distance:.1f} 公里",
                        attraction,
                        day_index,
                    )

        invalid_keys = {(issue.day_index, issue.poi_id or issue.name) for issue in issues}
        invalid_count = len(invalid_keys)
        return POIValidationReport(
            is_valid=not issues,
            total=total,
            valid=max(0, total - invalid_count),
            issues=issues,
            warnings=warnings,
        )
