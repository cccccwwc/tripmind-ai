"""Traceable, user-controlled long-term travel memory."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..models.schemas import (
    ArchivedConversationMessage,
    ArchivedConversationResponse,
    LongTermMemoryRecord,
    MemoryExtractionRequest,
    MemoryUpdateRequest,
)
from .llm_service import get_llm


MEMORY_EXTRACTION_PROMPT = """你是 TripMind 的长期旅行记忆提取器。请只从 user 消息中提取用户明确表达、未来旅行仍可能有用的稳定偏好和避雷项。

可以提取：喜欢博物馆、偏爱慢节奏、避免红眼航班、不能吃辣、讨厌频繁换酒店。
不要提取：本次目的地、具体日期、一次性预算、助手的推测、敏感身份信息。
每条必须能追溯到原消息，evidence 使用用户原话的简短片段，source_message_ids 只能使用输入中存在的 id。
kind 只能是 preference 或 avoidance。scope_city 仅在偏好明确局限于某城市时填写，否则为空字符串。

只返回 JSON：
{"memories":[{"kind":"preference","content":"偏爱历史文化景点","scope_city":"","source_message_ids":["1"],"evidence":"我喜欢历史文化"}]}
没有值得长期保存的信息时返回 {"memories":[]}。
"""


class LongTermMemoryService:
    def __init__(self, db_path: str | Path | None = None):
        configured = db_path or os.getenv("TRAVEL_MEMORY_DB_PATH")
        self.db_path = Path(configured) if configured else Path(__file__).resolve().parents[2] / "data" / "travel_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS travel_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('preference', 'avoidance')),
                    content TEXT NOT NULL,
                    scope_city TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved')),
                    source_conversation_id TEXT NOT NULL,
                    source_message_ids TEXT NOT NULL DEFAULT '[]',
                    evidence TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_travel_memories_user_status ON travel_memories(user_id, status)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS archived_conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    city TEXT NOT NULL DEFAULT '',
                    archived_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS archived_messages (
                    conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (conversation_id, message_id),
                    FOREIGN KEY (conversation_id) REFERENCES archived_conversations(id) ON DELETE CASCADE
                )
                """
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> LongTermMemoryRecord:
        data = dict(row)
        try:
            data["source_message_ids"] = json.loads(data["source_message_ids"])
        except (json.JSONDecodeError, TypeError):
            data["source_message_ids"] = []
        return LongTermMemoryRecord(**data)

    @staticmethod
    def _extract_json(text: str | None) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("模型返回空内容")
        cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "").strip()
        decoder = json.JSONDecoder()
        last_error: Exception | None = None
        for match in re.finditer(r"\{", cleaned):
            try:
                data, _ = decoder.raw_decode(cleaned[match.start():])
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
            if isinstance(data, dict) and isinstance(data.get("memories"), list):
                return data
        raise ValueError("记忆提取 Agent 未返回有效 JSON") from last_error

    @staticmethod
    def _protect_preference_polarity(kind: str, content: str, evidence: str) -> tuple[str, str]:
        """Do not allow an extractor to turn an explicit rejection into a positive preference."""
        negative_pattern = re.compile(
            r"不喜欢|不要|不想|不愿|避免|避开|讨厌|不能|不吃|拒绝|别去|不去|不坐"
        )
        if not negative_pattern.search(evidence):
            return kind, content

        kind = "avoidance"
        if not negative_pattern.search(content):
            # Evidence is user-authored and therefore safer than a polarity-flipped summary.
            content = evidence.strip(" \t\n\r‘’“”\"'，。！？!?；;")
        return kind, content[:240]

    def _invoke_extractor(self, request: MemoryExtractionRequest) -> dict[str, Any]:
        transcript = "\n".join(
            f"[{message.id}] {message.role}: {message.content}" for message in request.messages
        )
        prompt = f"对话城市上下文：{request.city or '未指定'}\n已归档对话：\n{transcript}"
        llm = get_llm()
        invalid = ""
        last_error: Exception | None = None
        for attempt in range(2):
            raw: str | None = None
            messages = [
                {"role": "system", "content": MEMORY_EXTRACTION_PROMPT},
                {"role": "user", "content": prompt},
            ]
            if attempt:
                messages.extend([
                    {"role": "assistant", "content": invalid[:3000]},
                    {"role": "user", "content": "上一条不是合法 JSON。只重新输出完整 JSON 对象。"},
                ])
            try:
                raw = llm.invoke(messages, temperature=0, max_tokens=1200)
                return self._extract_json(raw)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                invalid = raw if isinstance(raw, str) else ""
                last_error = exc
        raise RuntimeError("长期记忆提取暂时失败，请稍后重试") from last_error

    def extract_and_store(self, request: MemoryExtractionRequest) -> tuple[str, list[LongTermMemoryRecord]]:
        conversation_id = request.conversation_id.strip() or f"conversation-{uuid4().hex}"
        self._archive_conversation(conversation_id, request)
        parsed = self._invoke_extractor(request)
        valid_message_ids = {message.id for message in request.messages if message.role == "user"}
        now = datetime.now(timezone.utc).isoformat()
        created: list[LongTermMemoryRecord] = []

        with self._connect() as connection:
            for candidate in parsed.get("memories", [])[:10]:
                if not isinstance(candidate, dict):
                    continue
                kind = str(candidate.get("kind") or "").strip()
                content = str(candidate.get("content") or "").strip()[:240]
                scope_city = str(candidate.get("scope_city") or "").strip()[:50]
                evidence = str(candidate.get("evidence") or "").strip()[:500]
                kind, content = self._protect_preference_polarity(kind, content, evidence)
                source_ids = [
                    str(item) for item in candidate.get("source_message_ids", [])
                    if str(item) in valid_message_ids
                ]
                if kind not in {"preference", "avoidance"} or not content or not source_ids or not evidence:
                    continue

                duplicate = connection.execute(
                    """SELECT * FROM travel_memories
                       WHERE user_id = ? AND kind = ? AND lower(content) = lower(?) AND lower(scope_city) = lower(?)
                       LIMIT 1""",
                    (request.user_id, kind, content, scope_city),
                ).fetchone()
                if duplicate:
                    created.append(self._row_to_record(duplicate))
                    continue

                record = LongTermMemoryRecord(
                    id=f"memory-{uuid4().hex}",
                    user_id=request.user_id,
                    kind=kind,
                    content=content,
                    scope_city=scope_city,
                    status="pending",
                    source_conversation_id=conversation_id,
                    source_message_ids=source_ids,
                    evidence=evidence,
                    created_at=now,
                    updated_at=now,
                )
                connection.execute(
                    """INSERT INTO travel_memories
                       (id, user_id, kind, content, scope_city, status, source_conversation_id,
                        source_message_ids, evidence, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.id, record.user_id, record.kind, record.content, record.scope_city,
                        record.status, record.source_conversation_id,
                        json.dumps(record.source_message_ids, ensure_ascii=False), record.evidence,
                        record.created_at, record.updated_at,
                    ),
                )
                created.append(record)
        return conversation_id, created

    def _archive_conversation(self, conversation_id: str, request: MemoryExtractionRequest) -> None:
        archived_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO archived_conversations (id, user_id, city, archived_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET city = excluded.city""",
                (conversation_id, request.user_id, request.city, archived_at),
            )
            for position, message in enumerate(request.messages):
                connection.execute(
                    """INSERT INTO archived_messages
                       (conversation_id, message_id, role, content, position)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(conversation_id, message_id) DO UPDATE SET
                           role = excluded.role,
                           content = excluded.content,
                           position = excluded.position""",
                    (conversation_id, message.id, message.role, message.content, position),
                )

    def get_archived_conversation(
        self,
        conversation_id: str,
        user_id: str,
    ) -> ArchivedConversationResponse | None:
        with self._connect() as connection:
            conversation = connection.execute(
                "SELECT * FROM archived_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if not conversation:
                return None
            messages = connection.execute(
                """SELECT message_id, role, content FROM archived_messages
                   WHERE conversation_id = ? ORDER BY position""",
                (conversation_id,),
            ).fetchall()
        return ArchivedConversationResponse(
            conversation_id=conversation["id"],
            user_id=conversation["user_id"],
            city=conversation["city"],
            archived_at=conversation["archived_at"],
            messages=[
                ArchivedConversationMessage(
                    id=row["message_id"], role=row["role"], content=row["content"]
                )
                for row in messages
            ],
        )

    def list_memories(self, user_id: str, status: str = "") -> list[LongTermMemoryRecord]:
        query = "SELECT * FROM travel_memories WHERE user_id = ?"
        params: list[str] = [user_id]
        if status in {"pending", "approved"}:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, updated_at DESC"
        with self._connect() as connection:
            return [self._row_to_record(row) for row in connection.execute(query, params).fetchall()]

    def update_memory(self, memory_id: str, update: MemoryUpdateRequest) -> LongTermMemoryRecord | None:
        fields: list[str] = []
        values: list[str] = []
        for name in ("content", "scope_city", "status"):
            value = getattr(update, name)
            if value is not None:
                if name == "content" and not value.strip():
                    raise ValueError("记忆内容不能为空")
                fields.append(f"{name} = ?")
                values.append(value.strip() if isinstance(value, str) else value)
        if not fields:
            return self.get_memory(memory_id, update.user_id)
        fields.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.extend([memory_id, update.user_id])
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE travel_memories SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                values,
            )
            if not cursor.rowcount:
                return None
        return self.get_memory(memory_id, update.user_id)

    def get_memory(self, memory_id: str, user_id: str) -> LongTermMemoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM travel_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def forget_memory(self, memory_id: str, user_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM travel_memories WHERE id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            return bool(cursor.rowcount)


_service: LongTermMemoryService | None = None


def get_long_term_memory_service() -> LongTermMemoryService:
    global _service
    if _service is None:
        _service = LongTermMemoryService()
    return _service
