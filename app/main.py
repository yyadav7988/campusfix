"""Student ticket submission and retrieval."""

from contextlib import asynccontextmanager
from pathlib import Path
import os
import secrets
from uuid import UUID

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel

from app.database import engine, get_session
from app.models import Ticket
from app import admin
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler

APP_DIR = Path(__file__).resolve().parent
CATEGORIES = ("Electrical", "Plumbing", "Furniture", "Cleaning", "Network", "Other")


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="CampusFix", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=admin.SESSION_SECRET or secrets.token_urlsafe(32), session_cookie="campusfix_session", max_age=28800, same_site="lax", https_only=os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true")
app.include_router(admin.public_router)
app.include_router(admin.router)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")


def report_page(request, values=None, errors=None, status_code=200):
    return templates.TemplateResponse(
        request=request, name="report.html", status_code=status_code,
        context={"values": values or {}, "errors": errors or {}, "categories": CATEGORIES},
    )


@app.get("/report", response_class=HTMLResponse)
def report(request: Request):
    return report_page(request)


@app.post("/report", response_class=HTMLResponse)
def submit_report(
    request: Request,
    building: str = Form(""),
    room: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    session: Session = Depends(get_session),
):
    values = {
        "building": building.strip(), "room": room.strip(),
        "category": category.strip(), "description": description.strip(),
    }
    errors = {}
    for field, limit in (("building", 100), ("room", 50), ("description", 2000)):
        if not values[field]:
            errors[field] = f"Enter a {field}."
        elif len(values[field]) > limit:
            errors[field] = f"Use {limit} characters or fewer."
    if values["category"] not in CATEGORIES:
        errors["category"] = "Choose a valid category."
    if errors:
        return report_page(request, values, errors, 422)

    ticket = Ticket(**values)
    try:
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
    except SQLAlchemyError:
        session.rollback()
        return report_page(
            request, values, {"save": "We could not save your issue. Please try again."}, 503
        )
    return RedirectResponse(
        request.url_for("ticket_detail", ticket_id=str(ticket.id)), status_code=303
    )


@app.get("/track", response_class=HTMLResponse)
def track(request: Request, ticket_id: str | None = None):
    error = None
    if ticket_id is not None:
        try:
            reference = UUID(ticket_id.strip())
        except ValueError:
            error = "Enter a valid ticket ID, such as the reference shown after reporting an issue."
        else:
            return RedirectResponse(
                request.url_for("ticket_detail", ticket_id=str(reference)), status_code=303
            )
    return templates.TemplateResponse(
        request=request, name="track.html", status_code=422 if error else 200,
        context={"ticket_id": ticket_id or "", "error": error},
    )


def missing_ticket(request):
    return templates.TemplateResponse(
        request=request, name="not_found.html", status_code=404
    )


@app.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(request: Request, ticket_id: str, session: Session = Depends(get_session)):
    try:
        reference = UUID(ticket_id)
    except ValueError:
        return missing_ticket(request)
    ticket = session.get(Ticket, reference)
    if ticket is None:
        return missing_ticket(request)
    return templates.TemplateResponse(
        request=request, name="ticket.html", context={"ticket": ticket}
    )


@app.middleware("http")
async def protect_admin_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(StarletteHTTPException)
async def admin_http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/admin"):
        if exc.status_code == 303:
            return RedirectResponse("/admin/login", status_code=303)
        return templates.TemplateResponse(
            request=request, name="admin_error.html", status_code=exc.status_code,
            context={"message": exc.detail},
        )
    return await http_exception_handler(request, exc)
