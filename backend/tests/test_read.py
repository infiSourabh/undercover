from backend.store import CLAIM_INSTRUCTIONS_PATH, QUEUE_INSTRUCTIONS_PATH, instructions

PHASE2_IDS = {
    "health",
    "list_claims",
    "get_claim",
    "get_policy_wording",
    "get_instructions",
    "list_handlers",
}


def test_list_claims(client):
    response = client.get("/api/claims")
    assert response.status_code == 200
    claims = response.json()
    assert len(claims) == 25
    first = claims[0]
    assert first["claim_id"] == "CLM-1001"
    assert first["customer_name"] == "Maya Patel"
    assert first["amount_claimed"] == 420
    assert first["claim_type"] == "trip_delay"
    assert first["submitted_on"] == "2026-06-24"
    assert first["status"] == "waiting"
    assert first["outcome"] is None
    assert first["payout"] is None


def test_get_claim(client):
    response = client.get("/api/claims/CLM-1001")
    assert response.status_code == 200
    claim = response.json()
    assert "Rome" in claim["story"]
    assert "canceled" in claim["story"]
    hotel = next(item for item in claim["items"] if item["amount"] == 245)
    assert hotel["description"] == "Airport hotel, one night"
    assert claim["policy"]["plan"] == "premium"
    assert claim["policy"]["plan_name"] == "UnderCover Premium"
    assert claim["policy"]["travelers"] == ["Maya Patel"]
    assert claim["previous_claims"][0]["claim_id"] == "CLM-0412"
    assert claim["decision"] is None
    assert claim["sign_off"] is None
    assert claim["payment"] is None


def test_get_claim_missing(client):
    response = client.get("/api/claims/CLM-9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Claim CLM-9999 not found."


def test_policy_wording(client):
    response = client.get("/api/policy-wording")
    assert response.status_code == 200
    assert "10. How we work out your payment" in response.json()["wording"]


def test_instructions(client):
    response = client.get("/api/instructions")
    assert response.status_code == 200
    body = response.json()
    assert body == instructions()
    assert body["queue"] == QUEUE_INSTRUCTIONS_PATH.read_text()
    assert body["claim"] == CLAIM_INSTRUCTIONS_PATH.read_text()
    assert "at most {cap} claims" in body["queue"]
    assert "Do not try another amount" in body["claim"]


def test_handlers(client):
    response = client.get("/api/handlers")
    assert response.status_code == 200
    handlers = response.json()
    names = {handler["name"] for handler in handlers}
    assert names == {"Dana Whitfield", "Marcus Oyelaran", "Priya Raman"}
    assert all(handler["can_approve_over_limit"] is True for handler in handlers)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_phase2(client):
    spec = client.get("/openapi.json").json()
    ids = {
        operation["operationId"]
        for item in spec["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert ids >= PHASE2_IDS
    for item in spec["paths"].values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for param in operation.get("parameters", []):
                assert param["required"] is True
            if "requestBody" in operation:
                assert operation["requestBody"]["required"] is True
