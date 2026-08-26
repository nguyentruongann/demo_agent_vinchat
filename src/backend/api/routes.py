import asyncio
import json
import logging
import re
from queue import Queue
from threading import Event, Thread
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.data_postgre.db.app import AppUser

from ..agents.graph import agent_graph
from ..config import get_settings
from ..models.chat import (
    ChatHistoryMessage,
    ChatRequest,
    ChatResponse,
    ChatSessionHistory,
    ChatSessionSummary,
    SourceItem,
)
from ..services.auth import get_current_user, get_optional_user
from ..services.memory import MemoryService
from ..services.query_parser import load_destination_catalog, normalize_text
from ..services.rate_limit import enforce_rate_limit
from ..services.source_reranker import get_source_reranker

router = APIRouter(prefix="/api/v1", tags=["agent"])
logger = logging.getLogger(__name__)

URL_KEYS = (
    "source_url",
    "canonical_url",
    "page_url",
    "detail_url",
    "booking_url",
    "terms_url",
    "room_page_url",
    "dining_page_url",
    "map_url",
    "target_url",
    "to_url",
    "path",
)

_IMAGE_URL_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".avif")
_BLOCKED_SOURCE_HOST_PARTS = ("booking-static", "static.vinpearl", "cdn.vinpearl")


def _is_displayable_web_url(url: str | None) -> bool:
    """Only show customer-facing web links as sources; hide images/static/context-only rows."""
    raw = str(url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return False
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if not host:
        return False
    if any(part in host for part in _BLOCKED_SOURCE_HOST_PARTS):
        return False
    if path.endswith(_IMAGE_URL_EXTENSIONS):
        return False
    if "/room_types/" in path and any(path.endswith(ext) for ext in _IMAGE_URL_EXTENSIONS):
        return False
    return True


def _phrase_in_text(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    return f" {phrase} " in f" {text} "


def _document_matches_destination_ids(item: dict, destination_ids: set[str]) -> bool:
    if not destination_ids:
        return True

    metadata = item.get("metadata", {}) or {}
    matched_id = str(item.get("matched_destination_id") or "").strip()
    if matched_id and matched_id in destination_ids:
        return True

    metadata_destination = str(metadata.get("destination_id") or "").strip()
    if metadata_destination and metadata_destination in destination_ids:
        return True

    searchable = normalize_text(
        " ".join(
            [
                str(metadata.get("entity_name") or ""),
                str(metadata.get("source_file") or ""),
                str(item.get("text") or ""),
            ]
        )
    )
    catalog = load_destination_catalog()
    for destination_id in destination_ids:
        destination = catalog.get(destination_id) or {}
        aliases = destination.get("normalized_aliases", [])
        if any(_phrase_in_text(searchable, alias) for alias in aliases):
            return True
    return False


def _url_destination_ids(url: str | None) -> set[str]:
    """Return known destinations explicitly encoded in a URL/path."""
    normalized = normalize_text(url or "")
    if not normalized:
        return set()

    found: set[str] = set()
    for destination_id, destination in load_destination_catalog().items():
        for alias in destination.get("normalized_aliases", []):
            # Ignore very short aliases in URLs to reduce accidental matches.
            if len(alias) < 4:
                continue
            if _phrase_in_text(normalized, alias):
                found.add(str(destination_id))
                break
    return found


def _url_conflicts(url: str | None, target_destination_ids: set[str]) -> bool:
    if not url or not target_destination_ids:
        return False
    url_destinations = _url_destination_ids(url)
    # Generic URLs such as /grand-world/ encode no destination and are allowed.
    if not url_destinations:
        return False
    return url_destinations.isdisjoint(target_destination_ids)


def _candidate_urls(item: dict) -> list[str]:
    metadata = item.get("metadata", {}) or {}
    urls: list[str] = []
    for key in URL_KEYS:
        value = str(metadata.get(key) or "").strip()
        if _is_displayable_web_url(value) and value not in urls:
            urls.append(value)

    # Sometimes the row text contains a more specific entity URL than the first
    # metadata URL selected at ingest time. Prefer a non-conflicting URL if found.
    for value in re.findall(r"https?://[^\s<>\]\)\}]+", str(item.get("text") or "")):
        cleaned = value.rstrip(".,;:")
        if _is_displayable_web_url(cleaned) and cleaned not in urls:
            urls.append(cleaned)
    return urls


def _best_source_path(item: dict, target_destination_ids: set[str]) -> str | None:
    candidates = _candidate_urls(item)
    if not candidates:
        return None
    for url in candidates:
        if _is_displayable_web_url(url) and not _url_conflicts(url, target_destination_ids):
            return url
    # Every URL points to a different known destination: suppress the link rather
    # than displaying a misleading citation.
    return None


def _source_item_from_document(
    item: dict,
    target_destination_ids: set[str],
) -> SourceItem:
    metadata = item.get("metadata", {}) or {}
    source_file = (
        metadata.get("entity_name")
        or metadata.get("source_file")
        or metadata.get("entity_type")
        or metadata.get("source_table")
        or "unknown"
    )
    category = (
        metadata.get("entity_type")
        or metadata.get("category")
        or metadata.get("source_table")
    )
    path = item.get("best_source_url") or _best_source_path(item, target_destination_ids)

    return SourceItem(
        source_file=str(source_file),
        category=str(category) if category is not None else None,
        path=path,
        score=item.get("score"),
    )


def _build_sources(state: dict) -> list[SourceItem]:
    destination_ids = {
        str(value)
        for value in state.get("detected_destination_ids", [])
        if str(value).strip()
    }
    retrieved_documents = state.get("retrieved_documents", []) or []
    answer = str(state.get("answer") or "")

    # Citation selection happens AFTER answer generation. The answer may mention
    # only a subset of the retrieved context (e.g. Grand World Hanoi), so showing
    # retrieved_documents[:5] can expose semantically related but misleading URLs.
    # Re-rank sources against the final answer and resolve the best direct URL for
    # each entity actually named in that answer.
    try:
        documents = get_source_reranker().rerank(
            answer=answer,
            retrieved_documents=retrieved_documents,
            destination_ids=destination_ids,
            max_sources=5,
        )
    except Exception as exc:
        print(f"[SOURCE RERANK] fallback because of error: {exc}")
        documents = list(retrieved_documents)

    excluded_destination_ids = {
        normalize_text(str(value or ""))
        for value in state.get("excluded_destination_ids", [])
        if normalize_text(str(value or ""))
    }
    excluded_entity_names = {
        normalize_text(str(value or ""))
        for value in state.get("excluded_entity_names", [])
        if normalize_text(str(value or ""))
    }
    if excluded_destination_ids or excluded_entity_names:
        filtered_documents = []
        for item in documents:
            metadata = item.get("metadata", {}) or {}
            destination_norm = normalize_text(str(metadata.get("destination_id") or ""))
            entity_norm = normalize_text(str(metadata.get("entity_name") or ""))
            if destination_norm and destination_norm in excluded_destination_ids:
                continue
            if entity_norm and entity_norm in excluded_entity_names:
                continue
            filtered_documents.append(item)
        documents = filtered_documents

    # Safety guard: even a reranked source must not contradict the hard
    # destination. If reranking found fewer than five trustworthy sources, return
    # fewer sources instead of padding with unrelated pages.
    if destination_ids:
        documents = [
            item
            for item in documents
            if _document_matches_destination_ids(item, destination_ids)
        ]

    sources: list[SourceItem] = []
    seen_urls: set[str] = set()
    seen_entities: set[str] = set()
    for item in documents:
        source = _source_item_from_document(item, destination_ids)

        # Customer-visible sources must be clickable web pages only. Hide image URLs,
        # static assets, and context-only evidence rows with no URL.
        if not _is_displayable_web_url(source.path):
            continue
        normalized_entity = normalize_text(source.source_file)
        if source.path and source.path in seen_urls:
            continue
        if normalized_entity and normalized_entity in seen_entities:
            continue

        if source.path:
            seen_urls.add(source.path)
        if normalized_entity:
            seen_entities.add(normalized_entity)
        sources.append(source)
        if len(sources) >= 5:
            break

    return sources


def _build_chat_response(state: dict, session_id: str) -> ChatResponse:
    sources = _build_sources(state)
    return ChatResponse(
        answer=state.get("answer", ""),
        session_id=state.get("session_id") or session_id,
        language=state.get("original_language", "unknown"),
        route=state.get("route", "unknown"),
        ticket_id=state.get("ticket_id"),
        sources=sources,
        debug={
            "enough_information": state.get("enough_information"),
            "assessment_reason": state.get("assessment_reason"),
            "best_relevance_score": state.get("best_relevance_score"),
            "retrieved_count": len(state.get("retrieved_documents", [])),
            "source_count": len(sources),
            "sources_without_url": sum(1 for item in sources if not item.path),
            "retrieval_mode": state.get("retrieval_mode"),
            "detected_destinations": state.get("detected_destination_names", []),
            "detected_intent": state.get("detected_intent"),
            "detected_intents": state.get("detected_intents", []),
            "explicit_intents": state.get("explicit_intents", []),
            "intent_origin": state.get("intent_origin", "none"),
            "intent_results": state.get("intent_results", {}),
            "price_requested": state.get("price_requested", False),
            "cost_estimate_requested": state.get("cost_estimate_requested", False),
            "price_data_as_of": state.get("price_data_as_of"),
            "structured_enrichment_count": state.get("structured_enrichment_count", 0),
            "structured_price_document_count": state.get("structured_price_document_count", 0),
            "answer_mode": state.get("answer_mode"),
            "preferred_output_currency": state.get("preferred_output_currency"),
            "price_estimate_destination_ids": state.get("price_estimate_destination_ids", []),
            "request_mode": state.get("request_mode"),
            "resolution_mode": state.get("resolution_mode"),
            "support_triage_reason": state.get("support_triage_reason"),
            "support_triage_confidence": state.get("support_triage_confidence"),
            "recent_destinations": state.get("recent_destination_summary"),
            "safety_action": state.get("safety_action"),
            "safety_category": state.get("safety_category"),
            "safety_reason": state.get("safety_reason"),
            "safety_confidence": state.get("safety_confidence"),
            "logic_action": state.get("logic_action"),
            "logic_category": state.get("logic_category"),
            "logic_reason": state.get("logic_reason"),
            "logic_confidence": state.get("logic_confidence"),
        } if get_settings().expose_chat_debug else None,
    )


def _response_payload(response: ChatResponse) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    return response.dict()


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def _next_customer_stage(node_name: str, state: dict) -> str | None:
    """Map completed graph nodes to the real next customer-visible activity."""
    if node_name in {"guardrail", "language", "load_memory", "understand_request", "resolve_context"}:
        return "understanding"
    if node_name == "classify":
        return "searching" if state.get("route") == "rag" else "composing"
    if node_name == "retrieve":
        return "evaluating"
    if node_name in {"support_triage", "assess"}:
        return "composing"
    if node_name == "answer":
        return "verifying"
    if node_name == "grounding":
        return "finalizing"
    if node_name in {
        "conversation_context",
        "greeting",
        "out_of_scope",
        "invalid_request",
        "sensitive",
        "no_data",
        "ticket",
    }:
        return "finalizing"
    return None


async def _chat_event_stream(
    *,
    payload: ChatRequest,
    session_id: str,
    user_id: str | None,
):
    event_queue: Queue[tuple[str, dict] | object] = Queue()
    completed = object()
    cancelled = Event()
    visible_chunks: list[str] = []

    class StreamCancelled(Exception):
        pass

    def write_token(content: str) -> None:
        if cancelled.is_set():
            raise StreamCancelled("Chat stream was cancelled by the client.")
        visible_chunks.append(content)
        event_queue.put(("delta", {"content": content}))

    def run_graph() -> None:
        state: dict = {
            "user_message": payload.message,
            "session_id": session_id,
            "user_id": user_id,
            "page_context": payload.page_context,
            "stream_writer": write_token,
        }
        last_stage = "understanding"

        try:
            for update in agent_graph.stream(state, stream_mode="updates"):
                if not isinstance(update, dict):
                    continue
                for node_name, node_update in update.items():
                    if isinstance(node_update, dict):
                        state.update(node_update)
                    stage = _next_customer_stage(str(node_name), state)
                    if stage and stage != last_stage and not cancelled.is_set():
                        last_stage = stage
                        event_queue.put(("status", {"stage": stage}))
                if cancelled.is_set():
                    raise StreamCancelled("Chat stream was cancelled by the client.")

            if cancelled.is_set():
                return
            response = _build_chat_response(state, session_id)
            visible_answer = "".join(visible_chunks).strip()
            final_answer = str(response.answer or "").strip()
            if visible_answer and final_answer != visible_answer:
                event_queue.put(("replace", {"content": final_answer}))
            event_queue.put(("complete", _response_payload(response)))
        except StreamCancelled:
            # Client-initiated Stop is expected. Exiting graph iteration before
            # save_memory keeps an interrupted turn from becoming completed history.
            return
        except PermissionError:
            if not cancelled.is_set():
                event_queue.put(("error", {"detail": "Bạn không có quyền truy cập phiên chat này."}))
        except Exception:
            trace_id = uuid4().hex
            logger.exception("chat_stream_failed trace_id=%s", trace_id)
            if not cancelled.is_set():
                event_queue.put((
                    "error",
                    {"detail": f"Internal service error. Reference: {trace_id}"},
                ))
        finally:
            event_queue.put(completed)

    worker = Thread(target=run_graph, name=f"chat-stream-{session_id[-8:]}", daemon=True)
    worker.start()

    try:
        # Send an immediate event so the browser and reverse proxy can expose the
        # live connection before the first graph node finishes.
        yield _sse_event("status", {"stage": "understanding"})
        while True:
            item = await asyncio.to_thread(event_queue.get)
            if item is completed:
                break
            event, data = item
            yield _sse_event(event, data)
            await asyncio.sleep(0)
    finally:
        cancelled.set()


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    http_request: Request,
    current_user: AppUser | None = Depends(get_optional_user),
) -> ChatResponse:
    session_id = payload.session_id or f"SES-{uuid4().hex}"
    user_id = str(current_user.id) if current_user else None
    client_host = http_request.client.host if http_request.client else "unknown"
    enforce_rate_limit(
        bucket="chat",
        identity=user_id or client_host,
        limit=get_settings().chat_rate_limit_per_minute,
        window_seconds=60,
    )

    # Authorize/claim the session before entering LangGraph. This prevents a
    # caller from supplying another user's session UUID and inheriting its memory.
    try:
        MemoryService().ensure_session(session_id, user_id, channel="web")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập phiên chat này.") from exc

    try:
        state = agent_graph.invoke(
            {
                "user_message": payload.message,
                "session_id": session_id,
                "user_id": user_id,
                "page_context": payload.page_context,
            }
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập phiên chat này.") from exc
    except Exception as exc:
        trace_id = uuid4().hex
        logger.exception("chat_failed trace_id=%s", trace_id)
        raise HTTPException(
            status_code=500,
            detail=f"Internal service error. Reference: {trace_id}",
        ) from exc

    return _build_chat_response(state, session_id)


@router.post("/chat/stream", response_class=StreamingResponse)
def chat_stream(
    payload: ChatRequest,
    http_request: Request,
    current_user: AppUser | None = Depends(get_optional_user),
) -> StreamingResponse:
    """Stream real graph progress and the final, grounded answer over SSE."""
    session_id = payload.session_id or f"SES-{uuid4().hex}"
    user_id = str(current_user.id) if current_user else None
    client_host = http_request.client.host if http_request.client else "unknown"
    enforce_rate_limit(
        bucket="chat",
        identity=user_id or client_host,
        limit=get_settings().chat_rate_limit_per_minute,
        window_seconds=60,
    )

    try:
        MemoryService().ensure_session(session_id, user_id, channel="web")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập phiên chat này.") from exc

    return StreamingResponse(
        _chat_event_stream(
            payload=payload,
            session_id=session_id,
            user_id=user_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/sessions", response_model=list[ChatSessionSummary])
def list_chat_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AppUser = Depends(get_current_user),
) -> list[ChatSessionSummary]:
    rows = MemoryService().list_user_sessions(str(current_user.id), limit=limit)
    return [ChatSessionSummary(**row) for row in rows]


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatSessionHistory,
)
def get_chat_session_messages(
    session_id: str,
    current_user: AppUser = Depends(get_current_user),
) -> ChatSessionHistory:
    rows = MemoryService().get_user_session_messages(session_id, str(current_user.id))
    if rows is None:
        # Return 404 for both missing and foreign sessions so account ownership is
        # not leaked to callers probing random session IDs.
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên chat.")
    return ChatSessionHistory(
        session_id=session_id,
        messages=[ChatHistoryMessage(**row) for row in rows],
    )


@router.delete("/chat/{session_id}/history")
def clear_chat_history(
    session_id: str,
    current_user: AppUser = Depends(get_current_user),
) -> dict[str, int | str]:
    deleted = MemoryService().clear_for_user(session_id, str(current_user.id))
    if deleted is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên chat.")
    return {"session_id": session_id, "deleted_turns": deleted}
