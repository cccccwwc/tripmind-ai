import json

from app.models.schemas import MemoryExtractionRequest, MemoryUpdateRequest
from app.services import long_term_memory_service as memory_module
from app.services.long_term_memory_service import LongTermMemoryService


class FakeLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def invoke(self, messages, **kwargs):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else response


def memory_request():
    return MemoryExtractionRequest(
        user_id="user-1",
        conversation_id="archive-1",
        city="成都",
        messages=[
            {"id": "u1", "role": "user", "content": "我喜欢慢节奏，也不坐红眼航班。"},
            {"id": "a1", "role": "assistant", "content": "已经记下。"},
        ],
    )


def test_extract_archive_approve_edit_and_forget_memory(monkeypatch, tmp_path):
    fake_llm = FakeLLM([{
        "memories": [
            {
                "kind": "preference",
                "content": "偏爱慢节奏旅行",
                "scope_city": "",
                "source_message_ids": ["u1"],
                "evidence": "我喜欢慢节奏",
            },
            {
                "kind": "avoidance",
                "content": "避免红眼航班",
                "scope_city": "",
                "source_message_ids": ["u1", "a1"],
                "evidence": "不坐红眼航班",
            },
        ]
    }])
    monkeypatch.setattr(memory_module, "get_llm", lambda: fake_llm)
    service = LongTermMemoryService(tmp_path / "memory.db")

    conversation_id, records = service.extract_and_store(memory_request())

    assert conversation_id == "archive-1"
    assert len(records) == 2
    assert all(item.status == "pending" for item in records)
    assert records[1].source_message_ids == ["u1"]

    archive = service.get_archived_conversation("archive-1", "user-1")
    assert archive is not None
    assert [item.content for item in archive.messages] == [
        "我喜欢慢节奏，也不坐红眼航班。",
        "已经记下。",
    ]

    approved = service.update_memory(
        records[0].id,
        MemoryUpdateRequest(
            user_id="user-1",
            content="每天最多安排两个主要景点",
            status="approved",
        ),
    )
    assert approved is not None
    assert approved.status == "approved"
    assert approved.content == "每天最多安排两个主要景点"
    assert [item.id for item in service.list_memories("user-1", "approved")] == [records[0].id]

    assert service.forget_memory(records[0].id, "user-1") is True
    assert service.get_memory(records[0].id, "user-1") is None


def test_memory_extraction_retries_invalid_json(monkeypatch, tmp_path):
    fake_llm = FakeLLM([
        "",
        {"memories": []},
    ])
    monkeypatch.setattr(memory_module, "get_llm", lambda: fake_llm)
    service = LongTermMemoryService(tmp_path / "memory.db")

    _, records = service.extract_and_store(memory_request())

    assert records == []
    assert fake_llm.calls == 2


def test_negative_evidence_cannot_be_saved_as_positive_preference():
    kind, content = LongTermMemoryService._protect_preference_polarity(
        "preference",
        "喜欢烧烤",
        "我不喜欢烧烤",
    )

    assert kind == "avoidance"
    assert content == "我不喜欢烧烤"
