from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import demo
from app.classifier import ClassificationError
from app.config import get_demo_settings
from app.database import DatabaseError
from app.main import app
from app.schemas import TriageResult

client = TestClient(app)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_DEMO_MAX_REQUESTS", "20")
    monkeypatch.delenv("WEBHOOK_API_KEY", raising=False)
    monkeypatch.setattr(demo, "guard", demo.DemoGuard())


@pytest.fixture(autouse=True)
def pipeline(monkeypatch):
    classify = Mock(return_value=TriageResult(
        category="technical", priority="high", summary="Checkout failed.",
        suggested_action="Investigate checkout.",
    ))
    save, send, update = Mock(return_value=42), Mock(), Mock()
    for name, mock in [("classify_message", classify), ("save_request", save),
                       ("send_notification", send), ("update_notification_status", update)]:
        monkeypatch.setattr(f"app.pipeline.{name}", mock)
    return classify, save, send, update


@pytest.mark.parametrize("sample_id", list(demo.PRESETS))
def test_presets_use_real_pipeline_without_slack(pipeline, sample_id):
    classify, save, send, update = pipeline
    response = client.post("/demo", json={"sample_id": sample_id})
    assert response.status_code == 200
    assert response.json() == {**classify.return_value.model_dump(), "id": 42,
                               "notification_status": "not_required"}
    classify.assert_called_once_with(demo.PRESETS[sample_id][1])
    request, result, status = save.call_args.args
    assert request.customer_id == f"demo_{sample_id}"
    assert request.customer_email == "demo@example.com"
    assert result == classify.return_value and status == "not_required"
    send.assert_not_called()
    update.assert_not_called()
    assert demo.guard.used == 1 and not demo.guard.running


@pytest.mark.parametrize("payload", [{}, {"sample_id": "other"},
    {"sample_id": "urgent_checkout", "message": "injected"},
    {"sample_id": "urgent_checkout", "send_slack": True},
    {"sample_id": "urgent_checkout", "customer_email": "attacker@example.com"}])
def test_invalid_payload_does_not_consume_budget(payload, pipeline):
    assert client.post("/demo", json=payload).status_code == 422
    assert demo.guard.used == 0
    for mock in pipeline:
        mock.assert_not_called()


@pytest.mark.parametrize("enabled,budget", [("false", "20"), ("invalid", "20"),
                                          ("true", "0"), ("true", "abc")])
def test_disabled_or_invalid_configuration(enabled, budget, monkeypatch, pipeline):
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", enabled)
    monkeypatch.setenv("PUBLIC_DEMO_MAX_REQUESTS", budget)
    for response in [client.post("/demo", json={"sample_id": "routine_invoice"}),
                     client.get("/demo/samples")]:
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "demo_disabled"
    assert demo.guard.used == 0
    pipeline[0].assert_not_called()


def test_configuration_defaults_disabled(monkeypatch):
    monkeypatch.delenv("PUBLIC_DEMO_ENABLED")
    monkeypatch.delenv("PUBLIC_DEMO_MAX_REQUESTS")
    assert get_demo_settings() == (False, 20)


def test_budget_exhaustion_does_not_call_pipeline(monkeypatch, pipeline):
    monkeypatch.setenv("PUBLIC_DEMO_MAX_REQUESTS", "1")
    assert client.post("/demo", json={"sample_id": "routine_invoice"}).status_code == 200
    response = client.post("/demo", json={"sample_id": "routine_invoice"})
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "demo_budget_exhausted"
    assert pipeline[0].call_count == 1 and demo.guard.used == 1


@pytest.mark.parametrize("stage", ["classification", "save", "unexpected"])
def test_failure_consumes_budget_and_releases_slot(stage, pipeline):
    target = pipeline[1] if stage == "save" else pipeline[0]
    target.side_effect = {"classification": ClassificationError("failed"),
                          "save": DatabaseError("failed"), "unexpected": RuntimeError("failed")}[stage]
    response = TestClient(app, raise_server_exceptions=False).post("/demo", json={"sample_id": "account_access"})
    assert response.status_code == {"classification": 502, "save": 503, "unexpected": 500}[stage]
    assert demo.guard.used == 1 and not demo.guard.running
    target.side_effect = None
    assert client.post("/demo", json={"sample_id": "account_access"}).status_code == 200
    assert demo.guard.used == 2
    pipeline[2].assert_not_called()


def test_simultaneous_request_is_rejected_without_queueing(pipeline):
    entered, release = Event(), Event()
    result = pipeline[0].return_value

    def classify(message):
        entered.set()
        assert release.wait(5)
        return result

    pipeline[0].side_effect = classify
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(lambda: TestClient(app).post("/demo", json={"sample_id": "urgent_checkout"}))
        try:
            assert entered.wait(5)
            second = client.post("/demo", json={"sample_id": "routine_invoice"})
            assert second.status_code == 429
            assert second.json()["detail"]["code"] == "demo_busy"
            assert demo.guard.used == 1
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
    assert not demo.guard.running


def test_webhook_independent_of_demo_guard(monkeypatch, pipeline):
    monkeypatch.setenv("WEBHOOK_API_KEY", "private-key")
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "false")
    demo.guard.used = 20
    demo.guard.running = True
    request = {"customer_id": "customer", "customer_name": "Alex", "customer_email": "alex@example.com", "message": "Help"}
    assert client.post("/webhook", json=request).status_code == 401
    response = client.post("/webhook", json=request, headers={"X-API-Key": "private-key"})
    assert response.status_code == 200 and response.json()["notification_status"] == "sent"
    pipeline[2].assert_called_once()
    pipeline[3].assert_called_once_with(42, "sent", None)
    assert demo.guard.used == 20


def test_samples_and_ui_do_not_expose_key(monkeypatch):
    monkeypatch.setenv("WEBHOOK_API_KEY", "private-test-secret")
    samples = client.get("/demo/samples")
    assert {s["sample_id"] for s in samples.json()} == set(demo.PRESETS)
    assert demo.guard.used == 0
    for path in ["/", "/static/styles.css", "/static/app.js", "/demo/samples"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "private-test-secret" not in response.text
    script = client.get("/static/app.js").text
    assert "innerHTML" not in script and "localStorage" not in script
    assert "X-API-Key" not in script and "WEBHOOK_API_KEY" not in script
    assert client.get("/static/.env").status_code == 404
