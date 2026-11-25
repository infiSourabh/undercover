import threading
import time

from backend.tests.test_decisions import APPROVE_1001


def test_run_returns_in_progress_while_agent_works(app, client):
    started = threading.Event()
    release = threading.Event()

    def slow_run(claim_id: str, thread_id: str, llm=None) -> str:
        started.set()
        release.wait(timeout=5)
        return "done"

    app.state.run_agent = slow_run
    response = client.post("/api/claims/CLM-1001/run", json={"thread_id": "thread-1"})
    assert response.status_code == 200
    assert response.json() == {"status": "in_progress"}
    assert started.wait(timeout=2)
    messages = [
        row["message"] for row in client.get("/api/claims/CLM-1001/activity").json()
    ]
    assert "Started work on this claim." in messages
    assert client.get("/api/claims/CLM-1001").json()["status"] == "in_progress"
    release.set()
    finished = False
    for _ in range(50):
        messages = [
            row["message"] for row in client.get("/api/claims/CLM-1001/activity").json()
        ]
        if "Finished work on this claim." in messages:
            finished = True
            break
        time.sleep(0.05)
    assert finished
    assert "Stopped before recording a decision." in messages


def test_run_on_decided_claim_rejected(client):
    client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    client.post("/api/claims/CLM-1001/payment", json={"amount": 420})
    response = client.post("/api/claims/CLM-1001/run", json={"thread_id": "thread-1"})
    assert response.status_code == 409


def test_run_missing_claim(client):
    response = client.post("/api/claims/CLM-9999/run", json={"thread_id": "thread-1"})
    assert response.status_code == 404
