"""The UnderCover backend."""

import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

from agent.main import run as default_run
from backend.actions import (
    StoreError,
    has_decision,
    list_activity,
    pay,
    record_activity,
    set_status,
    sign_off,
)
from backend.actions import decide as store_decide
from backend.db import DEFAULT_DB, seed
from backend.runs import (
    create_run,
    current_run,
    failure_count,
    put_summary,
    put_todos,
    release_claim,
)
from backend.store import get_claim as load_claim
from backend.store import (
    get_policy_wording,
    instructions,
    list_claims,
    list_handlers,
    list_section_headings,
)
from backend.store import read_section as load_section

router = APIRouter()


class DecisionBody(BaseModel):
    outcome: str
    payout: float
    explanation: str
    policy_section: str


class SignOffBody(BaseModel):
    handler_id: str


class PaymentBody(BaseModel):
    amount: float


class ActivityBody(BaseModel):
    message: str
    status: str | None = None


class RunBody(BaseModel):
    thread_id: str


class CreateRunBody(BaseModel):
    max_claims: int


class TodoItem(BaseModel):
    claim_id: str
    status: str


class TodosBody(BaseModel):
    items: list[TodoItem]


class SummaryBody(BaseModel):
    summary: str


class ReleaseBody(BaseModel):
    result: str


def _db(request: Request) -> Path:
    return Path(request.app.state.db_path)


def _call(fn, *args):
    try:
        return fn(*args)
    except StoreError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@router.get("/api/claims", operation_id="list_claims")
def get_claims(request: Request) -> list[dict[str, Any]]:
    """Return the claims queue."""
    return list_claims(_db(request))


@router.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_one_claim(claim_id: str, request: Request) -> dict[str, Any]:
    """Return one claim in full."""
    claim = load_claim(_db(request), claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")
    return claim


@router.get("/api/claims/{claim_id}/activity", operation_id="list_activity")
def get_activity(claim_id: str, request: Request) -> list[dict[str, str]]:
    """Return the activity on a claim, oldest first."""
    return _call(list_activity, _db(request), claim_id)


@router.post("/api/claims/{claim_id}/activity", operation_id="record_activity")
def post_activity(
    claim_id: str, body: ActivityBody, request: Request
) -> list[dict[str, str]]:
    """Append an activity line on a claim."""
    path = _db(request)
    if body.status == "in_progress":
        _call(set_status, path, claim_id, "in_progress")
    elif body.status == "waiting" and not has_decision(path, claim_id):
        _call(set_status, path, claim_id, "waiting")
    return _call(record_activity, path, claim_id, body.message)


@router.post("/api/claims/{claim_id}/decision", operation_id="decide_claim")
def decide_claim(claim_id: str, body: DecisionBody, request: Request) -> dict[str, Any]:
    """Record the agent's decision on a claim."""
    return _call(store_decide, _db(request), claim_id, body.model_dump())


@router.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off_claim")
def sign_off_claim(
    claim_id: str, body: SignOffBody, request: Request
) -> dict[str, Any]:
    """Record a handler's sign-off on an over-limit payout."""
    return _call(sign_off, _db(request), claim_id, body.handler_id)


@router.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, body: PaymentBody, request: Request) -> dict[str, Any]:
    """Pay an approved claim when the payout rule allows it."""
    return _call(pay, _db(request), claim_id, body.amount)


@router.post("/api/claims/{claim_id}/run", operation_id="run_claim")
def run_claim(claim_id: str, body: RunBody, request: Request) -> dict[str, str]:
    """Start the agent on one claim."""
    path = _db(request)
    claim = load_claim(path, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")
    if claim["status"] in {"decided", "waiting_for_sign_off"}:
        raise HTTPException(
            status_code=409, detail="This claim is not waiting to be worked."
        )
    set_status(path, claim_id, "in_progress")
    record_activity(path, claim_id, "Started work on this claim.")
    thread = threading.Thread(
        target=_run_agent, args=(request, claim_id, body.thread_id), daemon=True
    )
    thread.start()
    return {"status": "in_progress"}


def _run_agent(request: Request, claim_id: str, thread_id: str) -> None:
    path = _db(request)
    run_fn = request.app.state.run_agent or default_run
    with suppress(Exception):
        run_fn(claim_id, thread_id)
    if not has_decision(path, claim_id):
        result = "handler" if failure_count(path, claim_id) >= 1 else "retry"
        release_claim(path, claim_id, result)
        record_activity(path, claim_id, "Stopped before recording a decision.")
    record_activity(path, claim_id, "Finished work on this claim.")


@router.post("/api/runs", operation_id="create_run")
def post_run(body: CreateRunBody, request: Request) -> dict[str, Any]:
    """Store a queue run."""
    return create_run(_db(request), body.max_claims)


@router.get("/api/runs/current", operation_id="get_current_run")
def get_current_run(request: Request) -> dict[str, Any]:
    """Return the latest queue run."""
    return _call(current_run, _db(request))


@router.put("/api/runs/{run_id}/todos", operation_id="put_todos")
def post_todos(run_id: str, body: TodosBody, request: Request) -> dict[str, Any]:
    """Replace the to-do list for a run."""
    return _call(
        put_todos,
        _db(request),
        run_id,
        [item.model_dump() for item in body.items],
    )


@router.post("/api/runs/{run_id}/summary", operation_id="put_run_summary")
def post_summary(run_id: str, body: SummaryBody, request: Request) -> dict[str, Any]:
    """Store the summary for a run."""
    return _call(put_summary, _db(request), run_id, body.summary)


@router.post("/api/claims/{claim_id}/release", operation_id="release_claim")
def post_release(claim_id: str, body: ReleaseBody, request: Request) -> dict[str, Any]:
    """Return an undecided claim to the queue, or leave it for a handler."""
    return _call(release_claim, _db(request), claim_id, body.result)


@router.get("/api/documents/{name}/sections", operation_id="list_sections")
def list_sections(name: str, request: Request) -> list[str]:
    """Return the section headings of the wording or the manual."""
    headings = list_section_headings(_db(request), name)
    if headings is None:
        raise HTTPException(status_code=404, detail=f"Document {name} not found.")
    return headings


@router.get(
    "/api/documents/{name}/sections/{heading:path}", operation_id="read_section"
)
def read_section(name: str, heading: str, request: Request) -> dict[str, str]:
    """Return one section of the wording or the manual."""
    text = load_section(_db(request), name, heading)
    if text is None:
        raise HTTPException(
            status_code=404, detail=f"Section {heading} not found in {name}."
        )
    return {"heading": heading, "text": text}


@router.get("/api/policy-wording", operation_id="get_policy_wording")
def policy_wording(request: Request) -> dict[str, str]:
    """Return the policy wording."""
    return {"wording": get_policy_wording(_db(request))}


@router.get("/api/instructions", operation_id="get_instructions")
def get_instructions() -> dict[str, str]:
    """Return the agent's instructions for the queue and for one claim."""
    return instructions()


@router.get("/api/handlers", operation_id="list_handlers")
def get_handlers(request: Request) -> list[dict[str, Any]]:
    """Return the claims handlers."""
    return list_handlers(_db(request))


def create_app(db_path: Path | None = None) -> FastAPI:
    """Build the API, seeding the database when the file is missing."""
    path = Path(db_path) if db_path is not None else DEFAULT_DB
    if not path.exists():
        seed(path)
    application = FastAPI(title="UnderCover")
    application.state.db_path = path
    application.state.run_agent = None
    application.include_router(router)
    return application


app = create_app()
