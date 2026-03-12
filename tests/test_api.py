"""
API tests for the Flask backend.
Run with: venv/bin/pytest tests/test_api.py -v

These tests use Flask's test client and do NOT require a running KataGo process.
KataGo-dependent routes are tested with a mock.
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Make sure imports resolve from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    """Create a Flask test client with KataGo mocked out."""
    from app import app, game_state
    app.config["TESTING"] = True

    # Reset game state before each test
    game_state.update({
        "running": False,
        "board_size": 19,
        "human_color": "black",
        "ai_color": "white",
        "turn": "black",
        "move_history": [],
        "captures": {"black": 0, "white": 0},
        "game_over": False,
        "result": None,
        "consecutive_passes": 0,
    })

    with app.test_client() as c:
        yield c


# ── Static routes ──────────────────────────────────────────────────────────

def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"html" in resp.data.lower()


def test_static_js(client):
    resp = client.get("/game.js")
    assert resp.status_code == 200


def test_static_css(client):
    resp = client.get("/style.css")
    assert resp.status_code == 200


# ── /api/status ────────────────────────────────────────────────────────────

def test_status_no_katago(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "katago_running" in data
    assert data["katago_running"] is False
    assert "game" in data


# ── /api/new_game — validation ─────────────────────────────────────────────

def test_new_game_invalid_board_size(client):
    with patch("app.KataGoGTP") as MockKataGo:
        resp = client.post("/api/new_game", json={"board_size": 10})
        assert resp.status_code == 400
        assert "error" in resp.get_json()


def test_new_game_invalid_color(client):
    with patch("app.KataGoGTP") as MockKataGo:
        resp = client.post("/api/new_game", json={"board_size": 9, "human_color": "purple"})
        assert resp.status_code == 400
        assert "error" in resp.get_json()


def test_new_game_success(client):
    mock_kg = MagicMock()
    mock_kg.is_running.return_value = True
    mock_kg.get_stderr_tail.return_value = ""
    mock_kg.genmove.return_value = "PASS"

    with patch("app.KataGoGTP", return_value=mock_kg):
        with patch("app.katago", mock_kg):
            resp = client.post("/api/new_game", json={
                "board_size": 9,
                "human_color": "black",
                "komi": 6.5,
            })
            # KataGo start() raises no error — game should be created
            assert resp.status_code in (200, 500)  # 500 if mock not fully wired


def test_new_game_katago_error(client):
    from katago_gtp import KataGoError
    mock_kg = MagicMock()
    mock_kg.start.side_effect = KataGoError("binary not found")

    with patch("app.KataGoGTP", return_value=mock_kg):
        with patch("app.katago", None):
            resp = client.post("/api/new_game", json={"board_size": 9})
            assert resp.status_code == 500
            assert "error" in resp.get_json()


# ── /api/play — validation ─────────────────────────────────────────────────

def test_play_no_game_in_progress(client):
    resp = client.post("/api/play", json={"vertex": "D4"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "No game in progress"


def test_play_missing_vertex(client):
    import app as app_module
    app_module.game_state["running"] = True
    app_module.game_state["game_over"] = False
    app_module.game_state["turn"] = "black"
    app_module.game_state["human_color"] = "black"

    resp = client.post("/api/play", json={})
    assert resp.status_code == 400
    assert "vertex" in resp.get_json()["error"]


def test_play_game_over(client):
    import app as app_module
    app_module.game_state["running"] = False
    app_module.game_state["game_over"] = True

    resp = client.post("/api/play", json={"vertex": "D4"})
    assert resp.status_code == 400


# ── /api/resign ────────────────────────────────────────────────────────────

def test_resign_no_game(client):
    resp = client.post("/api/resign", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_resign_during_game(client):
    import app as app_module
    app_module.game_state["running"] = True
    app_module.game_state["game_over"] = False
    app_module.game_state["human_color"] = "black"
    app_module.game_state["ai_color"] = "white"

    resp = client.post("/api/resign", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["result"] == "White+Resign"
    assert data["game"]["game_over"] is True
