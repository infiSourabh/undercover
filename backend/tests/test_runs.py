from backend.runs import failure_count
from backend.tests.test_decisions import APPROVE_1001

RUN_IDS = {
    "create_run",
    "get_current_run",
    "put_todos",
    "put_run_summary",
    "release_claim",
}


def test_current_run_missing(client):
    response = client.get("/api/runs/current")
    assert response.status_code == 404


def test_create_run(client):
    response = client.post("/api/runs", json={"max_claims": 5})
    assert response.status_code == 200
    run = response.json()
    assert run["max_claims"] == 5
    assert run["summary"] is None
    assert run["items"] == []
    assert client.get("/api/runs/current").json()["run_id"] == run["run_id"]


def test_put_todos_keeps_order(client):
    run_id = client.post("/api/runs", json={"max_claims": 5}).json()["run_id"]
    response = client.put(
        f"/api/runs/{run_id}/todos",
        json={
            "items": [
                {"claim_id": "CLM-1001", "status": "todo"},
                {"claim_id": "CLM-1002", "status": "in_progress"},
            ]
        },
    )
    assert response.status_code == 200
    assert client.get("/api/runs/current").json()["items"] == [
        {"claim_id": "CLM-1001", "status": "todo"},
        {"claim_id": "CLM-1002", "status": "in_progress"},
    ]


def test_summary_is_stored(client):
    run_id = client.post("/api/runs", json={"max_claims": 5}).json()["run_id"]
    response = client.post(
        f"/api/runs/{run_id}/summary",
        json={"summary": "Decided one claim."},
    )
    assert response.status_code == 200
    assert client.get("/api/runs/current").json()["summary"] == "Decided one claim."


def test_bad_todo_rejected(client):
    run_id = client.post("/api/runs", json={"max_claims": 5}).json()["run_id"]
    skipped = client.put(
        f"/api/runs/{run_id}/todos",
        json={"items": [{"claim_id": "CLM-1001", "status": "skipped"}]},
    )
    assert skipped.status_code == 409
    missing = client.put(
        f"/api/runs/{run_id}/todos",
        json={"items": [{"claim_id": "CLM-9999", "status": "todo"}]},
    )
    assert missing.status_code == 409


def test_release_counts_failures(client, db_path):
    first = client.post("/api/claims/CLM-1003/release", json={"result": "retry"})
    assert first.status_code == 200
    assert client.get("/api/claims/CLM-1003").json()["status"] == "waiting"
    assert failure_count(db_path, "CLM-1003") == 1
    second = client.post("/api/claims/CLM-1003/release", json={"result": "handler"})
    assert second.status_code == 200
    assert client.get("/api/claims/CLM-1003").json()["status"] == "left_for_handler"
    assert failure_count(db_path, "CLM-1003") == 2


def test_second_decision_and_release_are_rejected(client):
    client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    again = client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    assert again.status_code == 409
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["decision"]["payout"] == 420
    assert claim["status"] == "in_progress"
    released = client.post("/api/claims/CLM-1001/release", json={"result": "retry"})
    assert released.status_code == 409
    assert client.get("/api/claims/CLM-1001").json()["status"] == "in_progress"


def test_run_routes_are_required(client):
    spec = client.get("/openapi.json").json()
    ids = {
        operation["operationId"]
        for item in spec["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert ids >= RUN_IDS
    for path, item in spec["paths"].items():
        if "/runs" not in path and not path.endswith("/release"):
            continue
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for param in operation.get("parameters", []):
                assert param["required"] is True
            if "requestBody" in operation:
                assert operation["requestBody"]["required"] is True
