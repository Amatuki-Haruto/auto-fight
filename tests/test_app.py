"""app.py API のテスト"""
import pytest
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "sse_clients" in data


def test_index():
    r = client.get("/")
    assert r.status_code == 200
    assert "あるけみすと" in r.text


def test_check_go_initial():
    r = client.get("/api/check-go")
    assert r.status_code == 200
    assert r.json() == {"go": False}


def test_go_then_check():
    client.post("/api/go")
    r = client.get("/api/check-go")
    assert r.json() == {"go": True}
    r2 = client.get("/api/check-go")
    assert r2.json() == {"go": False}


def test_check_stop_initial():
    r = client.get("/api/check-stop")
    assert r.status_code == 200
    assert r.json() == {"stop": False}


def test_stop_then_check():
    client.post("/api/stop-exploration")
    r = client.get("/api/check-stop")
    assert r.json() == {"stop": True}
    r2 = client.get("/api/check-stop")
    assert r2.json() == {"stop": False}


def test_lucky_chance():
    r = client.post("/api/lucky-chance")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_exploration_started():
    r = client.post("/api/exploration-started")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_api_state():
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert "running" in data
    assert "lucky" in data
    assert "loop_count" in data
    assert "drops" in data


def test_exploration_log():
    r = client.post("/api/exploration-log", json={"loop_count": 5, "message": "テスト勝利", "exp": 13, "drops": ["[C] 弱体の種"]})
    assert r.status_code == 200
    r2 = client.get("/api/state")
    assert r2.json()["loop_count"] == 5
    assert r2.json()["last_message"] == "テスト勝利"
    assert r2.json()["total_exp"] == 13
    assert "[C] 弱体の種" in r2.json()["drops"]
    assert r2.json()["drops_by_rank"].get("C") == 1
