# Working in this repository

## Scope and workflow

- Keep changes scoped to the requested task. Report unrelated issues separately;
  do not silently fix them.
- Inspect existing code, tests, and README before editing. For external APIs,
  inspect the installed SDK and authoritative documentation before assuming
  behavior. Never invent API behavior.
- When the user requests a proposal first, wait for approval before editing.
  Once approved, complete the agreed scope without repeated confirmation.
- Preserve existing behavior during refactors, including HTTP responses,
  validation, logs, transaction ordering, and security boundaries.
- Prefer simple, readable code that the owner can understand and explain.
  Do not introduce dependencies, services, queues, workers, OAuth, or additional
  retries unless explicitly requested.
- Preserve unrelated working-tree changes. Do not commit unless instructed.
- Report changed files, verification results, and remaining limitations.
  Show the diff when requested.

## Project structure

- `app/main.py`: FastAPI setup, authenticated webhook, static UI.
- `app/pipeline.py`: shared classification, persistence, and notification flow.
- `app/classifier.py`: Gemini calls, bounded retries, explicit output validation.
- `app/database.py`: Psycopg SQL, table initialization, separate transactions.
- `app/notifications.py`: one Slack notification attempt.
- `app/config.py`, `app/security.py`: environment settings and API-key checks.
- `app/schemas.py`: validated input, classification, and response contracts.
- `app/demo.py`: three server-owned presets and process-local admission guard.
- `app/static/`: plain HTML, CSS, JavaScript; no frontend framework or build step.
- `tests/`: mocked integration boundaries and pipeline regression tests.

## Preserve these contracts

- `/webhook` requires `X-API-Key`; missing server configuration fails closed.
  Never expose `WEBHOOK_API_KEY` to the public UI.
- Send only the customer's message to Gemini, not separate identity fields.
- Use `response_json_schema=TriageResult.model_json_schema()` and explicitly
  validate with `TriageResult.model_validate_json(response.text)`. Do not weaken
  validation or accept invalid output as a successful classification.
- Gemini allows three total attempts only for HTTP 429/500/502/503/504, with
  jittered backoff. SDK retries remain disabled. Network and output-validation
  failures are not retried. Slack and database operations have no automatic retries.
- Commit the initial request before Slack. For authenticated high-priority
  requests, save `pending`, then separately record `sent` or `failed`.
  Slack failure must not undo the saved request.
- Initial database failures return 503. Notification-update failures use the
  separate 503 error body containing the saved `request_id`.
- `/demo` accepts only preset IDs and rejects extra fields. It uses the shared
  pipeline with Slack disabled; all demo rows use `not_required`.
- Preserve the demo's disabled default, cumulative process-local budget, atomic
  admission, and one active request. Failed admitted calls consume budget;
  rejected calls do not. Always release the active slot.
- Demo deployment assumes one worker/instance; restarts reset its allowance.

## Security and logging

- Never print or commit secrets, dump `.env`, or put credentials in browser code,
  storage, URLs, responses, or logs. Keep `.env.example` free of real credentials.
- Use parameterized SQL and preserve Pydantic input limits and output constraints.
- Logs may contain fixed failure categories, safe status codes, and saved request
  IDs. Never log customer names, emails, messages, Gemini output, connection URLs,
  webhook URLs, raw provider responses, or raw exception details/tracebacks.
- Keep HTTPX/HTTPCore logging at WARNING; verbose request logging can expose URLs.
- Render dynamic UI text with `textContent`, not `innerHTML`. Preserve Slack
  plain-text formatting and avoid automatic browser resubmission.
- Treat Supabase permissions/RLS, encrypted least-privilege database access,
  HTTPS, and deployment body-size limits as deployment checks. Do not claim
  they were verified from application tests.

## Verification

- Automated unit and application tests should mock Gemini, PostgreSQL, and Slack
  and use synthetic credentials. Any tests that intentionally use live services
  must be clearly separated and explicitly invoked.
- Add meaningful tests for changed behavior, failure paths, and security
  boundaries. Preserve existing regression coverage during refactors.
- Run relevant tests after changes; run the full suite for shared pipeline,
  authentication, or cross-cutting changes, and whenever requested.
- Clearly distinguish mocked/automated verification from real integration
  verification. Passing mocks does not prove provider availability, SQL execution,
  Slack delivery, or browser rendering.
- Use live services only within the user's authorized scope. State what was
  actually tested, what was not, and any warnings or blockers.
- For UI changes, check JavaScript syntax and browser behavior where available;
  disclose when visual/browser verification was unavailable.

Commands from the repository root (Git Bash):

```bash
./.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider
node --check app/static/app.js
git diff --check
```

Use targeted pytest paths when appropriate. Keep README and configuration examples
aligned with approved behavior changes when documentation is in scope.
