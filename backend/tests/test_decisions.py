APPROVE_1001 = {
    "outcome": "approve",
    "payout": 420,
    "explanation": "The delay is covered. The payout is the claimed expenses.",
    "policy_section": "3. Trip Delay",
}

APPROVE_1002 = {
    "outcome": "approve",
    "payout": 1150,
    "explanation": "Approved over the handler limit.",
    "policy_section": "5. Baggage and Personal Effects",
}

PHASE3_IDS = {
    "health",
    "list_claims",
    "get_claim",
    "list_activity",
    "record_activity",
    "decide_claim",
    "sign_off_claim",
    "pay_claim",
    "get_policy_wording",
    "get_instructions",
    "list_handlers",
}


def _messages(client, claim_id: str) -> list[str]:
    return [
        row["message"] for row in client.get(f"/api/claims/{claim_id}/activity").json()
    ]


def test_approve_under_limit(client):
    response = client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    assert response.status_code == 200
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["decision"]["outcome"] == "approve"
    assert claim["decision"]["payout"] == 420
    assert claim["decision"]["explanation"] == APPROVE_1001["explanation"]
    assert claim["decision"]["policy_section"] == "3. Trip Delay"
    assert claim["status"] == "in_progress"


def test_pay_under_limit_then_reject_second_pay(client):
    client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    response = client.post("/api/claims/CLM-1001/payment", json={"amount": 420})
    assert response.status_code == 200
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 420
    second = client.post("/api/claims/CLM-1001/payment", json={"amount": 420})
    assert second.status_code == 409
    again = client.get("/api/claims/CLM-1001").json()
    assert again["payment"]["amount"] == 420


def test_pay_wrong_amount(client):
    client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    response = client.post("/api/claims/CLM-1001/payment", json={"amount": 100})
    assert response.status_code == 409
    assert "The amount must match the approved payout." in response.json()["detail"]
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["payment"] is None


def test_approve_over_limit_waits_for_sign_off(client):
    response = client.post("/api/claims/CLM-1002/decision", json=APPROVE_1002)
    assert response.status_code == 200
    assert client.get("/api/claims/CLM-1002").json()["status"] == "waiting_for_sign_off"


def test_pay_over_limit_blocked_before_sign_off(client):
    client.post("/api/claims/CLM-1002/decision", json=APPROVE_1002)
    response = client.post("/api/claims/CLM-1002/payment", json={"amount": 1150})
    assert response.status_code == 409
    assert "The payout needs a handler's sign-off." in response.json()["detail"]
    assert client.get("/api/claims/CLM-1002").json()["payment"] is None


def test_sign_off_then_pay_over_limit(client):
    client.post("/api/claims/CLM-1002/decision", json=APPROVE_1002)
    signed = client.post("/api/claims/CLM-1002/sign-off", json={"handler_id": "HND-01"})
    assert signed.status_code == 200
    paid = client.post("/api/claims/CLM-1002/payment", json={"amount": 1150})
    assert paid.status_code == 200
    claim = client.get("/api/claims/CLM-1002").json()
    assert claim["status"] == "decided"
    assert claim["payment"]["amount"] == 1150
    assert claim["sign_off"]["handler_id"] == "HND-01"
    assert claim["sign_off"]["handler_name"] == "Dana Whitfield"


def test_sign_off_missing_handler_and_under_limit(client):
    client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    missing = client.post(
        "/api/claims/CLM-1001/sign-off", json={"handler_id": "HND-99"}
    )
    assert missing.status_code == 404
    under = client.post("/api/claims/CLM-1001/sign-off", json={"handler_id": "HND-01"})
    assert under.status_code == 409


def test_decline_and_pay_declined(client):
    ok = client.post(
        "/api/claims/CLM-1003/decision",
        json={
            "outcome": "decline",
            "payout": 0,
            "explanation": "Outside the cover.",
            "policy_section": "9. General exclusions",
        },
    )
    assert ok.status_code == 200
    assert client.get("/api/claims/CLM-1003").json()["status"] == "decided"
    bad = client.post(
        "/api/claims/CLM-1004/decision",
        json={
            "outcome": "decline",
            "payout": 10,
            "explanation": "Outside the cover.",
            "policy_section": "9. General exclusions",
        },
    )
    assert bad.status_code == 409
    pay_declined = client.post("/api/claims/CLM-1003/payment", json={"amount": 0})
    assert pay_declined.status_code == 409


def test_decide_after_payment_rejected(client):
    client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    client.post("/api/claims/CLM-1001/payment", json={"amount": 420})
    again = client.post("/api/claims/CLM-1001/decision", json=APPROVE_1001)
    assert again.status_code == 409


def test_activity_order_for_over_limit_claim(client):
    client.post("/api/claims/CLM-1002/decision", json=APPROVE_1002)
    client.post("/api/claims/CLM-1002/payment", json={"amount": 1150})
    client.post("/api/claims/CLM-1002/sign-off", json={"handler_id": "HND-01"})
    client.post("/api/claims/CLM-1002/payment", json={"amount": 1150})
    messages = _messages(client, "CLM-1002")
    assert "Approved $1,150.00." in messages[0]
    assert "sign-off" in messages[1]
    assert "Dana Whitfield signed off." in messages[2]
    assert "Paid $1,150.00." in messages[3]


def test_record_activity(client):
    response = client.post(
        "/api/claims/CLM-1001/activity",
        json={"message": "Read the claim, the policy, and the claim history"},
    )
    assert response.status_code == 200
    assert response.json()[0]["message"] == (
        "Read the claim, the policy, and the claim history"
    )


def test_openapi_phase3(client):
    spec = client.get("/openapi.json").json()
    ids = {
        operation["operationId"]
        for item in spec["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert ids >= PHASE3_IDS
    for item in spec["paths"].values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for param in operation.get("parameters", []):
                assert param["required"] is True
            if "requestBody" in operation:
                assert operation["requestBody"]["required"] is True
