from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerRequest(BaseModel):
    """Required customer details and the message submitted to the webhook."""

    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)
    customer_email: EmailStr
    message: str = Field(min_length=1)


class TriageResult(BaseModel):
    """The complete classification contract, also used as Gemini's schema."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    category: Literal["billing", "account", "technical", "general"]
    priority: Literal["low", "medium", "high"]
    summary: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)


NotificationStatus = Literal["not_required", "pending", "sent", "failed"]


class WebhookResponse(TriageResult):
    """Classification plus the identity and notification state of the saved row."""

    id: int = Field(gt=0)
    notification_status: NotificationStatus
