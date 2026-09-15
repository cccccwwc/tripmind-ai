import json

import pytest

from app.models.schemas import PlanningBrief, PlanningIntakeRequest
from app.services import planning_intake_service as intake_module
from app.services.planning_intake_service import (
    INTAKE_UNAVAILABLE_MESSAGE,
    PlanningIntakeService,
    PlanningIntakeUnavailableError,
)


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def invoke(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        payload = self.payload[min(len(self.calls) - 1, len(self.payload) - 1)] if isinstance(self.payload, list) else self.payload
        return json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload


def test_refine_merges_multiple_turns_and_projects_matching_memory(monkeypatch):
    fake_llm = FakeLLM({
        "assistant_message": "日期也清楚了，请确认右侧简报。",
        "brief": {
            "city": "杭州",
            "start_date": "2026-09-20",
            "end_date": "2026-09-23",
            "transportation": "高铁",
            "accommodation": "舒适型酒店",
            "preferences": ["历史文化", "美食"],
            "free_text_input": "想慢节奏游览"
        }
    })
    monkeypatch.setattr(intake_module, "get_llm", lambda: fake_llm)
    request = PlanningIntakeRequest(
        messages=[
            {"role": "user", "content": "想去杭州，喜欢历史和美食"},
            {"role": "assistant", "content": "什么时候出发和返程？"},
            {"role": "user", "content": "9月20日到23日，坐高铁"},
        ],
        brief=PlanningBrief(city="杭州", preferences=["历史文化", "美食"]),
        travel_memory=[
            {"name": "西湖", "city": "杭州", "category": "景点"},
            {"name": "故宫", "city": "北京", "category": "景点"},
        ],
        carryover_places=["灵隐寺"],
    )

    response = PlanningIntakeService().refine(request)

    assert response.ready_to_confirm is True
    assert response.missing_fields == []
    assert response.brief.travel_days == 4
    assert response.brief.memory_projection.visited_places == ["西湖"]
    assert response.brief.memory_projection.carryover_places == ["灵隐寺"]
    assert len(fake_llm.calls) == 1


def test_refine_keeps_brief_incomplete_when_required_dates_are_missing(monkeypatch):
    fake_llm = FakeLLM({
        "assistant_message": "你计划什么时候出发和返程？",
        "brief": {"city": "成都", "preferences": ["美食"]}
    })
    monkeypatch.setattr(intake_module, "get_llm", lambda: fake_llm)
    request = PlanningIntakeRequest(
        messages=[{"role": "user", "content": "我想去成都吃美食"}],
        brief=PlanningBrief(),
    )

    response = PlanningIntakeService().refine(request)

    assert response.ready_to_confirm is False
    assert response.missing_fields == ["start_date", "end_date"]
    assert response.brief.city == "成都"


def test_extract_json_accepts_markdown_and_surrounding_text():
    result = PlanningIntakeService._extract_json(
        '这里是结果：\n```json\n{"assistant_message":"请补充日期","brief":{"city":"成都"}}\n```'
    )

    assert result["brief"]["city"] == "成都"


def test_refine_retries_an_empty_response_and_preserves_existing_brief(monkeypatch):
    fake_llm = FakeLLM([
        "",
        {
            "assistant_message": "目的地已改为成都，请告诉我具体出发日期。",
            "brief": {"city": "成都"},
        },
    ])
    monkeypatch.setattr(intake_module, "get_llm", lambda: fake_llm)
    request = PlanningIntakeRequest(
        messages=[{"role": "user", "content": "只去成都"}],
        brief=PlanningBrief(
            city="成都、杭州",
            transportation="高铁",
            accommodation="舒适型酒店",
            preferences=["美食"],
        ),
    )

    response = PlanningIntakeService().refine(request)

    assert len(fake_llm.calls) == 2
    assert response.brief.city == "成都"
    assert response.brief.transportation == "高铁"
    assert response.brief.preferences == ["美食"]
    assert response.missing_fields == ["start_date", "end_date"]
    assert "不是完整、合法的 JSON" in fake_llm.calls[1][0][-1]["content"]


def test_refine_hides_parser_details_after_two_invalid_responses(monkeypatch):
    fake_llm = FakeLLM(["", '{"assistant_message": "坏掉的 JSON"'])
    monkeypatch.setattr(intake_module, "get_llm", lambda: fake_llm)
    request = PlanningIntakeRequest(
        messages=[{"role": "user", "content": "只去成都"}],
        brief=PlanningBrief(city="成都、杭州"),
    )

    with pytest.raises(PlanningIntakeUnavailableError) as exc_info:
        PlanningIntakeService().refine(request)

    assert str(exc_info.value) == INTAKE_UNAVAILABLE_MESSAGE
    assert "Expecting" not in str(exc_info.value)
    assert len(fake_llm.calls) == 2


def test_refine_blocks_confirmation_when_spoken_days_conflict_with_dates(monkeypatch):
    fake_llm = FakeLLM({
        "assistant_message": "日期已经记录。",
        "brief": {
            "city": "成都",
            "start_date": "2026-10-01",
            "end_date": "2026-10-09",
        },
    })
    monkeypatch.setattr(intake_module, "get_llm", lambda: fake_llm)
    request = PlanningIntakeRequest(
        messages=[
            {"role": "user", "content": "下个月想去成都玩4天"},
            {"role": "assistant", "content": "哪天出发？"},
            {"role": "user", "content": "10.1-10.9"},
        ],
        brief=PlanningBrief(city="成都", requested_days=4),
    )

    response = PlanningIntakeService().refine(request)

    assert response.brief.requested_days == 4
    assert response.brief.travel_days == 9
    assert response.ready_to_confirm is False
    assert "duration_conflict" in response.missing_fields
    assert "之前计划玩 4 天" in response.assistant_message
    assert "共 9 天" in response.assistant_message


def test_refine_accepts_explicit_duration_conflict_resolution(monkeypatch):
    fake_llm = FakeLLM({
        "assistant_message": "好的，按九天规划。",
        "brief": {},
    })
    monkeypatch.setattr(intake_module, "get_llm", lambda: fake_llm)
    request = PlanningIntakeRequest(
        messages=[{"role": "user", "content": "按九天安排"}],
        brief=PlanningBrief(
            city="成都",
            start_date="2026-10-01",
            end_date="2026-10-09",
            requested_days=4,
        ),
    )

    response = PlanningIntakeService().refine(request)

    assert response.brief.requested_days == 9
    assert response.brief.travel_days == 9
    assert response.ready_to_confirm is True
    assert response.missing_fields == []


def test_refine_projects_only_applicable_approved_long_term_memory(monkeypatch):
    fake_llm = FakeLLM({
        "assistant_message": "请补充日期。",
        "brief": {"city": "成都"},
    })
    monkeypatch.setattr(intake_module, "get_llm", lambda: fake_llm)
    request = PlanningIntakeRequest(
        messages=[{"role": "user", "content": "想去成都"}],
        brief=PlanningBrief(),
        long_term_memory=[
            {
                "id": "m1",
                "kind": "preference",
                "content": "喜欢慢节奏",
                "scope_city": "",
                "source_conversation_id": "archive-1",
                "evidence": "我喜欢慢慢逛",
            },
            {
                "id": "m2",
                "kind": "avoidance",
                "content": "不吃辣",
                "scope_city": "成都",
                "source_conversation_id": "archive-2",
                "evidence": "我不能吃辣",
            },
            {
                "id": "m3",
                "kind": "preference",
                "content": "喜欢西湖边住宿",
                "scope_city": "杭州",
                "source_conversation_id": "archive-3",
                "evidence": "杭州要住西湖边",
            },
        ],
    )

    response = PlanningIntakeService().refine(request)

    assert [item.id for item in response.brief.memory_projection.applied_preferences] == ["m1"]
    assert [item.id for item in response.brief.memory_projection.applied_avoidances] == ["m2"]
