"""Admin security and workflow checks using temporary SQLite databases."""

import re
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlmodel import Session

from app.main import app
from app.models import Ticket
import test_student_workflow


class AdminWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.config = patch.multiple("app.admin", ADMIN_ENABLED=True, ADMIN_PASSWORD="test-only-password")
        self.config.start()
        test_student_workflow.StudentWorkflowTests.setUp(self)

    def tearDown(self):
        test_student_workflow.StudentWorkflowTests.tearDown(self)
        self.config.stop()

    def token(self, response):
        return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)

    def login(self):
        csrf = self.token(self.client.get("/admin/login"))
        response = self.client.post("/admin/login", data={"password": "test-only-password", "csrf": csrf}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.login_response = response
        return self.token(self.client.get("/admin"))

    def create_ticket(self):
        response = self.client.post("/report", data=self.data, follow_redirects=False)
        return response.headers["location"].rsplit("/", 1)[1]

    def test_all_management_routes_require_authentication(self):
        ticket_id = self.create_ticket()
        for method, path in (("get", "/admin"), ("get", "/admin/tickets/" + ticket_id),
                             ("post", "/admin/tickets/" + ticket_id), ("post", "/admin/logout")):
            response = getattr(self.client, method)(path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/admin/login")
        with Session(self.engine) as session:
            self.assertEqual(session.get(Ticket, UUID(ticket_id)).status, "Open")

    def test_login_validation_rotation_and_signed_cookie(self):
        response = self.client.get("/admin/login")
        csrf = self.token(response)
        self.assertEqual(self.client.post("/admin/login", data={"password": "test-only-password"}).status_code, 403)
        response = self.client.post("/admin/login", data={"password": "wrong", "csrf": csrf})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('value="wrong"', response.text)
        self.login()
        self.assertNotEqual(csrf, self.token(self.client.get("/admin")))
        response = self.client.get("/admin")
        self.assertEqual(response.headers["cache-control"], "no-store")
        cookie = self.login_response.headers["set-cookie"]
        self.assertIn("httponly", cookie.lower())
        self.assertIn("samesite=lax", cookie.lower())
        self.assertIn("Max-Age=28800", cookie)
        self.client.cookies.clear()
        self.client.cookies.set("campusfix_session", "forged-session")
        self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 303)

    def test_csrf_protects_updates_and_logout(self):
        ticket_id = self.create_ticket()
        token = self.login()
        for csrf in ("", "wrong"):
            response = self.client.post("/admin/tickets/" + ticket_id,
                                        data={"status": "Resolved", "priority": "High", "csrf": csrf})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(self.client.post("/admin/logout", data={"csrf": csrf}).status_code, 403)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Ticket, UUID(ticket_id)).status, "Open")
        response = self.client.post("/admin/logout", data={"csrf": token}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 303)

    def test_update_is_persisted_and_visible_to_student(self):
        ticket_id = self.create_ticket()
        with Session(self.engine) as session:
            original = session.get(Ticket, UUID(ticket_id))
            created_at, updated_at = original.created_at, original.updated_at
        token = self.login()
        response = self.client.post("/admin/tickets/" + ticket_id,
                                    data={"status": "In Progress", "priority": "High", "csrf": token})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ticket updated.", response.text)
        with Session(self.engine) as session:
            ticket = session.get(Ticket, UUID(ticket_id))
            self.assertEqual((ticket.status, ticket.priority), ("In Progress", "High"))
            self.assertEqual(ticket.created_at, created_at)
            self.assertGreater(ticket.updated_at, updated_at)
        self.engine.dispose()
        response = self.client.get("/tickets/" + ticket_id)
        self.assertIn("In Progress", response.text)
        self.assertIn("High", response.text)

    def test_filters_counts_and_empty_state(self):
        first = self.create_ticket()
        second_data = self.data | {"building": "Library", "category": "Plumbing"}
        second = self.client.post("/report", data=second_data, follow_redirects=False).headers["location"].rsplit("/", 1)[1]
        token = self.login()
        self.client.post("/admin/tickets/" + second,
                         data={"status": "Resolved", "priority": "Low", "csrf": token})
        page = self.client.get("/admin").text
        self.assertIn("<span>Open</span><strong>1</strong>", page)
        self.assertIn("<span>Resolved</span><strong>1</strong>", page)
        self.assertIn("<span>In Progress</span><strong>0</strong>", page)
        for params in ({"status": "Open"}, {"priority": "Medium"}, {"category": "Electrical"},
                       {"status": "Open", "priority": "Medium", "category": "Electrical"}):
            response = self.client.get("/admin", params=params)
            self.assertIn(first, response.text)
            self.assertNotIn(second, response.text)
        response = self.client.get("/admin", params={"status": "Resolved", "priority": "High"})
        self.assertIn("No tickets to display", response.text)
        self.assertEqual(self.client.get("/admin?status=invalid").status_code, 422)

    def test_invalid_update_and_missing_ticket(self):
        ticket_id = self.create_ticket()
        token = self.login()
        for values in ({"status": "Deleted", "priority": "High"}, {"status": "Resolved", "priority": "Urgent"}):
            response = self.client.post("/admin/tickets/" + ticket_id, data=values | {"csrf": token})
            self.assertEqual(response.status_code, 422)
        with Session(self.engine) as session:
            ticket = session.get(Ticket, UUID(ticket_id))
            self.assertEqual((ticket.status, ticket.priority), ("Open", "Medium"))
        for reference in ("invalid", str(uuid4())):
            self.assertEqual(self.client.get("/admin/tickets/" + reference).status_code, 404)
            self.assertEqual(self.client.post("/admin/tickets/" + reference,
                data={"status": "Open", "priority": "Medium", "csrf": token}).status_code, 404)

    def test_missing_configuration_disables_admin(self):
        with patch("app.admin.ADMIN_ENABLED", False):
            self.assertEqual(self.client.get("/admin/login").status_code, 503)
            self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 303)
