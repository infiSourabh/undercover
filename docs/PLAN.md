# Pilot plan

The pilot lets a handler open the queue, watch the UnderCover Agent work one claim, and read the decision. The agent approves, declines, or refers from the policy wording, works out a payout when it approves, and explains the decision in two or three sentences with the section it used. A payout over $1,000 can be approved, and the payment stays blocked until a handler signs off.

The backend is the system of record. It keeps the queue in SQLite, seeded from `data/`, and it is the only way the agent reads a claim or its instructions. The payment rule lives in the pay operation, so a tool call cannot get around it. Tests use the stub model already in `agent/tests/test_agent.py` and never call OpenRouter. The hello-world page is replaced by the claims screens. `GET /api/health` stays, because `npm run dev` and Playwright use it to know the backend is up.

Out of this plan: the claims manual, `data/knowledge.json`, `data/security/`, `data/evals/`, sign-in, real payments, and messages to customers. The pilot does not score the agent against the handlers' decisions.

Implementation builds these phases in order. Each phase gets tests, a check against its criteria, a tick here, an update to `docs/STATUS.md`, and a commit.

## How a claim moves

Seeded claims have status `open` in `data/claims.json`. The queue stores them as `waiting`. The screen labels are Waiting, In progress, Waiting for sign-off, and Decided.

| From | What happens | To |
|---|---|---|
| Waiting or In progress | A run starts | In progress |
| Waiting, In progress, or Waiting for sign-off | Decline or refer | Decided |
| Waiting, In progress, or Waiting for sign-off | Approve for $1,000.00 or less | In progress, until the pay operation succeeds |
| Waiting, In progress, or Waiting for sign-off | Approve for more than $1,000.00 | Waiting for sign-off |
| In progress, payout at or under the limit | Pay the approved amount | Decided |
| Waiting for sign-off, after a handler signs off | Pay the approved amount | Decided |

The limit is `payout_approval_limit` in `data/company.json`, which is $1,000.00. A payout of $1,000.00 does not need sign-off. "Over $1,000" means greater than the limit. A claim that has been paid, or decided by a decline or a refer, rejects a new decision. Sign-off is stored on the claim and does not by itself pay it.

## API

Every operation has an `operation_id`, a one-line docstring, and no optional inputs. Path and body fields below are all required. Responses may contain null for a decision, sign-off, or payment that has not happened yet. Errors use FastAPI's `detail` string: 404 when the claim or handler does not exist, 409 when the move is not allowed.

| Method | Path | operation_id | Body |
|---|---|---|---|
| GET | `/api/health` | `health` | |
| GET | `/api/claims` | `list_claims` | |
| GET | `/api/claims/{claim_id}` | `get_claim` | |
| GET | `/api/claims/{claim_id}/activity` | `list_activity` | |
| POST | `/api/claims/{claim_id}/activity` | `record_activity` | `{message}` |
| POST | `/api/claims/{claim_id}/decision` | `decide_claim` | `{outcome, payout, explanation, policy_section}` |
| POST | `/api/claims/{claim_id}/sign-off` | `sign_off_claim` | `{handler_id}` |
| POST | `/api/claims/{claim_id}/payment` | `pay_claim` | `{amount}` |
| POST | `/api/claims/{claim_id}/run` | `run_claim` | `{thread_id}` |
| GET | `/api/policy-wording` | `get_policy_wording` | |
| GET | `/api/instructions` | `get_instructions` | |
| GET | `/api/handlers` | `list_handlers` | |

`outcome` is `approve`, `decline`, or `refer`. Decline and refer require a payout of 0. Pay pays the approved payout only: the amount has to match, the outcome has to be approve, and a payout over the limit is refused until a sign-off exists. The pay operation records the amount in SQLite. It does not move money.

`list_claims` returns every claim ordered by `claim_id`, with `customer_name`, `summary`, `amount_claimed`, `status`, and `outcome` (null until a decision exists). `get_claim` returns the story, items, and documents; the policy with its plan name, limits, deductible, add-ons, trip, and travelers; the customer's name and earlier claims (date, summary, outcome, amount paid); and the decision, sign-off, and payment. Email, phone, address, and date of birth stay out of the API. The queue and the agent can do their jobs without them.

## Phase 1: Records

Load the business data into SQLite so later phases share one store.

`backend/db.py` creates the schema and seeds it. `backend/seed.py` is `uv run -m backend.seed`: it deletes `backend/undercover.sqlite` and seeds again. `*.sqlite` is already gitignored. The app seeds on startup when the file is missing. Tests pass `create_app` a temporary file so they do not share the dev database.

Seed `company.json`, `plans.json`, `policies.json`, `customers.json`, `handlers.json`, `claims.json`, and `policy_wording.md`. Leave `claims_manual.md`, `knowledge.json`, `data/security/`, and `data/evals/` unread. Map each claim's `open` status to `waiting`.

Use the stdlib `sqlite3` module, with one connection per operation. SQLAlchemy is not part of this pilot.

- [x] `uv run -m backend.seed` prints `Reset the queue: 25 claims waiting.` and exits 0.
- [x] A second seed on a fresh file loads 25 claims, 25 policies, the customers those claims point at, 3 plans, 3 handlers, and a company row whose payout approval limit is 1000.
- [x] Claim `CLM-1001` joins to Maya Patel, policy `POL-2001`, plan Premium, deductible 50, four line items, and a previous claim `CLM-0412`.
- [x] The seeded claim ids are `CLM-1001` through `CLM-1025`. `CLM-1901` is not present.
- [x] The wording stored for the app contains the heading `3. Trip Delay`.
- [x] The test for the seed lists the files it reads, and that list does not include `evals`, `security`, `claims_manual.md`, or `knowledge.json`.
- [x] `uv run pytest -q backend/tests/test_health.py backend/tests/test_seed.py` passes.

## Phase 2: Read API

Serve the queue, one claim in full, the wording, the instructions, and the handlers. This is the contract the agent and the dashboard both use.

The instructions live in `backend/instructions.md`. The route and the agent both use that file, so the screen and the prompt cannot drift apart. The text is:

```
You are the UnderCover Agent. You decide travel insurance claims for UnderCover.

Work from the claim, the customer's policy and claim history, and the policy wording. Decide from the policy wording.

For the claim you are given:

1. Read the claim, the policy, and the claim history.
2. Read the policy wording and apply it.
3. Approve, decline, or refer. Refer when the wording does not settle the claim or a required document is missing. Decline when the wording leaves the loss outside the cover.
4. When you approve, work out the payout in US dollars the way section 10 describes. Start from the eligible amount of each item, take off anything a carrier or another party has already paid, take off the deductible where it applies, and stop at the maximum for that benefit.
5. Record the decision with a reason of two or three sentences and the section of the wording you relied on.
6. When you approve, pay that payout. When the payout is over $1,000, payment waits until a handler signs off. If payment is blocked, stop. Do not try another amount.
```

- [x] `GET /api/claims` returns 25 claims. The first is `CLM-1001`, customer Maya Patel, amount claimed 420, status `waiting`, outcome null.
- [x] `GET /api/claims/CLM-1001` returns the Rome trip-delay story, hotel item of 245, policy Premium, traveler Maya Patel, and previous claim `CLM-0412`. `decision`, `sign_off`, and `payment` are null.
- [x] `GET /api/claims/CLM-9999` returns 404.
- [x] `GET /api/policy-wording` returns the wording, including `10. How we work out your payment`.
- [x] `GET /api/instructions` returns the instructions text above.
- [x] `GET /api/handlers` returns Dana Whitfield, Marcus Oyelaran, and Priya Raman, each with `can_approve_over_limit` true.
- [x] `GET /api/health` still returns `{"status": "ok"}`.
- [x] The OpenAPI spec lists every operation id in the table above that this phase adds, and no route takes an optional parameter.
- [x] `uv run pytest -q backend/tests` passes.

## Phase 3: Decisions, sign-off, and payment

Record what the agent decided, append a step each time something happens, and enforce the payout rule in `pay_claim`.

`decide_claim` stores the outcome, payout, explanation, and policy section, and moves the status as in the table above. A decline or refer with a non-zero payout is a 409. `sign_off_claim` requires an approve decision over the limit and a handler who can approve over the limit. A second sign-off is a 409. `pay_claim` records a payment and sets Decided only when the amount equals the approved payout and the sign-off rule is satisfied. Any other pay is a 409 and writes no payment.

Activity is append-only, oldest first. The backend writes a line when a decision, sign-off, or payment is attempted, including a blocked payment. `record_activity` appends a line the agent's read tools will use in the next phase. `list_activity` returns those lines.

Use two fixed cases in the tests. They check the gate, not whether the payout is what a handler would choose.

- `CLM-1001`, approve, payout 420, explanation `The delay is covered. The payout is the claimed expenses.`, section `3. Trip Delay`.
- `CLM-1002`, approve, payout 1150, explanation `Approved over the handler limit.`, section `5. Baggage and Personal Effects`.

- [x] After the `CLM-1001` decision, `GET /api/claims/CLM-1001` shows outcome `approve`, payout 420, that explanation, section `3. Trip Delay`, and status `in_progress`.
- [x] `POST /api/claims/CLM-1001/payment` with amount 420 returns the payment, sets status `decided`, and a second pay returns 409 with no extra payment row.
- [x] `POST /api/claims/CLM-1001/payment` with amount 100, before any successful pay, returns 409 and the detail says the amount must match the approved payout.
- [x] After the `CLM-1002` decision, status is `waiting_for_sign_off`.
- [x] Paying 1150 on `CLM-1002` before sign-off returns 409, the detail says the payout needs a handler's sign-off, and `payment` is still null.
- [x] Sign-off with `HND-01` then pay 1150 sets status `decided`, payment 1150, and sign-off handler Dana Whitfield.
- [x] Sign-off with `HND-99` returns 404. Sign-off on `CLM-1001` after its under-limit approval returns 409.
- [x] A decline with payout 0 on a fresh claim sets status `decided`. A decline with payout 10 returns 409. Paying a declined claim returns 409.
- [x] Deciding a claim that already has a payment returns 409.
- [x] The activity list for `CLM-1002` contains, in order, the decision, the blocked payment, the sign-off, and the successful payment.
- [x] `uv run pytest -q backend/tests` passes.

## Phase 4: The agent

`agent.main.run(claim_id, thread_id)` stays the single entry point. It loads the instructions with `GET /api/instructions` and passes that text to `create_agent` as the system prompt. The model is unchanged: `openai/gpt-6-luna` at low reasoning effort, or `MODEL_NAME` when that variable is set.

Tools call the backend over HTTP and nowhere else. They do not open files under `data/`.

| Tool | API | Step recorded on the claim |
|---|---|---|
| `get_claim(claim_id)` | `GET /api/claims/{claim_id}` | Read the claim, the policy, and the claim history |
| `get_policy_wording(claim_id)` | `GET /api/policy-wording` | Read the policy wording |
| `decide(claim_id, outcome, payout, explanation, policy_section)` | `POST .../decision` | Written by the backend |
| `pay(claim_id, amount)` | `POST .../payment` | Written by the backend |

`pay` returns the backend's `detail` when the payment is refused, so the model can stop. It does not raise, and it does not retry with a different amount.

`POST /api/claims/{claim_id}/run` with `{thread_id}` is how the dashboard starts work. It sets the claim to `in_progress`, appends `Started work on this claim.`, and returns that status immediately. The agent then runs on a daemon thread. The thread is required because the tools call back into this same API; doing the work inside the request that started it would stall those calls. When the run ends, the thread appends `Finished work on this claim.` A run that records no decision also appends `Stopped before recording a decision.` Starting a run on a decided claim, or on a claim waiting for sign-off, returns 409.

`uv run -m agent` works the queue: it lists claims and calls `run` once for each claim whose status is `waiting`, with a new thread id per claim. The automated check uses a stub in place of `run`. A live `uv run -m agent` calls OpenRouter, so it is not part of `npm run check`.

- [x] A stubbed `run("CLM-1001", "thread-1")` calls the tools in order: get the claim, get the wording, decide approve for 420 with the phase 3 explanation and section, pay 420. The claim ends `decided` with payment 420.
- [x] The system prompt passed to `create_agent` is the instructions from `GET /api/instructions`.
- [x] A stubbed run on `CLM-1002` decides approve for 1150 and calls pay. The tool result contains `sign-off`. Status is `waiting_for_sign_off` and `payment` is null.
- [x] The tool module's source does not read a path containing `evals`, `security`, or `claims_manual`.
- [x] `POST /api/claims/CLM-1001/run` with `{"thread_id": "thread-1"}` returns `{"status": "in_progress"}` while a stubbed agent is still running, and the activity list includes `Started work on this claim.`
- [x] The same call on a decided claim returns 409.
- [x] The queue runner, with `run` stubbed, calls `run` once per waiting claim and does not call it for a claim already decided.
- [x] `test_model_name` still passes: the default model is `openai/gpt-6-luna`, and `MODEL_NAME=openrouter/free` selects that model.
- [x] `uv run pytest -q` passes. Coverage of `backend` and `agent` stays at or above 80%.

## Phase 5: Dashboard

Replace the health page with three screens the handlers can use. Add `react-router` so each claim and the instructions have their own URL.

| URL | Screen |
|---|---|
| `/` | Queue |
| `/claims/:claimId` | Claim |
| `/instructions` | Instructions |

The queue shows claim id, customer, summary, amount claimed, and status. A row opens the claim. The claim screen shows the story, items, documents, policy, plan limits, travelers, and earlier claims; the decision and its section when one exists; the payment; and the activity, oldest at the bottom. While the status is `in_progress`, the page polls the claim and the activity every second.

Buttons:

- **Work this claim** on a Waiting or In progress claim. It posts `run` with a new thread id.
- **Sign off** when the status is Waiting for sign-off. The handler is a required choice: Dana Whitfield, Marcus Oyelaran, or Priya Raman.
- **Pay** when there is an approve decision, no payment yet, and either the payout is at or under $1,000 or a sign-off is already stored. The button sends the approved payout as the amount.

The instructions screen renders the instructions as text. There is no text field and the text is not editable.

Brand, in `dashboard/src/styles.css`:

- Instrument Sans for headings and body, Instrument Serif for the tagline `Travel claims`, JetBrains Mono for claim ids and money. Load them from Google Fonts in `dashboard/index.html`.
- Light page background `#F0F4F5` and white panels. A header toggle switches to dark: page `#04232E`, black panels, Sea Mist text. The choice is stored on `document.documentElement` as `data-theme`.
- Panels are rounded and have no outline. No edge borders and no line across the top of the page.
- Status pills use Midnight text on Sea Green (Decided), Marigold (In progress), and Coral (Waiting for sign-off), and white text on Cerulean (Waiting). Decline uses Raspberry. Sea Green and Marigold are darkened when they are used as text on a light background.
- Money is formatted in US dollars with cents, such as `$1,150.00`.

Keep the Vite proxy so the screens call `/api` on the same origin.

- [x] Vitest renders the queue from a mocked `GET /api/claims` and shows `CLM-1001`, Maya Patel, and `Waiting`.
- [x] Vitest renders `CLM-1001` with the story, a decision of `$420.00`, the explanation, and two activity lines in order.
- [x] Vitest renders the over-limit claim with Sign off visible and Pay absent, then after a mocked sign-off shows Pay.
- [x] Vitest finds no textbox on the instructions screen, and the instructions text is present.
- [x] Vitest covers the dark-mode toggle setting `data-theme="dark"`.
- [x] `npm run check:ts` passes, including the 80% coverage threshold.

## Phase 6: Handler workflow in the browser

Playwright drives the screens against the real backend and a fresh database. These tests call the decision and payment routes. They do not call `run`, because that would call the model.

Replace `e2e/health.spec.ts` with specs for the queue, a claim, sign-off, and the instructions. The Playwright web server still waits on `GET /api/health`.

Then open the same flows in the browser and confirm them by hand: the queue, a claim, the blocked payment, sign-off, pay, the instructions, and dark mode.

- [x] The queue at `/` shows 25 claims, `CLM-1001`, and `Waiting`.
- [x] Opening `CLM-1001` shows Maya Patel, the canceled Rome flight, and the policy wording section is absent until a decision exists.
- [x] After the test posts the phase 3 approval for `CLM-1001`, the claim page shows the explanation, `3. Trip Delay`, and `$420.00`. Pay marks it Decided.
- [x] After the test posts the 1150 approval for `CLM-1002`, Pay is not available. Signing off as Dana Whitfield and paying shows Decided and `$1,150.00`.
- [x] `/instructions` shows the agent's instructions and has no text field. Reloading leaves the text unchanged.
- [x] A browser pass of `/`, `/claims/CLM-1001`, `/claims/CLM-1002`, and `/instructions` matches the brand: light surface, then dark after the toggle, status colors, and readable money and claim ids.
- [x] `npm run check` passes: ruff, pyright, pytest at 80% coverage, ESLint, Prettier, tsc, vitest at 80% coverage, and Playwright.
