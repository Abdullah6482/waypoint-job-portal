import os
import re
import sqlite3
import tempfile
import unittest

from flask import Flask, request

from app import app, configure_app, init_db


class JobPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app.config.update(
            TESTING=True,
            APP_ENV="development",
            ALLOW_ADMIN_BOOTSTRAP=False,
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

        second_admin = app.test_cli_runner().invoke(
            args=["create-admin"],
            input="other@example.com\nAnother Admin\n",
        )
        self.assertNotEqual(second_admin.exit_code, 0)
        self.assertIn("An administrator account already exists.", second_admin.output)

    def test_production_requires_secret_and_enforces_secure_cookie_and_proxy_settings(self):
        candidate = Flask("production-settings-test")
        with self.assertRaisesRegex(RuntimeError, "persistent SECRET_KEY"):
            configure_app(candidate, {"APP_ENV": "production"})
        with self.assertRaisesRegex(RuntimeError, "at least 32 bytes"):
            configure_app(
                candidate,
                {"APP_ENV": "production", "SECRET_KEY": "too-short"},
            )

        configure_app(
            candidate,
            {
                "APP_ENV": "production",
                "SECRET_KEY": "s" * 64,
                "TRUSTED_PROXY_COUNT": "1",
                "FLASK_DEBUG": "1",
            },
        )
        self.assertTrue(candidate.config["SESSION_COOKIE_SECURE"])
        self.assertFalse(candidate.config["DEBUG"])
        self.assertEqual(candidate.config["TRUSTED_PROXY_COUNT"], 1)

        @candidate.get("/")
        def secure_request():
            return {"secure": request.is_secure}

        response = candidate.test_client().get(
            "/", headers={"X-Forwarded-Proto": "https"}
        )
        self.assertEqual(response.json, {"secure": True})

        no_proxy = Flask("untrusted-forwarded-header-test")
        configure_app(
            no_proxy,
            {"APP_ENV": "production", "SECRET_KEY": "s" * 64},
        )

        @no_proxy.get("/")
        def untrusted_request():
            return {"secure": request.is_secure}

        response = no_proxy.test_client().get(
            "/", headers={"X-Forwarded-Proto": "https"}
        )
        self.assertEqual(response.json, {"secure": False})

    def test_production_admin_bootstrap_requires_explicit_opt_in(self):
        app.config.update(APP_ENV="production", ALLOW_ADMIN_BOOTSTRAP=False)
        try:
            result = app.test_cli_runner().invoke(args=["create-admin"])
            app.config["ALLOW_ADMIN_BOOTSTRAP"] = True
            opted_in = app.test_cli_runner().invoke(
                args=["create-admin"],
                input=(
                    "production-admin@example.com\nProduction Admin\n"
                    "a-strong-admin-password\na-strong-admin-password\n"
                ),
            )
        finally:
            app.config.update(APP_ENV="development", ALLOW_ADMIN_BOOTSTRAP=False)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Production admin bootstrap is disabled.", result.output)
        self.assertEqual(opted_in.exit_code, 0, opted_in.output)

    def test_hsts_is_only_added_to_production_https_responses(self):
        app.config["APP_ENV"] = "production"
        try:
            secure_response = self.client.get(
                "/", environ_overrides={"wsgi.url_scheme": "https"}
            )
            http_response = self.client.get("/")
        finally:
            app.config["APP_ENV"] = "development"
        self.assertEqual(
            secure_response.headers["Strict-Transport-Security"],
            "max-age=31536000",
        )
        self.assertNotIn("Strict-Transport-Security", http_response.headers)


if __name__ == "__main__":
    unittest.main()
