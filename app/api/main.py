from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db.store import latest_decision, list_submissions, rule_frequency
from app.graph.pipeline import process
from app.schemas.submission import VendorSubmission

BASE = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="Vendor onboarding")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/submissions")
def submit(sub: VendorSubmission) -> dict:
    """Run a submission through the pipeline and persist the result."""
    from app.db.store import save_decision, save_submission

    save_submission(sub)
    decision = process(sub)
    save_decision(decision)
    return decision.model_dump(mode="json")


@app.get("/api/submissions")
def api_list() -> list[dict]:
    return list_submissions()


@app.get("/api/submissions/{submission_id}")
def api_detail(submission_id: str) -> dict:
    d = latest_decision(submission_id)
    if d is None:
        raise HTTPException(404, f"No decision for {submission_id}")
    return d


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "rows": list_submissions(), "rules": rule_frequency()},
    )


@app.get("/submissions/{submission_id}", response_class=HTMLResponse)
def detail(request: Request, submission_id: str):
    d = latest_decision(submission_id)
    if d is None:
        raise HTTPException(404, f"No decision for {submission_id}")
    return templates.TemplateResponse(
        "detail.html", {"request": request, "d": d, "sid": submission_id}
    )