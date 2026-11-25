"""SQLite store and seed data for the UnderCover backend."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_DB = Path(__file__).resolve().parent / "undercover.sqlite"
SEED_FILES = [
    "company.json",
    "plans.json",
    "policies.json",
    "customers.json",
    "handlers.json",
    "claims.json",
    "policy_wording.md",
    "claims_manual.md",
]

SCHEMA = """
CREATE TABLE company (
    payout_approval_limit REAL NOT NULL,
    deductible_applies_to TEXT NOT NULL
);
CREATE TABLE plans (
    plan TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trip_cancellation_max REAL NOT NULL,
    trip_delay_waiting_hours INTEGER NOT NULL,
    trip_delay_max REAL NOT NULL,
    baggage_delay_waiting_hours INTEGER NOT NULL,
    baggage_delay_max REAL NOT NULL,
    baggage_max REAL NOT NULL,
    per_item_limit REAL NOT NULL,
    passport_max REAL NOT NULL,
    emergency_medical_max REAL NOT NULL,
    deductible REAL NOT NULL
);
CREATE TABLE add_ons (
    add_on TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    effect TEXT NOT NULL,
    electronics_per_item_limit REAL
);
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    previous_claims TEXT NOT NULL
);
CREATE TABLE handlers (
    handler_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    email TEXT NOT NULL,
    can_approve_over_limit INTEGER NOT NULL
);
CREATE TABLE policies (
    policy_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    plan TEXT NOT NULL,
    add_ons TEXT NOT NULL,
    purchased_on TEXT NOT NULL,
    sold_through TEXT NOT NULL,
    destination TEXT NOT NULL,
    departs_on TEXT NOT NULL,
    returns_on TEXT NOT NULL,
    trip_cost REAL NOT NULL,
    travelers TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    submitted_on TEXT NOT NULL,
    incident_date TEXT NOT NULL,
    incident_location TEXT NOT NULL,
    summary TEXT NOT NULL,
    story TEXT NOT NULL,
    items TEXT NOT NULL,
    amount_claimed REAL NOT NULL,
    documents TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE policy_wording (
    wording TEXT NOT NULL
);
CREATE TABLE claims_manual (
    manual TEXT NOT NULL
);
CREATE TABLE decisions (
    claim_id TEXT PRIMARY KEY,
    outcome TEXT NOT NULL,
    payout REAL NOT NULL,
    explanation TEXT NOT NULL,
    policy_section TEXT NOT NULL
);
CREATE TABLE sign_offs (
    claim_id TEXT PRIMARY KEY,
    handler_id TEXT NOT NULL
);
CREATE TABLE payments (
    claim_id TEXT PRIMARY KEY,
    amount REAL NOT NULL
);
CREATE TABLE activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    max_claims INTEGER NOT NULL,
    summary TEXT
);
CREATE TABLE todos (
    run_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    claim_id TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (run_id, position)
);
CREATE TABLE claim_failures (
    claim_id TEXT PRIMARY KEY,
    failures INTEGER NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection for one operation."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _load_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text())


def _seed_company(conn: sqlite3.Connection) -> None:
    company = _load_json("company.json")
    plans_file = _load_json("plans.json")
    conn.execute(
        """
        INSERT INTO company (payout_approval_limit, deductible_applies_to)
        VALUES (?, ?)
        """,
        (
            company["payout_approval_limit"],
            json.dumps(plans_file["deductible_applies_to"]),
        ),
    )


def _seed_plans(conn: sqlite3.Connection) -> None:
    plans_file = _load_json("plans.json")
    for plan in plans_file["plans"]:
        conn.execute(
            """
            INSERT INTO plans (
                plan, name, trip_cancellation_max, trip_delay_waiting_hours,
                trip_delay_max, baggage_delay_waiting_hours, baggage_delay_max,
                baggage_max, per_item_limit, passport_max, emergency_medical_max,
                deductible
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan["plan"],
                plan["name"],
                plan["trip_cancellation_max"],
                plan["trip_delay_waiting_hours"],
                plan["trip_delay_max"],
                plan["baggage_delay_waiting_hours"],
                plan["baggage_delay_max"],
                plan["baggage_max"],
                plan["per_item_limit"],
                plan["passport_max"],
                plan["emergency_medical_max"],
                plan["deductible"],
            ),
        )
    for add_on in plans_file["add_ons"]:
        conn.execute(
            """
            INSERT INTO add_ons (add_on, name, effect, electronics_per_item_limit)
            VALUES (?, ?, ?, ?)
            """,
            (
                add_on["add_on"],
                add_on["name"],
                add_on["effect"],
                add_on.get("electronics_per_item_limit"),
            ),
        )


def _seed_people(conn: sqlite3.Connection) -> None:
    for customer in _load_json("customers.json"):
        conn.execute(
            """
            INSERT INTO customers (customer_id, name, previous_claims)
            VALUES (?, ?, ?)
            """,
            (
                customer["customer_id"],
                customer["name"],
                json.dumps(customer["previous_claims"]),
            ),
        )
    for handler in _load_json("handlers.json"):
        conn.execute(
            """
            INSERT INTO handlers (handler_id, name, role, email, can_approve_over_limit)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                handler["handler_id"],
                handler["name"],
                handler["role"],
                handler["email"],
                int(handler["can_approve_over_limit"]),
            ),
        )


def _seed_policies(conn: sqlite3.Connection) -> None:
    for policy in _load_json("policies.json"):
        trip = policy["trip"]
        conn.execute(
            """
            INSERT INTO policies (
                policy_id, customer_id, plan, add_ons, purchased_on, sold_through,
                destination, departs_on, returns_on, trip_cost, travelers, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                policy["policy_id"],
                policy["customer_id"],
                policy["plan"],
                json.dumps(policy["add_ons"]),
                policy["purchased_on"],
                policy["sold_through"],
                trip["destination"],
                trip["departs_on"],
                trip["returns_on"],
                trip["trip_cost"],
                json.dumps(policy["travelers"]),
                policy["status"],
            ),
        )


def _seed_claims(conn: sqlite3.Connection) -> None:
    for claim in _load_json("claims.json"):
        status = "waiting" if claim["status"] == "open" else claim["status"]
        conn.execute(
            """
            INSERT INTO claims (
                claim_id, policy_id, customer_id, claim_type, submitted_on,
                incident_date, incident_location, summary, story, items,
                amount_claimed, documents, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim["claim_id"],
                claim["policy_id"],
                claim["customer_id"],
                claim["claim_type"],
                claim["submitted_on"],
                claim["incident_date"],
                claim["incident_location"],
                claim["summary"],
                claim["story"],
                json.dumps(claim["items"]),
                claim["amount_claimed"],
                json.dumps(claim["documents"]),
                status,
            ),
        )


def seed(db_path: Path) -> None:
    """Create the schema and load the business data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _seed_company(conn)
        _seed_plans(conn)
        _seed_people(conn)
        _seed_policies(conn)
        _seed_claims(conn)
        wording = (DATA_DIR / "policy_wording.md").read_text()
        manual = (DATA_DIR / "claims_manual.md").read_text()
        conn.execute("INSERT INTO policy_wording (wording) VALUES (?)", (wording,))
        conn.execute("INSERT INTO claims_manual (manual) VALUES (?)", (manual,))
        conn.commit()


def waiting_count(db_path: Path) -> int:
    """Return how many claims are waiting."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM claims WHERE status = 'waiting'"
        ).fetchone()
    if row is None:
        raise sqlite3.Error("COUNT(*) returned no row")
    return int(row["n"])
