"""Ticket records. SQLite timestamps are stored as naive UTC values."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Ticket(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    building: str = Field(max_length=100)
    room: str = Field(max_length=50)
    category: str = Field(max_length=50)
    description: str = Field(max_length=2000)
    priority: str = Field(default="Medium", max_length=20)
    status: str = Field(default="Open", max_length=20)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime)
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime)
