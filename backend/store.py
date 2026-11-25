"""Read claims and related records from SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.db import connect

QUEUE_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "instructions_queue.md"
CLAIM_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "instructions_claim.md"

CLAIM_SELECT = """
SELECT
    c.claim_id, c.policy_id, c.customer_id, c.claim_type, c.submitted_on,
    c.incident_date, c.incident_location, c.summary, c.story, c.items,
    c.amount_claimed, c.documents, c.status,
    cu.name AS customer_name, cu.previous_claims,
    p.plan, p.add_ons, p.purchased_on, p.sold_through, p.destination,
    p.departs_on, p.returns_on, p.trip_cost, p.travelers,
    p.status AS policy_status,
    pl.name AS plan_name, pl.trip_cancellation_max,
    pl.trip_delay_waiting_hours, pl.trip_delay_max,
    pl.baggage_delay_waiting_hours, pl.baggage_delay_max, pl.baggage_max,
    pl.per_item_limit, pl.passport_max, pl.emergency_medical_max, pl.deductible,
    co.deductible_applies_to,
    d.outcome, d.payout, d.explanation, d.policy_section,
    s.handler_id AS sign_off_handler_id, h.name AS sign_off_handler_name,
    pay.amount AS payment_amount,
    f.failures AS failures
FROM claims c
JOIN customers cu ON cu.customer_id = c.customer_id
JOIN policies p ON p.policy_id = c.policy_id
JOIN plans pl ON pl.plan = p.plan
JOIN company co
LEFT JOIN decisions d ON d.claim_id = c.claim_id
LEFT JOIN sign_offs s ON s.claim_id = c.claim_id
LEFT JOIN handlers h ON h.handler_id = s.handler_id
LEFT JOIN payments pay ON pay.claim_id = c.claim_id
LEFT JOIN claim_failures f ON f.claim_id = c.claim_id
WHERE c.claim_id = ?
"""


def instructions() -> dict[str, str]:
    """Return the queue instructions and the claim instructions."""
    return {
        "queue": QUEUE_INSTRUCTIONS_PATH.read_text(),
        "claim": CLAIM_INSTRUCTIONS_PATH.read_text(),
    }


def list_claims(db_path: Path) -> list[dict[str, Any]]:
    """Return the queue ordered by claim id."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.claim_id, cu.name AS customer_name, c.summary,
                   c.claim_type, c.submitted_on, c.amount_claimed, c.status,
                   d.outcome, d.payout
            FROM claims c
            JOIN customers cu ON cu.customer_id = c.customer_id
            LEFT JOIN decisions d ON d.claim_id = c.claim_id
            ORDER BY c.claim_id
            """
        ).fetchall()
    return [
        {
            "claim_id": row["claim_id"],
            "customer_name": row["customer_name"],
            "summary": row["summary"],
            "claim_type": row["claim_type"],
            "submitted_on": row["submitted_on"],
            "amount_claimed": row["amount_claimed"],
            "status": row["status"],
            "outcome": row["outcome"],
            "payout": row["payout"],
        }
        for row in rows
    ]


def list_handlers(db_path: Path) -> list[dict[str, Any]]:
    """Return the claims handlers."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT handler_id, name, role, email, can_approve_over_limit
            FROM handlers
            ORDER BY handler_id
            """
        ).fetchall()
    return [
        {
            "handler_id": row["handler_id"],
            "name": row["name"],
            "role": row["role"],
            "email": row["email"],
            "can_approve_over_limit": bool(row["can_approve_over_limit"]),
        }
        for row in rows
    ]


def get_policy_wording(db_path: Path) -> str:
    """Return the policy wording."""
    return _document(db_path, "wording")


def list_section_headings(db_path: Path, name: str) -> list[str] | None:
    """Return the section headings of the wording or the manual."""
    if name not in {"wording", "manual"}:
        return None
    return [heading for heading, _text in _sections(_document(db_path, name))]


def read_section(db_path: Path, name: str, heading: str) -> str | None:
    """Return one section of the wording or the manual."""
    if name not in {"wording", "manual"}:
        return None
    for found, text in _sections(_document(db_path, name)):
        if found == heading:
            return text
    return None


def _document(db_path: Path, name: str) -> str:
    if name == "wording":
        query = "SELECT wording AS body FROM policy_wording"
    else:
        query = "SELECT manual AS body FROM claims_manual"
    with connect(db_path) as conn:
        row = conn.execute(query).fetchone()
    if row is None:
        raise sqlite3.Error(f"{name} is missing")
    return str(row["body"])


def _sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(lines).strip()))
            heading = line[3:].strip()
            lines = [line]
        elif heading is not None:
            lines.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def get_claim(db_path: Path, claim_id: str) -> dict[str, Any] | None:
    """Return one claim with its policy, history, decision, sign-off and payment."""
    with connect(db_path) as conn:
        row = conn.execute(CLAIM_SELECT, (claim_id,)).fetchone()
        if row is None:
            return None
        add_ons = _add_ons(conn, json.loads(row["add_ons"]))
    return _claim_from_row(row, add_ons)


def _add_ons(conn: sqlite3.Connection, ids: list[str]) -> list[dict[str, Any]]:
    add_ons: list[dict[str, Any]] = []
    for add_on_id in ids:
        row = conn.execute(
            """
            SELECT add_on, name, effect, electronics_per_item_limit
            FROM add_ons WHERE add_on = ?
            """,
            (add_on_id,),
        ).fetchone()
        if row is None:
            raise sqlite3.Error(f"add-on {add_on_id} is missing")
        add_on: dict[str, Any] = {
            "add_on": row["add_on"],
            "name": row["name"],
            "effect": row["effect"],
        }
        if row["electronics_per_item_limit"] is not None:
            add_on["electronics_per_item_limit"] = row["electronics_per_item_limit"]
        add_ons.append(add_on)
    return add_ons


def _claim_from_row(row: sqlite3.Row, add_ons: list[dict[str, Any]]) -> dict[str, Any]:
    decision = None
    if row["outcome"] is not None:
        decision = {
            "outcome": row["outcome"],
            "payout": row["payout"],
            "explanation": row["explanation"],
            "policy_section": row["policy_section"],
        }
    sign_off = None
    if row["sign_off_handler_id"] is not None:
        sign_off = {
            "handler_id": row["sign_off_handler_id"],
            "handler_name": row["sign_off_handler_name"],
        }
    payment = None
    if row["payment_amount"] is not None:
        payment = {"amount": row["payment_amount"]}
    return {
        "claim_id": row["claim_id"],
        "policy_id": row["policy_id"],
        "customer_id": row["customer_id"],
        "claim_type": row["claim_type"],
        "submitted_on": row["submitted_on"],
        "incident_date": row["incident_date"],
        "incident_location": row["incident_location"],
        "summary": row["summary"],
        "story": row["story"],
        "items": json.loads(row["items"]),
        "amount_claimed": row["amount_claimed"],
        "documents": json.loads(row["documents"]),
        "status": row["status"],
        "customer_name": row["customer_name"],
        "previous_claims": json.loads(row["previous_claims"]),
        "policy": {
            "policy_id": row["policy_id"],
            "plan": row["plan"],
            "plan_name": row["plan_name"],
            "add_ons": add_ons,
            "purchased_on": row["purchased_on"],
            "sold_through": row["sold_through"],
            "trip": {
                "destination": row["destination"],
                "departs_on": row["departs_on"],
                "returns_on": row["returns_on"],
                "trip_cost": row["trip_cost"],
            },
            "travelers": json.loads(row["travelers"]),
            "status": row["policy_status"],
            "limits": {
                "trip_cancellation_max": row["trip_cancellation_max"],
                "trip_delay_waiting_hours": row["trip_delay_waiting_hours"],
                "trip_delay_max": row["trip_delay_max"],
                "baggage_delay_waiting_hours": row["baggage_delay_waiting_hours"],
                "baggage_delay_max": row["baggage_delay_max"],
                "baggage_max": row["baggage_max"],
                "per_item_limit": row["per_item_limit"],
                "passport_max": row["passport_max"],
                "emergency_medical_max": row["emergency_medical_max"],
                "deductible": row["deductible"],
                "deductible_applies_to": json.loads(row["deductible_applies_to"]),
            },
        },
        "decision": decision,
        "sign_off": sign_off,
        "payment": payment,
        "failures": int(row["failures"] or 0),
    }
