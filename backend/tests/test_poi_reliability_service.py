from app.models.schemas import Attraction, DayPlan, Location, TripPlan
from app.services.poi_location_service import ResolvedPOI
from app.services.poi_reliability_service import POIReliabilityService


def attraction(
    name: str,
    poi_id: str,
    longitude: float,
    latitude: float,
    *,
    city: str = "开封市",
    status: str = "available",
    confidence: float = 1.0,
) -> Attraction:
    return Attraction(
        name=name,
        address="开封市龙亭区",
        location=Location(longitude=longitude, latitude=latitude),
        visit_duration=120,
        description="测试景点",
        poi_id=poi_id,
        city=city,
        district="龙亭区",
        operational_status=status,
        data_source="amap",
        verified_at="2026-09-14T00:00:00+00:00",
        verification_confidence=confidence,
    )


def plan_with(attractions: list[Attraction]) -> TripPlan:
    return TripPlan(
        city="开封",
        start_date="2026-09-14",
        end_date="2026-09-14",
        days=[DayPlan(
            date="2026-09-14",
            day_index=0,
            description="测试",
            transportation="公共交通",
            accommodation="舒适型酒店",
            attractions=attractions,
        )],
        overall_suggestions="测试",
    )


def test_plan_validation_accepts_complete_amap_metadata():
    report = POIReliabilityService().validate_plan(plan_with([
        attraction("清明上河园", "a1", 114.340685, 34.809044),
        attraction("龙亭景区", "a2", 114.35113, 34.811187),
    ]), "开封")

    assert report.is_valid
    assert report.valid == 2
    assert report.issues == []


def test_plan_validation_rejects_wrong_city_closed_and_spatial_outlier():
    report = POIReliabilityService().validate_plan(plan_with([
        attraction("清明上河园", "a1", 114.340685, 34.809044),
        attraction("关闭景点", "a2", 114.35113, 34.811187, status="unavailable"),
        attraction("外地同名景点", "a3", 121.47, 31.23, city="上海市"),
    ]), "开封")

    codes = {issue.code for issue in report.issues}
    assert not report.is_valid
    assert "unavailable" in codes
    assert "wrong_city" in codes
    assert "spatial_outlier" in codes
    assert "day_route_too_far" in codes


def test_category_candidates_drop_spatial_outliers():
    service = POIReliabilityService()
    pois = [
        ResolvedPOI("a1", "A", "开封", 114.34, 34.80, 1),
        ResolvedPOI("a2", "B", "开封", 114.35, 34.81, 1),
        ResolvedPOI("a3", "C", "上海", 121.47, 31.23, 1),
    ]

    assert [item.poi_id for item in service.filter_spatial_outliers(pois)] == ["a1", "a2"]
