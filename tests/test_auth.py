"""
Tests for user registration, login, logout, and profile API.
Run with: pytest tests/test_auth.py -v
"""
import pytest
import sys
import os
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Use a temporary database for each test."""
    import database as db
    tmpdir = tempfile.mkdtemp()
    from pathlib import Path
    monkeypatch.setattr(db, "DB_PATH", Path(tmpdir) / "test_users.db")
    db.init_db()
    yield
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def client():
    from app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as c:
        yield c


# ── Registration ───────────────────────────────────────────────────────

def test_register_success(client):
    resp = client.post("/api/register", json={
        "username": "player1",
        "password": "pass1234",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["user"]["username"] == "player1"
    assert data["user"]["games_played"] == 0


def test_register_with_display_name(client):
    resp = client.post("/api/register", json={
        "username": "player2",
        "password": "pass1234",
        "display_name": "棋手小明",
    })
    assert resp.status_code == 200
    assert resp.get_json()["user"]["display_name"] == "棋手小明"


def test_register_duplicate_username(client):
    client.post("/api/register", json={"username": "taken", "password": "1234"})
    resp = client.post("/api/register", json={"username": "taken", "password": "5678"})
    assert resp.status_code == 409
    assert "已被注册" in resp.get_json()["error"]


def test_register_short_username(client):
    resp = client.post("/api/register", json={"username": "a", "password": "1234"})
    assert resp.status_code == 400


def test_register_short_password(client):
    resp = client.post("/api/register", json={"username": "player", "password": "12"})
    assert resp.status_code == 400


def test_register_invalid_username_chars(client):
    resp = client.post("/api/register", json={"username": "a b c", "password": "1234"})
    assert resp.status_code == 400


# ── Login ──────────────────────────────────────────────────────────────

def test_login_success(client):
    client.post("/api/register", json={"username": "user1", "password": "pass123"})
    client.post("/api/logout")

    resp = client.post("/api/login", json={"username": "user1", "password": "pass123"})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["username"] == "user1"


def test_login_wrong_password(client):
    client.post("/api/register", json={"username": "user2", "password": "correct"})
    resp = client.post("/api/login", json={"username": "user2", "password": "wrong"})
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    resp = client.post("/api/login", json={"username": "ghost", "password": "1234"})
    assert resp.status_code == 401


def test_login_missing_fields(client):
    resp = client.post("/api/login", json={"username": "", "password": ""})
    assert resp.status_code == 400


# ── Session / Me ───────────────────────────────────────────────────────

def test_me_not_logged_in(client):
    resp = client.get("/api/me")
    assert resp.status_code == 200
    assert resp.get_json()["user"] is None


def test_me_after_login(client):
    client.post("/api/register", json={"username": "sess", "password": "1234"})
    resp = client.get("/api/me")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["username"] == "sess"


# ── Logout ─────────────────────────────────────────────────────────────

def test_logout(client):
    client.post("/api/register", json={"username": "bye", "password": "1234"})
    client.post("/api/logout")
    resp = client.get("/api/me")
    assert resp.get_json()["user"] is None


# ── Case-insensitive username ──────────────────────────────────────────

def test_username_case_insensitive(client):
    client.post("/api/register", json={"username": "Alice", "password": "1234"})
    resp = client.post("/api/register", json={"username": "alice", "password": "5678"})
    assert resp.status_code == 409

    resp = client.post("/api/login", json={"username": "ALICE", "password": "1234"})
    assert resp.status_code == 200
