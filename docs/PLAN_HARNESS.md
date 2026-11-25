# Harness plan

The queue agent takes the whole waiting queue in one run. It writes a to-do list, chooses the order, and hands each claim to a fresh claim agent. That claim agent reads only the sections of the policy wording and the claims manual it needs, then decides and, when it approves, pays. A trial run takes a cap and leaves every other claim waiting. One named claim can still be run on its own.

Both agents are LangChain's `create_agent` on OpenRouter, which is already the stack in `docs/TECH_STACK.md`. The to-do list is a tool of ours, stored in SQLite, so the queue page can show it and an item can be left for a handler. LangChain's `ModelRetryMiddleware`, `ToolRetryMiddleware`, and `ModelCallLimitMiddleware` sit on `create_agent` and cover a timeout or a provider error on a single call. The claim-level rules live in our `work_claim` tool, so a stub model can prove them and a confused model cannot leave a claim stuck in progress.

The wording stays the contract. The manual covers what the wording leaves open. A payout over $1,000 still waits for a handler's sign-off, and that rule stays in `pay_claim`. The agent never sees `data/evals/`. Tests never call a model. A live run is reseeded first and capped at five claims, and it is not part of `npm run check`.

`docs/PLAN.md` stays as the finished pilot plan. This file is the one we tick off.

## How a run moves

`uv run -m agent` works every waiting claim. `uv run -m agent 5` caps the run at five. `uv run -m agent CLM-1001` runs that one claim. The first two call `run_queue(max_claims)`. The third calls `run(claim_id, thread_id)`, which stays the single-claim entry point the dashboard already uses.

A run has a cap. The queue agent chooses which waiting claims to take, up to that cap, and in which order. Each taken claim is one to-do item: `todo`, `in_progress`, `done`, or `left_for_handler`. A retry of the same claim does not use a second place in the cap. Claims that were never taken stay `waiting`.

| What happens | Claim status | To-do item |
|---|---|---|
| The run takes the claim | `in_progress` | `in_progress` |
| The claim agent records a decision | `in_progress`, `waiting_for_sign_off`, or `decided`, as in the pilot | `done` |
| The attempt ends with no decision, and this run has failed it once | `waiting` | `todo` |
| The attempt ends with no decision, and this run has failed it twice | `left_for_handler` | `left_for_handler` |

A decision row or a payment row is never replaced. `decide_claim` returns 409 when a decision already exists, including an approval that is still unpaid. `pay_claim` already returns 409 when a payment exists. `work_claim` builds its one-line report from the stored claim, so a second attempt that finds a decision pays only when the pilot rules allow it and does not call the model to decide again.

Failure counts live on the claim and reset when the database is seeded. The queue runner does not pick up `left_for_handler`. **Work this claim** still can, so a handler can try that claim again. If that attempt also ends with no decision, the claim goes back to `left_for_handler` rather than sitting in progress.

## API

Every new operation has an `operation_id`, a one-line docstring, and no optional inputs. Errors use FastAPI's `detail` string.

| Method | Path | operation_id | Body |
|---|---|---|---|
| GET | `/api/documents/{name}/sections` | `list_sections` | |
| GET | `/api/documents/{name}/sections/{heading}` | `read_section` | |
| POST | `/api/runs` | `create_run` | `{max_claims}` |
| GET | `/api/runs/current` | `get_current_run` | |
| PUT | `/api/runs/{run_id}/todos` | `put_todos` | `{items}` |
| POST | `/api/runs/{run_id}/summary` | `put_run_summary` | `{summary}` |
| POST | `/api/claims/{claim_id}/release` | `release_claim` | `{result}` |

`name` is `wording` or `manual`. `heading` is the section heading, such as `3. Trip Delay`. Anything else is 404.

`create_run` stores the run and returns `{run_id, max_claims, summary, items}`. It does not start a model. `summary` is null until the run finishes. `items` is empty until the agent writes the list. `get_current_run` is the latest run, or 404 when there is none. `items` keep the order they were written. Each item is `{claim_id, status}` with status `todo`, `in_progress`, `done`, or `left_for_handler`. A bad status or an unknown claim is 409.

`release_claim` is how a failed attempt leaves the claim. `result` is `retry` or `handler`. With no decision, `retry` sets `waiting` and `handler` sets `left_for_handler`, and both add one to the failure count. With a decision already stored, the call is 409 and the status stays as it is.

`GET /api/instructions` becomes `{"queue": "...", "claim": "..."}`. `GET /api/policy-wording` stays, for the store. The claim agent does not call it.

The screen labels for a claim are Waiting, In progress, Waiting for sign-off, Decided, and Left for a handler. To-do labels are To do, In progress, Done, and Left for a handler.

## Instructions

Two files, `backend/instructions_queue.md` and `backend/instructions_claim.md`. The queue prompt receives the cap as the first line when the run starts. The text below is the claim prompt and the queue prompt. Both are written from `data/policy_wording.md` and `data/claims_manual.md`.

Claim:

```
You are the UnderCover Agent. You decide one travel insurance claim.

The policy wording is the contract with the customer. The claims manual covers what the wording leaves open, including which documents to ask for, how to read a clause, repeat claims, and how to work out a payment. Where they disagree, follow the wording.

For this claim:

1. Read the claim, the customer's policy, and the claim history.
2. List the sections of the policy wording and of the claims manual. Read only the sections that apply. Read a section before you rely on it.
3. Approve, decline, or refer. Approve when the incident is covered and the required documents are on file. Decline when the wording leaves the loss outside the cover. Refer when a required document is missing, when the story and the documents disagree, when this is the customer's third claim within 12 months, or when the wording and the manual together still do not settle it. Say what is needed.
4. When you approve, work out the payout in US dollars. Follow section 10 of the wording and the payout section of the manual. Start from the eligible amount of each item, take off anything a carrier or another party has already paid, take off the deductible where it applies, and stop at the maximum for that benefit.
5. Record the decision with a reason of two or three sentences and the section of the wording you relied on.
6. When you approve, pay that payout. A payout over $1,000 waits until a handler signs off. If payment is blocked, stop. Do not try another amount, and do not record a second decision.
```

Queue:

```
You are the UnderCover Agent working the claims queue. This run may take on at most {cap} claims. Leave every other waiting claim untouched.

1. List the waiting claims and choose which ones to work, up to the cap, in the order you choose.
2. Write a to-do list with one item for each claim you take. Keep each item as to do, in progress, done, or left for a handler.
3. Hand each claim to the claim helper. It starts from a clean conversation and answers in one line: the decision and the payout, or what went wrong. Do not decide the claim yourself.
4. When the line says the claim is back in the queue, hand that claim over once more. When the line says it is left for a handler, mark it and move on. One claim never stops the run.
5. Before you finish, list the waiting claims again. When a claim you took on is still waiting, and this run is still under the cap, hand it over. Do not start a claim past the cap.
6. End with a short summary for the handlers: how many claims were decided, which are waiting for sign-off, and which are left for a handler.
```

## Phase 1: The manual and its sections

Load `data/claims_manual.md` into SQLite next to the policy wording, and serve one section at a time. The seed test that lists files is updated so `claims_manual.md` is expected. `data/evals/`, `data/security/`, and `data/knowledge.json` stay unread.

Sections are the `##`  headings already in the two documents. `read_section` returns the heading and the text up to the next heading. The claim page shows a read by the activity line the agent writes in phase 3, so this phase only stores and serves the text.

- [x] `uv run -m backend.seed` prints `Reset the queue: 25 claims waiting.` and exits 0.
- [x] The seed test's file list includes `claims_manual.md` and does not include `evals`, `security`, or `knowledge.json`.
- [x] `GET /api/documents/manual/sections` includes `9. Repeat claims` and `10. Meals without receipts`.
- [x] `GET /api/documents/wording/sections` includes `3. Trip Delay` and `10. How we work out your payment`.
- [x] `GET /api/documents/manual/sections/10. Meals without receipts` contains `$35`.
- [x] `GET /api/documents/manual/sections/7. Interpretation notes` contains `Wild animals`.
- [x] `GET /api/documents/other/sections` and a missing heading return 404.
- [x] The OpenAPI spec lists `list_sections` and `read_section`, and neither takes an optional parameter.
- [x] `uv run pytest -q backend/tests` passes.

## Phase 2: The run and the to-do list

Store the current run, its to-do list, its summary, and each claim's failure count. `create_run` does not call the agent. Releasing a claim is a store rule, so later phases can trust it without a model.

`docs/SPEC.md` drops the claims manual from "Not for now" and says decisions follow the policy wording and the claims manual, with the wording winning if they disagree. It names the queue run, the cap, the to-do list, and a claim left for a handler after two failures.

- [x] `POST /api/runs` with `{"max_claims": 5}` returns a run whose `max_claims` is 5, `summary` is null, and `items` is empty.
- [x] `PUT /api/runs/{run_id}/todos` with `CLM-1001` as `todo` and `CLM-1002` as `in_progress` is what `GET /api/runs/current` returns, in that order.
- [x] A to-do status of `skipped`, or a claim id that does not exist, returns 409.
- [x] `POST /api/claims/CLM-1003/release` with `{"result": "retry"}` sets that claim to `waiting` and its failure count to 1.
- [x] A second release with `{"result": "handler"}` sets `left_for_handler` and the failure count to 2.
- [x] After the phase-3-style approval of `CLM-1001` for 420, a second `decide_claim` returns 409 and the stored payout is still 420. Releasing that claim returns 409 and the status stays `in_progress`.
- [x] `uv run pytest -q backend/tests` passes.

## Phase 3: The claim agent

`run(claim_id, thread_id)` loads the claim instructions and calls `create_agent` with a new message list. The model is `deepseek/deepseek-v4.1-flash` at low reasoning effort, or `MODEL_NAME` when that variable is set. When `MODEL_NAME` is set, reasoning effort is left unset, so `openrouter/free` still works.

Tools call the backend over HTTP and do not open files under `data/`.

| Tool | API | Activity line |
|---|---|---|
| `get_claim(claim_id)` | `GET /api/claims/{claim_id}` | `Read the claim, the policy, and the claim history` |
| `list_sections(claim_id, name)` | `GET /api/documents/{name}/sections` | none |
| `read_section(claim_id, name, heading)` | `GET /api/documents/{name}/sections/{heading}` | `Read policy wording: {heading}` or `Read claims manual: {heading}` |
| `decide(...)` | `POST .../decision` | Written by the backend |
| `pay(claim_id, amount)` | `POST .../payment` | Written by the backend |

`decide` and `pay` return the backend's `detail` on a 409 and do not raise. Middleware on this agent is `ModelRetryMiddleware`, `ToolRetryMiddleware`, and `ModelCallLimitMiddleware(run_limit=25, exit_behavior="end")`. A 409 is a tool result, so the retry middleware does not send a second decision.

The pilot's scripted tool order changes from `get_policy_wording` to `list_sections` plus `read_section`. The decisions in those tests stay the same: `CLM-1001` approved for 420, `CLM-1002` approved for 1150 and blocked at pay.

- [x] A stubbed `run("CLM-1001", "thread-1")` lists sections, reads `3. Trip Delay`, decides approve for 420, and pays 420. The claim ends `decided`. The activity list includes `Read policy wording: 3. Trip Delay`.
- [x] A stubbed run on `CLM-1002` decides approve for 1150 and calls pay. The tool result contains `sign-off`. Status is `waiting_for_sign_off` and `payment` is null.
- [x] The system prompt is the claim text from `GET /api/instructions`. That response also includes the queue text.
- [x] The tool module does not read a path containing `evals` or `security`.
- [x] The default model is `deepseek/deepseek-v4.1-flash` with low reasoning effort. `MODEL_NAME=openrouter/free` selects that model and does not set a reasoning effort.
- [x] The middleware passed to `create_agent` for a claim is the retry, tool-retry, and model-call-limit middleware above.
- [x] `uv run pytest -q` passes, with coverage of `backend` and `agent` at or above 80%.

## Phase 4: The queue agent

`run_queue(max_claims)` creates a run, then calls `create_agent` with the queue instructions and a fresh conversation. Its tools are `list_waiting`, `update_todos`, `work_claim`, and `finish`.

`work_claim(claim_id)` does the claim-level rules in code:

1. If this run has already taken `max_claims` other claims, it returns that the cap is full and does not change the claim.
2. It marks the to-do `in_progress`, sets the claim `in_progress`, and appends `Started work on this claim.`
3. If a decision is already stored, it does not call the model. It returns one line from that decision, and it calls `pay` only when the claim is an unpaid approval at or under $1,000.
4. Otherwise it calls `run(claim_id, new_thread_id)` on a new agent. The queue conversation gains only the line `work_claim` returns.
5. The line is `CLM-1001 approve $420.00` from the stored decision, or `CLM-1001 failed and is back in the queue.`, or `CLM-1001 failed twice and is left for a handler.`
6. An exception, a model-call limit, or a finish with no decision is a failure. The first failure releases the claim with `retry`. The second releases it with `handler`. `work_claim` does not raise.

After the queue agent returns, `run_queue` runs the missed-claim check in code. While the number of claims this run has taken is under the cap, it takes the next waiting claim in claim-id order and calls `work_claim`. It then stores the agent's closing summary.

The same middleware as phase 3 is on the queue agent, with `ModelCallLimitMiddleware(run_limit=40, exit_behavior="end")`. Hitting that limit ends the model loop and still runs the missed-claim check.

`uv run -m agent` counts the waiting claims and passes that count as the cap. `uv run -m agent 5` passes 5. `uv run -m agent CLM-1001` calls `run` for that claim. The Python loop that used to walk the queue is removed, so the queue agent is the only thing that chooses the order.

- [x] A stubbed `run_queue(2)` writes a to-do list, calls `work_claim` for two claims, and leaves the third waiting. `GET /api/runs/current` shows those two items as `done` and a summary string.
- [x] With the claim agent raising, `work_claim` on `CLM-1004` returns the claim to `waiting`, and a following `work_claim` on `CLM-1005` still runs. The run's summary is reached.
- [x] The same raising claim agent, called twice for `CLM-1004`, leaves that claim `left_for_handler` with failure count 2. A third call does not invoke the claim agent.
- [x] A stubbed queue agent that works only one claim under a cap of 2 leaves a waiting claim. The missed-claim check then works one more waiting claim and does not work a third.
- [x] A second `work_claim` on a claim that already has the 420 approval does not call `decide`. The payout on the claim is still 420, and there is one payment.
- [x] `uv run pytest -q` passes, with coverage of `backend` and `agent` at or above 80%.

## Phase 5: The queue page and the instructions

The queue page polls `GET /api/runs/current` with the claims, once a second. Under the queue counts it shows the current run: the cap, each to-do item with its claim id and label, and the summary once it exists. No run yet shows the line `No run yet`.

To-do pills use the brand colors. To do is white text on Cerulean. In progress is Midnight text on Marigold. Done is Midnight text on Sea Green. Left for a handler is white text on Raspberry. On a light surface, Sea Green and Marigold text is darkened. Panels stay rounded, with no outline and no edge border.

The claim page is unchanged in structure. The activity list is where a handler sees `Read policy wording: ...` and `Read claims manual: ...`. The status pill learns Left for a handler. **Work this claim** is shown for Waiting, In progress, and Left for a handler.

The instructions page shows two headings, `Running the queue` and `Working a claim`, and the two texts. There is no text field.

- [x] Vitest renders a mocked current run with cap 5, `CLM-1001` as To do, and `CLM-1002` as Left for a handler.
- [x] Vitest renders the queue with no current run and shows `No run yet`.
- [x] Vitest renders a claim whose activity includes `Read claims manual: 10. Meals without receipts`.
- [x] Vitest finds no textbox on the instructions page and finds both headings and a sentence from each prompt.
- [x] `npm run check:ts` passes, including the 80% coverage threshold.

## Phase 6: The handler's screens, the documents, and one capped run

Playwright drives the new screens against the real backend and a fresh database. It writes a run and a to-do list through the API. It does not call `run` or `run_queue`.

Then open the dashboard and confirm the same screens: the to-do list on the queue, a claim's activity, both instruction texts, and dark mode.

Update `docs/TECH_STACK.md` so the agent is described as it is now: the default model, `run` for one claim, `run_queue` for the queue, section tools, and the three middleware classes. Update `docs/STATUS.md` with the three ways to start the agent and with the to-do list on the queue page.

The live check is once, after `uv run -m backend.seed`, with the backend and the dashboard running. `uv run -m agent 5` uses the default model. It is not part of `npm run check`.

- [x] After the test posts a run of cap 5 with `CLM-1001` done and `CLM-1002` left for a handler, `/` shows both claim ids and both labels.
- [x] `/claims/CLM-1001` shows an activity line naming a wording section after the test posts that line.
- [x] `/instructions` shows `Running the queue` and `Working a claim`, and has no text field.
- [x] A browser pass of `/`, `/claims/CLM-1001`, and `/instructions` shows the to-do list, the section line, both prompts, and the same screens in dark mode.
- [x] `docs/SPEC.md`, `docs/TECH_STACK.md`, and `docs/STATUS.md` match the product. `docs/PLAN.md` is unchanged.
- [x] After a reseed, `uv run -m agent 5` takes five claims. The queue page shows the to-do list moving to Done or Left for a handler. Each worked claim's activity names the sections it read. The other twenty claims stay Waiting. On this machine `MODEL_NAME` is `openrouter/free`. OpenRouter's free daily limit stopped the model after `CLM-1001`, which was approved for $420.00 with the wording sections it read on the activity list. The other four claims in the cap were left for a handler, and twenty stayed waiting.
- [x] `npm run check` passes: ruff, pyright, pytest at 80% coverage, ESLint, Prettier, tsc, vitest at 80% coverage, and Playwright.
