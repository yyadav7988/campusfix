"""Run with: python -m unittest discover -s tests -v."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.main import app
from app.database import get_session
from app.models import Ticket


class StudentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + (Path(self.temp.name) / "tickets.db").as_posix(),
            connect_args={"check_same_thread": False},
        )
        def session_override():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_session] = session_override
        self.engine_patch = patch("app.main.engine", self.engine)
        self.engine_patch.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.data = dict(building=" Science Block ", room="101",
                         category="Electrical", description="Projector will not turn on.")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        self.engine_patch.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_create_retrieve_and_track_persisted_ticket(self):
        response = self.client.post("/report", data=self.data, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        ticket_id = response.headers["location"].rsplit("/", 1)[1]
        self.assertEqual(UUID(ticket_id).version, 4)
        with Session(self.engine) as session:
            ticket = session.get(Ticket, UUID(ticket_id))
            self.assertEqual(ticket.building, "Science Block")
            self.assertEqual(ticket.status, "Open")
            self.assertEqual(ticket.priority, "Medium")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            self.assertLess(abs((now - ticket.created_at).total_seconds()), 10)
            self.assertLess(abs((now - ticket.updated_at).total_seconds()), 10)
        self.engine.dispose()  # Reopen SQLite, rather than relying on a live connection.
        response = self.client.get("/tickets/" + ticket_id)
        self.assertEqual(response.status_code, 200)
        for value in (ticket_id, "Science Block", "Open", "Medium", "UTC"):
            self.assertIn(value, response.text)
        response = self.client.get("/track", params={"ticket_id": ticket_id})
        self.assertEqual(response.status_code, 200)
        self.assertIn(ticket_id, response.text)

    def test_validation_does_not_create_tickets(self):
        for changes in (
            {"building": " "}, {"room": ""}, {"description": ""},
            {"category": "invalid"}, {"building": "x" * 101},
            {"room": "x" * 51}, {"description": "x" * 2001},
        ):
            with self.subTest(changes=changes):
                response = self.client.post("/report", data=self.data | changes)
                self.assertEqual(response.status_code, 422)
                self.assertIn('aria-invalid="true"', response.text)
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(Ticket)).all(), [])

    def test_missing_and_malformed_references(self):
        for reference in (str(uuid4()), "invalid"):
            response = self.client.get("/tickets/" + reference)
            self.assertEqual(response.status_code, 404)
            self.assertIn("Ticket not found", response.text)
        self.assertEqual(self.client.get("/track", params={"ticket_id": ""}).status_code, 422)
        self.assertEqual(self.client.get("/track", params={"ticket_id": "invalid"}).status_code, 422)

    def test_defaults_unique_ids_and_html_escaping(self):
        data = self.data | {"description": "<script>alert(1)</script>", "status": "Closed", "priority": "High", "id": str(uuid4())}
        first = self.client.post("/report", data=data)
        second = self.client.post("/report", data=data)
        self.assertNotEqual(first.url, second.url)
        self.assertIn("&lt;script&gt;", first.text)
        self.assertNotIn("<script>alert(1)</script>", first.text)
        with Session(self.engine) as session:
            for ticket in session.exec(select(Ticket)):
                self.assertEqual(ticket.status, "Open")
                self.assertEqual(ticket.priority, "Medium")

    def test_pages_health_and_assets(self):
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})
        for path in ("/", "/report", "/track", "/static/css/styles.css"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/tickets").status_code, 404)


if __name__ == "__main__":
    unittest.main()
