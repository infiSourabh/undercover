import json
from pathlib import Path

from backend import seed as seed_mod
from backend.db import SEED_FILES, connect, seed, waiting_count
from backend.main import create_app


def test_seed_files_are_the_allowed_set():
    assert SEED_FILES == [
        "company.json",
        "plans.json",
        "policies.json",
        "customers.json",
        "handlers.json",
        "claims.json",
        "policy_wording.md",
        "claims_manual.md",
    ]
    listed = " ".join(SEED_FILES)
    assert "evals" not in listed
    assert "security" not in listed
    assert "knowledge.json" not in listed


def test_seed_loads_the_queue(db_path: Path):
    seed(db_path)
    with connect(db_path) as conn:
        claims = conn.execute(
            "SELECT claim_id FROM claims ORDER BY claim_id"
        ).fetchall()
        policies = conn.execute("SELECT policy_id FROM policies").fetchall()
        plans = conn.execute("SELECT plan FROM plans").fetchall()
        handlers = conn.execute("SELECT handler_id FROM handlers").fetchall()
        company = conn.execute("SELECT payout_approval_limit FROM company").fetchone()
        claim_customer_ids = {
            row["customer_id"] for row in conn.execute("SELECT customer_id FROM claims")
        }
        customers = {
            row["customer_id"]
            for row in conn.execute("SELECT customer_id FROM customers")
        }
        claim_policy_ids = {
            row["policy_id"] for row in conn.execute("SELECT policy_id FROM claims")
        }
        policy_ids = {row["policy_id"] for row in policies}
    assert [row["claim_id"] for row in claims] == [
        f"CLM-{n}" for n in range(1001, 1026)
    ]
    assert "CLM-1901" not in [row["claim_id"] for row in claims]
    assert len(claim_policy_ids) == 25
    assert claim_policy_ids <= policy_ids
    assert claim_customer_ids <= customers
    assert len(plans) == 3
    assert len(handlers) == 3
    assert company is not None
    assert company["payout_approval_limit"] == 1000
    assert waiting_count(db_path) == 25


def test_clm_1001_joins(db_path: Path):
    seed(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT c.policy_id, c.items, c.documents, cu.name, cu.previous_claims,
                   p.plan, pl.name AS plan_name, pl.deductible
            FROM claims c
            JOIN customers cu ON cu.customer_id = c.customer_id
            JOIN policies p ON p.policy_id = c.policy_id
            JOIN plans pl ON pl.plan = p.plan
            WHERE c.claim_id = 'CLM-1001'
            """
        ).fetchone()
        wording = conn.execute("SELECT wording FROM policy_wording").fetchone()
    assert row is not None
    items = json.loads(row["items"])
    documents = json.loads(row["documents"])
    previous = json.loads(row["previous_claims"])
    assert row["name"] == "Maya Patel"
    assert row["policy_id"] == "POL-2001"
    assert row["plan"] == "premium"
    assert row["plan_name"] == "UnderCover Premium"
    assert row["deductible"] == 50
    assert len(items) == 3
    assert len(documents) == 4
    assert previous[0]["claim_id"] == "CLM-0412"
    assert wording is not None
    assert "3. Trip Delay" in wording["wording"]


def test_create_app_seeds_when_missing(db_path: Path):
    assert not db_path.exists()
    create_app(db_path)
    assert waiting_count(db_path) == 25


def test_reset_prints(monkeypatch, tmp_path: Path, capsys):
    db = tmp_path / "undercover.sqlite"
    monkeypatch.setattr(seed_mod, "DEFAULT_DB", db)
    seed_mod.reset()
    assert capsys.readouterr().out == "Reset the queue: 25 claims waiting.\n"
    assert waiting_count(db) == 25
