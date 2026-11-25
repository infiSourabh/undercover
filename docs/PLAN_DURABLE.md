# Durable state plan

SIDENOTE (from the brief): For consistency with the course, please read `labs/week2day3free.ipynb` and build the solution in the same style as the lab. Where the lab and this brief differ, follow the brief. Include this sidenote in your plan too.

This plan follows that sidenote. The claim agent becomes the lab's graph: a `ClaimState` TypedDict with `add_messages`, an `agent` node and a `ToolNode` looping until the model stops asking for tools, a `decide` node that turns the agent's work into a structured `ClaimDecision`, a `sign_off` node that waits with `interrupt()`, a `pay` node of its own, `RetryPolicy` on the nodes that call out, `PostgresSaver` with `durability="sync"`, and `Command(resume=...)` to carry on. Where the brief differs from the lab, the brief wins:

| The lab | This build, from the brief |
|---|---|
| The graph checks `payout > APPROVAL_LIMIT` | The backend says whether the claim needs a sign-off. The graph never applies the limit |
| The pay node writes to a `payments` table | The pay node calls the backend's `pay_claim`, which still blocks an unsigned payout over the limit |
| The decide node only keeps the decision in the state | A `record` node sends it to the backend. A refusal goes back to the model |
| The thread id is the claim id | Each fresh attempt gets a new thread id, stored on the claim, so a claim that fails starts afresh |
| Tables in the `lab` schema, one connection | Tables in the `undercover` schema, pooled, at most 4 connections a process |
| The handler is typed into a cell | The handler signs off on the dashboard, and the backend calls the agent's service |

`docs/PLAN.md` and `docs/PLAN_HARNESS.md` stay as they are. This file is the one we tick off.

## Where the brief and the code differ

- The brief says the middleware records every step, returns refusals and stops at 30 model calls. In the code, the tools write their own activity lines, a 409 comes back as a tool result, and the limit is 25. The graph keeps the intent: every node and tool writes an activity line, refusals go back to the model, and the limit becomes 30, as the brief says.
- The brief calls the service "a fourth part of the agent beside the three in `docs/CODE_STANDARDS.md`". Our `docs/CODE_STANDARDS.md` has no such list. The parts of the agent (instructions, tools, graph and service) are described in `docs/TECH_STACK.md` instead, and `docs/CODE_STANDARDS.md` stays as it is.
- `docs/SPEC.md` has no section called "working the queue". The section that describes how the agent works a claim is "The pilot", so that is the one that changes. "Rules" is left alone.

## How a claim moves now

| What happens | Claim status | Thread |
|---|---|---|
| A fresh attempt starts | `in_progress`, attempts + 1, new `thread_id` stored | New thread from `START` |
| Decline or refer is recorded | `decided` | Ends |
| Approval at or under the limit is recorded | `in_progress` | Goes straight to `pay` |
| Approval over the limit is recorded | `waiting_for_sign_off` | Pauses at `sign_off` with `interrupt()` |
| A handler signs off on the dashboard | `in_progress` | Backend calls the agent's service, which resumes with `Command(resume=...)` |
| The pay node succeeds | `decided` | Ends |
| The process is killed, restarted or stopped with Ctrl-C | stays `in_progress` | Checkpoint kept. The next run carries on from the last saved step, same thread, attempts unchanged |
| A node raises after its retries, the model-call limit is hit, or the graph ends with no decision | `waiting`, or `left_for_handler` on the second failure, as today | Abandoned. The next attempt gets a new thread |

The difference between "stopped" and "failed" is whether our code got to run. An exception is caught and the claim is released. A kill or Ctrl-C (`KeyboardInterrupt` is not an `Exception`) leaves the claim `in_progress` with its thread saved, so the next run finds it and carries on.

## Nothing happens twice

A node can run again after a restart, so the backend treats a repeat as done:

- `decide_claim` with the same outcome and payout as the stored decision returns 200 and the claim, and adds nothing. A different decision is still 409.
- `pay_claim` with the stored amount on a paid claim returns 200 and the claim, and adds nothing. A payment over the limit with no sign-off is still 409, whoever calls it.
- The `decide` node (one model call) and the `record` node (one backend call) are separate, so a restart during `record` sends the same decision again from the saved state instead of asking the model a second time.
- The `sign_off` node does nothing before `interrupt()`, because LangGraph runs it again from the top on resume.

## The graph

```
START -> agent -> tools -> agent ... -> decide -> record -> sign_off -> pay -> END
                                          |         |           (over the limit)
                                          |         +-> pay -> END   (approve, no sign-off)
                                          |         +-> END          (decline or refer)
                                          |         +-> agent        (refused: the reason goes back to the model)
              agent -> END when the model-call count reaches 30 (a failure)
```

State, as in the lab:

```python
class ClaimState(TypedDict):
    messages: Annotated[list, add_messages]
    claim_id: str
    model_calls: int
    decision: dict          # outcome, payout, explanation, policy_section from ClaimDecision
    needs_sign_off: bool    # from the backend's answer to record, never worked out here
    signed_off_by: str
    signed_off_at: str
```

Tools on the `agent` node: `get_claim`, `list_sections`, `read_section` and `calculate_payout`. The claim agent loses `decide` and `pay` as tools. Deciding is the `decide` node's structured output, as in the lab, and paying is the `pay` node. `ToolNode(handle_tool_errors=True)` returns a tool's error to the model. `RetryPolicy(max_attempts=3)` sits on `agent`, `tools`, `decide`, `record` and `pay`, in place of `ModelRetryMiddleware` and `ToolRetryMiddleware`.

The queue agent stays on `create_agent` with its middleware. It gains the same checkpointer, with the run id as its thread, so a stopped queue run can be finished.

## Connections

The Supabase free plan allows 15 connections through the session pooler. Each process uses at most 4:

| Process | Pool |
|---|---|
| Backend (`uvicorn`, the reloader's worker) | SQLAlchemy, `pool_size=4`, `max_overflow=0` |
| Agent service | `psycopg_pool.ConnectionPool`, `max_size=2`, for the checkpointer |
| `uv run -m agent` | the same, `max_size=2` |

That is at most 8 during a live run, under the 12 the brief checks for. The agent reaches our tables only through the backend's API, so it has no SQLAlchemy pool. Every Postgres connection sets `options="-c search_path=undercover"`, so the SQL stays the same as on SQLite, and the checkpointer gets `autocommit=True`, `prepare_threshold=0` and `row_factory=dict_row`, as in the lab.

## The environment

Today `agent/main.py` calls `load_dotenv(override=True)` when it is imported, and the backend imports it, so the backend and pytest both read `.env`. That would point the tests at Supabase. In this build:

- `load_dotenv` moves into the agent's entry points (`uv run -m agent` and the service).
- The backend no longer imports the agent. It reads `DATABASE_URL` only from its environment.
- `npm run dev` and a new `npm run seed` pass `.env` with `uv run --env-file .env`. The tests and Playwright never do.
- Without `DATABASE_URL`, the backend uses `backend/undercover.sqlite` and the agent uses LangGraph's in-memory saver. That keeps tests offline, but a pause does not outlive the process there. Durable state is a Supabase feature, which is what the brief asks for.

## API

Every new operation has an `operation_id`, a one-line docstring and no optional inputs.

Backend:

| Method | Path | operation_id | Body |
|---|---|---|---|
| POST | `/api/payouts` | `work_out_payout` | `{policy_id, benefit, lines, paid_by_others}` |
| POST | `/api/claims/{claim_id}/start` | `start_claim` | `{thread_id}` |
| POST | `/api/claims/{claim_id}/decision` | `decide_claim` | unchanged; a repeat is 200 |
| POST | `/api/claims/{claim_id}/payment` | `pay_claim` | unchanged; a repeat is 200 |
| POST | `/api/claims/{claim_id}/sign-off` | `sign_off_claim` | unchanged; now stores the time, sets `in_progress` and calls the agent's service |
| POST | `/api/claims/{claim_id}/run` | `run_claim` | unchanged; now asks the agent's service to work the claim |

Each line in `lines` is `{description, amount, quantity, kind, nights, hours}`, all required, so the API has no optional inputs. `work_out_payout` returns `{calculation, payout, needs_sign_off}`, using the policy, plan, add-ons and approval limit in our database, which are seeded from `data/plans.json` and `data/company.json`.

A claim gains `thread_id` and `attempts`. `sign_off` gains `signed_off_at`. `payment` gains `paid_at`, `signed_off_by` and `signed_off_at`, copied from the sign-off when the payment is made. Times are ISO 8601 in UTC.

Agent service, at `UNDERCOVER_AGENT` or `http://127.0.0.1:8002`:

| Method | Path | operation_id | What it does |
|---|---|---|---|
| GET | `/health` | `health` | `{"status": "ok"}` |
| POST | `/claims/{claim_id}/run` | `run_claim` | Works the claim on a background thread, returns 202 |
| POST | `/claims/{claim_id}/resume` | `resume_claim` | Carries on the claim's thread after a sign-off, on a background thread, returns 202 |

The backend calls `resume_claim` after the sign-off is committed, as a FastAPI background task, so the handler's request doesn't wait for the payment. If the service can't be reached, the error is logged and the sign-off stands; the next `uv run -m agent` picks the claim up. "Work this claim" also goes through the service, so the backend never runs the graph or holds checkpointer connections. That is the split the brief describes for the cloud.

## Phase 1: The payout rules and tracing

The payout rules from `labs/week2day1_payout.py` move into `backend/payout.py`. The functions keep their shape (`limit_for`, `eligible_amount`, `benefit_maximum`, `work_out_payout`), but take the plan, the add-ons and the approval limit from our database instead of reading the JSON files, so the backend stays the system of record. The claim agent, still on `create_agent` in this phase, gets `calculate_payout`, which calls `work_out_payout` over HTTP. The claim instructions say to use it, as the lab's `PAYOUT_TOOL_LINE` does.

Tracing uses Langfuse's `CallbackHandler`, as in `labs/week2day1free.ipynb`, passed in the run's `config` with `metadata={"langfuse_session_id": f"{claim_id}-{thread_id}"}`. Every invoke on that thread, before and after a pause, lands in one session. Tracing is on only when `LANGFUSE_PUBLIC_KEY` is set, so tests never reach Langfuse. `load_dotenv` moves out of import time here, because tracing is the first thing that depends on it.

- [ ] `POST /api/payouts` for `POL-2002`, benefit `baggage`, with the six lines of `CLM-1002` (the wool suit at $420 as an `item`, the four shirts with quantity 4) and `paid_by_others` 0 returns `payout` 980.00, `needs_sign_off` false, a step `Wool suit, limited to $300.00` and a step `Less the deductible` of -50.
- [ ] The same call for `POL-2011` with the eight lines of `CLM-1011` returns `needs_sign_off` true.
- [ ] Cash over $100, a hotel over $350 a room a night, meals without receipts at $35 a traveler a day, and a trip cancellation over the trip cost each have a test with the expected step.
- [ ] An unknown policy is 404, and a line without `quantity` is 422.
- [ ] The approval limit comes from the `company` table: a test that seeds a limit of 2,000 gets `needs_sign_off` false for the `POL-2011` case.
- [ ] The OpenAPI spec lists `work_out_payout` with no optional inputs.
- [ ] A stubbed claim run calls `calculate_payout` and the activity shows `Worked out the payout: $980.00`.
- [ ] With `LANGFUSE_PUBLIC_KEY` unset, `run` passes no Langfuse callback. With it set (monkeypatched, handler stubbed), the config carries the callback and `langfuse_session_id` of `CLM-1001-thread-1`.
- [ ] `uv run pytest -q` passes at 80% coverage with `.env` moved out of the way.

## Phase 2: The database on SQLAlchemy Core and Supabase

`backend/db.py` describes every table once as SQLAlchemy Core `Table`s, and `store.py`, `actions.py` and `runs.py` use Core queries, so each query is written once for SQLite and Postgres. The SQLite-only parts go: `JOIN company` without `ON`, `INSERT ... ON CONFLICT`, `executescript` and `sqlite3.Row`. `create_app(database_url)` takes a URL; tests pass `sqlite:///<tmp>`. The default is `DATABASE_URL` when it is set (rewritten to `postgresql+psycopg://`), otherwise the SQLite file. On Postgres, the engine sets `search_path=undercover`, `pool_size=4`, `max_overflow=0` and `pool_pre_ping=True`.

Seeding creates the `undercover` schema on Postgres, drops and recreates our tables, loads `data/` as today, and empties the checkpointer's tables when they exist, so a reseed also forgets saved threads. `sqlalchemy` moves into the main dependencies; today it is only in the `server` group, which `uv sync` doesn't install.

This phase also brings in the store changes the graph needs: `thread_id` and `attempts` on a claim, `start_claim`, the time on a sign-off, who signed off and when on a payment, and a repeated decision or payment counting as done. A sign-off now sets the claim `in_progress`.

- [ ] `uv run pytest -q` passes with `.env` moved out of the way and no network, on SQLite.
- [ ] `npm run seed` prints `Reset the queue: 25 claims waiting.` against Supabase, twice in a row.
- [ ] Through the Supabase MCP server, `list_tables` for the `undercover` schema shows our tables and `public` has none of them. `SELECT count(*) FROM undercover.claims` is 25.
- [ ] `npm run dev` with `.env` serves `GET /api/claims` from Supabase: 25 claims, all waiting.
- [ ] `POST /api/claims/CLM-1001/start` with a thread id sets `in_progress`, stores the thread id and sets attempts to 1. A second start with another thread id sets attempts to 2.
- [ ] Approving `CLM-1001` for 420 twice returns 200 both times, with one decision and one `Approved $420.00.` line. Approving it for 400 after that is 409.
- [ ] Paying `CLM-1001` 420 twice returns 200 both times with one payment. Paying `CLM-1002` 1150 after an approval and no sign-off is still 409.
- [ ] After a sign-off by `Dana Whitfield`, `CLM-1002` is `in_progress`, its sign-off has `signed_off_at`, and a payment of 1150 records `signed_off_by` and `signed_off_at` with a `paid_at`.
- [ ] A backend test of the engine's settings for a Postgres URL shows `search_path=undercover`, pool size 4 and no overflow, without connecting.

## Phase 3: The claim agent as a LangGraph graph

`agent/graph.py` builds the graph above. `run(claim_id, thread_id)` stays the entry point for one attempt; a new `work(claim_id)` decides what to do with a claim:

1. If the claim is `in_progress` with a `thread_id` and that thread has a next step, carry on: `invoke(None, config)`, attempts unchanged, and the activity line `Carried on from the last saved step.`
2. If it is `in_progress` after a sign-off and its thread waits at `sign_off`, resume with `Command(resume={handler, signed_off_at})` from the stored sign-off.
3. Otherwise start fresh: a new thread id, `start_claim`, then `invoke` from `START`.

An exception, the model-call limit or an end with no decision releases the claim as today (`retry`, then `handler`). `invoke` uses `durability="sync"`. `work_claim` in the queue agent and the CLI's single claim both call `work`.

The checkpointer is `PostgresSaver` on a pool of 2 when `DATABASE_URL` is set, after `setup()`, and LangGraph's `InMemorySaver` otherwise. Tests pass an `InMemorySaver` and build a second graph on it to stand in for a restart.

`uv run -m agent` first carries on every claim that was stopped or signed off while the agent was away (steps 1 and 2 above). Then, if the latest queue run has no summary, it finishes that run: the queue agent resumes its own thread, its `taken` set is rebuilt from the run's to-do list, and the missed-claim check and summary follow. Otherwise it starts the run it was asked for.

The claim instructions drop "pay that payout" and say to work out the payout with the payout tool, then give the decision, payout and reasons in the reply; the system records it and pays it, and a payout over $1,000 waits for a handler. The queue instructions' line about sign-off stays true.

- [ ] Stub model, `CLM-1001`: the graph reads the claim, a section and the payout, the decide node returns approve 420, and the pay node pays. The claim is `decided` with one payment, and the activity has a line for every step.
- [ ] Stub model, `CLM-1002` approved for 1150: the run returns with `__interrupt__`, `get_state(config).next` is `("sign_off",)`, the claim is `waiting_for_sign_off`, and there is no payment. The graph's code has no reference to the limit.
- [ ] After a sign-off by Dana Whitfield, `work("CLM-1002")` resumes the same thread and pays 1150 once. The payment has her handler id and the sign-off time. A second `work` call adds no payment.
- [ ] A stub model that raises `KeyboardInterrupt` on its third call leaves `CLM-1001` `in_progress` with attempts 1. A second graph on the same saver, via `work`, carries on with the same thread id, does not call `get_claim` again, ends with attempts 1, one decision and one payment.
- [ ] A stub model that raises `RuntimeError` on every call releases `CLM-1004` to `waiting` with failures 1. The next `work` starts a new thread id and attempts become 2. A second failure leaves it for a handler.
- [ ] Stub decision `decline` with payout 50: the record node's refusal goes back to the model as a message, the model's next decision `decline` 0 is recorded, and the claim is `decided`.
- [ ] A stub that always asks for a tool stops after 30 model calls and the claim is released.
- [ ] Running the `record` node twice on the same state leaves one decision; running the `pay` node twice leaves one payment.
- [ ] A stubbed `run_queue(2)` still writes the to-do list, works two claims and stores a summary. A run whose summary is null is finished by the next `run_queue` call: no new run is created and the summary is stored on the old run.
- [ ] `uv run pytest -q` passes at 80% coverage with `.env` moved out of the way.

## Phase 4: The agent's service

`agent/service.py` is a FastAPI app with `health`, `run_claim` and `resume_claim`. Each POST checks the claim through the backend and returns 202, then calls `work(claim_id)` on a thread, so the backend never waits on a model. A lock per claim id stops one process working the same claim twice at once.

The backend gets `UNDERCOVER_AGENT` from its environment, or `http://127.0.0.1:8002`. `sign_off_claim` commits, then adds a background task that posts to `resume_claim`; `httpx.HTTPError` is logged and ignored, which is the one place this build catches an error on purpose. `run_claim` posts to the service's `run_claim` and returns 503 with `The agent isn't running.` when it can't be reached. The backend's `_run_agent` thread and its import of `agent.main` go.

`npm run dev` runs three processes with `concurrently`: backend, agent and dashboard. Each is a `uv run` or `vite` command, so it works on Windows.

- [ ] A backend test with the notifier replaced records one call for `CLM-1002` after its sign-off, and only after the sign-off is stored.
- [ ] With `UNDERCOVER_AGENT` pointing at a closed port, a sign-off returns 200, the claim stays `in_progress` with its sign-off, and nothing is paid.
- [ ] Service tests with `work` replaced: `POST /claims/CLM-1002/resume` returns 202 and calls `work("CLM-1002")` once. `GET /health` is ok. The OpenAPI spec lists the three operation ids with no optional inputs.
- [ ] `npm run dev` starts the backend on 8000, the agent on 8002 and the dashboard on 5173, and `curl http://127.0.0.1:8002/health` returns ok.
- [ ] `uv run pytest -q` passes at 80% coverage.

## Phase 5: The dashboard and the end-to-end tests

The claim page shows who signed off and when, and when the claim was paid. The Pay button goes, because paying is now the agent's step; after a sign-off the status pill reads In progress until the agent pays. Sign off stays for Waiting for sign-off. Everything else stays as it is.

Playwright gets its own ports so it never reaches the servers `npm run dev` starts: the backend on 8001, the dashboard on 5174 with its `/api` proxy pointed at 8001 (the proxy target becomes `UNDERCOVER_API`, defaulting to 8000), and a stand-in for the agent's service on 8003. The stand-in is `e2e/agent_stand_in.mjs`, a small Node server that records the posts it gets and lists them at `GET /calls`. The backend under test gets `UNDERCOVER_AGENT=http://127.0.0.1:8003` through Playwright's `webServer.env`. `reuseExistingServer` is off for all three.

- [ ] Vitest: a claim with a sign-off at a set time shows `Dana Whitfield signed off` with that time; a paid claim shows `Paid $1,150.00` with the time; no claim shows a Pay button.
- [ ] Playwright: after the test approves `CLM-1002` for 1150, signing off as Dana Whitfield on the page shows In progress, and the stand-in's `/calls` lists `resume_claim` for `CLM-1002` within five seconds.
- [ ] Playwright: after that, the test posts the payment as the agent would, and the page shows Decided, `$1,150.00`, Dana Whitfield and the time.
- [ ] The other end-to-end tests still pass, with the under-limit payment posted through the API instead of the removed Pay button.
- [ ] `npm run check` passes with `npm run dev` running at the same time.

## Phase 6: Live checks and the documents

Each live check starts from `npm run seed`, with `npm run dev` running, and is capped at five claims. `.env` sets `MODEL_NAME`; the brief asks for the default model, so the live run unsets it for that command only (`MODEL_NAME= uv run -m agent 5` on a Mac, `$env:MODEL_NAME=""; uv run -m agent 5` in PowerShell). This needs credit on OpenRouter. The Playwright MCP server is not configured on this machine yet, so this phase starts with `claude mcp add playwright -- npx @playwright/mcp@latest`.

`docs/SPEC.md`'s "The pilot" section describes the pause for a sign-off and carrying on after a restart, and "Rules" is unchanged. `docs/TECH_STACK.md` describes Supabase with SQLAlchemy Core, the `undercover` schema and pools, the graph, the checkpointer, the service and Langfuse. `docs/PROCESS.md` says `npm run dev` starts three processes, how to reseed Supabase, and that Playwright uses its own ports. `docs/STATUS.md` says how to run all of it.

- [ ] After `npm run seed`, `MODEL_NAME= uv run -m agent 5` works five claims. The other twenty stay Waiting.
- [ ] A claim over the limit waits for a sign-off. Signed off on the dashboard through the Playwright MCP server, it shows Decided with the payment, the handler and the time within five seconds.
- [ ] After a reseed, `uv run -m agent CLM-1001` is killed after its first two activity lines. The claim is `in_progress` and its thread has a next step in `undercover.checkpoints`. The next `uv run -m agent CLM-1001` carries on with the same thread id, attempts still 1, and one decision.
- [ ] During the live run, `SELECT count(*) FROM pg_stat_activity WHERE usename = 'postgres'` through the Supabase MCP server is 12 or fewer.
- [ ] Through Langfuse's API, the held claim's session `<claim>-<thread>` has traces from before and after the sign-off.
- [ ] `docs/SPEC.md`, `docs/TECH_STACK.md`, `docs/PROCESS.md` and `docs/STATUS.md` describe the product as it now is. `docs/PLAN.md` and `docs/PLAN_HARNESS.md` are unchanged.
- [ ] With `.env` moved out of the way, `npm run check` passes: ruff, pyright, pytest at 80% coverage, ESLint, Prettier, tsc, vitest at 80% coverage, and Playwright.
