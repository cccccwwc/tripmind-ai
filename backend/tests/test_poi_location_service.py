from app.services.poi_location_service import POILocationService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_resolve_selects_best_name_match_in_requested_city(monkeypatch):
    service = POILocationService()
    service.api_key = "test-key"
    payload = {
        "status": "1",
        "pois": [
            {
                "id": "wrong-first",
                "name": "龙亭便利店",
                "address": "龙亭区体育路",
                "pname": "河南省",
                "cityname": "开封市",
                "adname": "龙亭区",
                "location": "114.300000,34.800000",
            },
            {
                "id": "right-poi",
                "name": "龙亭景区",
                "address": "龙亭北路",
                "pname": "河南省",
                "cityname": "开封市",
                "adname": "龙亭区",
                "location": "114.351130,34.811187",
            },
        ],
    }
    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: FakeResponse(payload))

    result = service.resolve("龙亭公园", "开封", "开封市龙亭区")

    assert result is not None
    assert result.poi_id == "right-poi"
    assert result.name == "龙亭景区"
    assert result.longitude == 114.35113
    assert result.latitude == 34.811187
    assert result.confidence >= 0.72
    assert result.city == "开封市"
    assert result.district == "龙亭区"
    assert result.operational_status == "unknown"
    assert result.data_source == "amap"
    assert result.verified_at


def test_resolve_rejects_same_name_from_another_city(monkeypatch):
    service = POILocationService()
    service.api_key = "test-key"
    payload = {
        "status": "1",
        "pois": [{
            "id": "other-city",
            "name": "人民公园",
            "address": "南京西路",
            "pname": "上海市",
            "cityname": "上海市",
            "adname": "黄浦区",
            "location": "121.470000,31.230000",
        }],
    }
    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: FakeResponse(payload))

    assert service.resolve("人民公园", "开封") is None


def test_resolve_rejects_low_confidence_result(monkeypatch):
    service = POILocationService()
    service.api_key = "test-key"
    payload = {
        "status": "1",
        "pois": [{
            "id": "unrelated",
            "name": "火车站便利店",
            "address": "开封市鼓楼区",
            "pname": "河南省",
            "cityname": "开封市",
            "adname": "鼓楼区",
            "location": "114.300000,34.790000",
        }],
    }
    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: FakeResponse(payload))

    assert service.resolve("清明上河园", "开封") is None


def test_search_returns_only_city_restricted_pois_with_coordinates(monkeypatch):
    service = POILocationService()
    service.api_key = "test-key"
    payload = {
        "status": "1",
        "pois": [
            {
                "id": "kaifeng-poi",
                "name": "清明上河园",
                "address": "龙亭西路",
                "pname": "河南省",
                "cityname": "开封市",
                "adname": "龙亭区",
                "location": "114.340685,34.809044",
            },
            {
                "id": "other-city",
                "name": "外地景点",
                "address": "上海市黄浦区",
                "pname": "上海市",
                "cityname": "上海市",
                "adname": "黄浦区",
                "location": "121.470000,31.230000",
            },
            {
                "id": "missing-location",
                "name": "无坐标景点",
                "address": "开封市",
                "cityname": "开封市",
                "location": "",
            },
        ],
    }
    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: FakeResponse(payload))

    results = service.search("旅游景点", "开封", 20)

    assert len(results) == 1
    assert results[0].name == "清明上河园"
    assert results[0].longitude == 114.340685


def test_search_rejects_places_marked_unavailable(monkeypatch):
    service = POILocationService()
    service.api_key = "test-key"
    payload = {
        "status": "1",
        "pois": [
            {
                "id": "closed-island",
                "name": "渔山列岛(不对外开放)",
                "address": "宁波市象山县",
                "pname": "浙江省",
                "cityname": "宁波市",
                "adname": "象山县",
                "location": "122.266000,28.884000",
            },
            {
                "id": "open-museum",
                "name": "宁波博物院",
                "address": "首南中路1000号",
                "pname": "浙江省",
                "cityname": "宁波市",
                "adname": "鄞州区",
                "location": "121.545000,29.807000",
            },
        ],
    }
    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: FakeResponse(payload))

    results = service.search("旅游景点", "宁波", 20)

    assert [item.name for item in results] == ["宁波博物院"]
