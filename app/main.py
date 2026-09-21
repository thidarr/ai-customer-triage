from fastapi import FastAPI, HTTPException

from app.classifier import ClassificationError, classify_message
from app.config import ConfigurationError
from app.database import DatabaseError, save_request
from app.schemas import CustomerRequest, WebhookResponse

app = FastAPI(title="Customer Request Triage")


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

    return WebhookResponse(
        **result.model_dump(), id=request_id, notification_status=notification_status
    )
