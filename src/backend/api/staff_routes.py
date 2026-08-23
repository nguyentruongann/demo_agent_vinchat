from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from src.backend.models.ticket import TicketPublic, TicketUpdateRequest
from src.backend.services.auth import require_staff
from src.backend.services.db import open_session
from src.data_postgre.db.app import AppUser, Ticket

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


def _ticket_public(ticket: Ticket, assignee_name: str | None = None) -> TicketPublic:
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
        assigned_to_name=assignee_name,
        created_at=ticket.created_at.isoformat(),
        updated_at=ticket.updated_at.isoformat(),
        resolved_at=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
    )


@router.get("/tickets", response_model=list[TicketPublic])
def list_tickets(
    status: str | None = Query(default=None),
    current: AppUser = Depends(require_staff),
) -> list[TicketPublic]:
    with open_session() as db:
        stmt = select(Ticket).order_by(Ticket.created_at.desc())
        if status:
            stmt = stmt.where(Ticket.status == status)
        tickets = db.scalars(stmt).all()
        assignee_ids = {item.assigned_to for item in tickets if item.assigned_to}
        names = {}
        if assignee_ids:
            staff = db.scalars(select(AppUser).where(AppUser.id.in_(assignee_ids))).all()
            names = {item.id: item.display_name for item in staff}
        return [_ticket_public(item, names.get(item.assigned_to)) for item in tickets]


@router.patch("/tickets/{ticket_id}", response_model=TicketPublic)
def update_ticket(
    ticket_id: str,
    payload: TicketUpdateRequest,
    current: AppUser = Depends(require_staff),
) -> TicketPublic:
    with open_session() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Không tìm thấy ticket.")
        if payload.status is not None:
            ticket.status = payload.status
            if payload.status in {"resolved", "closed"}:
                ticket.resolved_at = datetime.now(UTC)
            elif ticket.resolved_at is not None:
                ticket.resolved_at = None
        if payload.priority is not None:
            ticket.priority = payload.priority
        if payload.assigned_to == "":
            ticket.assigned_to = None
        elif payload.assigned_to is not None:
            try:
                staff_id = UUID(payload.assigned_to)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="assigned_to không hợp lệ.") from exc
            staff = db.get(AppUser, staff_id)
            if not staff or staff.role not in {"staff", "admin"} or not staff.is_active:
                raise HTTPException(status_code=422, detail="Nhân viên được gán không hợp lệ.")
            ticket.assigned_to = staff.id
        # Staff can claim an unassigned ticket automatically when moving it to in_progress.
        if ticket.status == "in_progress" and ticket.assigned_to is None:
            ticket.assigned_to = current.id
        db.commit()
        db.refresh(ticket)
        assignee = db.get(AppUser, ticket.assigned_to) if ticket.assigned_to else None
        return _ticket_public(ticket, assignee.display_name if assignee else None)
