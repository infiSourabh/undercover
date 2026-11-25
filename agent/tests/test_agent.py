import sys
from contextlib import contextmanager
from pathlib import Path

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import main
from agent.__main__ import cli as agent_entry
from backend.runs import failure_count
from backend.store import instructions


def _patch_backend(monkeypatch, client) -> None:
    @contextmanager
    def fake_backend():
        yield client

    monkeypatch.setattr(main, "backend", fake_backend)


APPROVE_1001 = {
    "claim_id": "CLM-1001",
    "outcome": "approve",
    "payout": 420,
    "explanation": "The delay is covered. The payout is the claimed expenses.",
    "policy_section": "3. Trip Delay",
}

APPROVE_1002 = {
    "claim_id": "CLM-1002",
    "outcome": "approve",
    "payout": 1150,
    "explanation": "Approved over the handler limit.",
    "policy_section": "5. Baggage and Personal Effects",
}


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    def bind_tools(self, tools, **kwargs):
        return self


def _run_replies(decide_args: dict, amount: float) -> list[AIMessage]:
    claim_id = decide_args["claim_id"]
    return [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_claim", "args": {"claim_id": claim_id}, "id": "1"}
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "list_sections",
                    "args": {"claim_id": claim_id, "name": "wording"},
                    "id": "2",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_section",
                    "args": {
                        "claim_id": claim_id,
                        "name": "wording",
                        "heading": "3. Trip Delay",
                    },
                    "id": "2b",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "decide", "args": decide_args, "id": "3"}],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "pay",
                    "args": {"claim_id": claim_id, "amount": amount},
                    "id": "4",
                }
            ],
        ),
        AIMessage(content="Done."),
    ]


def test_run_under_limit(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    main.run(
        "CLM-1001",
        "thread-1",
        StubModel(messages=iter(_run_replies(APPROVE_1001, 420))),
    )
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 420
    messages = [
        row["message"] for row in client.get("/api/claims/CLM-1001/activity").json()
    ]
    assert "Read policy wording: 3. Trip Delay" in messages


def test_system_prompt_from_instructions(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    captured: dict[str, str] = {}

    def fake_create_agent(llm, tools, system_prompt, middleware):
        captured["prompt"] = system_prompt
        captured["middleware"] = middleware

        class Fake:
            def invoke(self, *args, **kwargs):
                return {"messages": [AIMessage(content="ok")]}

        return Fake()

    monkeypatch.setattr(main, "create_agent", fake_create_agent)
    main.run("CLM-1001", "thread-1", StubModel(messages=iter([])))
    body = client.get("/api/instructions").json()
    assert captured["prompt"] == body["claim"]
    assert captured["prompt"] == instructions()["claim"]
    middleware = captured["middleware"]
    assert isinstance(middleware[0], ModelRetryMiddleware)
    assert isinstance(middleware[1], ToolRetryMiddleware)
    assert isinstance(middleware[2], ModelCallLimitMiddleware)
    assert middleware[2].run_limit == 25
    assert middleware[2].exit_behavior == "end"


def test_run_over_limit_blocks_payment(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    main.run(
        "CLM-1002",
        "thread-2",
        StubModel(messages=iter(_run_replies(APPROVE_1002, 1150))),
    )
    blocked = main.pay.invoke({"claim_id": "CLM-1002", "amount": 1150})
    assert "sign-off" in blocked.lower()
    claim = client.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "waiting_for_sign_off"
    assert claim["payment"] is None


def test_tools_do_not_read_held_out_data():
    source = Path(main.__file__).read_text()
    assert "evals" not in source
    assert "security" not in source


def _steps(*steps: tuple[str, dict]) -> list[AIMessage]:
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": str(index)}],
        )
        for index, (name, args) in enumerate(steps, start=1)
    ]
    messages.append(AIMessage(content="Run finished."))
    return messages


def _decline(client, claim_id: str) -> None:
    client.post(
        f"/api/claims/{claim_id}/decision",
        json={
            "outcome": "decline",
            "payout": 0,
            "explanation": "Outside the cover.",
            "policy_section": "9. General exclusions",
        },
    )


def test_run_queue_caps_the_run(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    worked: list[str] = []

    def fake_run(claim_id: str, thread_id: str, llm=None) -> str:
        worked.append(claim_id)
        _decline(client, claim_id)
        return "ok"

    monkeypatch.setattr(main, "run", fake_run)
    main.run_queue(
        2,
        StubModel(
            messages=iter(
                _steps(
                    (
                        "update_todos",
                        {
                            "items": [
                                {"claim_id": "CLM-1001", "status": "todo"},
                                {"claim_id": "CLM-1002", "status": "todo"},
                            ]
                        },
                    ),
                    ("work_claim", {"claim_id": "CLM-1001"}),
                    ("work_claim", {"claim_id": "CLM-1002"}),
                    ("finish", {"summary": "Decided two claims."}),
                )
            )
        ),
    )
    current = client.get("/api/runs/current").json()
    assert [item["status"] for item in current["items"]] == ["done", "done"]
    assert current["summary"] == "Decided two claims."
    assert worked == ["CLM-1001", "CLM-1002"]
    assert client.get("/api/claims/CLM-1003").json()["status"] == "waiting"


def test_decide_conflict_is_returned(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    detail = main.decide.invoke(
        {
            "claim_id": "CLM-1001",
            "outcome": "decline",
            "payout": 10,
            "explanation": "Outside the cover.",
            "policy_section": "3. Trip Delay",
        }
    )
    assert "payout" in detail.lower()
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    assert claim["decision"] is None


def test_failed_claim_does_not_stop_the_run(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    monkeypatch.setattr(main, "catch_up", lambda: None)
    worked: list[str] = []

    def fake_run(claim_id: str, thread_id: str, llm=None) -> str:
        worked.append(claim_id)
        if claim_id == "CLM-1004":
            raise RuntimeError("model failed")
        _decline(client, claim_id)
        return "ok"

    monkeypatch.setattr(main, "run", fake_run)
    main.run_queue(
        2,
        StubModel(
            messages=iter(
                _steps(
                    ("work_claim", {"claim_id": "CLM-1004"}),
                    ("work_claim", {"claim_id": "CLM-1005"}),
                    ("finish", {"summary": "Kept going."}),
                )
            )
        ),
    )
    assert worked == ["CLM-1004", "CLM-1005"]
    assert client.get("/api/claims/CLM-1004").json()["status"] == "waiting"
    assert client.get("/api/runs/current").json()["summary"] == "Kept going."


def test_second_failure_is_left_for_a_handler(monkeypatch, client, db_path):
    _patch_backend(monkeypatch, client)
    monkeypatch.setattr(main, "catch_up", lambda: None)
    worked: list[str] = []

    def fake_run(claim_id: str, thread_id: str, llm=None) -> str:
        worked.append(claim_id)
        raise RuntimeError("model failed")

    monkeypatch.setattr(main, "run", fake_run)
    main.run_queue(
        1,
        StubModel(
            messages=iter(
                _steps(
                    ("work_claim", {"claim_id": "CLM-1004"}),
                    ("work_claim", {"claim_id": "CLM-1004"}),
                    ("work_claim", {"claim_id": "CLM-1004"}),
                    ("finish", {"summary": "Left one claim."}),
                )
            )
        ),
    )
    assert worked == ["CLM-1004", "CLM-1004"]
    assert client.get("/api/claims/CLM-1004").json()["status"] == "left_for_handler"
    assert failure_count(db_path, "CLM-1004") == 2


def test_catch_up_works_one_missed_claim(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    worked: list[str] = []

    def fake_run(claim_id: str, thread_id: str, llm=None) -> str:
        worked.append(claim_id)
        _decline(client, claim_id)
        return "ok"

    monkeypatch.setattr(main, "run", fake_run)
    main.run_queue(
        2,
        StubModel(
            messages=iter(
                _steps(
                    ("work_claim", {"claim_id": "CLM-1001"}),
                    ("finish", {"summary": "Checked the queue."}),
                )
            )
        ),
    )
    assert worked == ["CLM-1001", "CLM-1002"]
    assert client.get("/api/claims/CLM-1003").json()["status"] == "waiting"


def test_second_work_does_not_decide_again(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    monkeypatch.setattr(main, "catch_up", lambda: None)
    worked: list[str] = []

    def fake_run(claim_id: str, thread_id: str, llm=None) -> str:
        worked.append(claim_id)
        client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
        client.post("/api/claims/CLM-1001/payment", json={"amount": 420})
        return "ok"

    monkeypatch.setattr(main, "run", fake_run)
    main.run_queue(
        1,
        StubModel(
            messages=iter(
                _steps(
                    ("work_claim", {"claim_id": "CLM-1001"}),
                    ("work_claim", {"claim_id": "CLM-1001"}),
                    ("finish", {"summary": "Paid once."}),
                )
            )
        ),
    )
    assert worked == ["CLM-1001"]
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["decision"]["payout"] == 420
    assert claim["payment"]["amount"] == 420


def test_module_entrypoint():
    assert agent_entry is main.cli


def test_cli_chooses_a_run(monkeypatch, client):
    _patch_backend(monkeypatch, client)
    seen: dict[str, object] = {}

    def fake_queue(max_claims: int, llm=None) -> str:
        seen["cap"] = max_claims
        return "ok"

    def fake_run(claim_id: str, thread_id: str, llm=None) -> str:
        seen["claim"] = claim_id
        return "ok"

    monkeypatch.setattr(main, "run_queue", fake_queue)
    monkeypatch.setattr(main, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["agent", "5"])
    main.cli()
    assert seen["cap"] == 5
    monkeypatch.setattr(sys, "argv", ["agent", "CLM-1009"])
    main.cli()
    assert seen["claim"] == "CLM-1009"
    monkeypatch.setattr(sys, "argv", ["agent"])
    main.cli()
    assert seen["cap"] == 25


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    default = main.model()
    assert default.model_name == "deepseek/deepseek-v4.1-flash"
    assert default.reasoning_effort == "low"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    override = main.model()
    assert override.model_name == "openrouter/free"
    assert override.reasoning_effort is None
