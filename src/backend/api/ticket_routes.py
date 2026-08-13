from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.backend.models.ticket import ManualTicketCreate, TicketPublic
from src.backend.services.auth import get_current_user, get_optional_user, normalize_phone
from src.backend.services.db import open_session
from src.backend.services.ticket import TicketService
from src.data_postgre.db.app import AppUser, Ticket

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


def _public(ticket: Ticket) -> TicketPublic:
    return TicketPublic(
        id=ticket.id,
        customer_name=ticket.contact_name,
        email=ticket.contact_email,
        phone=ticket.contact_phone,
        subject=ticket.subject,
        content=ticket.message,
        language=ticket.language,
        status=ticket.status,
        priority=ticket.priority,
        reason=ticket.reason,
        assigned_to=str(ticket.assigned_to) if ticket.assigned_to else None,
        assigned_to_name=None,
        created_at=ticket.created_at.isoformat(),
        updated_at=ticket.updated_at.isoformat(),
        resolved_at=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
    )


@router.post("", response_model=TicketPublic, status_code=201)
def create_manual_ticket(
    payload: ManualTicketCreate,
    current: AppUser | None = Depends(get_optional_user),
) -> TicketPublic:
    ticket_id = TicketService().create(
        message=payload.content,
        language=payload.language,
        session_id=None,
        user_id=str(current.id) if current else None,
        reason="Manual support request",
        contact_name=payload.customer_name,
        contact_email=str(payload.email) if payload.email else None,
        contact_phone=normalize_phone(payload.phone),
        subject=payload.subject,
    )
    with open_session() as db:
        return _public(db.get(Ticket, ticket_id))


@router.get("/mine", response_model=list[TicketPublic])
def my_tickets(current: AppUser = Depends(get_current_user)) -> list[TicketPublic]:
    with open_session() as db:
        rows = db.scalars(
            select(Ticket).where(Ticket.user_id == current.id).order_by(Ticket.created_at.desc())
        ).all()
        return [_public(item) for item in rows]
