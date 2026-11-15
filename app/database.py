"""Database configuration for future issue routes."""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./campusfix.db")
# SQLite connections may be used across request threads.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite:") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def get_session():
    """Close each request's database session when it finishes."""
    with Session(engine) as session:
        yield session
