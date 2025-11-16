def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True

def test_questions_next_and_get(client):
    r = client.get("/questions/next", params={"username": "alice", "k": 2})
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 1

    ex_id = items[0]["exercise_id"]
    r2 = client.get(f"/questions/{ex_id}")
    assert r2.status_code == 200
    assert r2.json()["exercise_id"] == ex_id

def test_submit_attempt_and_list_attempts(client):
    # get one question
    nxt = client.get("/questions/next", params={"username": "bob", "k": 1}).json()
    ex_id = nxt[0]["exercise_id"]

    # submit an answer
    payload = {"username": "bob", "exercise_id": ex_id, "answer": "I would use Banach contraction."}
    r = client.post("/attempts", json=payload)
    assert r.status_code == 200
    out = r.json()
    assert "score" in out and "correct" in out

    # recent attempts should show the attempt
    r2 = client.get("/users/bob/attempts", params={"limit": 10})
    assert r2.status_code == 200
    attempts = r2.json()
    assert any(a["exercise_id"] == ex_id for a in attempts)
