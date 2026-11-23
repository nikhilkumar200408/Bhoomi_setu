"""Persistent, ownership-scoped RAG chat sessions for TrustLens AI."""
import re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import models
from ..database import chat_sessions_collection
from ..deps import get_current_user
from ..services.docai.errors import DocAIError
from .document_ai import AskRequest, ask

router = APIRouter(prefix="/api/chat", tags=["rag-chat"])
MAX_MESSAGES = 80


class ChatMessageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: List[str] = Field(min_length=1, max_length=100)
    language: Literal["en", "hi"] = "en"
    session_id: Optional[str] = Field(default=None, max_length=80)
    include_superseded_documents: bool = True


def _follow_up_context(question: str, messages: list) -> str:
    """Keep follow-up retrieval focused on the current question.

    Conversation history remains persisted; previous question wording is not
    injected into BM25 because unrelated terms can suppress relevant passages.
    """
    current = question.strip()
    if not messages:
        return current

    starts_with_reference = bool(re.match(
        r"^(and|what about|how about|why|when|where|which one|iska|iski|iske|uska|uski|aur|phir|then|it|that|those|they)\b",
        current, re.IGNORECASE
    ))
    if not starts_with_reference:
        return current

    cleaned = re.sub(
        r"^(?:and|what about|how about|which one|why|when|where|iska|iski|iske|uska|uski|aur|phir|then|it|that|those|they)\b\s*",
        "",
        current,
        flags=re.IGNORECASE,
    ).strip()

    return cleaned or current


@router.get("/sessions")
async def list_chat_sessions(limit: int = Query(default=30, ge=1, le=100),
                             user: dict = Depends(get_current_user)):
    cursor = chat_sessions_collection.find(
        {"user_id": user["_id"]},
        {"messages": 0, "user_id": 0},
    ).sort("updated_at", -1).limit(limit)
    items = []
    async for session in cursor:
        last = (session.get("messages") or [{}])[-1]
        items.append({
            "id": session["_id"],
            "title": session.get("title", "New conversation"),
            "document_ids": session.get("document_ids", []),
            "updated_at": session.get("updated_at"),
            "message_count": session.get("message_count", 0),
            "preview": session.get("last_message_preview", ""),
        })
    return {"items": items}


@router.get("/sessions/{session_id}")
async def get_chat_session(session_id: str, user: dict = Depends(get_current_user)):
    session = await chat_sessions_collection.find_one({"_id": session_id, "user_id": user["_id"]})
    if not session:
        raise DocAIError(404, "RESOURCE_NOT_FOUND", "The requested chat session was not found.")
    return {
        "id": session["_id"],
        "title": session.get("title", "New conversation"),
        "document_ids": session.get("document_ids", []),
        "messages": session.get("messages", []),
        "updated_at": session.get("updated_at"),
    }


@router.post("/messages")
async def send_chat_message(payload: ChatMessageRequest, user: dict = Depends(get_current_user)):
    question = payload.question.strip()
    if not question:
        raise DocAIError(400, "INVALID_REQUEST", "Question cannot be empty.")

    session = None
    if payload.session_id:
        session = await chat_sessions_collection.find_one(
            {"_id": payload.session_id, "user_id": user["_id"]}
        )
        if not session:
            raise DocAIError(404, "RESOURCE_NOT_FOUND", "The requested chat session was not found.")

    prior_messages = (session or {}).get("messages", [])[-12:]
    retrieval_question = _follow_up_context(question, prior_messages)

    # Reuse the existing evidence-first QA pipeline; chat does not introduce a
    # second retrieval or verification implementation.
    answer = await ask(
        AskRequest(
            question=retrieval_question,
            document_ids=payload.document_ids,
            language=payload.language,
            include_superseded_documents=payload.include_superseded_documents,
        ),
        user,
    )
    answer["question"] = question
    answer["contextual_follow_up"] = retrieval_question != question

    now = models.utcnow()
    session_id = session["_id"] if session else "chat_" + models.gen_uuid()[:16]
    user_message = {
        "id": "msg_" + models.gen_uuid()[:12], "role": "user",
        "content": question, "created_at": now.isoformat() + "Z",
    }
    assistant_message = {
        "id": "msg_" + models.gen_uuid()[:12], "role": "assistant",
        "content": answer.get("answer", ""), "answer": answer,
        "created_at": now.isoformat() + "Z",
    }

    if session:
        await chat_sessions_collection.update_one(
            {"_id": session_id, "user_id": user["_id"]},
            {"$push": {"messages": {"$each": [user_message, assistant_message], "$slice": -MAX_MESSAGES}},
             "$set": {"updated_at": now, "document_ids": payload.document_ids,
                      "last_message_preview": question[:140]},
             "$inc": {"message_count": 2}},
        )
    else:
        await chat_sessions_collection.insert_one({
            "_id": session_id, "user_id": user["_id"],
            "title": question[:72] + ("…" if len(question) > 72 else ""),
            "document_ids": payload.document_ids,
            "messages": [user_message, assistant_message],
            "message_count": 2, "last_message_preview": question[:140],
            "created_at": now, "updated_at": now,
        })

    return {"session_id": session_id, "user_message": user_message,
            "assistant_message": assistant_message, "answer": answer}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_chat_session(session_id: str, user: dict = Depends(get_current_user)):
    result = await chat_sessions_collection.delete_one({"_id": session_id, "user_id": user["_id"]})
    if not result.deleted_count:
        raise DocAIError(404, "RESOURCE_NOT_FOUND", "The requested chat session was not found.")
    return None
