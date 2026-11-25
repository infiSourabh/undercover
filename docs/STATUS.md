# Status

The claims pilot is built.

## Running it

`npm run dev` starts the backend and the dashboard (http://localhost:5173). `uv run -m backend.seed` resets the queue. `uv run -m agent` works every waiting claim, `uv run -m agent 5` caps a run at five, and `uv run -m agent CLM-1001` runs one claim. `npm run check` runs the full suite.

## Built so far

- `backend/`: SQLite store seeded from `data/`, including the claims manual. Queue, claim, wording, manual sections, instructions and handler routes. `GET /api/documents/wording/sections` and `GET /api/documents/manual/sections` list headings, and a section path returns that section. A run stores a cap, a to-do list and a summary. Releasing an undecided claim sends it back to the queue, or leaves it for a handler after a second failure. A claim that already has a decision cannot be decided or released again. Decision, sign-off, payment (blocked over $1,000 until a handler signs off) and activity. `POST /api/claims/{id}/run` starts the agent on a side thread.
- `agent/`: `run(claim_id, thread_id)` decides one claim. `run_queue(max_claims)` works the queue: a to-do list, a fresh claim agent per claim, and a check for a claim still waiting under the cap. A claim that fails before a decision goes back once, and a second failure leaves it for a handler. `uv run -m agent` works every waiting claim, `uv run -m agent 5` caps the run, and `uv run -m agent CLM-1001` runs that claim. The default model is `deepseek/deepseek-v4.1-flash` at low reasoning effort, or `MODEL_NAME` when that is set.
- `dashboard/`: queue with submitted date, payout, and the current run's to-do list. A claim page leads with the decision and its policy basis plus the agent's steps, including the sections it read. The instructions page shows the queue instructions and the claim instructions, read only. Light and dark surfaces from the brand.
- `e2e/`: Playwright covers the queue, a claim, under-limit pay, over-limit sign-off, instructions and dark mode.

Decisions follow the policy wording and the claims manual. The wording wins if they disagree. The agent does not see `data/evals/`. There is no sign-in, no real payments and no customer messages.
