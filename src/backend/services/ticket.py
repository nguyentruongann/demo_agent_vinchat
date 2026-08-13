from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from src.backend.services.db import open_session
from src.data_postgre.db.app import AppUser, ChatSession, Ticket


class TicketService:
    def create(
        self,
        message: str,
        language: str,
        session_id: str | None,
        user_id: str | None,
        reason: str,
        conversation_turns: list[dict[str, Any]] | None = None,
        *,
        contact_name: str | None = None,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        subject: str | None = None,
    ) -> str:
        ticket_id = f"VP-{uuid4().hex[:10].upper()}"
        parsed_user_id = None
        if user_id:
            try:
                parsed_user_id = UUID(str(user_id))
            except ValueError:
                parsed_user_id = None

        with open_session() as db:
            if parsed_user_id:
                user = db.get(AppUser, parsed_user_id)
                if user:
                    contact_name = contact_name or user.display_name
                    contact_email = contact_email or user.email
                    contact_phone = contact_phone or user.phone
            valid_session_id = session_id if session_id and db.get(ChatSession, session_id) else None
            record = Ticket(
                id=ticket_id,
                user_id=parsed_user_id,
                session_id=valid_session_id,
                status="open",
                reason=reason,
                priority="normal",
                message=message,
                language=language,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                subject=subject or "Chatbot support request",
                conversation_turns=conversation_turns or [],
            )
            db.add(record)
            db.commit()
        return ticket_id
