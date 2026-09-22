import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CustomerRequest
from app.schemas import TriageResult
from app.classifier import ClassificationError
from app.config import ConfigurationError
from app.database import DatabaseError
from app.notifications import NotificationError

client = TestClient(app)


@pytest.fixture(autouse=True)
def notifications(monkeypatch):
    send, update = Mock(), Mock()
    monkeypatch.setattr("app.main.send_notification", send)
    monkeypatch.setattr("app.main.update_notification_status", update)
    return send, update


@pytest.fixture(autouse=True)
def persistence(monkeypatch):
    mock = Mock(return_value=42)
    monkeypatch.setattr("app.main.save_request", mock)
    return mock


@pytest.fixture(autouse=True)
def classifier(monkeypatch):
    mock = Mock(return_value=TriageResult(
        category="account", priority="medium", summary="Cannot access account.",
        suggested_action="Help the customer recover access.",
    ))
    monkeypatch.setattr("app.main.classify_message", mock)
    return mock


@pytest.fixture
def valid_request():
    return {
        "customer_id": "customer_123",
        "customer_name": "Alex Smith",
        "customer_email": "alex@example.com",
        "message": "Please help me access my account.",
    }


def test_valid_request_is_accepted(valid_request, classifier):
    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 200
    assert response.json() == {
        **classifier.return_value.model_dump(), "id": 42,
        "notification_status": "not_required",
    }
    classifier.assert_called_once_with(valid_request["message"])


def test_invalid_email_is_rejected(valid_request, classifier, persistence):
    valid_request["customer_email"] = "not-an-email"

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 422
    classifier.assert_not_called()
    persistence.assert_not_called()
    assert response.json()["detail"][0]["loc"] == ["body", "customer_email"]


@pytest.mark.parametrize(
    "field", ["customer_id", "customer_name", "customer_email", "message"]
)
def test_missing_required_field_is_rejected(valid_request, field, classifier, persistence):
    del valid_request[field]

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 422
    classifier.assert_not_called()
    persistence.assert_not_called()
    assert response.json()["detail"][0]["loc"] == ["body", field]


@pytest.mark.parametrize("message", ["", "   ", "\t\n", None, 123])
def test_invalid_message_is_rejected(valid_request, message, classifier, persistence):
    valid_request["message"] = message

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 422
    classifier.assert_not_called()
    persistence.assert_not_called()
    assert response.json()["detail"][0]["loc"] == ["body", "message"]


def test_message_with_surrounding_whitespace_is_trimmed(valid_request, classifier):
    valid_request["message"] = "  Please help. \n"

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 200
    assert CustomerRequest(**valid_request).message == "Please help."
    classifier.assert_called_once_with("Please help.")


@pytest.mark.parametrize("error, status", [
    (ClassificationError("private provider details"), 502),
    (ConfigurationError("private settings"), 503),
])
def test_classification_failure_is_not_success(valid_request, classifier, error, status, persistence):
    classifier.side_effect = error
    response = client.post("/webhook", json=valid_request)
    assert response.status_code == status
    assert "private" not in response.text
    assert "category" not in response.json()
    persistence.assert_not_called()


@pytest.mark.parametrize("priority,status", [
    ("high", "pending"), ("medium", "not_required"), ("low", "not_required"),
])
def test_save_precedes_response_and_sets_status(valid_request, classifier, persistence, priority, status):
    classifier.return_value.priority = priority

    def save(request, result, notification_status):
        classifier.assert_called_once_with(valid_request["message"])
        assert request.model_dump() == valid_request
        assert result == classifier.return_value
        assert notification_status == status
        return 71

    persistence.side_effect = save
    response = client.post("/webhook", json=valid_request)
    assert response.status_code == 200
    assert response.json() == {
        **classifier.return_value.model_dump(), "id": 71,
        "notification_status": "sent" if priority == "high" else status,
    }
    persistence.assert_called_once()


@pytest.mark.parametrize("error", [DatabaseError("private connection info"), ConfigurationError("private URL")])
def test_save_failure_returns_503(valid_request, persistence, error, classifier, notifications):
    classifier.return_value.priority = "high"
    persistence.side_effect = error
    response = client.post("/webhook", json=valid_request)
    assert response.status_code == 503
    assert "private" not in response.text
    assert "id" not in response.json()
    notifications[0].assert_not_called()
    notifications[1].assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_high_priority_notification_order(valid_request, classifier, persistence, notifications, failure):
    classifier.return_value.priority = "high"
    events = []
    persistence.side_effect = lambda *args: events.append("committed") or 42

    def send(*args):
        assert events == ["committed"]
        events.append("slack")
        if failure:
            raise NotificationError("Slack network error; delivery is uncertain.")

    def update(*args):
        assert events == ["committed", "slack"]
        events.append("updated")

    notifications[0].side_effect = send
    notifications[1].side_effect = update
    response = client.post("/webhook", json=valid_request)
    assert response.status_code == 200
    status = "failed" if failure else "sent"
    assert response.json()["notification_status"] == status
    notifications[1].assert_called_once_with(
        42, status, "Slack network error; delivery is uncertain." if failure else None
    )
    assert events == ["committed", "slack", "updated"]
    persistence.assert_called_once()


@pytest.mark.parametrize("priority", ["low", "medium"])
def test_nonurgent_skips_slack(valid_request, classifier, notifications, priority):
    classifier.return_value.priority = priority
    response = client.post("/webhook", json=valid_request)
    assert response.json()["notification_status"] == "not_required"
    notifications[0].assert_not_called()
    notifications[1].assert_not_called()


@pytest.mark.parametrize("slack_fails", [False, True])
@pytest.mark.parametrize("error", [DatabaseError("secret"), ConfigurationError("secret")])
def test_update_failure_has_separate_error_body(valid_request, classifier, notifications, error, slack_fails):
    classifier.return_value.priority = "high"
    if slack_fails:
        notifications[0].side_effect = NotificationError("Slack failed.")
    notifications[1].side_effect = error
    response = client.post("/webhook", json=valid_request)
    assert response.status_code == 503
    assert response.json() == {"detail": {
        "code": "notification_status_update_failed",
        "message": "The request was saved, but the notification outcome could not be recorded.",
        "request_id": 42,
    }}
