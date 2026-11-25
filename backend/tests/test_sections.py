def test_manual_sections(client):
    response = client.get("/api/documents/manual/sections")
    assert response.status_code == 200
    headings = response.json()
    assert "9. Repeat claims" in headings
    assert "10. Meals without receipts" in headings


def test_wording_sections(client):
    response = client.get("/api/documents/wording/sections")
    assert response.status_code == 200
    headings = response.json()
    assert "3. Trip Delay" in headings
    assert "10. How we work out your payment" in headings


def test_read_meals_section(client):
    response = client.get("/api/documents/manual/sections/10. Meals without receipts")
    assert response.status_code == 200
    assert "$35" in response.json()["text"]


def test_read_wild_animals_section(client):
    response = client.get("/api/documents/manual/sections/7. Interpretation notes")
    assert response.status_code == 200
    assert "Wild animals" in response.json()["text"]


def test_unknown_document_and_heading(client):
    missing = client.get("/api/documents/other/sections")
    assert missing.status_code == 404
    heading = client.get("/api/documents/wording/sections/99. Missing")
    assert heading.status_code == 404


def test_section_routes_are_required(client):
    spec = client.get("/openapi.json").json()
    ids = {
        operation["operationId"]
        for item in spec["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert {"list_sections", "read_section"} <= ids
    for path, item in spec["paths"].items():
        if not path.startswith("/api/documents/"):
            continue
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for param in operation.get("parameters", []):
                assert param["required"] is True
