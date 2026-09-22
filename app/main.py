import logging

from fastapi import FastAPI, HTTPException

from app.classifier import ClassificationError, classify_message
from app.config import ConfigurationError
from app.database import DatabaseError, save_request, update_notification_status
from app.notifications import NotificationError, send_notification
from app.schemas import CustomerRequest, WebhookResponse

app = FastAPI(title="Customer Request Triage")
logger = logging.getLogger(__name__)


@app.post("/webhook", response_model=WebhookResponse)
def receive_customer_request(request: CustomerRequest) -> WebhookResponse:
    """Classify and persist a request before acknowledging success."""
    try:
        result = classify_message(request.message)
    except ConfigurationError as exc:
        raise HTTPException(503, "Classification is not configured.") from exc
    except ClassificationError as exc:
        raise HTTPException(502, "Unable to classify the request.") from exc

    notification_status = "pending" if result.priority == "high" else "not_required"
    try:
        request_id = save_request(request, result, notification_status)
    except ConfigurationError as exc:
        raise HTTPException(503, "Database is not configured.") from exc
    except DatabaseError as exc:
        raise HTTPException(503, "Unable to save the request.") from exc

    if result.priority == "high":
        notification_error = None
        try:
            send_notification(request_id, result)
            notification_status = "sent"
        except NotificationError as exc:
            notification_status = "failed"
            notification_error = str(exc)

        try:
            update_notification_status(request_id, notification_status, notification_error)
        except (ConfigurationError, DatabaseError) as exc:
            logger.error("Could not record notification outcome for request %s", request_id)
            raise HTTPException(503, detail={
                "code": "notification_status_update_failed",
                "message": "The request was saved, but the notification outcome could not be recorded.",
                "request_id": request_id,
            }) from exc

    return WebhookResponse(
        **result.model_dump(), id=request_id, notification_status=notification_status
    )
