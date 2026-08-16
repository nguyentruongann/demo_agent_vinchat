from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select

from src.backend.config import get_settings
from src.backend.services.db import open_session
from src.backend.services.query_parser import normalize_text
from src.data_postgre.db.app import AppUser, ChatSession, EventLog, Message


class MemoryService:
    """Persistent conversation memory backed by PostgreSQL.

    Raw chat content is stored in ``app.message`` and conversation metadata is
    stored in ``app.session``. Small structured turn metadata (destination IDs,
    intents, support mode) is written to ``app.event_log`` without duplicating
    the raw user/assistant content.

    ``load_recent()`` keeps the legacy turn-shaped return value expected by the
    LangGraph nodes, so the rest of the agent does not need to change.
    """

    _DB_ROUTES = {"greeting", "out_of_scope", "rag"}
    _META_EVENT = "chat_turn_metadata"

    def __init__(self) -> None:
        settings = get_settings()
        self.max_turns = settings.memory_max_turns
        self.max_chars = settings.memory_max_chars
        self.enabled = settings.memory_enabled
        self.model_name = settings.llm_model

    @staticmethod
    def _parse_user_id(value: str | None) -> UUID | None:
        if not value:
            return None
        try:
            return UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def _clip(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    @staticmethod
    def _check_session_access(
        chat_session: ChatSession,
        parsed_user_id: UUID | None,
    ) -> None:
        """Reject cross-account access to an owned conversation.

        Anonymous sessions intentionally have ``user_id = NULL`` and are only
        protected by their high-entropy client-generated session ID. Once a
        session belongs to an authenticated account, anonymous callers and other
        users must never be able to load or append to it.
        """
        if chat_session.user_id is None:
            return
        if parsed_user_id is None or chat_session.user_id != parsed_user_id:
            raise PermissionError("Chat session does not belong to the current user.")

    def ensure_session(
        self,
        session_id: str | None,
        user_id: str | None = None,
        *,
        channel: str = "web",
    ) -> None:
        """Create/claim the conversation row before the graph runs.

        A previously anonymous session may be claimed by the user who logs in.
        An already-owned session can only be reused by that same user.
        """
        if not self.enabled or not session_id:
            return

        parsed_user_id = self._parse_user_id(user_id)
        now = datetime.now(timezone.utc)

        with open_session() as db:
            if parsed_user_id is not None and db.get(AppUser, parsed_user_id) is None:
                parsed_user_id = None

            chat_session = db.get(ChatSession, session_id)
            if chat_session is None:
                db.add(
                    ChatSession(
                        id=session_id,
                        user_id=parsed_user_id,
                        channel=channel if channel in {"web", "api"} else "web",
                        last_activity_at=now,
                    )
                )
                db.commit()
                return

            self._check_session_access(chat_session, parsed_user_id)
            if parsed_user_id is not None and chat_session.user_id is None:
                chat_session.user_id = parsed_user_id
            chat_session.last_activity_at = now
            db.commit()

    def load_recent(
        self,
        session_id: str | None,
        limit: int | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.enabled or not session_id:
            return []

        keep = max(1, limit if limit is not None else self.max_turns)
        parsed_user_id = self._parse_user_id(user_id)

        with open_session() as db:
            chat_session = db.get(ChatSession, session_id)
            if chat_session is None:
                return []
            self._check_session_access(chat_session, parsed_user_id)

            # Two messages are normally stored per turn. Read a small cushion so
            # legacy/system rows do not accidentally remove the oldest wanted turn.
            rows = list(
                db.scalars(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.seq.desc())
                    .limit(keep * 2 + 8)
                ).all()
            )
            rows.reverse()

            # Structured metadata is deliberately separated from raw message text.
            metadata_by_assistant_seq: dict[int, dict[str, Any]] = {}
            events = db.scalars(
                select(EventLog)
                .where(
                    EventLog.session_id == session_id,
                    EventLog.event_type == self._META_EVENT,
                )
                .order_by(EventLog.id.desc())
                .limit(keep + 8)
            ).all()
            for event in events:
                payload = dict(event.payload or {})
                try:
                    assistant_seq = int(payload.get("assistant_seq"))
                except (TypeError, ValueError):
                    continue
                metadata_by_assistant_seq.setdefault(assistant_seq, payload)

        turns: list[dict[str, Any]] = []
        pending_user: Message | None = None

        for row in rows:
            if row.role == "user":
                pending_user = row
                continue

            if row.role != "assistant":
                continue

            user_message = pending_user.content if pending_user is not None else ""
            turn_user_id = (
                str(pending_user.user_id)
                if pending_user is not None and pending_user.user_id
                else (str(row.user_id) if row.user_id else None)
            )
            metadata = metadata_by_assistant_seq.get(row.seq, {})

            turns.append(
                {
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "session_id": session_id,
                    "user_id": turn_user_id,
                    "user_message": user_message,
                    "assistant_answer": row.content,
                    "language": row.language
                    or (pending_user.language if pending_user is not None else None)
                    or "unknown",
                    "route": row.route or metadata.get("route") or "unknown",
                    "rag_query": metadata.get("rag_query"),
                    "ticket_id": metadata.get("ticket_id"),
                    "detected_destinations": metadata.get("detected_destinations") or [],
                    "resolved_destinations": metadata.get("resolved_destinations") or [],
                    "focus_entities": metadata.get("focus_entities") or [],
                    "context_uses_memory": bool(metadata.get("context_uses_memory", False)),
                    "context_resolution_reason": metadata.get("context_resolution_reason"),
                    "context_resolution_confidence": metadata.get("context_resolution_confidence"),
                    "context_resolution_source": metadata.get("context_resolution_source"),
                    "detected_intent": metadata.get("detected_intent"),
                    "detected_intents": metadata.get("detected_intents") or [],
                    "request_mode": metadata.get("request_mode"),
                    "resolution_mode": metadata.get("resolution_mode"),
                }
            )
            pending_user = None

        return turns[-keep:]

    def list_user_sessions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent conversations owned by one authenticated user."""
        parsed_user_id = self._parse_user_id(user_id)
        if parsed_user_id is None:
            return []

        safe_limit = max(1, min(int(limit), 100))

        first_user_message = (
            select(Message.content)
            .where(
                Message.session_id == ChatSession.id,
                Message.role == "user",
            )
            .order_by(Message.seq.asc())
            .limit(1)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        message_count = (
            select(func.count(Message.id))
            .where(Message.session_id == ChatSession.id)
            .correlate(ChatSession)
            .scalar_subquery()
        )

        with open_session() as db:
            rows = db.execute(
                select(
                    ChatSession.id,
                    ChatSession.language,
                    ChatSession.started_at,
                    ChatSession.last_activity_at,
                    first_user_message.label("first_user_message"),
                    message_count.label("message_count"),
                )
                .where(ChatSession.user_id == parsed_user_id)
                .order_by(
                    func.coalesce(
                        ChatSession.last_activity_at,
                        ChatSession.started_at,
                    ).desc()
                )
                .limit(safe_limit)
            ).all()

        sessions: list[dict[str, Any]] = []
        for row in rows:
            title = self._clip(row.first_user_message or "New conversation", 72)
            # Do not show empty sessions created by a failed request in the history list.
            if int(row.message_count or 0) <= 0:
                continue
            sessions.append(
                {
                    "id": row.id,
                    "title": title or "New conversation",
                    "language": row.language,
                    "started_at": row.started_at,
                    "last_activity_at": row.last_activity_at,
                    "message_count": int(row.message_count or 0),
                }
            )
        return sessions

    def get_user_session_messages(
        self,
        session_id: str,
        user_id: str,
    ) -> list[dict[str, Any]] | None:
        """Return one owned conversation; ``None`` hides missing/foreign sessions."""
        parsed_user_id = self._parse_user_id(user_id)
        if parsed_user_id is None:
            return None

        with open_session() as db:
            chat_session = db.get(ChatSession, session_id)
            if chat_session is None or chat_session.user_id != parsed_user_id:
                return None

            rows = db.scalars(
                select(Message)
                .where(
                    Message.session_id == session_id,
                    Message.role.in_(("user", "assistant")),
                )
                .order_by(Message.seq.asc())
            ).all()

            metadata_by_assistant_seq: dict[int, dict[str, Any]] = {}
            events = db.scalars(
                select(EventLog)
                .where(
                    EventLog.session_id == session_id,
                    EventLog.event_type == self._META_EVENT,
                )
                .order_by(EventLog.id.desc())
            ).all()
            for event in events:
                payload = dict(event.payload or {})
                try:
                    assistant_seq = int(payload.get("assistant_seq"))
                except (TypeError, ValueError):
                    continue
                metadata_by_assistant_seq.setdefault(assistant_seq, payload)

            return [
                {
                    "id": str(row.id),
                    "seq": row.seq,
                    "role": row.role,
                    "content": row.content,
                    "language": row.language,
                    "route": row.route,
                    "ticket_id": (
                        metadata_by_assistant_seq.get(row.seq, {}).get("ticket_id")
                        if row.role == "assistant"
                        else None
                    ),
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def format_for_prompt(self, turns: list[dict[str, Any]]) -> str:
        """Build a compact recent history without dropping memory on long turns."""
        if not turns:
            return "(no previous conversation)"

        blocks: list[str] = []
        total_chars = 0

        for turn in reversed(turns):
            user_text = self._clip(turn.get("user_message", ""), 700)
            assistant_text = self._clip(turn.get("assistant_answer", ""), 1700)
            block = f"User: {user_text}\nAssistant: {assistant_text}"

            remaining = self.max_chars - total_chars
            if remaining <= 120:
                break
            if len(block) > remaining:
                block = block[:remaining].rstrip()

            blocks.append(block)
            total_chars += len(block)

        blocks.reverse()
        return "\n\n".join(blocks) or "(no previous conversation)"

    def extract_recent_destinations(
        self,
        turns: list[dict[str, Any]],
        limit: int = 4,
    ) -> list[dict[str, str]]:
        """Return unique recently discussed destinations, newest first.

        Destination focus can come from three structured surfaces, in order:
        (1) destinations resolved for the user's request, (2) destinations detected
        during retrieval, and (3) destination IDs attached to grounded entities that
        the final answer actually named.  The third surface is important for broad
        discovery answers: a user can naturally say "tell me more about these places"
        even though none of those places appeared literally in the preceding user
        message.
        """
        recent: list[dict[str, str]] = []
        seen: set[str] = set()

        def append_destination(destination_id: str, name: str | None = None) -> bool:
            destination_id = str(destination_id or "").strip()
            if not destination_id or destination_id in seen:
                return False

            canonical_name = str(name or "").strip()
            if not canonical_name:
                try:
                    from src.backend.services.query_parser import load_destination_catalog

                    catalog_item = load_destination_catalog().get(destination_id) or {}
                    canonical_name = str(
                        catalog_item.get("name_vi")
                        or catalog_item.get("name_en")
                        or destination_id
                    ).strip()
                except Exception:
                    canonical_name = destination_id

            recent.append({"id": destination_id, "name": canonical_name or destination_id})
            seen.add(destination_id)
            return len(recent) >= limit

        for turn in reversed(turns):
            # Resolved destinations are stronger than raw retrieval detections because
            # they already incorporate semantic reference resolution.
            structured = (
                turn.get("resolved_destinations")
                or turn.get("detected_destinations")
                or []
            )
            for item in structured:
                if append_destination(
                    str(item.get("id") or ""),
                    str(
                        item.get("name")
                        or item.get("name_vi")
                        or item.get("name_en")
                        or ""
                    ),
                ):
                    return recent

            # A grounded assistant answer may introduce several concrete options in
            # response to a broad request.  Persist their canonical destination IDs
            # as structured focus so plural follow-ups ("these places") do not lose
            # one location simply because it was absent from the user's wording.
            grounded_focus = turn.get("focus_entities") or []
            added_grounded_destination = False
            for entity in grounded_focus:
                destination_id = str(entity.get("destination_id") or "").strip()
                if not destination_id:
                    continue
                added_grounded_destination = True
                if append_destination(destination_id):
                    return recent

            if structured or added_grounded_destination:
                continue

            # Legacy fallback for old rows that predate structured entity memory.
            # Mine only user wording / resolved RAG query from accepted RAG turns;
            # never mine arbitrary assistant prose.
            if str(turn.get("route") or "") != "rag":
                continue
            try:
                from src.backend.services.query_parser import detect_destinations

                searchable = " ".join(
                    [
                        str(turn.get("user_message") or ""),
                        str(turn.get("rag_query") or ""),
                    ]
                )
                for item in detect_destinations(searchable):
                    if append_destination(
                        str(item.get("id") or ""),
                        str(item.get("name_vi") or item.get("name_en") or ""),
                    ):
                        return recent
            except Exception:
                pass

        return recent

    @staticmethod
    def format_destination_summary(destinations: list[dict[str, str]]) -> str:
        if not destinations:
            return "(none yet)"
        return ", ".join(
            f"{item.get('name') or item.get('id')} [{item.get('id')}]"
            for item in destinations
        )

    @staticmethod
    def extract_recent_entities(
        turns: list[dict[str, Any]],
        limit: int = 12,
    ) -> list[dict[str, str]]:
        """Return grounded recent entities, newest first, across arbitrary types.

        Entity names/types come from retrieval metadata saved with each turn; this
        method does not know about specific packages, hotels, promotions or future
        catalog classes.
        """
        recent: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for turn in reversed(turns):
            for item in turn.get("focus_entities") or []:
                name = str(item.get("name") or "").strip()
                entity_type = str(item.get("type") or item.get("entity_type") or "entity").strip() or "entity"
                if not name:
                    continue
                key = (entity_type.casefold(), normalize_text(name))
                if not key[1] or key in seen:
                    continue
                seen.add(key)
                entity = {
                    "name": name,
                    "type": entity_type,
                    "source": str(item.get("source") or "grounded_retrieval"),
                }
                destination_id = str(item.get("destination_id") or "").strip()
                if destination_id:
                    entity["destination_id"] = destination_id
                recent.append(entity)
                if len(recent) >= limit:
                    return recent
        return recent

    @staticmethod
    def format_entity_summary(entities: list[dict[str, str]]) -> str:
        if not entities:
            return "(none yet)"
        return ", ".join(
            f"{item.get('name')} <{item.get('type') or 'entity'}>"
            for item in entities
            if item.get("name")
        ) or "(none yet)"

    @staticmethod
    def derive_focus_entities(state: dict[str, Any], limit: int = 12) -> list[dict[str, str]]:
        """Derive grounded entities that are safe to carry into later turns.

        The old implementation considered only entity names present in the first
        handful of retrieved documents.  That loses options introduced by a grounded
        broad answer (for example the third city in a three-place recommendation)
        and makes plural anaphora brittle.

        This version combines retrieval metadata with *exact canonical KB entities*
        explicitly named in the final grounded answer.  Assistant prose is still not
        trusted blindly: answer-derived entities must exactly match the current KB and
        the turn must have passed grounding.
        """
        if str(state.get("route") or "") != "rag":
            return []
        if state.get("grounding_passed") is False:
            return []

        user_blob = normalize_text(
            " ".join(
                [
                    str(state.get("user_message") or ""),
                    str(state.get("sanitized_user_request") or ""),
                    str(state.get("rag_query") or ""),
                ]
            )
        )
        answer_text = str(state.get("answer") or "")
        answer_blob = normalize_text(answer_text)
        documents = list(state.get("retrieved_documents") or [])

        ranked: dict[tuple[str, str], tuple[float, dict[str, str]]] = {}

        def phrase_match(name: str, blob: str) -> float:
            name_norm = normalize_text(name)
            if not name_norm or not blob:
                return 0.0
            if f" {name_norm} " in f" {blob} ":
                return 1.0
            name_tokens = set(name_norm.split())
            blob_tokens = set(blob.split())
            if not name_tokens:
                return 0.0
            return len(name_tokens & blob_tokens) / len(name_tokens)

        def add_candidate(
            *,
            name: str,
            entity_type: str,
            source: str,
            score: float,
            destination_id: str | None = None,
        ) -> None:
            name = str(name or "").strip()
            entity_type = str(entity_type or "entity").strip() or "entity"
            normalized_name = normalize_text(name)
            if not normalized_name:
                return
            key = (entity_type.casefold(), normalized_name)
            item: dict[str, str] = {
                "name": name,
                "type": entity_type,
                "source": source,
            }
            destination_id = str(destination_id or "").strip()
            if destination_id:
                item["destination_id"] = destination_id
            current = ranked.get(key)
            if current is None or score > current[0]:
                # If a lower-scored copy knew the destination but the stronger copy
                # does not, preserve that structural relationship.
                if current and not destination_id and current[1].get("destination_id"):
                    item["destination_id"] = current[1]["destination_id"]
                ranked[key] = (score, item)
            elif destination_id and not current[1].get("destination_id"):
                current[1]["destination_id"] = destination_id

        # Retrieval metadata remains useful, but inspect more than the first 12 rows
        # because memory is a compact structure and answer context may include a
        # round-robin set of entities from several branches/destinations.
        for position, doc in enumerate(documents[:32]):
            metadata = dict(doc.get("metadata") or {})
            entity_type = str(
                metadata.get("entity_type")
                or metadata.get("source_table")
                or "entity"
            ).strip() or "entity"
            destination_id = str(metadata.get("destination_id") or "").strip()

            names: list[tuple[str, str]] = []
            if entity_type == "faq":
                subcategory = str(metadata.get("subcategory") or "").strip()
                if subcategory:
                    names.append((subcategory, "faq_subject"))
            else:
                entity_name = str(metadata.get("entity_name") or "").strip()
                if entity_name:
                    names.append((entity_name, entity_type))

            for name, candidate_type in names:
                user_match = phrase_match(name, user_blob)
                answer_match = phrase_match(name, answer_blob)
                if user_match < 0.60 and answer_match < 0.82:
                    continue
                try:
                    doc_score = float(doc.get("score") or 0.0)
                except (TypeError, ValueError):
                    doc_score = 0.0
                source = "user_or_query" if user_match >= 0.60 else "grounded_answer"
                score = (
                    2.0 * user_match
                    + 1.25 * answer_match
                    + min(1.0, max(0.0, doc_score))
                    - position * 0.005
                )
                add_candidate(
                    name=name,
                    entity_type=candidate_type,
                    source=source,
                    score=score,
                    destination_id=destination_id,
                )

        # Exact KB probing closes the gap where the answer names an entity that was
        # supported compositionally by retrieved context but that entity's canonical
        # row was not among the top retrieved documents.  This is safe only after
        # grounding has passed, hence the guard at the top of the function.
        try:
            from src.backend.services.kb_scope_probe import probe_kb_scope_evidence

            user_matches = probe_kb_scope_evidence(
                " ".join(
                    [
                        str(state.get("user_message") or ""),
                        str(state.get("rag_query") or ""),
                    ]
                ),
                limit=max(24, limit * 3),
            )
            for position, item in enumerate(user_matches):
                add_candidate(
                    name=str(item.get("entity_name") or ""),
                    entity_type=str(item.get("entity_type") or "entity"),
                    source="user_or_query_kb",
                    score=4.0 - position * 0.001,
                    destination_id=str(item.get("destination_id") or ""),
                )

            answer_matches = probe_kb_scope_evidence(
                answer_text,
                limit=max(24, limit * 3),
            )
            for position, item in enumerate(answer_matches):
                add_candidate(
                    name=str(item.get("entity_name") or ""),
                    entity_type=str(item.get("entity_type") or "entity"),
                    source="grounded_answer_kb",
                    score=3.0 - position * 0.001,
                    destination_id=str(item.get("destination_id") or ""),
                )
        except Exception as exc:
            print(f"[MEMORY] canonical grounded-entity probe unavailable: {exc}")

        ordered = sorted(ranked.values(), key=lambda pair: pair[0], reverse=True)
        return [item for _, item in ordered[: max(1, limit)]]

    def append_turn(
        self,
        *,
        session_id: str | None,
        user_id: str | None,
        user_message: str,
        assistant_answer: str,
        language: str,
        route: str,
        rag_query: str | None = None,
        ticket_id: str | None = None,
        detected_destinations: list[dict[str, Any]] | None = None,
        resolved_destinations: list[dict[str, Any]] | None = None,
        focus_entities: list[dict[str, Any]] | None = None,
        context_uses_memory: bool = False,
        context_resolution_reason: str | None = None,
        context_resolution_confidence: float | None = None,
        context_resolution_source: str | None = None,
        detected_intent: str | None = None,
        detected_intents: list[str] | None = None,
        request_mode: str | None = None,
        resolution_mode: str | None = None,
    ) -> None:
        if not self.enabled or not session_id:
            return

        parsed_user_id = self._parse_user_id(user_id)
        now = datetime.now(timezone.utc)

        def _compact_destination_list(items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
            compact: list[dict[str, str]] = []
            seen_ids: set[str] = set()
            for item in items or []:
                destination_id = str(item.get("id") or "").strip()
                if not destination_id or destination_id in seen_ids:
                    continue
                seen_ids.add(destination_id)
                compact.append(
                    {
                        "id": destination_id,
                        "name": str(
                            item.get("name")
                            or item.get("name_vi")
                            or item.get("name_en")
                            or destination_id
                        ),
                    }
                )
            return compact

        compact_destinations = _compact_destination_list(detected_destinations)
        compact_resolved_destinations = _compact_destination_list(resolved_destinations)

        def _compact_entity_list(items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
            compact: list[dict[str, str]] = []
            seen_entities: set[tuple[str, str]] = set()
            for item in items or []:
                name = str(item.get("name") or "").strip()
                entity_type = str(item.get("type") or item.get("entity_type") or "entity").strip() or "entity"
                if not name:
                    continue
                key = (entity_type.casefold(), normalize_text(name))
                if not key[1] or key in seen_entities:
                    continue
                seen_entities.add(key)
                entity = {
                    "name": name[:220],
                    "type": entity_type[:100],
                    "source": str(item.get("source") or "grounded_retrieval")[:80],
                }
                destination_id = str(item.get("destination_id") or "").strip()
                if destination_id:
                    entity["destination_id"] = destination_id[:120]
                compact.append(entity)
            return compact[:12]

        compact_focus_entities = _compact_entity_list(focus_entities)

        with open_session() as db:
            if parsed_user_id is not None and db.get(AppUser, parsed_user_id) is None:
                parsed_user_id = None

            chat_session = db.get(ChatSession, session_id)
            if chat_session is None:
                chat_session = ChatSession(
                    id=session_id,
                    user_id=parsed_user_id,
                    channel="web",
                    language=language or None,
                    last_activity_at=now,
                )
                db.add(chat_session)
                db.flush()
            else:
                chat_session = db.scalar(
                    select(ChatSession)
                    .where(ChatSession.id == session_id)
                    .with_for_update()
                )
                if chat_session is None:
                    return
                self._check_session_access(chat_session, parsed_user_id)
                if parsed_user_id is not None and chat_session.user_id is None:
                    chat_session.user_id = parsed_user_id
                if language:
                    chat_session.language = language
                chat_session.last_activity_at = now

            max_seq = db.scalar(
                select(func.max(Message.seq)).where(Message.session_id == session_id)
            )
            user_seq = int(max_seq or 0) + 1
            assistant_seq = user_seq + 1

            db.add(
                Message(
                    session_id=session_id,
                    user_id=parsed_user_id,
                    seq=user_seq,
                    role="user",
                    content=user_message,
                    language=language or None,
                    route=None,
                )
            )
            db.add(
                Message(
                    session_id=session_id,
                    user_id=parsed_user_id,
                    seq=assistant_seq,
                    role="assistant",
                    content=assistant_answer,
                    language=language or None,
                    route=route if route in self._DB_ROUTES else None,
                    model=self.model_name,
                )
            )

            db.add(
                EventLog(
                    user_id=parsed_user_id,
                    session_id=session_id,
                    event_type=self._META_EVENT,
                    payload={
                        "assistant_seq": assistant_seq,
                        "route": route,
                        "ticket_id": ticket_id,
                        "rag_query": rag_query,
                        "detected_destinations": compact_destinations,
                        "resolved_destinations": compact_resolved_destinations,
                        "focus_entities": compact_focus_entities,
                        "context_uses_memory": bool(context_uses_memory),
                        "context_resolution_reason": context_resolution_reason,
                        "context_resolution_confidence": context_resolution_confidence,
                        "context_resolution_source": context_resolution_source,
                        "detected_intent": detected_intent,
                        "detected_intents": list(detected_intents or []),
                        "request_mode": request_mode,
                        "resolution_mode": resolution_mode,
                    },
                )
            )

            chat_session.last_activity_at = now
            db.commit()

    @staticmethod
    def _delete_session_rows(db: Any, chat_session: ChatSession) -> int:
        session_id = chat_session.id
        deleted_turns = int(
            db.scalar(
                select(func.count(Message.id)).where(
                    Message.session_id == session_id,
                    Message.role == "user",
                )
            )
            or 0
        )

        db.execute(
            delete(EventLog).where(
                EventLog.session_id == session_id,
                EventLog.event_type == MemoryService._META_EVENT,
            )
        )
        db.delete(chat_session)
        return deleted_turns

    def clear_for_user(self, session_id: str, user_id: str) -> int | None:
        """Delete an authenticated user's own conversation only.

        Returns ``None`` for missing/foreign sessions so the API can answer with
        a non-disclosing 404.
        """
        parsed_user_id = self._parse_user_id(user_id)
        if not session_id or parsed_user_id is None:
            return None

        with open_session() as db:
            chat_session = db.get(ChatSession, session_id)
            if chat_session is None or chat_session.user_id != parsed_user_id:
                return None
            deleted_turns = self._delete_session_rows(db, chat_session)
            db.commit()
            return deleted_turns

    def clear(self, session_id: str) -> int:
        """Internal unconditional delete kept for maintenance/backward compatibility."""
        if not session_id:
            return 0

        with open_session() as db:
            chat_session = db.get(ChatSession, session_id)
            if chat_session is None:
                return 0
            deleted_turns = self._delete_session_rows(db, chat_session)
            db.commit()
            return deleted_turns
