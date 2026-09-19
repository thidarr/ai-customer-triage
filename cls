[1mdiff --git a/.gitignore b/.gitignore[m
[1mnew file mode 100644[m
[1mindex 0000000..d8c1352[m
[1m--- /dev/null[m
[1m+++ b/.gitignore[m
[36m@@ -0,0 +1,5 @@[m
[32m+[m[32m.venv/[m
[32m+[m[32m.env[m
[32m+[m[32m__pycache__/[m
[32m+[m[32m*.py[cod][m
[32m+[m[32m.pytest_cache/[m
[1mdiff --git a/README.md b/README.md[m
[1mnew file mode 100644[m
[1mindex 0000000..3b1b3a3[m
[1m--- /dev/null[m
[1m+++ b/README.md[m
[36m@@ -0,0 +1,68 @@[m
[32m+[m[32m# Customer Request Triage[m
[32m+[m
[32m+[m[32mPhase one receives customer requests through a FastAPI webhook and validates[m
[32m+[m[32mthem using Pydantic. A successful response acknowledges receipt only; requests[m
[32m+[m[32mare not stored or classified yet.[m
[32m+[m
[32m+[m[32m## Setup and run (PowerShell)[m
[32m+[m
[32m+[m[32m```powershell[m
[32m+[m[32mpython -m venv .venv[m
[32m+[m[32m.\.venv\Scripts\python.exe -m pip install -r requirements.txt[m
[32m+[m[32m.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload[m
[32m+[m[32m```[m
[32m+[m
[32m+[m[32mOpen http://127.0.0.1:8000/docs to try the webhook interactively.[m
[32m+[m
[32m+[m[32m## Webhook[m
[32m+[m
[32m+[m[32mSend `POST /webhook` with a JSON body:[m
[32m+[m
[32m+[m[32m```json[m
[32m+[m[32m{[m
[32m+[m[32m  "customer_id": "customer_123",[m
[32m+[m[32m  "customer_name": "Alex Smith",[m
[32m+[m[32m  "customer_email": "alex@example.com",[m
[32m+[m[32m  "message": "Please help me access my account."[m
[32m+[m[32m}[m
[32m+[m[32m```[m
[32m+[m
[32m+[m[32mAll four fields are required. ID, name, and message must be strings with at[m
[32m+[m[32mleast one character after trimming surrounding whitespace. Email must be a[m
[32m+[m[32mvalid email address; validation does not verify mailbox ownership or delivery.[m
[32m+[m[32mMissing, null, empty, and whitespace-only messages are rejected. Nonempty text[m
[32m+[m[32mis accepted without attempting to judge its meaning. Unrecognized fields are[m
[32m+[m[32mignored, following Pydantic's default behavior.[m
[32m+[m
[32m+[m[32mValid requests return HTTP 200:[m
[32m+[m
[32m+[m[32m```json[m
[32m+[m[32m{"status": "received", "customer_id": "customer_123"}[m
[32m+[m[32m```[m
[32m+[m
[32m+[m[32mInvalid requests return HTTP 422 with validation errors identifying the fields.[m
[32m+[m
[32m+[m[32m## Tests[m
[32m+[m
[32m+[m[32m```powershell[m
[32m+[m[32m.\.venv\Scripts\python.exe -m pytest -q[m
[32m+[m[32m```[m
[32m+[m
[32m+[m[32mTests cover valid input, invalid email, missing required fields, empty and[m
[32m+[m[32mwhitespace-only messages, null and numeric messages, and whitespace trimming.[m
[32m+[m
[32m+[m[32m## Files[m
[32m+[m
[32m+[m[32m- `app/__init__.py`: marks the application directory as a Python package.[m
[32m+[m[32m- `app/main.py`: creates FastAPI and defines the webhook endpoint.[m
[32m+[m[32m- `app/schemas.py`: defines the incoming request and its validation rules.[m
[32m+[m[32m- `tests/test_webhook.py`: checks the endpoint and input validation.[m
[32m+[m[32m- `requirements.txt`: lists application and test dependencies.[m
[32m+[m[32m- `.gitignore`: excludes local secrets, environments, and generated caches.[m
[32m+[m
[32m+[m[32m## Later phases[m
[32m+[m
[32m+[m[32mGemini classification, AI output validation, PostgreSQL storage, and Slack[m
[32m+[m[32mnotifications are planned but not implemented. The approved future database[m
[32m+[m[32mdesign includes `notification_status` (`not_required`, `pending`, `sent`,[m
[32m+[m[32m`failed`) and nullable `notification_error` for tracking notification outcomes.[m
[1mdiff --git a/app/__init__.py b/app/__init__.py[m
[1mnew file mode 100644[m
[1mindex 0000000..e69de29[m
[1mdiff --git a/app/main.py b/app/main.py[m
[1mnew file mode 100644[m
[1mindex 0000000..de925b1[m
[1m--- /dev/null[m
[1m+++ b/app/main.py[m
[36m@@ -0,0 +1,11 @@[m
[32m+[m[32mfrom fastapi import FastAPI[m
[32m+[m
[32m+[m[32mfrom app.schemas import CustomerRequest[m
[32m+[m
[32m+[m[32mapp = FastAPI(title="Customer Request Triage")[m
[32m+[m
[32m+[m
[32m+[m[32m@app.post("/webhook")[m
[32m+[m[32mdef receive_customer_request(request: CustomerRequest) -> dict[str, str]:[m
[32m+[m[32m    """Acknowledge a validated request. Persistence comes in a later phase."""[m
[32m+[m[32m    return {"status": "received", "customer_id": request.customer_id}[m
[1mdiff --git a/app/schemas.py b/app/schemas.py[m
[1mnew file mode 100644[m
[1mindex 0000000..0e98bcd[m
[1m--- /dev/null[m
[1m+++ b/app/schemas.py[m
[36m@@ -0,0 +1,12 @@[m
[32m+[m[32mfrom pydantic import BaseModel, ConfigDict, EmailStr, Field[m
[32m+[m
[32m+[m
[32m+[m[32mclass CustomerRequest(BaseModel):[m
[32m+[m[32m    """Required customer details and the message submitted to the webhook."""[m
[32m+[m
[32m+[m[32m    model_config = ConfigDict(str_strip_whitespace=True)[m
[32m+[m
[32m+[m[32m    customer_id: str = Field(min_length=1)[m
[32m+[m[32m    customer_name: str = Field(min_length=1)[m
[32m+[m[32m    customer_email: EmailStr[m
[32m+[m[32m    message: str = Field(min_length=1)[m
[1mdiff --git a/requirements.txt b/requirements.txt[m
[1mnew file mode 100644[m
[1mindex 0000000..be59707[m
[1m--- /dev/null[m
[1m+++ b/requirements.txt[m
[36m@@ -0,0 +1,5 @@[m
[32m+[m[32mfastapi>=0.115,<1.0[m
[32m+[m[32mpydantic[email]>=2.10,<3.0[m
[32m+[m[32muvicorn>=0.30,<1.0[m
[32m+[m[32mhttpx>=0.27,<1.0[m
[32m+[m[32mpytest>=8.0,<10.0[m
[1mdiff --git a/tests/test_webhook.py b/tests/test_webhook.py[m
[1mnew file mode 100644[m
[1mindex 0000000..887780b[m
[1m--- /dev/null[m
[1m+++ b/tests/test_webhook.py[m
[36m@@ -0,0 +1,67 @@[m
[32m+[m[32mimport pytest[m
[32m+[m[32mfrom fastapi.testclient import TestClient[m
[32m+[m
[32m+[m[32mfrom app.main import app[m
[32m+[m[32mfrom app.schemas import CustomerRequest[m
[32m+[m
[32m+[m[32mclient = TestClient(app)[m
[32m+[m
[32m+[m
[32m+[m[32m@pytest.fixture[m
[32m+[m[32mdef valid_request():[m
[32m+[m[32m    return {[m
[32m+[m[32m        "customer_id": "customer_123",[m
[32m+[m[32m        "customer_name": "Alex Smith",[m
[32m+[m[32m        "customer_email": "alex@example.com",[m
[32m+[m[32m        "message": "Please help me access my account.",[m
[32m+[m[32m    }[m
[32m+[m
[32m+[m
[32m+[m[32mdef test_valid_request_is_accepted(valid_request):[m
[32m+[m[32m    response = client.post("/webhook", json=valid_request)[m
[32m+[m
[32m+[m[32m    assert response.status_code == 200[m
[32m+[m[32m    assert response.json() == {[m
[32m+[m[32m        "status": "received",[m
[32m+[m[32m        "customer_id": "customer_123",[m
[32m+[m[32m    }[m
[32m+[m
[32m+[m
[32m+[m[32mdef test_invalid_email_is_rejected(valid_request):[m
[32m+[m[32m    valid_request["customer_email"] = "not-an-email"[m
[32m+[m
[32m+[m[32m    response = client.post("/webhook", json=valid_request)[m
[32m+[m
[32m+[m[32m    assert response.status_code == 422[m
[32m+[m[32m    assert response.json()["detail"][0]["loc"] == ["body", "customer_email"][m
[32m+[m
[32m+[m
[32m+[m[32m@pytest.mark.parametrize([m
[32m+[m[32m    "field", ["customer_id", "customer_name", "customer_email", "message"][m
[32m+[m[32m)[m
[32m+[m[32mdef test_missing_required_field_is_rejected(valid_request, field):[m
[32m+[m[32m    del valid_request[field][m
[32m+[m
[32m+[m[32m    response = client.post("/webhook", json=valid_request)[m
[32m+[m
[32m+[m[32m    assert response.status_code == 422[m
[32m+[m[32m    assert response.json()["detail"][0]["loc"] == ["body", field][m
[32m+[m
[32m+[m
[32m+[m[32m@pytest.mark.parametrize("message", ["", "   ", "\t\n", None, 123])[m
[32m+[m[32mdef test_invalid_message_is_rejected(valid_request, message):[m
[32m+[m[32m    valid_request["message"] = message[m
[32m+[m
[32m+[m[32m    response = client.post("/webhook", json=valid_request)[m
[32m+[m
[32m+[m[32m    assert response.status_code == 422[m
[32m+[m[32m    assert response.json()["detail"][0]["loc"] == ["body", "message"][m
[32m+[m
[32m+[m
[32m+[m[32mdef test_message_with_surrounding_whitespace_is_trimmed(valid_request):[m
[32m+[m[32m    valid_request["message"] = "  Please help. \n"[m
[32m+[m
[32m+[m[32m    response = client.post("/webhook", json=valid_request)[m
[32m+[m
[32m+[m[32m    assert response.status_code == 200[m
[32m+[m[32m    assert CustomerRequest(**valid_request).message == "Please help."[m
