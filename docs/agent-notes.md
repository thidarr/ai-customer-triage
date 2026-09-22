# Agent-assisted development: selected cases

I used Codex as the coding agent while I defined requirements, reviewed
proposals and diffs, tested changes, and made final implementation decisions.
These cases highlight how code review, automated tests, and live integration
testing contributed different evidence.

## Case 1: Structured output passed mocks but failed against Gemini

**Context and implementation.** The backend needed Gemini to return category,
priority, summary, and suggested action under a strict Pydantic contract.
The initial agent implementation passed `response_schema=TriageResult` to
the SDK and explicitly validated the returned JSON locally.

**What I observed.** Mocked tests passed, but a real request through the application
failed with HTTP 502. Investigation revealed the underlying Gemini/provider error:
HTTP 400 `INVALID_ARGUMENT`. The schema generated from `extra="forbid"`
contained `additionalProperties: false`. Through that SDK/provider path,
the request included `additional_properties` in `generation_config.response_schema`,
which the provider rejected.

**Decision and correction.** I approved switching to
`response_json_schema=TriageResult.model_json_schema()`. We retained
`TriageResult.model_validate_json(response.text)` and the existing validation
rules, including rejection of extra fields and whitespace-only output strings.

**Verification.** Updated automated tests checked the JSON Schema request
parameter and SDK serialization using mocked transport. Subsequent live testing
confirmed that the corrected request worked with the configured model.

**Lesson.** Mocked tests verified application behavior and serialization, but
did not prove real provider compatibility. The correction addressed the
integration boundary without weakening local validation.

## Case 2: Live availability failures led to bounded retries

**Context and observation.** Later live requests failed because Gemini returned
HTTP 503 `UNAVAILABLE`, reporting high demand. The backend exposed these
classification failures as HTTP 502 and stopped before database storage or Slack.
This was a provider-availability problem, not an agent implementation mistake.

**Proposal and decision.** Codex proposed bounded classification retries and
safe diagnostic logging. I approved a change limited to Gemini, preserving
database, Slack, validation, and webhook response behavior.

**Implementation.** `app/classifier.py` now makes at most three total attempts
for provider HTTP 429, 500, 502, 503, and 504. The application owns the retry
loop, waiting 1–2 seconds and then 2–3 seconds with jitter. SDK retries remain
disabled with `attempts=1`, preventing nested retries. Network exceptions and
invalid model output are not retried. Logs report safe attempt, status, and
failure information without customer content, credentials, or raw provider errors.

**Verification.** Automated tests covered recovery, exhaustion after three
attempts, non-retryable failures, and log privacy. In later live testing, I
observed a real request recover after an initial 503. That observation confirmed
recovery in that instance, not guaranteed availability.

**Lesson.** Live behavior revealed a reliability improvement worth making.
Bounded retries handle some temporary failures while limiting repeated calls;
they do not solve sustained provider overload. Keeping retries inside
classification avoids repeating database inserts or Slack notifications.
