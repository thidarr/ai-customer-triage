import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.demo import router as demo_router
from app.pipeline import process_request
from app.schemas import CustomerRequest, WebhookResponse
from app.security import require_api_key

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
app = FastAPI(title="Customer Request Triage")
app.include_router(demo_router)
static_directory = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_directory), name="static")


@app.get("/", include_in_schema=False)
def demo_page() -> FileResponse:
    return FileResponse(static_directory / "index.html")


@app.post("/webhook", response_model=WebhookResponse, dependencies=[Depends(require_api_key)])
def receive_customer_request(request: CustomerRequest) -> WebhookResponse:
    return process_request(request, send_slack=True)
