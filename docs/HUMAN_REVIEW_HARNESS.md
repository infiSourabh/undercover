# Human review of the harness

This is the review a person does after `docs/PLAN_HARNESS.md` is built. The automated suite proves the store, the tools, and the failure rules on a stub model. It does not judge whether a handler can follow a live run, whether a decision follows the wording and the manual, or whether the summary is something a handler can use. That is this review.

Review the product as it is described in `docs/SPEC.md`, `docs/HARNESS.md`, and `docs/STATUS.md`. Do not open `data/evals/` while reviewing. Those files are for a later accuracy check, and the agent must never see them. Do not treat a later day's work (durable state, a swarm, sign-in, AWS) as a defect in this build.

Tick a box only after you have looked. A live run is capped at five claims and starts from a reseed.

## Before you start

1. `uv run -m backend.seed` prints `Reset the queue: 25 claims waiting.`
2. `npm run dev` is running. The dashboard is http://localhost:5173 and the API is http://localhost:8000. `uv run -m agent` calls that API. If the backend is stopped, the agent fails with `Connection refused` before any model call.
3. Decide which model you are reviewing. With `MODEL_NAME` unset, the agent uses `deepseek/deepseek-v4.1-flash` at low reasoning effort. With `MODEL_NAME` set, that name wins and reasoning effort is left unset. `MODEL_NAME=openrouter/free` is a free-route override, not the default in the brief.
4. The OpenRouter key needs enough quota for the run. A five-claim run is many model calls, because each section read is its own step. A key on the free daily cap of 50 calls will stop in the middle. When that happens, review the recovery (below), then stop. Do not keep retrying until the cap resets or the key has credits.
5. Open the queue before you start the agent. You should see 25 claims Waiting, and the line `No run yet`.

## How to walk a run

Use two terminals. Leave `npm run dev` in the first. In the second, after the reseed:

```bash
uv run -m agent 5
```

Watch the queue page while it runs. It polls once a second. Then open each claim the run took. Then open the instructions page. Then switch dark mode and look again.

For one named claim, with the backend still running:

```bash
uv run -m agent CLM-1001
```

That path does not create a queue run. The claim page should still gain steps, a decision, and a payment or a sign-off block. The queue page keeps showing the previous run, or `No run yet` if you have not started one.

`npm run check` is the machine pass: ruff, pyright, pytest at 80% coverage, ESLint, Prettier, tsc, vitest at 80% coverage, and Playwright. Run it before you treat the build as ready to hand over. It does not call the model and it reseeds the database, so run it separately from the live review. A green check does not replace the walkthrough below.

## What you are judging

### The run as a whole

- [ ] The run starts once and keeps going until it has taken five claims, or until it has left a taken claim for a handler and moved on.
- [ ] The queue page shows `Up to 5 claims` and one row per claim the run took.
- [ ] Each row moves through To do, In progress, and then Done or Left for a handler.
- [ ] Claims the run never took stay Waiting. After a cap of five, twenty claims are still Waiting.
- [ ] A retry of a claim already taken does not take a sixth slot.
- [ ] The run ends with a short summary on the queue page: how many claims were decided, which are waiting for sign-off, and which are left for a handler.
- [ ] The terminal prints a line per step (`CLM-1001: read wording ...`) and exits 0. A claim that fails does not dump a traceback that aborts the process.

### A claim the agent finished

Open the claim. Judge it as a handler would, from the story, the documents, and the sections named on the activity list. The wording is the contract. The manual covers what the wording leaves open, including a third claim within 12 months, losses to wild animals, and meals without receipts. Where they disagree, the wording wins.

- [ ] The activity list shows `Started work on this claim.` and a `Read policy wording:` or `Read claims manual:` line for every section the decision relies on.
- [ ] The decision is approve, decline, or refer, with a reason of two or three sentences and the wording section it used.
- [ ] Approve is used when the incident is covered and the required documents are on file. Decline is used when the wording leaves the loss outside the cover. Refer is used when a document is missing, the story and the documents disagree, this is the third claim within 12 months, or the wording and the manual still do not settle it.
- [ ] An approval at or under $1,000 has one payment for that amount, and the claim is Decided.
- [ ] An approval over $1,000 is Waiting for sign-off, the payment is empty, and the activity says the payout needs a handler's sign-off. The agent did not record a second decision or a smaller amount to get around the block.
- [ ] A decline or a referral has a payout of $0 and no payment.
- [ ] There is one decision and at most one payment. Refreshing the page does not add another.

### A claim that failed

A provider error, a timeout, or a claim agent that stops without a decision is a failure. The first failure puts the claim back to Waiting and adds one to its failure count. The second leaves it for a handler. The claim must not stay In progress.

- [ ] One bad claim does not stop the other claims in the cap.
- [ ] A claim left for a handler shows that status on the queue and on its to-do row (white text on Raspberry).
- [ ] Its activity explains that work started and that it stopped before a decision. It does not show a decision or a payment.
- [ ] **Work this claim** is still available. A further failed attempt returns the claim to Left for a handler rather than leaving it In progress.

### The screens

Labels are Waiting, In progress, Waiting for sign-off, Decided, and Left for a handler. To-do labels are To do, In progress, Done, and Left for a handler. Money is US dollars, such as $420.00.

- [ ] To do is white on Cerulean. In progress is Midnight on Marigold. Done is Midnight on Sea Green. Left for a handler is white on Raspberry.
- [ ] Panels are rounded, with no outline and no edge border. Light page background is `#F0F4F5`. Dark page background is `#04232E`.
- [ ] The instructions page has the headings `Running the queue` and `Working a claim`, the two texts, and no text field.
- [ ] The same queue, claim, and instructions screens are readable in dark mode.
- [ ] Nothing on the screens mentions `data/evals/` or offers the agent those decisions.

### The single-claim path

- [ ] `uv run -m agent CLM-1001` works that claim only.
- [ ] **Work this claim** on a Waiting claim does the same from the dashboard.
- [ ] A claim that is already Decided or Waiting for sign-off cannot be started again from the dashboard.

## Score the five claims

Fill this in during the capped run. Outcome is approve, decline, or refer. Payment is the amount paid, `sign-off`, or `none`. Sections are the headings you saw on the activity list. Verdict is accept or query, with one line on why.

| Claim | Outcome | Payout | Payment | Sections read | Verdict |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |

Summary as shown on the queue page:

```
```

Claims still Waiting (expect 20 after a cap of 5):

```
```

## What already showed up in a live run

These are observations from runs on this machine, not a new requirement. Use them as things to look for, then decide whether they are defects.

- With `MODEL_NAME=openrouter/free`, or with the default model on a key that has no credits, OpenRouter returns `429` once the free daily limit of 50 calls is used. The harness kept going: it left the unfinished claims for a handler and stored the provider error as the run summary. The queue page then shows that raw error instead of a handler summary. That misses the brief. The summary should say how far the run got, in plain language.
- The model sometimes sends `Approve` or `approved`. The API accepts only `approve`, `decline`, or `refer`, so the tool rejects the first call and the model spends another turn fixing the case. The decision can still land, but the trial costs more and the activity shows a rejected decision before the real one.
- A claim the model never reached can show only `Started work on this claim.` twice, with no section lines. That is consistent with a failure before any read. It should be obvious on the claim page why it was left for a handler, without opening the run summary.
- `catch_up` fills any unused cap slots in claim-id order after the queue agent returns. If the agent takes fewer than the cap, the extra claims are not the agent's own choice. Note on the scorecard which claims the terminal shows the agent picking, and which appear only at the end.

## Scope of improvements

Change only what makes this harness meet the brief more reliably. Keep the stack: LangChain `create_agent`, the tools we already have, and the rules in `docs/SPEC.md`. Tests stay on a stub model. A live check stays a reseed plus a cap of five, and stays out of `npm run check`.

### In scope

A person can pick these up as a follow-up to this harness. Each one is visible to a handler or changes a rule the brief already states.

| Improvement | Why it is in scope | Done when |
|---|---|---|
| Write the run summary from the stored claims when the model dies or returns a provider error | The brief asks for a short summary for handlers. A raw `429` body is not that | The queue page states how many were decided, which wait for sign-off, and which were left for a handler |
| Record the failure reason on the claim | A claim left for a handler should say what went wrong, on that claim | The activity list contains one plain line, and the claim is not In progress |
| Accept `approve`, `decline`, and `refer` regardless of case, once | The instructions already name those three outcomes. A casing miss should not be a second decision or a second model round-trip | One `decide` call stores the outcome, and a second `decide` is still 409 |
| Keep the $1,000 sign-off rule where it is | The brief says the pilot rules stay | An approval over $1,000 still cannot be paid until a handler signs off, and the agent cannot replace the decision |
| Keep section lookup as the only way to read the wording and the manual | The brief says the agent is not handed the whole document | The claim agent still has no tool that returns either full document, and the activity line names the heading |
| Make a five-claim trial finish inside a normal paid quota | The brief asks for a cheap trial. Section-by-section reads are right, but a run that dies on call 50 never shows five finished claims | One reseeded `uv run -m agent 5` on the default model, with credits, takes five claims and leaves twenty Waiting |
| Tighten the instructions from the wording and the manual only | The instructions page is what the handler reads, and it must not be derived from `data/evals/` | Both texts still match `backend/instructions_queue.md` and `backend/instructions_claim.md`, and neither mentions a held-out decision |

### Out of scope

Do not treat these as gaps in the harness review.

- Sign-in, real payments, and messages to customers. `docs/SPEC.md` lists them under "Not for now".
- Scoring the agent against `data/evals/`, and any change that puts those decisions into the prompt, the tools, or the dashboard.
- A second agent framework, including deepagents and the Claude Agent SDK. The brief says to build into the current agent.
- Replacing the to-do list with LangChain's `TodoListMiddleware`. That list cannot represent Left for a handler, and the dashboard cannot read it.
- Durable state, a swarm of claim agents, configuration versions, an improver, or AWS. Those are later briefs. They are not defects in this one.
- Lowering a coverage threshold, turning off a lint rule, or excluding a file so `npm run check` goes green.
- Another live run after the free-tier limit is already exhausted. Wait for the reset or add credits, reseed, and run once.

## Review outcome

Write one of these at the end, with the scorecard above attached.

- **Accept.** The five-claim walkthrough matches the boxes, and the summary is usable by a handler.
- **Accept with follow-ups.** The rules hold (no double decision, no double payment, no claim stuck in progress, cap respected), and the follow-ups are items from the in-scope table.
- **Send back.** A claim was decided or paid twice, a claim stayed In progress, the run stopped on the first failure, the cap was ignored, the agent was given `data/evals/`, or a handler cannot tell what the run did from the screens.
