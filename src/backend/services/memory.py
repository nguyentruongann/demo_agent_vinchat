from __future__ import annotations

from datetime import UTC, datetime
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

    # Memory provenance is intentionally more important than recency.
    # A destination the assistant merely suggested must remain retrievable for
    # recap/follow-up, but it must not become a user preference or a hard RAG
    # filter until the user explicitly names or confirms it.
    _USER_FOCUS_SOURCES = {
        "current_explicit",
        "user_explicit",
        "user_explicit_kb",
        "user_explicit_legacy_detection",
        "user_explicit_logic_subject",
        "user_confirmed",
        "user_confirmed_via_memory",
        "recent_user_focus",
        "user_focus_from_selected_turn",
    }
    _ASSISTANT_PROPOSAL_SOURCES = {
        "assistant_suggestion",
        "assistant_suggestion_kb",
        "grounded_answer",
        "grounded_answer_kb",
    }
    _RETRIEVAL_ONLY_SOURCES = {
        "retrieval_detection",
        "retrieval_evidence",
        "grounded_retrieval",
    }

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
        now = datetime.now(UTC)

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
                    "sanitized_user_request": metadata.get("sanitized_user_request")
                    or metadata.get("rag_query")
                    or "",
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
                    "memory_provenance_version": metadata.get("memory_provenance_version"),
                    "conversation_subjects": metadata.get("conversation_subjects") or [],
                    "context_uses_memory": bool(metadata.get("context_uses_memory", False)),
                    "context_resolution_reason": metadata.get("context_resolution_reason"),
                    "context_resolution_confidence": metadata.get("context_resolution_confidence"),
                    "context_resolution_source": metadata.get("context_resolution_source"),
                    "detected_intent": metadata.get("detected_intent"),
                    "detected_intents": metadata.get("detected_intents") or [],
                    "request_tasks": metadata.get("request_tasks") or [],
                    "request_mode": metadata.get("request_mode"),
                    "resolution_mode": metadata.get("resolution_mode"),
                    "logic_action": metadata.get("logic_action"),
                    "logic_category": metadata.get("logic_category"),
                    "scope_action": metadata.get("scope_action"),
                    "safety_action": metadata.get("safety_action"),
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
            user_text = self._clip(
                turn.get("sanitized_user_request") or turn.get("rag_query") or "",
                700,
            )
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
        """Return unique USER-OWNED destination focus, newest first.

        This is deliberately strict.  It powers hard contextual constraints, so it
        may include only destinations the user explicitly mentioned or confirmed.
        Retrieval hits and assistant recommendations remain available through
        ``extract_recent_discussed_destinations()`` / focus turns, but they must not
        be promoted into ``recent_user_focus`` merely because they appeared in an
        answer.  That was the source of the Phú Quốc-overfitting bug.
        """
        recent: list[dict[str, str]] = []
        seen: set[str] = set()

        def append_destination(
            destination_id: str,
            name: str | None = None,
            *,
            source: str = "user_explicit",
        ) -> bool:
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

            recent.append(
                {
                    "id": destination_id,
                    "name": canonical_name or destination_id,
                    "source": source,
                    "confirmed": "true" if source in self._USER_FOCUS_SOURCES else "false",
                }
            )
            seen.add(destination_id)
            return len(recent) >= limit

        for turn in reversed(turns):
            try:
                from src.backend.services.query_parser import detect_destinations

                user_explicit_ids = {
                    str(item.get("id") or "").strip()
                    for item in detect_destinations(
                        str(turn.get("sanitized_user_request") or turn.get("rag_query") or "")
                    )
                    if str(item.get("id") or "").strip()
                }
            except Exception:
                user_explicit_ids = set()

            for item in turn.get("resolved_destinations") or []:
                destination_id = str(item.get("id") or "").strip()
                if not destination_id:
                    continue
                source = str(item.get("source") or "").strip()
                if source in self._USER_FOCUS_SOURCES or destination_id in user_explicit_ids:
                    if append_destination(
                        destination_id,
                        str(
                            item.get("name")
                            or item.get("name_vi")
                            or item.get("name_en")
                            or ""
                        ),
                        source=source or "user_explicit",
                    ):
                        return recent

            # Legacy support: old metadata may have only detected_destinations.
            # Accept it as user focus only when the user literally named it.
            for item in turn.get("detected_destinations") or []:
                destination_id = str(item.get("id") or "").strip()
                if not destination_id or destination_id not in user_explicit_ids:
                    continue
                if append_destination(
                    destination_id,
                    str(item.get("name") or item.get("name_vi") or item.get("name_en") or ""),
                    source="user_explicit_legacy_detection",
                ):
                    return recent

            # Backward-compatible recovery for turns saved before provenance v3.
            # A logic-invalid turn can still contain a perfectly valid SUBJECT
            # (for example: "Phú Quốc for 2 days 3 nights").  If the turn was
            # rejected only for logical coherence and the raw user text names
            # exactly one canonical destination, preserve that destination as
            # user-owned focus.  Do not do this for safety/scope blocks,
            # conversation-meta turns, or ambiguous multi-destination text.
            route = str(turn.get("route") or "").strip()
            logic_action = str(turn.get("logic_action") or "").strip().lower()
            scope_action = str(turn.get("scope_action") or "allow").strip().lower()
            safety_action = str(turn.get("safety_action") or "allow").strip().lower()
            recover_logic_subject = (
                route == "invalid_request" or logic_action == "reject"
            ) and scope_action != "block" and safety_action != "block"
            if recover_logic_subject and len(user_explicit_ids) == 1:
                destination_id = next(iter(user_explicit_ids))
                if append_destination(
                    destination_id,
                    source="user_explicit_logic_subject",
                ):
                    return recent

        return recent

    def extract_recent_discussed_destinations(
        self,
        turns: list[dict[str, Any]],
        limit: int = 8,
    ) -> list[dict[str, str]]:
        """Return recently discussed/proposed destinations without implying choice.

        These destinations are suitable for conversation recap, plural follow-ups
        ("các phương án lúc nãy"), and resolving anaphora. They must be treated as
        unconfirmed unless their source is also a user-focus source.
        """
        recent: list[dict[str, str]] = []
        seen: set[str] = set()

        def append_destination(
            destination_id: str,
            name: str | None = None,
            *,
            source: str = "assistant_suggestion",
        ) -> bool:
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
            confirmed = source in self._USER_FOCUS_SOURCES
            recent.append(
                {
                    "id": destination_id,
                    "name": canonical_name or destination_id,
                    "source": source,
                    "confirmed": "true" if confirmed else "false",
                }
            )
            seen.add(destination_id)
            return len(recent) >= limit

        for turn in reversed(turns):
            # User-owned focus is also discussed, but marked confirmed/user-owned.
            for item in turn.get("resolved_destinations") or []:
                destination_id = str(item.get("id") or "").strip()
                if not destination_id:
                    continue
                source = str(item.get("source") or "retrieval_evidence").strip()
                if append_destination(
                    destination_id,
                    str(item.get("name") or item.get("name_vi") or item.get("name_en") or ""),
                    source=source,
                ):
                    return recent

            # Retrieval-detected destinations are discussed evidence, not user focus.
            for item in turn.get("detected_destinations") or []:
                destination_id = str(item.get("id") or "").strip()
                if not destination_id:
                    continue
                source = str(item.get("source") or "retrieval_detection").strip()
                if append_destination(
                    destination_id,
                    str(item.get("name") or item.get("name_vi") or item.get("name_en") or ""),
                    source=source,
                ):
                    return recent

            for entity in turn.get("focus_entities") or []:
                destination_id = str(entity.get("destination_id") or "").strip()
                if not destination_id:
                    continue
                entity_source = str(entity.get("source") or "grounded_answer").strip()
                if entity_source in self._USER_FOCUS_SOURCES:
                    dest_source = entity_source
                elif entity_source in self._ASSISTANT_PROPOSAL_SOURCES:
                    dest_source = "assistant_suggestion"
                else:
                    dest_source = "retrieval_evidence"
                if append_destination(destination_id, source=dest_source):
                    return recent

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
                source = str(item.get("source") or "grounded_retrieval")
                entity = {
                    "name": name,
                    "type": entity_type,
                    "source": source,
                    "confirmed": "true" if source in MemoryService._USER_FOCUS_SOURCES else "false",
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

        # Use only the user's current wording for user-owned memory.  The RAG query
        # may contain assistant/LLM rewrites or selected prior context, so mining it
        # as "user focus" would turn retrieved suggestions into user preferences.
        user_blob = normalize_text(
            str(state.get("sanitized_user_request") or state.get("rag_query") or "")
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
                source = "user_explicit" if user_match >= 0.60 else "assistant_suggestion"
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
                str(state.get("sanitized_user_request") or state.get("rag_query") or ""),
                limit=max(24, limit * 3),
            )
            for position, item in enumerate(user_matches):
                add_candidate(
                    name=str(item.get("entity_name") or ""),
                    entity_type=str(item.get("entity_type") or "entity"),
                    source="user_explicit_kb",
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
                    source="assistant_suggestion_kb",
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
        sanitized_user_request: str | None = None,
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
        request_tasks: list[dict[str, Any]] | None = None,
        request_mode: str | None = None,
        resolution_mode: str | None = None,
        logic_action: str | None = None,
        logic_category: str | None = None,
        scope_action: str | None = None,
        safety_action: str | None = None,
    ) -> None:
        if not self.enabled or not session_id:
            return

        parsed_user_id = self._parse_user_id(user_id)
        now = datetime.now(UTC)

        def _compact_destination_list(items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
            compact: list[dict[str, str]] = []
            seen_ids: set[str] = set()
            for item in items or []:
                destination_id = str(item.get("id") or "").strip()
                if not destination_id or destination_id in seen_ids:
                    continue
                seen_ids.add(destination_id)
                source = str(item.get("source") or "retrieval_detection")[:80]
                compact_item = {
                    "id": destination_id,
                    "name": str(
                        item.get("name")
                        or item.get("name_vi")
                        or item.get("name_en")
                        or destination_id
                    ),
                    "source": source,
                    "confirmed": "true" if source in self._USER_FOCUS_SOURCES else "false",
                }
                compact.append(compact_item)
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
                source = str(item.get("source") or "grounded_retrieval")[:80]
                entity = {
                    "name": name[:220],
                    "type": entity_type[:100],
                    "source": source,
                    "confirmed": "true" if source in self._USER_FOCUS_SOURCES else "false",
                }
                destination_id = str(item.get("destination_id") or "").strip()
                if destination_id:
                    entity["destination_id"] = destination_id[:120]
                compact.append(entity)
            return compact[:12]

        compact_focus_entities = _compact_entity_list(focus_entities)

        compact_request_tasks: list[dict[str, Any]] = []
        for index, item in enumerate(request_tasks or [], start=1):
            if not isinstance(item, dict):
                continue
            goal = str(item.get("goal") or "").strip()
            if not goal:
                continue
            compact_request_tasks.append({
                "task_id": str(item.get("task_id") or f"t{index}")[:40],
                "task_type": str(item.get("task_type") or "general_qa")[:80],
                "goal": goal[:500],
                "needs_memory": bool(item.get("needs_memory", False)),
                "depends_on": [str(value)[:40] for value in (item.get("depends_on") or [])[:8]],
            })

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
                        "sanitized_user_request": self._clip(
                            sanitized_user_request or rag_query or "",
                            2000,
                        ),
                        "detected_destinations": compact_destinations,
                        "resolved_destinations": compact_resolved_destinations,
                        "focus_entities": compact_focus_entities,
                        "memory_provenance_version": 2,
                        "conversation_subjects": compact_focus_entities[:8],
                        "context_uses_memory": bool(context_uses_memory),
                        "context_resolution_reason": context_resolution_reason,
                        "context_resolution_confidence": context_resolution_confidence,
                        "context_resolution_source": context_resolution_source,
                        "detected_intent": detected_intent,
                        "detected_intents": list(detected_intents or []),
                        "request_tasks": compact_request_tasks,
                        "request_mode": request_mode,
                        "resolution_mode": resolution_mode,
                        "logic_action": str(logic_action or "")[:40] or None,
                        "logic_category": str(logic_category or "")[:80] or None,
                        "scope_action": str(scope_action or "")[:40] or None,
                        "safety_action": str(safety_action or "")[:40] or None,
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
