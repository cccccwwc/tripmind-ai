"""Direct AMap weather client used by deterministic LangGraph nodes."""

from __future__ import annotations

from datetime import date
from typing import Any

import requests

from ..config import get_settings
from ..models.schemas import WeatherInfo


class AmapWeatherService:
    endpoint = "https://restapi.amap.com/v3/weather/weatherInfo"

    def __init__(self) -> None:
        self.api_key = get_settings().amap_api_key.strip()
        self.session = requests.Session()

    def get_forecast(self, city: str, start_date: str, end_date: str) -> list[WeatherInfo]:
        """Fetch AMap forecast and keep only dates requested by the trip."""
        if not self.api_key or not city.strip():
            raise RuntimeError("AMAP_API_KEY 未配置")
        response = self.session.get(
            self.endpoint,
            params={"key": self.api_key, "city": city.strip(), "extensions": "all"},
            timeout=(6, 15),
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        if payload.get("status") != "1":
            raise RuntimeError(
                f"高德天气 API 返回错误: {payload.get('info') or 'UNKNOWN_ERROR'}"
            )
        forecasts = payload.get("forecasts") or []
        casts = (forecasts[0].get("casts") or []) if forecasts else []
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        result: list[WeatherInfo] = []
        for cast in casts:
            cast_date_text = str(cast.get("date") or "")
            try:
                cast_date = date.fromisoformat(cast_date_text)
            except ValueError:
                continue
            if not start <= cast_date <= end:
                continue
            result.append(WeatherInfo(
                date=cast_date_text,
                day_weather=str(cast.get("dayweather") or ""),
                night_weather=str(cast.get("nightweather") or ""),
                day_temp=cast.get("daytemp") or 0,
                night_temp=cast.get("nighttemp") or 0,
                wind_direction=str(cast.get("daywind") or cast.get("nightwind") or ""),
                wind_power=str(cast.get("daypower") or cast.get("nightpower") or ""),
            ))
        return result
