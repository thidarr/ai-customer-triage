from unittest.mock import Mock
import logging

import httpx
import pytest

from app.notifications import NotificationError, send_notification
from app.schemas import TriageResult


@pytest.fixture
def slack(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/test/secret/token")
    post = Mock(return_value=httpx.Response(200, text="ok"))
    monkeypatch.setattr("app.notifications.httpx.post", post)
    return post


@pytest.fixture
def result():
    return TriageResult(category="technical", priority="high", summary="<!channel> Failure",
                        suggested_action="Investigate now.")


def test_success_plain_text_payload(slack, result):
    send_notification(42, result)
    slack.assert_called_once()
    kwargs = slack.call_args.kwargs
    block = kwargs["json"]["blocks"][0]["text"]
    assert block["type"] == "plain_text"
    assert result.summary in block["text"]
    assert "#42" in block["text"]
    assert kwargs["timeout"] == 10.0
    assert kwargs["follow_redirects"] is False


@pytest.mark.parametrize("status,text", [(400,"invalid_payload"),(403,"forbidden"),(429,"rate_limited"),(500,"secret"),(200,"secret")])
def test_rejections_are_safe(slack, result, status, text):
    slack.return_value = httpx.Response(status, text=text)
    with pytest.raises(NotificationError) as caught:
        send_notification(42, result)
    assert "secret" not in str(caught.value)
    slack.assert_called_once()


@pytest.mark.parametrize("error", [httpx.ReadTimeout("secret URL"), httpx.ConnectError("secret URL")])
def test_transport_errors_are_safe(slack, result, error):
    slack.side_effect = error
    with pytest.raises(NotificationError) as caught:
        send_notification(42, result)
    assert "secret" not in str(caught.value)
    assert "uncertain" in str(caught.value)


@pytest.mark.parametrize("url", ["", "not a URL", "http://hooks.slack.com/services/test", "https://example.com/services/test"])
def test_invalid_configuration_skips_http(slack, result, monkeypatch, url):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", url)
    with pytest.raises(NotificationError):
        send_notification(42, result)
    slack.assert_not_called()


def test_http_client_does_not_log_webhook_url(monkeypatch, caplog, result):
    # Exercise the actual HTTPX request path; only the network transport is mocked.
    from app.main import app
    assert app is not None
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: None)
    url = "https://hooks.slack.com/services/private/secret/token"
    monkeypatch.setenv("SLACK_WEBHOOK_URL", url)
    original_client = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text="ok")

    def make_client(**kwargs):
        return original_client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr("httpx._api.Client", make_client)
    with caplog.at_level(logging.INFO):
        send_notification(42, result)
    assert len(requests) == 1
    assert url not in caplog.text
    assert "secret" not in caplog.text
    assert not [r for r in caplog.records if r.name in ("httpx", "httpcore")]
