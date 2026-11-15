"""Password-based staff access and ticket management."""

import os
import secrets
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.database import get_session
from app.models import Ticket, utc_now

STATUSES = ("Open", "In Progress", "Resolved")
PRIORITIES = ("Low", "Medium", "High")
CATEGORIES = ("Electrical", "Plumbing", "Furniture", "Cleaning", "Network", "Other")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
ADMIN_ENABLED = bool(ADMIN_PASSWORD and len(SESSION_SECRET) >= 32)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


def csrf_token(request: Request):
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def check_csrf(request: Request, csrf: str = Form("")):
    expected = request.session.get("csrf", "")
    if not expected or not secrets.compare_digest(csrf.encode(), expected.encode()):
        raise HTTPException(403, "This form has expired or is invalid. Reload the page and try again.")


def require_admin(request: Request):
    if not ADMIN_ENABLED or request.session.get("admin") is not True:
        raise HTTPException(303, headers={"Location": "/admin/login"})


public_router = APIRouter(prefix="/admin")
router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def login_page(request, error=None, status_code=200):
    return templates.TemplateResponse(
        request=request, name="admin_login.html", status_code=status_code,
        context={"csrf": csrf_token(request), "error": error, "enabled": ADMIN_ENABLED},
    )


@public_router.get("/login")
def admin_login(request: Request):
    if not ADMIN_ENABLED:
        return login_page(request, "Administrator access is not configured. Contact the application maintainer.", 503)
    if request.session.get("admin") is True:
        return RedirectResponse("/admin", status_code=303)
    return login_page(request)


@public_router.post("/login", dependencies=[Depends(check_csrf)])
def admin_sign_in(request: Request, password: str = Form("")):
    if not ADMIN_ENABLED:
        return login_page(request, "Administrator access is not configured.", 503)
    if not secrets.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        return login_page(request, "Incorrect password. Please try again.", 401)
    # Discard the anonymous session and rotate the form token on authentication.
    request.session.clear()
    request.session.update(admin=True, csrf=secrets.token_urlsafe(32))
    return RedirectResponse("/admin", status_code=303)


@router.post("/logout", dependencies=[Depends(check_csrf)])
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("")
def admin_dashboard(
    request: Request, status: str = "", priority: str = "", category: str = "",
    session: Session = Depends(get_session),
):
    query = select(Ticket)
    for value, options, column in (
        (status, STATUSES, Ticket.status),
        (priority, PRIORITIES, Ticket.priority),
        (category, CATEGORIES, Ticket.category),
    ):
        if value:
            if value not in options:
                raise HTTPException(422, "Choose a valid filter value.")
            query = query.where(column == value)
    tickets = session.exec(query.order_by(Ticket.created_at.desc(), Ticket.id)).all()
    counts = dict(session.exec(select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)).all())
    return templates.TemplateResponse(
        request=request, name="admin_dashboard.html",
        context={
            "tickets": tickets, "counts": counts, "statuses": STATUSES,
            "priorities": PRIORITIES, "categories": CATEGORIES,
            "filters": {"status": status, "priority": priority, "category": category},
            "csrf": csrf_token(request),
        },
    )


def find_ticket(session, ticket_id):
    try:
        ticket = session.get(Ticket, UUID(ticket_id))
    except ValueError:
        ticket = None
    if ticket is None:
        raise HTTPException(404, "No ticket matches this reference.")
    return ticket


def edit_page(request, ticket, error=None, status_code=200, values=None):
    return templates.TemplateResponse(
        request=request, name="admin_ticket.html", status_code=status_code,
        context={
            "ticket": ticket, "statuses": STATUSES, "priorities": PRIORITIES,
            "csrf": csrf_token(request), "error": error,
            "values": values or {"status": ticket.status, "priority": ticket.priority},
        },
    )


@router.get("/tickets/{ticket_id}")
def admin_ticket(request: Request, ticket_id: str, session: Session = Depends(get_session)):
    return edit_page(request, find_ticket(session, ticket_id))


@router.post("/tickets/{ticket_id}", dependencies=[Depends(check_csrf)])
def admin_update(
    request: Request, ticket_id: str, status: str = Form(""), priority: str = Form(""),
    session: Session = Depends(get_session),
):
    ticket = find_ticket(session, ticket_id)
    if status not in STATUSES or priority not in PRIORITIES:
        return edit_page(request, ticket, "Choose a valid status and priority.", 422,
                         {"status": status, "priority": priority})
    if ticket.status != status or ticket.priority != priority:
        ticket.status = status
        ticket.priority = priority
        ticket.updated_at = utc_now()
        try:
            session.add(ticket)
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            return edit_page(request, ticket, "Changes could not be saved. Please try again.", 503)
    request.session["notice"] = "Ticket updated."
    return RedirectResponse(f"/admin/tickets/{ticket.id}", status_code=303)
