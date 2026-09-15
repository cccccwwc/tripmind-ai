import pytest

from app.services.amap_weather_service import AmapWeatherService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_weather_service_returns_only_requested_dates(monkeypatch):
    service = AmapWeatherService()
    service.api_key = "test-key"
    payload = {
        "status": "1",
        "forecasts": [{
            "casts": [
                {
                    "date": "2026-09-14",
                    "dayweather": "晴",
                    "nightweather": "多云",
                    "daytemp": "28",
                    "nighttemp": "19",
                    "daywind": "东",
                    "daypower": "1-3",
                },
                {
                    "date": "2026-09-15",
                    "dayweather": "小雨",
                    "nightweather": "小雨",
                    "daytemp": "24",
                    "nighttemp": "18",
                    "daywind": "北",
                    "daypower": "3",
                },
            ]
        }],
    }
    monkeypatch.setattr(service.session, "get", lambda *args, **kwargs: FakeResponse(payload))

    result = service.get_forecast("杭州", "2026-09-15", "2026-09-16")

    assert len(result) == 1
    assert result[0].date == "2026-09-15"
    assert result[0].day_weather == "小雨"
    assert result[0].day_temp == 24


def test_weather_service_raises_for_amap_error(monkeypatch):
    service = AmapWeatherService()
    service.api_key = "test-key"
    monkeypatch.setattr(
        service.session,
        "get",
        lambda *args, **kwargs: FakeResponse({"status": "0", "info": "INVALID_USER_KEY"}),
    )

    with pytest.raises(RuntimeError, match="INVALID_USER_KEY"):
        service.get_forecast("杭州", "2026-09-15", "2026-09-16")
