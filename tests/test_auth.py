"""
Tests for user registration, login, logout, Google OAuth, and profile API.
Run with: pytest tests/test_auth.py -v
"""
import pytest
import json
import sys
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

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


# ── Auth config ────────────────────────────────────────────────────────

def test_auth_config_returns_client_id(client):
    resp = client.get("/api/auth/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "google_client_id" in data


# ── Google OAuth ───────────────────────────────────────────────────────

def test_google_auth_disabled_when_no_client_id(client):
    with patch("app.GOOGLE_CLIENT_ID", ""):
        resp = client.post("/api/auth/google", json={"credential": "fake"})
        assert resp.status_code == 501


def test_google_auth_missing_credential(client):
    with patch("app.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com"):
        resp = client.post("/api/auth/google", json={})
        assert resp.status_code == 400


def _mock_google_tokeninfo(monkeypatch, token_info):
    """Mock urllib.request.urlopen to return a fake Google tokeninfo response."""
    import urllib.request

    class FakeResp:
        def read(self):
            return json.dumps(token_info).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())


def test_google_auth_success(client, monkeypatch):
    client_id = "test-client-id.apps.googleusercontent.com"
    token_info = {
        "aud": client_id,
        "sub": "google-uid-12345",
        "email": "alice@gmail.com",
        "name": "Alice",
    }
    _mock_google_tokeninfo(monkeypatch, token_info)

    with patch("app.GOOGLE_CLIENT_ID", client_id):
        resp = client.post("/api/auth/google", json={"credential": "valid-token"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["user"]["display_name"] == "Alice"

        # Should be logged in now
        me = client.get("/api/me").get_json()
        assert me["user"]["display_name"] == "Alice"


def test_google_auth_wrong_audience(client, monkeypatch):
    token_info = {
        "aud": "wrong-client-id",
        "sub": "google-uid-999",
        "email": "bob@gmail.com",
        "name": "Bob",
    }
    _mock_google_tokeninfo(monkeypatch, token_info)

    with patch("app.GOOGLE_CLIENT_ID", "correct-client-id"):
        resp = client.post("/api/auth/google", json={"credential": "token"})
        assert resp.status_code == 401


def test_google_auth_reuse_existing_user(client, monkeypatch):
    client_id = "test-id.apps.googleusercontent.com"
    token_info = {
        "aud": client_id,
        "sub": "google-uid-repeat",
        "email": "repeat@gmail.com",
        "name": "Repeat User",
    }
    _mock_google_tokeninfo(monkeypatch, token_info)

    with patch("app.GOOGLE_CLIENT_ID", client_id):
        # First login creates user
        resp1 = client.post("/api/auth/google", json={"credential": "token"})
        user_id_1 = resp1.get_json()["user"]["id"]

        client.post("/api/logout")

        # Second login reuses same user
        resp2 = client.post("/api/auth/google", json={"credential": "token"})
        user_id_2 = resp2.get_json()["user"]["id"]

        assert user_id_1 == user_id_2
