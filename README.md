<div align="center">
  <img src="screenshots/task-5-job-portal/01-job-marketplace-overview.png" alt="Waypoint Job Portal marketplace showing job search and open listings" width="100%">

  <h1>Waypoint Job Portal</h1>
  <p><strong>Find work that moves you.</strong></p>
  <p>A thoughtfully designed job marketplace for candidates, employers, and the people keeping the platform healthy.</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10 or later">
    <img src="https://img.shields.io/badge/Flask-3.1%2B-000000?logo=flask&logoColor=white" alt="Flask 3.1 or later">
    <img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
    <img src="https://img.shields.io/badge/License-Not%20specified-lightgrey" alt="License not specified">
  </p>
</div>

Waypoint brings job discovery, applications, and hiring into one responsive application. Candidates can find and track opportunities, employers can manage openings and review applicants, and administrators can oversee accounts and platform activity.

> **Project status:** This is a local-development and learning project. It has no production deployment configuration or license grant.

## What you can do

| Workspace | Capabilities |
| --- | --- |
| **Job seekers** | Search open roles by keyword and location; filter by work type and category; apply once per role with an optional portfolio/resume link and cover letter; track application status. |
| **Employers** | Create, edit, and close job listings; review candidate details and applications; update application statuses. |
| **Administrators** | View platform statistics and recent listings; activate or deactivate member accounts; manage job listings and applications. |
| **Everyone** | Browse job details, use responsive layouts, and receive clear validation and empty-state feedback. |

### Built-in safeguards

- Passwords are stored as Werkzeug password hashes, not plaintext.
- Forms use CSRF tokens; queries are parameterized; input and role/ownership checks are performed server-side.
- Session cookies use `HttpOnly` and `SameSite=Lax`; production always requires secure cookies.
- Responses include a restrictive Content Security Policy and common browser security headers.
- SQLite data is kept in the ignored `instance/` directory by default.

These safeguards are not a production security certification. Review the application and deployment configuration for your environment before handling real user data.

## Screenshots

<p align="center">
  <img src="screenshots/task-5-job-portal/02-search-by-keyword.png" alt="Searching job listings by keyword" width="49%">
  <img src="screenshots/task-5-job-portal/16-employer-hiring-dashboard.png" alt="Employer hiring dashboard with job listings and applications" width="49%">
</p>

The [complete feature screenshot gallery](screenshots/task-5-job-portal/README.md) includes all 25 Task 5 captures, descriptions, and demo-data notes.

The backend includes a job-deletion endpoint, but the current interface does not expose a delete control.

## Get started

Requires Python 3.10 or later. The application uses Flask and Python's built-in SQLite support.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python app.py
```

Open [http://127.0.0.1:5001](http://127.0.0.1:5001). The app creates its SQLite database at `instance/jobs.sqlite3` on first request. For local work, it can generate a random secret key if `SECRET_KEY` is unset; set a persistent random value to retain sessions across restarts.

### Create the first administrator (local development)

With the virtual environment active, run:

```bash
python -m flask --app app create-admin
```

Follow the prompts to provide the administrator email, name, and password. Password input is hidden. The command refuses to create another administrator once one exists.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Set to `production` to enable production safeguards. |
| `SECRET_KEY` | Random per process in development | Flask session signing key. Production requires a persistent value of at least 32 bytes; generate one with `python -c "import secrets; print(secrets.token_hex(32))"` and store it in your deployment's secret manager. |
| `DATABASE` | `instance/jobs.sqlite3` | SQLite database file path. |
| `HOST` | `127.0.0.1` | Local development server bind address. |
| `PORT` | `5001` | Local development server port. |
| `COOKIE_SECURE` | Unset | Set to `1` to require HTTPS for session cookies during development. Production always enables this. |
| `TRUSTED_PROXY_COUNT` | `0` | Number of trusted reverse proxies whose `X-Forwarded-Proto` value the app may use. Leave unset unless the app is reachable only through those proxies and they overwrite that header. |
| `ALLOW_ADMIN_BOOTSTRAP` | Unset | Production-only, one-command opt-in to create the first administrator from a trusted shell. |
| `FLASK_DEBUG` | Unset | Set to `1` to enable Flask debug mode for local development only. |

### Production WSGI server

The bundled Flask development server is not intended for public hosting. Install the dependencies, configure production mode and a persistent secret, then run Waitress:

```bash
export APP_ENV=production
export SECRET_KEY="<persistent value from your secret manager>"
export TRUSTED_PROXY_COUNT=1
waitress-serve --listen=127.0.0.1:8000 app:app
```

Terminate HTTPS at a reverse proxy that redirects HTTP to HTTPS, overwrites `X-Forwarded-Proto`, and is the only network path to Waitress. Set `TRUSTED_PROXY_COUNT` to the exact number of trusted proxies; the default is zero, so client-supplied forwarding headers are ignored. The app enables secure session cookies in production and adds HSTS on requests recognized as HTTPS. Configure the database path and persistent storage for your hosting environment. Review the full deployment and operational security requirements before handling real user data.

For a one-time production administrator bootstrap, run `python -m flask --app app create-admin` from a trusted shell with production secrets loaded and `ALLOW_ADMIN_BOOTSTRAP=1` set only for that command. The command is refused by default in production and refuses to add another admin if one already exists; remove the opt-in immediately afterward. Never expose this setting through the public web app or leave it enabled in the normal server environment. Do not commit `.env` files or live database data.

## Run the tests

```bash
python -m unittest discover -s tests -v
```

The test suite uses temporary SQLite databases and exercises listing search, registration and authentication flows, application submission and review, role and ownership enforcement, CSRF rejection, and administrator setup.

## Project layout

```text
.
├── app.py                 # Flask routes, validation, and SQLite data access
├── instance/              # Local runtime database (ignored by Git)
├── static/                # Styles and client-side authentication helpers
├── templates/             # Jinja templates
├── tests/                 # unittest suite
└── screenshots/
    └── task-5-job-portal/ # Feature captures and gallery index
```

## License

No license is currently specified. All rights are reserved by default; contact the project owner before reusing or distributing this code.
