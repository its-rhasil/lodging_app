"""/health: used by the uptime monitor (Day 5). It must answer GET and HEAD without a login."""


def test_health_answers_get(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "connected", "result": 1}


def test_health_answers_head_for_uptime_monitors(client):
    res = client.head("/health")
    assert res.status_code == 200
    assert res.content == b""  # HEAD never carries a body
