import httpx

from app.config import ConfigurationError, get_slack_webhook_url
from app.schemas import TriageResult


class NotificationError(Exception):
    """A safe failure reason suitable for storage; never includes the webhook URL."""


def send_notification(request_id: int, result: TriageResult) -> None:
    """Send one Slack notification without changing database state."""
    try:
        url = get_slack_webhook_url()
    except ConfigurationError as exc:
        raise NotificationError("Slack webhook is missing or invalid.") from exc

    # Plain-text blocks prevent customer-derived content from becoming mentions.
    text = (
        f"Request #{request_id}\nCategory: {result.category}\nPriority: {result.priority}"
        f"\nSummary: {result.summary[:1000]}"
        f"\nSuggested action: {result.suggested_action[:1000]}"
    )
    payload = {
        "text": f"High-priority customer request #{request_id}",
        "blocks": [{"type": "section", "text": {"type": "plain_text", "text": text}}],
    }
    try:
        response = httpx.post(url, json=payload, timeout=10.0, follow_redirects=False)
    except httpx.TimeoutException as exc:
        raise NotificationError("Slack request timed out; delivery is uncertain.") from exc
    except httpx.HTTPError as exc:
        raise NotificationError("Slack network error; delivery is uncertain.") from exc

    if response.status_code != 200:
        raise NotificationError(f"Slack rejected the notification (HTTP {response.status_code}).")
    if response.text.strip() != "ok":
        raise NotificationError("Slack returned an unexpected response; delivery is uncertain.")
