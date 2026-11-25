# Tech stack

- `backend/`: FastAPI and SQLite. Every API operation has an `operation_id`, a one-line docstring and no optional inputs. Paying a claim is a separate operation that takes the amount.
- `agent/`: LangChain's `create_agent` on OpenRouter. `run(claim_id, thread_id)` decides one claim. `run_queue(max_claims)` works the queue and hands each claim to a fresh claim agent. Both reach claims, sections, and their instructions only through the backend's API. A claim tool reads one section of the policy wording or the claims manual at a time. `ModelRetryMiddleware` and `ToolRetryMiddleware` retry a failed call. `ModelCallLimitMiddleware` stops a claim after 25 model calls and a queue run after 40. The default model is `deepseek/deepseek-v4.1-flash` with low reasoning effort, or the model in `MODEL_NAME` when that variable is set, such as `openrouter/free`.
- `dashboard/`: React, Vite and TypeScript.
- `e2e/`: Playwright tests.
- `data/`: the business data the backend starts from. The agent never sees `data/evals/`, which holds the answer key.

Python 3.12 with uv, all in the root `pyproject.toml`. Node 26. The OpenRouter key is `OPENROUTER_API_KEY` in `.env`.
