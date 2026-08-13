from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select

from src.backend.config import get_settings
from src.backend.services.db import open_session
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
                    "rag_query": None,
                    "ticket_id": metadata.get("ticket_id"),
                    "detected_destinations": metadata.get("detected_destinations") or [],
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
        """Return unique recently discussed destinations, newest first."""
        recent: list[dict[str, str]] = []
        seen: set[str] = set()

        for turn in reversed(turns):
            structured = turn.get("detected_destinations") or []
            if not structured and turn.get("detected_destination"):
                structured = [
                    {
                        "id": turn.get("detected_destination"),
                        "name": turn.get("detected_destination_name"),
                    }
                ]

            if not structured:
                try:
                    from src.backend.services.query_parser import detect_destinations

                    searchable = " ".join(
                        [
                            str(turn.get("user_message") or ""),
                            str(turn.get("assistant_answer") or ""),
                            str(turn.get("rag_query") or ""),
                        ]
                    )
                    structured = [
                        {
                            "id": item.get("id"),
                            "name": item.get("name_vi") or item.get("name_en") or item.get("id"),
                        }
                        for item in detect_destinations(searchable)
                    ]
                except Exception:
                    structured = []

            for item in structured:
                destination_id = str(item.get("id") or "").strip()
                if not destination_id or destination_id in seen:
                    continue
                name = str(
                    item.get("name")
                    or item.get("name_vi")
                    or item.get("name_en")
                    or destination_id
                ).strip()
                recent.append({"id": destination_id, "name": name})
                seen.add(destination_id)
                if len(recent) >= limit:
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
        detected_intent: str | None = None,
        detected_intents: list[str] | None = None,
        request_mode: str | None = None,
        resolution_mode: str | None = None,
    ) -> None:
        if not self.enabled or not session_id:
            return

        parsed_user_id = self._parse_user_id(user_id)
        now = datetime.now(timezone.utc)

        compact_destinations: list[dict[str, str]] = []
        for item in detected_destinations or []:
            destination_id = str(item.get("id") or "").strip()
            if not destination_id:
                continue
            compact_destinations.append(
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
                        "detected_destinations": compact_destinations,
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
