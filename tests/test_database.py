from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import database
from app.config import ConfigurationError, get_database_url
from app.main import app
from app.schemas import CustomerRequest, TriageResult


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("WEBHOOK_API_KEY", "test-webhook-key")


@pytest.fixture
def connection(monkeypatch):
    connect = MagicMock()
    conn = connect.return_value
    conn.__enter__.return_value = conn
    conn.execute.return_value.fetchone.return_value = (42,)
    monkeypatch.setattr(database.psycopg, "connect", connect)
    return connect, conn


@pytest.fixture
def request_data():
    return CustomerRequest(customer_id="customer_1", customer_name="Alex",
                           customer_email="alex@example.com", message="Please send my invoice's copy.")


@pytest.fixture
def result():
    return TriageResult(category="billing", priority="high", summary="Invoice needed urgently.",
                        suggested_action="Send the invoice.")


def test_save_uses_parameters_and_returns_committed_id(connection, request_data, result):
    connect, conn = connection
    assert database.save_request(request_data, result, "pending") == 42
    sql, parameters = conn.execute.call_args.args
    assert request_data.message not in sql
    assert parameters == (
        request_data.customer_id, request_data.customer_name, request_data.customer_email,
        request_data.message, result.category, result.priority, result.summary,
        result.suggested_action, "pending", None,
    )
    conn.__exit__.assert_called_once_with(None, None, None)
    connect.assert_called_once_with(get_database_url(), connect_timeout=10)


@pytest.mark.parametrize("stage", ["connect", "insert", "commit"])
def test_database_failure_preserves_cause(connection, request_data, result, stage):
    connect, conn = connection
    failure = psycopg.OperationalError("private database details")
    target = {"connect": connect, "insert": conn.execute, "commit": conn.__exit__}[stage]
    target.side_effect = failure
    with pytest.raises(database.DatabaseError) as caught:
        database.save_request(request_data, result, "pending")
    assert caught.value.__cause__ is failure
    if stage == "insert":
        assert conn.__exit__.call_args.args[0] is psycopg.OperationalError


def test_no_returned_id_fails(connection, request_data, result):
    connection[1].execute.return_value.fetchone.return_value = None
    with pytest.raises(database.DatabaseError):
        database.save_request(request_data, result, "pending")


def test_initialize_table(connection):
    database.initialize_database()
    connection[1].execute.assert_called_once_with(database.CREATE_TABLE)
    connection[1].__exit__.assert_called_once_with(None, None, None)


def test_initialize_failure(connection):
    connection[1].execute.side_effect = psycopg.OperationalError("Unavailable")
    with pytest.raises(database.DatabaseError):
        database.initialize_database()


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_database_url(connection, monkeypatch, request_data, result, value):
    if value is None:
        monkeypatch.delenv("DATABASE_URL")
    else:
        monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(ConfigurationError):
        database.save_request(request_data, result, "pending")
    connection[0].assert_not_called()


def test_database_config_does_not_require_gemini(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert get_database_url() == "postgresql://test:test@localhost/test"


def test_commit_failure_reaches_webhook_as_503(connection, monkeypatch, request_data, result):
    send = MagicMock()
    monkeypatch.setattr("app.pipeline.send_notification", send)
    monkeypatch.setattr("app.pipeline.classify_message", lambda message: result)
    connection[1].__exit__.side_effect = psycopg.OperationalError("private commit details")
    response = TestClient(app).post("/webhook", json=request_data.model_dump(),
                                    headers={"X-API-Key": "test-webhook-key"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Unable to save the request."}
    send.assert_not_called()


@pytest.mark.parametrize("status,error", [("sent", None), ("failed", "Slack failed.")])
def test_notification_update(connection, status, error):
    conn = connection[1]
    conn.execute.return_value.rowcount = 1
    database.update_notification_status(42, status, error)
    sql, params = conn.execute.call_args.args
    assert params == (status, error, 42)
    assert "notification_status = 'pending'" in sql
    conn.__exit__.assert_called_once_with(None, None, None)


def test_missing_pending_record_is_error(connection):
    connection[1].execute.return_value.rowcount = 0
    with pytest.raises(database.DatabaseError):
        database.update_notification_status(42, "sent", None)


@pytest.mark.parametrize("stage", ["connect", "update", "commit"])
def test_notification_update_failure(connection, stage):
    connect, conn = connection
    conn.execute.return_value.rowcount = 1
    failure = psycopg.OperationalError("secret")
    {"connect": connect, "update": conn.execute, "commit": conn.__exit__}[stage].side_effect = failure
    with pytest.raises(database.DatabaseError) as caught:
        database.update_notification_status(42, "failed", "Slack failed.")
    assert caught.value.__cause__ is failure
