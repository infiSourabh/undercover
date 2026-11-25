"""Queue runs, to-do lists, and releasing a claim that was not decided."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from backend.actions import StoreError
from backend.db import connect
from backend.store import get_claim

TODO_STATUSES = {"todo", "in_progress", "done", "left_for_handler"}


def create_run(db_path: Path, max_claims: int) -> dict[str, Any]:
    """Store a run. This does not start the agent."""
    run_id = str(uuid.uuid4())
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, max_claims, summary) VALUES (?, ?, NULL)",
            (run_id, max_claims),
        )
        conn.commit()
    return _saved_run(db_path, run_id)


def current_run(db_path: Path) -> dict[str, Any]:
    """Return the latest run."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT run_id FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise StoreError(404, "No run yet.")
        return _run(conn, str(row["run_id"]))


def put_todos(
    db_path: Path, run_id: str, items: list[dict[str, str]]
) -> dict[str, Any]:
    """Replace the to-do list for a run."""
    with connect(db_path) as conn:
        _require_run(conn, run_id)
        seen: set[str] = set()
        for item in items:
            claim_id = item["claim_id"]
            status = item["status"]
            if status not in TODO_STATUSES:
                raise StoreError(409, f"Status {status} is not a to-do status.")
            if claim_id in seen:
                raise StoreError(409, f"Claim {claim_id} is already on the list.")
            seen.add(claim_id)
            found = conn.execute(
                "SELECT claim_id FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
            if found is None:
                raise StoreError(409, f"Claim {claim_id} not found.")
        conn.execute("DELETE FROM todos WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO todos (run_id, position, claim_id, status)
            VALUES (?, ?, ?, ?)
            """,
            [
                (run_id, position, item["claim_id"], item["status"])
                for position, item in enumerate(items)
            ],
        )
        conn.commit()
    return _saved_run(db_path, run_id)


def put_summary(db_path: Path, run_id: str, summary: str) -> dict[str, Any]:
    """Store the handlers' summary for a run."""
    with connect(db_path) as conn:
        _require_run(conn, run_id)
        conn.execute("UPDATE runs SET summary = ? WHERE run_id = ?", (summary, run_id))
        conn.commit()
    return _saved_run(db_path, run_id)


def release_claim(db_path: Path, claim_id: str, result: str) -> dict[str, Any]:
    """Send an undecided claim back to the queue, or leave it for a handler."""
    if result not in {"retry", "handler"}:
        raise StoreError(409, "Result must be retry or handler.")
    with connect(db_path) as conn:
        _claim_row(conn, claim_id)
        decision = conn.execute(
            "SELECT claim_id FROM decisions WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if decision is not None:
            raise StoreError(409, "This claim already has a decision.")
        row = conn.execute(
            "SELECT failures FROM claim_failures WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        failures = 1 if row is None else int(row["failures"]) + 1
        conn.execute(
            """
            INSERT INTO claim_failures (claim_id, failures) VALUES (?, ?)
            ON CONFLICT(claim_id) DO UPDATE SET failures = excluded.failures
            """,
            (claim_id, failures),
        )
        status = "waiting" if result == "retry" else "left_for_handler"
        conn.execute(
            "UPDATE claims SET status = ? WHERE claim_id = ?", (status, claim_id)
        )
        conn.commit()
    claim = get_claim(db_path, claim_id)
    if claim is None:
        raise sqlite3.Error(f"Claim {claim_id} is missing")
    return claim


def failure_count(db_path: Path, claim_id: str) -> int:
    """Return how many times a claim has failed before a decision."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT failures FROM claim_failures WHERE claim_id = ?", (claim_id,)
        ).fetchone()
    if row is None:
        return 0
    return int(row["failures"])


def _require_run(conn: sqlite3.Connection, run_id: str) -> None:
    row = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise StoreError(404, f"Run {run_id} not found.")


def _claim_row(conn: sqlite3.Connection, claim_id: str) -> None:
    row = conn.execute(
        "SELECT claim_id FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise StoreError(404, f"Claim {claim_id} not found.")


def _saved_run(db_path: Path, run_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        return _run(conn, run_id)


def _run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise StoreError(404, f"Run {run_id} not found.")
    items = conn.execute(
        """
        SELECT claim_id, status FROM todos
        WHERE run_id = ? ORDER BY position
        """,
        (run_id,),
    ).fetchall()
    return {
        "run_id": run["run_id"],
        "max_claims": run["max_claims"],
        "summary": run["summary"],
        "items": [
            {"claim_id": row["claim_id"], "status": row["status"]} for row in items
        ],
    }
