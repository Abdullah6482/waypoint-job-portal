import os
import re
import sqlite3
import tempfile
import unittest

from app import app, init_db


class JobPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            DATABASE=os.path.join(self.temp_dir.name, "test.sqlite3"),
        )
        with app.app_context():
            init_db()
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def token(self, response):
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def register(self, role, name, email, company=""):
        response = self.client.get("/register")
        return self.client.post(
            "/register",
            data={
                "csrf_token": self.token(response),
                "name": name,
                "email": email,
                "password": "a-strong-password",
                "role": role,
                "company": company,
            },
            follow_redirects=True,
        )

    def create_job(self):
        employer = self.register(
            "employer", "Hiring Manager", "hiring@example.com", "Northstar"
        )
        return self.client.post(
            "/jobs/new",
            data={
                "csrf_token": self.token(employer),
                "title": "Product Designer",
                "location": "Remote",
                "job_type": "Full-time",
                "category": "Design",
                "salary_min": "80000",
                "salary_max": "110000",
                "description": "Help us make useful products.",
            },
            follow_redirects=True,
        )

    def test_employer_can_post_and_search_job(self):
        response = self.create_job()
        self.assertEqual(response.status_code, 200)
        search = self.client.get("/?q=Product&location=Remote&type=Full-time&category=Design")
        self.assertIn(b"Product Designer", search.data)
        self.assertIn(b"Northstar", search.data)
        detail = self.client.get("/jobs/1")
        self.assertIn(b"<h2>Northstar</h2>", detail.data)
        self.assertIn(b"<h1>Product Designer</h1>", detail.data)

    def test_seeker_can_apply_once_and_employer_can_review(self):
        self.create_job()
        self.client.post("/logout", data={"csrf_token": self.token(self.client.get("/"))})
        response = self.register("seeker", "Alex Candidate", "alex@example.com")
        detail = self.client.get("/jobs/1")
        applied = self.client.post(
            "/jobs/1/apply",
            data={
                "csrf_token": self.token(detail),
                "resume_url": "https://example.com/resume",
                "cover_letter": "I would love to join the team.",
            },
            follow_redirects=True,
        )
        self.assertIn(b"applied for this role", applied.data)
        duplicate = self.client.post(
            "/jobs/1/apply",
            data={"csrf_token": self.token(applied)},
            follow_redirects=True,
        )
        self.assertIn(b"already applied", duplicate.data)
        with app.app_context():
            connection = sqlite3.connect(app.config["DATABASE"])
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM applications"
                ).fetchone()[0]
            finally:
                connection.close()
        self.assertEqual(count, 1)

        self.client.post("/logout", data={"csrf_token": self.token(self.client.get("/"))})
        login_page = self.client.get("/login")
        employer = self.client.post(
            "/login",
            data={
                "csrf_token": self.token(login_page),
                "email": "hiring@example.com",
                "password": "a-strong-password",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Alex Candidate", employer.data)
        reviewed = self.client.post(
            "/applications/1/status",
            data={
                "csrf_token": self.token(employer),
                "status": "Reviewing",
            },
            follow_redirects=True,
        )
        self.assertEqual(reviewed.status_code, 200)

    def test_job_posting_requires_employer_and_csrf(self):
        response = self.client.get("/jobs/new")
        self.assertEqual(response.status_code, 302)
        rejected = self.client.post(
            "/register",
            data={"name": "Alex", "email": "alex@example.com"},
        )
        self.assertEqual(rejected.status_code, 400)

    def test_other_employer_cannot_edit_listing(self):
        self.create_job()
        self.client.post("/logout", data={"csrf_token": self.token(self.client.get("/"))})
        self.register("employer", "Another Manager", "other@example.com", "Other Co")
        response = self.client.get("/jobs/1/edit")
        self.assertEqual(response.status_code, 403)

    def test_create_admin_command_bootstraps_database_and_dashboard(self):
        result = app.test_cli_runner().invoke(
            args=["create-admin"],
            input=(
                "admin@example.com\nPlatform Admin\n"
                "a-strong-admin-password\na-strong-admin-password\n"
            ),
        )
        self.assertEqual(result.exit_code, 0, result.output)
        login_page = self.client.get("/login")
        response = self.client.post(
            "/login",
            data={
                "csrf_token": self.token(login_page),
                "email": "admin@example.com",
                "password": "a-strong-admin-password",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PLATFORM OVERVIEW", response.data)


if __name__ == "__main__":
    unittest.main()
