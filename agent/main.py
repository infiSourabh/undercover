"""The UnderCover Agent."""

from __future__ import annotations

import contextvars
import json
import os
import sys
import uuid
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=60)


def _stage(claim_id: str, message: str) -> None:
    print(f"{claim_id}: {message}", flush=True)


@tool
def get_claim(claim_id: str) -> str:
    """Read the claim, the customer's policy and claim history."""
    with backend() as client:
        response = client.get(f"/api/claims/{claim_id}")
        response.raise_for_status()
        client.post(
            f"/api/claims/{claim_id}/activity",
            json={"message": "Read the claim, the policy, and the claim history"},
        )
    _stage(claim_id, "read the claim")
    return json.dumps(response.json())


@tool
def list_sections(claim_id: str, name: str) -> str:
    """List the section headings of the policy wording or the claims manual."""
    with backend() as client:
        response = client.get(f"/api/documents/{name}/sections")
        response.raise_for_status()
    _stage(claim_id, f"list {name} sections")
    return json.dumps(response.json())


@tool
def read_section(claim_id: str, name: str, heading: str) -> str:
    """Read one section of the policy wording or the claims manual."""
    with backend() as client:
        response = client.get(f"/api/documents/{name}/sections/{quote(heading)}")
        response.raise_for_status()
        label = "policy wording" if name == "wording" else "claims manual"
        client.post(
            f"/api/claims/{claim_id}/activity",
            json={"message": f"Read {label}: {heading}"},
        )
    _stage(claim_id, f"read {name} {heading}")
    return response.json()["text"]


@tool
def decide(
    claim_id: str,
    outcome: str,
    payout: float,
    explanation: str,
    policy_section: str,
) -> str:
    """Record the decision on the claim."""
    with backend() as client:
        response = client.post(
            f"/api/claims/{claim_id}/decision",
            json={
                "outcome": outcome,
                "payout": payout,
                "explanation": explanation,
                "policy_section": policy_section,
            },
        )
    _stage(claim_id, f"decide {outcome} {payout}")
    if response.status_code == httpx.codes.CONFLICT:
        detail = str(response.json()["detail"])
        _stage(claim_id, f"decision rejected: {detail}")
        return detail
    response.raise_for_status()
    return json.dumps(response.json()["decision"])


@tool
def pay(claim_id: str, amount: float) -> str:
    """Pay the approved payout. If payment is blocked, return the reason and stop."""
    with backend() as client:
        response = client.post(
            f"/api/claims/{claim_id}/payment", json={"amount": amount}
        )
    _stage(claim_id, f"pay {amount}")
    if response.status_code == httpx.codes.CONFLICT:
        detail = str(response.json()["detail"])
        _stage(claim_id, f"payment blocked: {detail}")
        return detail
    response.raise_for_status()
    return json.dumps(response.json()["payment"])


CLAIM_TOOLS = [get_claim, list_sections, read_section, decide, pay]


def claim_middleware():
    """Return the middleware for one claim."""
    return [
        ModelRetryMiddleware(),
        ToolRetryMiddleware(),
        ModelCallLimitMiddleware(run_limit=25, exit_behavior="end"),
    ]


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the agent on one claim and return its final reply."""
    with backend() as client:
        prompt = client.get("/api/instructions").json()["claim"]
    agent = create_agent(
        llm or model(),
        tools=CLAIM_TOOLS,
        system_prompt=prompt,
        middleware=claim_middleware(),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Claim {claim_id}"}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].text


_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "queue_run", default=None
)
MAX_FAILURES = 2


def queue_middleware():
    """Return the middleware for a queue run."""
    return [
        ModelRetryMiddleware(),
        ToolRetryMiddleware(),
        ModelCallLimitMiddleware(run_limit=40, exit_behavior="end"),
    ]


def _state() -> dict:
    state = _current.get()
    if state is None:
        raise RuntimeError("No queue run is in progress.")
    return state


def _money(amount: float) -> str:
    return f"${amount:,.2f}"


def _load(client: httpx.Client, claim_id: str) -> dict:
    response = client.get(f"/api/claims/{claim_id}")
    response.raise_for_status()
    return response.json()


def _set_todo(client: httpx.Client, claim_id: str, status: str) -> None:
    state = _state()
    run_id = str(state["run_id"])
    current = client.get("/api/runs/current").json()
    items = list(current["items"])
    found = False
    for item in items:
        if item["claim_id"] == claim_id:
            item["status"] = status
            found = True
    if not found:
        items.append({"claim_id": claim_id, "status": status})
    response = client.put(f"/api/runs/{run_id}/todos", json={"items": items})
    response.raise_for_status()


def _report(claim: dict) -> str:
    decision = claim["decision"]
    amount = _money(float(decision["payout"]))
    return f"{claim['claim_id']} {decision['outcome']} {amount}"


def _pay_if_ready(client: httpx.Client, claim: dict) -> None:
    decision = claim["decision"]
    if decision is None or decision["outcome"] != "approve":
        return
    if claim["payment"] is not None or claim["status"] != "in_progress":
        return
    pay.invoke({"claim_id": claim["claim_id"], "amount": decision["payout"]})


def work_claim(claim_id: str) -> str:
    """Hand one claim to a fresh claim helper. It answers in one line."""
    state = _state()
    taken: set[str] = state["taken"]
    with backend() as client:
        claim = _load(client, claim_id)
        if claim["decision"] is not None:
            _pay_if_ready(client, claim)
            claim = _load(client, claim_id)
            _set_todo(client, claim_id, "done")
            return _report(claim)
        if int(claim["failures"]) >= MAX_FAILURES:
            _set_todo(client, claim_id, "left_for_handler")
            return f"{claim_id} failed twice and is left for a handler."
        if claim_id not in taken and len(taken) >= int(state["max_claims"]):
            cap = state["max_claims"]
            return f"The cap for this run is {cap}. Leave {claim_id} waiting."
        taken.add(claim_id)
        _set_todo(client, claim_id, "in_progress")
        client.post(
            f"/api/claims/{claim_id}/activity",
            json={"message": "Started work on this claim.", "status": "in_progress"},
        )
        try:
            run(claim_id, str(uuid.uuid4()), state["llm"])
        except Exception as exc:
            _stage(claim_id, f"failed: {exc}")
        claim = _load(client, claim_id)
        if claim["decision"] is None:
            failed_before = int(claim["failures"]) >= MAX_FAILURES - 1
            result = "handler" if failed_before else "retry"
            client.post(
                f"/api/claims/{claim_id}/release", json={"result": result}
            ).raise_for_status()
            if result == "handler":
                _set_todo(client, claim_id, "left_for_handler")
                return f"{claim_id} failed twice and is left for a handler."
            _set_todo(client, claim_id, "todo")
            return f"{claim_id} failed and is back in the queue."
        _pay_if_ready(client, claim)
        claim = _load(client, claim_id)
        _set_todo(client, claim_id, "done")
        return _report(claim)


@tool
def list_waiting() -> str:
    """List the claims still waiting, in claim id order."""
    with backend() as client:
        claims = client.get("/api/claims").json()
    waiting = [
        {"claim_id": claim["claim_id"], "summary": claim["summary"]}
        for claim in claims
        if claim["status"] == "waiting"
    ]
    return json.dumps(waiting)


@tool
def update_todos(items: list[dict]) -> str:
    """Replace the to-do list. Each item has claim_id and status."""
    state = _state()
    with backend() as client:
        response = client.put(
            f"/api/runs/{state['run_id']}/todos",
            json={"items": items},
        )
    if response.status_code == httpx.codes.CONFLICT:
        return str(response.json()["detail"])
    response.raise_for_status()
    return f"To-do list has {len(items)} items."


@tool("work_claim")
def work_claim_tool(claim_id: str) -> str:
    """Hand one claim to a fresh claim helper. It answers in one line."""
    return work_claim(claim_id)


@tool
def finish(summary: str) -> str:
    """Store the short summary for the handlers."""
    state = _state()
    with backend() as client:
        response = client.post(
            f"/api/runs/{state['run_id']}/summary",
            json={"summary": summary},
        )
    response.raise_for_status()
    return summary


QUEUE_TOOLS = [list_waiting, update_todos, work_claim_tool, finish]


def catch_up() -> None:
    """Work a waiting claim the run still has room for."""
    state = _state()
    taken: set[str] = state["taken"]
    while True:
        with backend() as client:
            claims = client.get("/api/claims").json()
        waiting = [
            str(claim["claim_id"]) for claim in claims if claim["status"] == "waiting"
        ]
        retry = [claim_id for claim_id in waiting if claim_id in taken]
        if retry:
            work_claim(retry[0])
            continue
        if len(taken) >= int(state["max_claims"]):
            return
        fresh = [claim_id for claim_id in waiting if claim_id not in taken]
        if not fresh:
            return
        work_claim(fresh[0])


def run_queue(max_claims: int, llm: BaseChatModel | None = None) -> str:
    """Run the queue agent up to max_claims, then check for a missed claim."""
    with backend() as client:
        created = client.post("/api/runs", json={"max_claims": max_claims}).json()
        prompt = client.get("/api/instructions").json()["queue"].format(cap=max_claims)
    token = _current.set(
        {
            "run_id": created["run_id"],
            "max_claims": max_claims,
            "llm": llm,
            "taken": set(),
        }
    )
    try:
        agent = create_agent(
            llm or model(),
            tools=QUEUE_TOOLS,
            system_prompt=prompt,
            middleware=queue_middleware(),
        )
        try:
            result = agent.invoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Work up to {max_claims} waiting claims.",
                        }
                    ]
                }
            )
            reply = result["messages"][-1].text
        except Exception as exc:
            reply = f"The run stopped: {exc}"
        catch_up()
        with backend() as client:
            current = client.get("/api/runs/current").json()
            if current["summary"] is None:
                client.post(
                    f"/api/runs/{current['run_id']}/summary",
                    json={"summary": reply},
                )
        return reply
    finally:
        _current.reset(token)


def cli() -> None:
    """Start a capped queue run, the whole queue, or one named claim."""
    args = sys.argv[1:]
    if len(args) == 1 and not args[0].isdigit():
        run(args[0], str(uuid.uuid4()))
        return
    if len(args) == 1:
        run_queue(int(args[0]))
        return
    with backend() as client:
        claims = client.get("/api/claims").json()
    waiting = sum(claim["status"] == "waiting" for claim in claims)
    run_queue(waiting)
