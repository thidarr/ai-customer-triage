# Customer Request Triage

Phase three validates customer requests, sends only their message to Gemini,
and saves the validated request and classification to PostgreSQL before returning
success. Slack is not implemented.

## Setup and run (Git Bash)

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
cp -n .env.example .env
```

Edit `.env` and set your `GEMINI_API_KEY` and a `GEMINI_MODEL` available to your
account that supports structured output. Add `DATABASE_URL` pointing to an existing
PostgreSQL database, for example:

```dotenv
DATABASE_URL=postgresql://username:password@localhost:5432/customer_triage
```

Replace the example credentials; URL-encode special characters in the username
or password. The Python driver does not install a PostgreSQL server. If needed,
create a database using pgAdmin or `psql` before initializing the table:

```bash
psql -U postgres -h localhost -c "CREATE DATABASE customer_triage;"
```

The database user in `DATABASE_URL` needs access to that database and permission
to create the table. Use your database owner account for this simple local setup.
The example values are placeholders.
Existing environment variables take precedence over `.env`. Never commit your
API key or database credentials. Initialize the table once, then start the server:

```bash
./.venv/Scripts/python.exe -m app.database
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
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
{
  "id": 42,
  "notification_status": "not_required",
  "category": "account",
  "priority": "medium",
  "summary": "Customer cannot access their account.",
  "suggested_action": "Help the customer recover account access."
}
```

Invalid requests return HTTP 422 with validation errors identifying the fields.
The classification above is illustrative; actual results depend on the message
and Gemini. Category and priority are determined independently.

Gemini receives the classification policy and only the validated `message` as
customer content. Customer ID, name, and email fields are not sent. Personal
information written inside the message itself is not automatically removed.

`TriageResult.model_json_schema()` is passed as `response_json_schema` to preserve
JSON Schema constraints without converting them to Gemini's `response_schema`
format. The returned text is
explicitly validated with `TriageResult.model_validate_json(response.text)`.
Only the four required fields are allowed. Categories are `billing`, `account`,
`technical`, or `general`; priorities are `low`, `medium`, or `high`. Summary
and suggested action must be nonempty strings after trimming whitespace.

API/network failures and invalid or absent model output return HTTP 502 with a
safe error message. Missing configuration returns HTTP 503. There is a 30-second
SDK HTTP timeout and one SDK attempt, with no application retry loop. Failed
classification never returns a successful result. Validation checks structure,
not the factual accuracy of the model's judgment.

## Persistence

After classification, the webhook selects `pending` for high priority and
`not_required` for medium/low, then saves one row in `customer_requests`.
The row contains all four validated customer fields, all four classification
fields, notification status, a null `notification_error`, and a database-generated
`id` and timezone-aware `created_at`. The original customer fields are stored
after existing validation/normalization, not as the untouched raw HTTP body.

`id` identifies a request; `customer_id` identifies a customer and is not unique.
The response includes the saved ID and status only after the transaction commits.
Connection, insert, or commit failures return HTTP 503 without a success result.
In the future, Slack must run only after this commit. High-priority records remain
`pending` in this phase; no notification is attempted.

The initialization command creates the table if absent; it does not migrate
existing tables. Inserts use SQL parameters and a connection context that commits
on success, rolls back on failure, and closes the connection. Each submission
creates a separate row; duplicate prevention and automatic retries are not added.
If a connection is lost during commit, its outcome can be uncertain; an error
response is not proof that no row exists.

To verify real persistence, submit a valid request through `/docs`, note its
returned ID, then use pgAdmin or a `psql` session connected to your database:

```sql
SELECT id, customer_id, category, priority, notification_status,
       notification_error, created_at
FROM customer_requests
ORDER BY id DESC
LIMIT 10;
```

Confirm that the returned ID exists and its priority matches the initial status.

## Tests

```bash
./.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
```

Tests cover input validation, message-only forwarding, structured-output setup,
output validation, provider failures, missing configuration, SQL parameters,
notification status, and connection/insert/commit failures. Gemini and database
connections are mocked: no real credentials or services are needed. These tests
do not verify actual PostgreSQL DDL execution; use the local check above as well.

## Files

- `app/__init__.py`: marks the application directory as a Python package.
- `app/main.py`: creates FastAPI and defines the webhook endpoint.
- `app/schemas.py`: defines input and classification validation rules.
- `app/classifier.py`: calls Gemini and returns a validated classification.
- `app/config.py`: reads Gemini and database configuration independently.
- `app/database.py`: defines the table, initializes it, and saves requests.
- `tests/test_webhook.py`: checks the endpoint and input validation.
- `tests/test_classifier.py`: checks classification using mocked Gemini calls.
- `tests/test_database.py`: checks persistence and database failures with mocks.
- `.env.example`: lists configuration placeholders.
- `requirements.txt`: lists application and test dependencies.
- `.gitignore`: excludes local secrets, environments, and generated caches.

## Later phases

Slack notifications and updates to `sent`/`failed` status are future work.
The table already allows those statuses and includes nullable `notification_error`.
