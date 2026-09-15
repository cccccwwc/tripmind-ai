"""User-approved long-term travel memory API."""

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from ...models.schemas import (
    ArchivedConversationResponse,
    LongTermMemoryRecord,
    MemoryExtractionRequest,
    MemoryExtractionResponse,
    MemoryListResponse,
    MemoryUpdateRequest,
)
from ...services.long_term_memory_service import get_long_term_memory_service


router = APIRouter(prefix="/memory", tags=["长期旅行记忆"])


@router.post("/extract", response_model=MemoryExtractionResponse)
async def extract_memories(request: MemoryExtractionRequest) -> MemoryExtractionResponse:
    try:
        conversation_id, memories = await run_in_threadpool(
            get_long_term_memory_service().extract_and_store,
            request,
        )
        return MemoryExtractionResponse(conversation_id=conversation_id, memories=memories)
    except Exception as exc:
        print(f"❌ 长期记忆提取失败: {exc}")
        raise HTTPException(status_code=502, detail="长期记忆提取暂时失败，请稍后重试") from exc


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    user_id: str = Query(default="local-user", min_length=1, max_length=80),
    status: str = Query(default=""),
) -> MemoryListResponse:
    memories = await run_in_threadpool(
        get_long_term_memory_service().list_memories,
        user_id,
        status,
    )
    return MemoryListResponse(memories=memories)


@router.get("/conversations/{conversation_id}", response_model=ArchivedConversationResponse)
async def get_archived_conversation(
    conversation_id: str,
    user_id: str = Query(default="local-user", min_length=1, max_length=80),
) -> ArchivedConversationResponse:
    conversation = await run_in_threadpool(
        get_long_term_memory_service().get_archived_conversation,
        conversation_id,
        user_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="没有找到归档对话")
    return conversation


@router.patch("/{memory_id}", response_model=LongTermMemoryRecord)
async def update_memory(memory_id: str, update: MemoryUpdateRequest) -> LongTermMemoryRecord:
    try:
        memory = await run_in_threadpool(
            get_long_term_memory_service().update_memory,
            memory_id,
            update,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code=404, detail="没有找到这条旅行记忆")
    return memory


@router.delete("/{memory_id}")
async def forget_memory(
    memory_id: str,
    user_id: str = Query(default="local-user", min_length=1, max_length=80),
) -> dict[str, bool]:
    deleted = await run_in_threadpool(
        get_long_term_memory_service().forget_memory,
        memory_id,
        user_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="没有找到这条旅行记忆")
    return {"success": True}
