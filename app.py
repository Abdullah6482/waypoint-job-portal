import os
import re
import secrets
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

import click
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


ROOT = Path(__file__).resolve().parent
app = Flask(__name__, instance_path=str(ROOT / "instance"))
Path(app.instance_path).mkdir(parents=True, exist_ok=True)


def configure_app(application, environ=None):
    environ = os.environ if environ is None else environ
    environment = environ.get("APP_ENV", "development").strip().lower()
    if environment not in ("development", "production"):
        raise RuntimeError("APP_ENV must be either 'development' or 'production'.")

    secret_key = environ.get("SECRET_KEY")
    if environment == "production":
        if not secret_key or len(secret_key.encode("utf-8")) < 32:
            raise RuntimeError(
                "Production requires a persistent SECRET_KEY of at least 32 bytes."
            )
    elif not secret_key:
        secret_key = secrets.token_hex(32)

    try:
        trusted_proxy_count = int(environ.get("TRUSTED_PROXY_COUNT", "0"))
    except ValueError as error:
        raise RuntimeError("TRUSTED_PROXY_COUNT must be a non-negative integer.") from error
    if trusted_proxy_count < 0:
        raise RuntimeError("TRUSTED_PROXY_COUNT must be a non-negative integer.")

    application.config.update(
        APP_ENV=environment,
        DEBUG=environment == "development" and environ.get("FLASK_DEBUG") == "1",
        SECRET_KEY=secret_key,
        DATABASE=environ.get(
            "DATABASE", str(Path(application.instance_path) / "jobs.sqlite3")
        ),
        MAX_CONTENT_LENGTH=16 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(
            environment == "production" or environ.get("COOKIE_SECURE") == "1"
        ),
        ALLOW_ADMIN_BOOTSTRAP=environ.get("ALLOW_ADMIN_BOOTSTRAP") == "1",
        TRUSTED_PROXY_COUNT=trusted_proxy_count,
    )
    if trusted_proxy_count:
        application.wsgi_app = ProxyFix(
            application.wsgi_app, x_proto=trusted_proxy_count
        )
    return application


configure_app(app)

JOB_TYPES = ("Full-time", "Part-time", "Contract", "Internship", "Remote")
CATEGORIES = (
    "Engineering",
    "Design",
    "Product",
    "Marketing",
    "Customer Support",
    "Operations",
    "Finance",
    "Other",
)
APPLICATION_STATUSES = ("Pending", "Reviewing", "Accepted", "Rejected")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('seeker', 'employer', 'admin')),
            company TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT NOT NULL,
            job_type TEXT NOT NULL,
            category TEXT NOT NULL,
            salary_min INTEGER,
            salary_max INTEGER,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            seeker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cover_letter TEXT NOT NULL DEFAULT '',
            resume_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK (status IN ('Pending', 'Reviewing', 'Accepted', 'Rejected')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, seeker_id)
        );
        CREATE INDEX IF NOT EXISTS jobs_status_date ON jobs(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS jobs_employer ON jobs(employer_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS applications_job ON applications(job_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS applications_seeker ON applications(seeker_id, created_at DESC);
        """
    )
    db.commit()


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.before_request
def initialize_and_check_account():
    init_db()
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, description="This form expired. Reload the page and try again.")
    if "user_id" in session:
        user = get_db().execute(
            "SELECT id, name, role, company, is_active FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()
        if user is None or not user["is_active"]:
            session.clear()
            flash("Your account is unavailable. Please contact the administrator.", "error")
            return redirect(url_for("login"))
        g.user = user


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'self'"
    )
    if app.config["APP_ENV"] == "production" and request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.context_processor
def template_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {
        "csrf_token": session["csrf_token"],
        "current_user": getattr(g, "user", None),
        "job_types": JOB_TYPES,
        "categories": CATEGORIES,
        "application_statuses": APPLICATION_STATUSES,
    }


def role_required(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(**kwargs):
            if "user_id" not in session:
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            if g.user["role"] not in roles:
                abort(403)
            return view(**kwargs)

        return wrapped

    return decorate


def clean_text(value, label, maximum, required=True):
    value = (value or "").strip()
    if required and not value:
        raise ValueError(f"{label} is required.")
    if len(value) > maximum:
        raise ValueError(f"{label} must be {maximum} characters or fewer.")
    return value


def valid_email(value):
    return len(value) <= 254 and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value)


@app.route("/")
def home():
    search = request.args.get("q", "").strip()[:100]
    location = request.args.get("location", "").strip()[:100]
    job_type = request.args.get("type", "").strip()
    category = request.args.get("category", "").strip()
    conditions = ["j.status = 'open'", "u.is_active = 1"]
    params = []
    if search:
        conditions.append("(j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if location:
        conditions.append("j.location LIKE ?")
        params.append(f"%{location}%")
    if job_type in JOB_TYPES:
        conditions.append("j.job_type = ?")
        params.append(job_type)
    else:
        job_type = ""
    if category in CATEGORIES:
        conditions.append("j.category = ?")
        params.append(category)
    else:
        category = ""
    jobs = get_db().execute(
        f"""
        SELECT j.*, u.name AS employer_name
        FROM jobs j JOIN users u ON u.id = j.employer_id
        WHERE {" AND ".join(conditions)}
        ORDER BY j.created_at DESC, j.id DESC
        LIMIT 100
        """,
        params,
    ).fetchall()
    return render_template(
        "home.html",
        jobs=jobs,
        search=search,
        location=location,
        selected_type=job_type,
        selected_category=category,
    )


@app.route("/register", methods=("GET", "POST"))
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        company = request.form.get("company", "").strip()
        error = None
        if not name or len(name) > 80:
            error = "Enter a name between 1 and 80 characters."
        elif not valid_email(email):
            error = "Enter a valid email address."
        elif len(password) < 10 or len(password) > 128:
            error = "Password must be between 10 and 128 characters."
        elif role not in ("seeker", "employer"):
            error = "Choose a valid account type."
        elif role == "employer" and (not company or len(company) > 100):
            error = "Enter your company name (up to 100 characters)."
        if error:
            flash(error, "error")
        else:
            try:
                cursor = get_db().execute(
                    """
                    INSERT INTO users (name, email, password_hash, role, company)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, email, generate_password_hash(password), role, company if role == "employer" else ""),
                )
                get_db().commit()
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")
            else:
                session.clear()
                session["user_id"] = cursor.lastrowid
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=("GET", "POST"))
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, password_hash, is_active FROM users WHERE email = ?", (email,)
        ).fetchone()
        if (
            user is None
            or not user["is_active"]
            or len(password) > 128
            or not check_password_hash(user["password_hash"], password)
        ):
            flash("Email or password is incorrect.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            destination = request.args.get("next", "")
            if not destination.startswith("/") or destination.startswith("//"):
                destination = url_for("dashboard")
            return redirect(destination)
    return render_template("auth.html", mode="login")


@app.post("/logout")
def logout():
    if "user_id" not in session:
        return redirect(url_for("login"))
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
@role_required("seeker", "employer", "admin")
def dashboard():
    db = get_db()
    user = g.user
    if user["role"] == "seeker":
        applications = db.execute(
            """
            SELECT a.*, j.title, j.company, j.location, j.job_type, j.status AS job_status
            FROM applications a JOIN jobs j ON j.id = a.job_id
            WHERE a.seeker_id = ? ORDER BY a.created_at DESC LIMIT 50
            """,
            (user["id"],),
        ).fetchall()
        return render_template("dashboard.html", applications=applications)
    if user["role"] == "employer":
        jobs = db.execute(
            """
            SELECT j.*,
                (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.id) AS application_count
            FROM jobs j WHERE j.employer_id = ?
            ORDER BY j.created_at DESC LIMIT 50
            """,
            (user["id"],),
        ).fetchall()
        applications = db.execute(
            """
            SELECT a.*, j.title AS job_title, u.name AS seeker_name, u.email AS seeker_email
            FROM applications a JOIN jobs j ON j.id = a.job_id
            JOIN users u ON u.id = a.seeker_id
            WHERE j.employer_id = ? ORDER BY a.created_at DESC LIMIT 100
            """,
            (user["id"],),
        ).fetchall()
        return render_template("dashboard.html", jobs=jobs, applications=applications)

    stats = {
        row["label"]: row["total"]
        for row in db.execute(
            """
            SELECT 'users' AS label, COUNT(*) AS total FROM users WHERE role != 'admin'
            UNION ALL SELECT 'jobs', COUNT(*) FROM jobs
            UNION ALL SELECT 'open_jobs', COUNT(*) FROM jobs WHERE status = 'open'
            UNION ALL SELECT 'applications', COUNT(*) FROM applications
            """
        ).fetchall()
    }
    users = db.execute(
        "SELECT id, name, email, role, company, is_active, created_at FROM users ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    recent_jobs = db.execute(
        """
        SELECT j.id, j.title, j.company, j.status, j.created_at, u.name AS employer_name
        FROM jobs j JOIN users u ON u.id = j.employer_id
        ORDER BY j.created_at DESC LIMIT 10
        """
    ).fetchall()
    return render_template("dashboard.html", stats=stats, users=users, recent_jobs=recent_jobs)


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    job = get_db().execute(
        """
        SELECT j.*, u.name AS employer_name
        FROM jobs j JOIN users u ON u.id = j.employer_id
        WHERE j.id = ? AND u.is_active = 1
        """,
        (job_id,),
    ).fetchone()
    if job is None:
        abort(404)
    application = None
    if "user_id" in session and g.user["role"] == "seeker":
        application = get_db().execute(
            "SELECT id, status FROM applications WHERE job_id = ? AND seeker_id = ?",
            (job_id, session["user_id"]),
        ).fetchone()
    return render_template("job_detail.html", job=job, application=application)


@app.route("/jobs/new", methods=("GET", "POST"))
@role_required("employer")
def create_job():
    if request.method == "POST":
        try:
            data = validate_job_form()
        except ValueError as error:
            flash(str(error), "error")
        else:
            db = get_db()
            db.execute(
                """
                INSERT INTO jobs
                  (employer_id, title, company, location, job_type, category,
                   salary_min, salary_max, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    data[0],
                    g.user["company"],
                    *data[1:],
                ),
            )
            db.commit()
            flash("Your job listing is live.", "success")
            return redirect(url_for("dashboard"))
    return render_template("job_form.html", mode="new", job=None)


def validate_job_form():
    title = clean_text(request.form.get("title"), "Job title", 100)
    location = clean_text(request.form.get("location"), "Location", 100)
    job_type = request.form.get("job_type", "")
    category = request.form.get("category", "")
    description = clean_text(request.form.get("description"), "Description", 10000)
    if job_type not in JOB_TYPES:
        raise ValueError("Choose a valid job type.")
    if category not in CATEGORIES:
        raise ValueError("Choose a valid category.")

    salaries = []
    for field in ("salary_min", "salary_max"):
        raw = request.form.get(field, "").strip()
        if not raw:
            salaries.append(None)
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as error:
            raise ValueError("Salary must be a whole number between 1 and 10,000,000.") from error
        if not value.is_finite() or value < 1 or value > 10_000_000 or value != value.to_integral_value():
            raise ValueError("Salary must be a whole number between 1 and 10,000,000.")
        salaries.append(int(value))
    if salaries[0] and salaries[1] and salaries[0] > salaries[1]:
        raise ValueError("Minimum salary cannot exceed maximum salary.")
    return title, location, job_type, category, salaries[0], salaries[1], description


def can_manage_job(job_id):
    job = get_db().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        abort(404)
    if g.user["role"] != "admin" and job["employer_id"] != g.user["id"]:
        abort(403)
    return job


@app.route("/jobs/<int:job_id>/edit", methods=("GET", "POST"))
@role_required("employer", "admin")
def edit_job(job_id):
    job = can_manage_job(job_id)
    if request.method == "POST":
        try:
            data = validate_job_form()
            status = request.form.get("status", "open")
            if status not in ("open", "closed"):
                raise ValueError("Choose a valid listing status.")
        except ValueError as error:
            flash(str(error), "error")
        else:
            get_db().execute(
                """
                UPDATE jobs SET title = ?, location = ?, job_type = ?, category = ?,
                    salary_min = ?, salary_max = ?, description = ?, status = ?
                WHERE id = ?
                """,
                (*data[:4], data[4], data[5], data[6], status, job_id),
            )
            get_db().commit()
            flash("Job listing updated.", "success")
            return redirect(url_for("dashboard"))
    return render_template("job_form.html", mode="edit", job=job)


@app.post("/jobs/<int:job_id>/delete")
@role_required("employer", "admin")
def delete_job(job_id):
    can_manage_job(job_id)
    get_db().execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    get_db().commit()
    flash("Job listing and its applications were deleted.", "success")
    return redirect(url_for("dashboard"))


@app.post("/jobs/<int:job_id>/apply")
@role_required("seeker")
def apply_for_job(job_id):
    job = get_db().execute(
        "SELECT id, status FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    if job is None:
        abort(404)
    if job["status"] != "open":
        flash("This job is no longer accepting applications.", "error")
        return redirect(url_for("job_detail", job_id=job_id))
    cover_letter = request.form.get("cover_letter", "").strip()
    resume_url = request.form.get("resume_url", "").strip()
    parsed_url = urlparse(resume_url)
    if len(cover_letter) > 5000:
        flash("Cover letter must be 5,000 characters or fewer.", "error")
    elif resume_url and (
        len(resume_url) > 500
        or parsed_url.scheme not in ("http", "https")
        or not parsed_url.netloc
    ):
        flash("Resume link must be a valid HTTP or HTTPS URL.", "error")
    else:
        try:
            get_db().execute(
                """
                INSERT INTO applications (job_id, seeker_id, cover_letter, resume_url)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, g.user["id"], cover_letter, resume_url),
            )
            get_db().commit()
        except sqlite3.IntegrityError:
            flash("You have already applied for this job.", "error")
        else:
            flash("Application submitted. Good luck!", "success")
    return redirect(url_for("job_detail", job_id=job_id))


@app.post("/applications/<int:application_id>/status")
@role_required("employer", "admin")
def update_application_status(application_id):
    application = get_db().execute(
        """
        SELECT a.id, j.employer_id
        FROM applications a JOIN jobs j ON j.id = a.job_id
        WHERE a.id = ?
        """,
        (application_id,),
    ).fetchone()
    if application is None:
        abort(404)
    if g.user["role"] != "admin" and application["employer_id"] != g.user["id"]:
        abort(403)
    status = request.form.get("status", "")
    if status not in APPLICATION_STATUSES:
        abort(400, description="Choose a valid application status.")
    get_db().execute(
        "UPDATE applications SET status = ? WHERE id = ?", (status, application_id)
    )
    get_db().commit()
    flash("Application status updated.", "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/users/<int:user_id>/toggle")
@role_required("admin")
def toggle_user(user_id):
    if user_id == g.user["id"]:
        flash("You cannot deactivate your own administrator account.", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    user = db.execute("SELECT id, is_active, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if user["role"] == "admin":
        flash("Administrator accounts cannot be changed here.", "error")
    else:
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (0 if user["is_active"] else 1, user_id))
        db.commit()
        flash("Account deactivated." if user["is_active"] else "Account activated.", "success")
    return redirect(url_for("dashboard"))


@app.cli.command("create-admin")
def create_admin():
    """Create the first administrator account with hidden password prompts."""
    if (
        app.config["APP_ENV"] == "production"
        and not app.config["ALLOW_ADMIN_BOOTSTRAP"]
    ):
        raise click.ClickException(
            "Production admin bootstrap is disabled. Set "
            "ALLOW_ADMIN_BOOTSTRAP=1 only for this one-time command."
        )
    init_db()
    admin_exists = get_db().execute(
        "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
    ).fetchone()
    if admin_exists:
        raise click.ClickException("An administrator account already exists.")
    email = click.prompt("Administrator email").strip().lower()
    if not valid_email(email):
        raise click.ClickException("Enter a valid email address.")
    name = click.prompt("Administrator name").strip()
    if not name or len(name) > 80:
        raise click.ClickException("Name must be between 1 and 80 characters.")
    password = click.prompt("Password (at least 10 characters)", hide_input=True, confirmation_prompt=True)
    if len(password) < 10 or len(password) > 128:
        raise click.ClickException("Password must be between 10 and 128 characters.")
    try:
        get_db().execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
            (name, email, generate_password_hash(password)),
        )
        get_db().commit()
    except sqlite3.IntegrityError as error:
        raise click.ClickException("An account with that email already exists.") from error
    click.echo("Administrator account created.")


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5001")),
        debug=app.config["DEBUG"],
    )
