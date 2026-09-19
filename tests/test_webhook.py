import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CustomerRequest

client = TestClient(app)


@pytest.fixture
def valid_request():
    return {
        "customer_id": "customer_123",
        "customer_name": "Alex Smith",
        "customer_email": "alex@example.com",
        "message": "Please help me access my account.",
    }


def test_valid_request_is_accepted(valid_request):
    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 200
    assert response.json() == {
        "status": "received",
        "customer_id": "customer_123",
    }


def test_invalid_email_is_rejected(valid_request):
    valid_request["customer_email"] = "not-an-email"

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "customer_email"]


@pytest.mark.parametrize(
    "field", ["customer_id", "customer_name", "customer_email", "message"]
)
def test_missing_required_field_is_rejected(valid_request, field):
    del valid_request[field]

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


@pytest.mark.parametrize("message", ["", "   ", "\t\n", None, 123])
def test_invalid_message_is_rejected(valid_request, message):
    valid_request["message"] = message

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "message"]


def test_message_with_surrounding_whitespace_is_trimmed(valid_request):
    valid_request["message"] = "  Please help. \n"

    response = client.post("/webhook", json=valid_request)

    assert response.status_code == 200
    assert CustomerRequest(**valid_request).message == "Please help."
