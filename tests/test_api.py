def test_health_reports_the_synthetic_book(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["recipes"] == 40
    assert body["suppliers"] == 6
    assert body["embeddings"] == "hash"
    assert body["currency"] == "PHP"
    page = client.get("/")
    assert page.status_code == 200
    assert "Shopping list" in page.text


def test_run_and_issue(client, desk):
    started = client.post(
        "/api/runs",
        json={"text": "Northwind BPO needs a corporate lunch for 60 guests in 21 days at 12:00 in Taguig. Budget 45000 pesos. No pork. 8 vegetarian guests."},
    )
    assert started.status_code == 200
    run_id = started.json()["run_id"]
    desk.wait(run_id)
    view = client.get(f"/api/runs/{run_id}")
    assert view.status_code == 200
    assert view.json()["status"] == "pass"
    issued = client.post(f"/api/runs/{run_id}/decision", json={"action": "issue", "notes": "Send it."})
    assert issued.status_code == 200
    assert issued.json()["status"] == "issued"


def test_unknown_run(client):
    missing = client.get("/api/runs/not-a-run")
    assert missing.status_code == 404
    assert "error" in missing.json()
