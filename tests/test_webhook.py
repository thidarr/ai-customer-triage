import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CustomerRequest
from app.schemas import TriageResult
from app.classifier import ClassificationError
from app.config import ConfigurationError
from app.database import DatabaseError

client = TestClient(app)


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
        **classifier.return_value.model_dump(), "id": 71, "notification_status": status,
    }
    persistence.assert_called_once()


@pytest.mark.parametrize("error", [DatabaseError("private connection info"), ConfigurationError("private URL")])
def test_save_failure_returns_503(valid_request, persistence, error):
    persistence.side_effect = error
    response = client.post("/webhook", json=valid_request)
    assert response.status_code == 503
    assert "private" not in response.text
    assert "id" not in response.json()
