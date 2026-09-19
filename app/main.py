from fastapi import FastAPI

from app.schemas import CustomerRequest

app = FastAPI(title="Customer Request Triage")


@app.post("/webhook")
def receive_customer_request(request: CustomerRequest) -> dict[str, str]:
    """Acknowledge a validated request. Persistence comes in a later phase."""
    return {"status": "received", "customer_id": request.customer_id}
