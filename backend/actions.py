"""Record decisions, sign-off, payment and activity."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from backend.db import connect
from backend.store import get_claim


class StoreError(Exception):
    """An API error from a store operation."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def usd(amount: float) -> str:
    """Format an amount as US dollars with cents."""
    return f"${amount:,.2f}"


def _claim_row(conn: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise StoreError(404, f"Claim {claim_id} not found.")
    return row


def _decision_row(conn: sqlite3.Connection, claim_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM decisions WHERE claim_id = ?", (claim_id,)
    ).fetchone()


def _append(conn: sqlite3.Connection, claim_id: str, message: str) -> None:
    conn.execute(
        "INSERT INTO activity (claim_id, message) VALUES (?, ?)",
        (claim_id, message),
    )


def _limit(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT payout_approval_limit FROM company").fetchone()
    if row is None:
        raise sqlite3.Error("company is missing")
    return float(row["payout_approval_limit"])


def _saved_claim(db_path: Path, claim_id: str) -> dict[str, Any]:
    claim = get_claim(db_path, claim_id)
    if claim is None:
        raise sqlite3.Error(f"Claim {claim_id} is missing")
    return claim


def _decide_error(claim: sqlite3.Row, outcome: str, payout: float) -> str | None:
    if claim["status"] == "decided":
        return "This claim is already decided."
    if outcome not in {"approve", "decline", "refer"}:
        return "Outcome must be approve, decline or refer."
    if outcome != "approve" and round(payout, 2) != 0:
        return "A decline or refer must have a payout of 0."
    return None


def _status_after_decision(outcome: str, payout: float, limit: float) -> str:
    if outcome != "approve":
        return "decided"
    if round(payout, 2) > limit:
        return "waiting_for_sign_off"
    return "in_progress"


def _decision_message(outcome: str, payout: float) -> str:
    if outcome == "approve":
        return f"Approved {usd(payout)}."
    if outcome == "decline":
        return "Declined."
    return "Referred."


def _pay_error(
    decision: sqlite3.Row | None,
    amount: float,
    sign_off: sqlite3.Row | None,
    payment: sqlite3.Row | None,
    limit: float,
) -> str | None:
    if payment is not None:
        return "This claim is already paid."
    if decision is None or decision["outcome"] != "approve":
        return "This claim has no approved payout."
    if round(float(amount), 2) != round(float(decision["payout"]), 2):
        return "The amount must match the approved payout."
    if round(float(decision["payout"]), 2) > limit and sign_off is None:
        return "The payout needs a handler's sign-off."
    return None


def _sign_off_error(
    decision: sqlite3.Row | None,
    existing: sqlite3.Row | None,
    handler: sqlite3.Row,
    limit: float,
) -> str | None:
    if existing is not None:
        return "This claim already has a sign-off."
    if decision is None or decision["outcome"] != "approve":
        return "Sign-off needs an approved payout over the limit."
    if round(float(decision["payout"]), 2) <= limit:
        return "Sign-off is only for payouts over the limit."
    if not handler["can_approve_over_limit"]:
        return "This handler cannot approve over the limit."
    return None


def decide(db_path: Path, claim_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Store a decision and move the claim's status."""
    outcome = str(body["outcome"])
    payout = float(body["payout"])
    with connect(db_path) as conn:
        claim = _claim_row(conn, claim_id)
        if _decision_row(conn, claim_id) is not None:
            raise StoreError(409, "This claim already has a decision.")
        error = _decide_error(claim, outcome, payout)
        if error:
            raise StoreError(409, error)
        conn.execute("DELETE FROM sign_offs WHERE claim_id = ?", (claim_id,))
        conn.execute(
            """
            INSERT INTO decisions
                (claim_id, outcome, payout, explanation, policy_section)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                outcome,
                payout,
                body["explanation"],
                body["policy_section"],
            ),
        )
        status = _status_after_decision(outcome, payout, _limit(conn))
        conn.execute(
            "UPDATE claims SET status = ? WHERE claim_id = ?", (status, claim_id)
        )
        _append(conn, claim_id, _decision_message(outcome, payout))
        conn.commit()
    return _saved_claim(db_path, claim_id)


def pay(db_path: Path, claim_id: str, amount: float) -> dict[str, Any]:
    """Record a payment when the payout rule allows it."""
    with connect(db_path) as conn:
        _claim_row(conn, claim_id)
        decision = _decision_row(conn, claim_id)
        sign_off = conn.execute(
            "SELECT * FROM sign_offs WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        payment = conn.execute(
            "SELECT * FROM payments WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        error = _pay_error(decision, amount, sign_off, payment, _limit(conn))
        if error:
            blocked = error[0].lower() + error[1:]
            _append(conn, claim_id, f"Payment of {usd(amount)} blocked: {blocked}")
            conn.commit()
            raise StoreError(409, error)
        conn.execute(
            "INSERT INTO payments (claim_id, amount) VALUES (?, ?)",
            (claim_id, amount),
        )
        conn.execute(
            "UPDATE claims SET status = 'decided' WHERE claim_id = ?", (claim_id,)
        )
        _append(conn, claim_id, f"Paid {usd(amount)}.")
        conn.commit()
    return _saved_claim(db_path, claim_id)


def sign_off(db_path: Path, claim_id: str, handler_id: str) -> dict[str, Any]:
    """Record a handler's sign-off on an over-limit approval."""
    with connect(db_path) as conn:
        _claim_row(conn, claim_id)
        handler = conn.execute(
            "SELECT * FROM handlers WHERE handler_id = ?", (handler_id,)
        ).fetchone()
        if handler is None:
            raise StoreError(404, f"Handler {handler_id} not found.")
        existing = conn.execute(
            "SELECT * FROM sign_offs WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        error = _sign_off_error(
            _decision_row(conn, claim_id), existing, handler, _limit(conn)
        )
        if error:
            raise StoreError(409, error)
        conn.execute(
            "INSERT INTO sign_offs (claim_id, handler_id) VALUES (?, ?)",
            (claim_id, handler_id),
        )
        _append(conn, claim_id, f"{handler['name']} signed off.")
        conn.commit()
    return _saved_claim(db_path, claim_id)


def list_activity(db_path: Path, claim_id: str) -> list[dict[str, str]]:
    """Return activity lines for a claim, oldest first."""
    with connect(db_path) as conn:
        _claim_row(conn, claim_id)
        rows = conn.execute(
            "SELECT message FROM activity WHERE claim_id = ? ORDER BY id",
            (claim_id,),
        ).fetchall()
    return [{"message": row["message"]} for row in rows]


def record_activity(db_path: Path, claim_id: str, message: str) -> list[dict[str, str]]:
    """Append an activity line."""
    with connect(db_path) as conn:
        _claim_row(conn, claim_id)
        _append(conn, claim_id, message)
        conn.commit()
    return list_activity(db_path, claim_id)


def set_status(db_path: Path, claim_id: str, status: str) -> None:
    """Set a claim's status."""
    with connect(db_path) as conn:
        _claim_row(conn, claim_id)
        conn.execute(
            "UPDATE claims SET status = ? WHERE claim_id = ?", (status, claim_id)
        )
        conn.commit()


def has_decision(db_path: Path, claim_id: str) -> bool:
    """Return whether a decision has been recorded."""
    with connect(db_path) as conn:
        return _decision_row(conn, claim_id) is not None
