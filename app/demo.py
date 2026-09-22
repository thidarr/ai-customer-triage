from contextlib import contextmanager
from threading import Lock
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.config import ConfigurationError, get_demo_settings
from app.pipeline import process_request
from app.schemas import CustomerRequest, WebhookResponse

router = APIRouter(prefix="/demo", tags=["Public demo"])
PRESETS = {
    "routine_invoice": ("Routine invoice", "Please send me a copy of last month's invoice for my records. There is no urgency."),
    "account_access": ("Account access", "I forgot my password and cannot access my account. Please help me recover access."),
    "urgent_checkout": ("Urgent checkout failure", "Our checkout is failing for every customer right now. Nobody can complete a purchase, and our live sale ends in 20 minutes. We need immediate help."),
}


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: Literal["routine_invoice", "account_access", "urgent_checkout"]


def demo_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def require_demo_enabled() -> int:
    try:
        enabled, budget = get_demo_settings()
    except ConfigurationError:
        raise demo_error(503, "demo_disabled", "The public demo is unavailable.") from None
    if not enabled:
        raise demo_error(503, "demo_disabled", "The public demo is disabled.")
    return budget


class DemoGuard:
    """Single-process allowance; admission and release are atomic."""

    def __init__(self):
        self.lock = Lock()
        self.used = 0
        self.running = False

    @contextmanager
    def admit(self, budget: int):
        with self.lock:
            if self.used >= budget:
                raise demo_error(429, "demo_budget_exhausted", "The demo allowance has been used. Please contact the project owner.")
            if self.running:
                raise demo_error(429, "demo_busy", "Another demo request is running. Please try again shortly.")
            self.used += 1
            self.running = True
        try:
            yield
        finally:
            with self.lock:
                self.running = False


guard = DemoGuard()


@router.get("/samples", dependencies=[Depends(require_demo_enabled)])
def samples():
    return [{"sample_id": key, "title": value[0], "message": value[1]}
            for key, value in PRESETS.items()]


@router.post("", response_model=WebhookResponse)
def run_demo(sample: DemoRequest, budget: int = Depends(require_demo_enabled)):
    with guard.admit(budget):
        request = CustomerRequest(
            customer_id=f"demo_{sample.sample_id}", customer_name="Demo Customer",
            customer_email="demo@example.com", message=PRESETS[sample.sample_id][1],
        )
        return process_request(request, send_slack=False)
