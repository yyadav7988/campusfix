# Student workflow verification

From the project folder in PowerShell, using the prepared virtual environment:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

1. Open http://127.0.0.1:8000/report.
2. Enter fictional values: Science Block, 101, Electrical, Projector will not turn on.
3. Submit. Confirm the redirect to /tickets/{id}, a UUID ticket ID, Open status,
   Medium priority, the entered details, and timestamps labeled UTC.
4. Save the ticket ID, open /track, and enter it. Confirm the same details appear.
5. Restart the app and open the saved ticket URL. The ticket should remain in SQLite.
6. Visit /tickets/00000000-0000-4000-8000-000000000000. Expect a Ticket not found page (HTTP 404).
7. Enter an invalid ID on /track. Expect an inline error. Submit whitespace for Building
   on /report to verify server validation; the form should retain the other values.

No student names, email addresses, or phone numbers are requested. The ticket reference
allows anyone who has it to view that ticket.

## Automated checks

The tests use temporary SQLite files and do not modify campusfix.db.

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

The project targets Python 3.12. This machine currently provides Python 3.15.
Runtime verification used that installed version. SQLAlchemy 2.0.36's pure Python
wheel was installed locally because Windows Application Control blocked the
previous compiled SQLAlchemy build. No Windows security settings were changed.

For a fresh Python 3.12 environment, install requirements.txt before starting the app.
The database tables are created at application startup. DATABASE_URL defaults to
sqlite:///./campusfix.db and can be configured in .env or the process environment.
Run from the project folder so the default SQLite path is consistent.
