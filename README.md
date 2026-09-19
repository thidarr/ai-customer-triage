# Customer Request Triage

Phase one receives customer requests through a FastAPI webhook and validates
them using Pydantic. A successful response acknowledges receipt only; requests
are not stored or classified yet.

## Setup and run (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs to try the webhook interactively.

## Webhook

Send `POST /webhook` with a JSON body:

```json
{
  "customer_id": "customer_123",
  "customer_name": "Alex Smith",
  "customer_email": "alex@example.com",
  "message": "Please help me access my account."
}
```

All four fields are required. ID, name, and message must be strings with at
least one character after trimming surrounding whitespace. Email must be a
valid email address; validation does not verify mailbox ownership or delivery.
Missing, null, empty, and whitespace-only messages are rejected. Nonempty text
is accepted without attempting to judge its meaning. Unrecognized fields are
ignored, following Pydantic's default behavior.

Valid requests return HTTP 200:

```json
{"status": "received", "customer_id": "customer_123"}
```

Invalid requests return HTTP 422 with validation errors identifying the fields.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover valid input, invalid email, missing required fields, empty and
whitespace-only messages, null and numeric messages, and whitespace trimming.

## Files

- `app/__init__.py`: marks the application directory as a Python package.
- `app/main.py`: creates FastAPI and defines the webhook endpoint.
- `app/schemas.py`: defines the incoming request and its validation rules.
- `tests/test_webhook.py`: checks the endpoint and input validation.
- `requirements.txt`: lists application and test dependencies.
- `.gitignore`: excludes local secrets, environments, and generated caches.

## Later phases

Gemini classification, AI output validation, PostgreSQL storage, and Slack
notifications are planned but not implemented. The approved future database
design includes `notification_status` (`not_required`, `pending`, `sent`,
`failed`) and nullable `notification_error` for tracking notification outcomes.
