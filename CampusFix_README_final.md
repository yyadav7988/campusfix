# CampusFix

Campus maintenance issues are often reported in chats or passed along verbally, with no straightforward way to check what happened afterward. CampusFix gives each report a ticket ID and a status that students can look up later.

**Live demo:** https://campusfix-ik76.onrender.com  
**Repository:** https://github.com/yyadav7988/campusfix

## The workflow

1. **Report:** A student records the building, room, issue category and description.
2. **Track:** The app generates a ticket ID that can be used to view the report's status.
3. **Resolve:** A staff administrator signs in, reviews tickets and updates their progress.

For example, a faulty classroom projector can be reported without tracking down the right person to contact. The student keeps the ticket ID and checks it again after maintenance staff have acted.

## How it's built

- **Web app:** Python 3.12, FastAPI, Jinja2, HTML/CSS
- **Data:** SQLModel with a configurable database URL (SQLite for local development; PostgreSQL for hosted persistence)
- **Hosting:** Render; database connection and admin/session settings are supplied through environment variables

This project focuses on a practical issue-tracking workflow and making a small Python application deployable and maintainable. Docker, automated CI checks and monitoring are follow-up DevOps work; they should be marked complete only after they have been tested and merged into `main`.

## Run locally

With Python 3.12 installed, open PowerShell:

```powershell
git clone https://github.com/yyadav7988/campusfix.git
cd campusfix
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Configure the local `.env` before starting: set a strong admin password and random session secret, and use a local SQLite `DATABASE_URL` if you don't have PostgreSQL running. Do not commit `.env`. If the example file or configuration names change, follow the configuration in `app/`.

Open http://127.0.0.1:8000. To verify the demo, submit a sample issue, save its ticket ID, track it, and update its status through admin sign-in.

## Deployment

The Render web service installs packages from `requirements.txt` and starts the FastAPI app with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The hosted service needs its database URL and admin/session secrets set in Render's environment settings. PostgreSQL URLs using the `psycopg` driver require `psycopg[binary]` in the dependencies.

**Free-tier note:** Render may spin the web service down after 15 minutes without requests. A new visit wakes it automatically; the first load can take about a minute. Render's filesystem is temporary, so use an external PostgreSQL database if tickets must survive restarts.

## Limits

CampusFix is an introductory DevOps capstone, not a production university helpdesk. It uses a small administrator flow rather than university SSO and should be demonstrated using fictional campus details, not personal information.
