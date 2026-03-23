"""
Full-cycle test: register → play game → game recorded → replay moves.
Run with: pytest tests/test_game_history.py -v
"""
import pytest
import shutil
import tempfile
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
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


def _register_and_login(client, username="tester", password="pass1234"):
    client.post("/api/register", json={"username": username, "password": password})


def _simulate_game(client, human_color="black", moves=None, result="B+Resign"):
    """Directly manipulate game_state and trigger _record_game_result, simulating a finished AI game."""
    import app as app_module
    moves = moves or [
        {"color": "black", "vertex": "D4"},
        {"color": "white", "vertex": "F6"},
        {"color": "black", "vertex": "F4"},
        {"color": "white", "vertex": "D6"},
    ]
    app_module.game_state.update({
        "running": False,
        "game_over": True,
        "mode": "vs_ai",
        "board_size": 9,
        "human_color": human_color,
        "ai_color": "white" if human_color == "black" else "black",
        "komi": 7.5,
        "result": result,
        "move_history": moves,
        "captures": {"black": 0, "white": 0},
        "consecutive_passes": 0,
        "difficulty": "easy",
    })
    # Call _record_game_result within the active test request context
    app_module._record_game_result(result)


# ── List endpoint requires login ────────────────────────────────────────────

def test_my_games_requires_login(client):
    resp = client.get("/api/my_games")
    assert resp.status_code == 401


def test_my_games_empty_before_any_game(client):
    _register_and_login(client)
    resp = client.get("/api/my_games")
    assert resp.status_code == 200
    assert resp.get_json()["games"] == []


# ── Game is saved on completion ─────────────────────────────────────────────

def test_game_saved_after_resign(client):
    _register_and_login(client)
    _simulate_game(client, result="B+Resign")
    resp = client.get("/api/my_games")
    games = resp.get_json()["games"]
    assert len(games) == 1
    assert games[0]["result"] == "B+Resign"
    assert games[0]["board_size"] == 9
    assert games[0]["human_color"] == "black"


def test_game_saved_after_score(client):
    _register_and_login(client)
    _simulate_game(client, result="W+12.5")
    resp = client.get("/api/my_games")
    games = resp.get_json()["games"]
    assert len(games) == 1
    assert games[0]["result"] == "W+12.5"


def test_multiple_games_saved(client):
    _register_and_login(client)
    _simulate_game(client, result="B+Resign")
    _simulate_game(client, result="W+5.5")
    games = client.get("/api/my_games").get_json()["games"]
    assert len(games) == 2
    # Newest first
    assert games[0]["result"] == "W+5.5"
    assert games[1]["result"] == "B+Resign"


def test_game_not_saved_when_not_logged_in(client):
    # Use the resign API without being logged in — no game should be saved
    import app as app_module
    app_module.game_state.update({
        "running": True, "game_over": False, "mode": "vs_ai",
        "board_size": 9, "human_color": "black", "ai_color": "white",
        "komi": 7.5, "result": None, "move_history": [],
        "captures": {"black": 0, "white": 0}, "consecutive_passes": 0,
    })
    client.post("/api/resign")
    # Register now and check — should be empty
    _register_and_login(client)
    games = client.get("/api/my_games").get_json()["games"]
    assert games == []


def test_game_not_saved_in_local_mode(client):
    _register_and_login(client)
    import app as app_module
    app_module.game_state.update({
        "running": False, "game_over": True, "mode": "vs_human",
        "board_size": 9, "human_color": "black", "ai_color": "white",
        "komi": 7.5, "result": "B+Resign", "move_history": [],
        "captures": {"black": 0, "white": 0}, "consecutive_passes": 0,
    })
    app_module._record_game_result("B+Resign")
    games = client.get("/api/my_games").get_json()["games"]
    assert games == []


# ── Fetch a single game and replay its moves ────────────────────────────────

def test_fetch_game_by_id(client):
    _register_and_login(client)
    moves = [
        {"color": "black", "vertex": "D4"},
        {"color": "white", "vertex": "Q16"},
        {"color": "black", "vertex": "PASS"},
        {"color": "white", "vertex": "PASS"},
    ]
    _simulate_game(client, moves=moves, result="B+2.5")
    game_id = client.get("/api/my_games").get_json()["games"][0]["id"]

    resp = client.get(f"/api/my_games/{game_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    game = data["game"]
    assert game["id"] == game_id
    assert "played_at" in game


def test_fetched_game_has_correct_moves(client):
    _register_and_login(client)
    moves = [
        {"color": "black", "vertex": "D4"},
        {"color": "white", "vertex": "F6"},
        {"color": "black", "vertex": "F4"},
        {"color": "white", "vertex": "D6"},
    ]
    _simulate_game(client, moves=moves, result="B+Resign")
    game_id = client.get("/api/my_games").get_json()["games"][0]["id"]

    game = client.get(f"/api/my_games/{game_id}").get_json()["game"]
    parsed_moves = game["moves"]
    assert len(parsed_moves) == 4
    assert parsed_moves[0]["color"] == "black" and parsed_moves[0]["vertex"] == "D4"
    assert parsed_moves[1]["color"] == "white" and parsed_moves[1]["vertex"] == "F6"
    assert parsed_moves[2]["color"] == "black" and parsed_moves[2]["vertex"] == "F4"
    assert parsed_moves[3]["color"] == "white" and parsed_moves[3]["vertex"] == "D6"


def test_fetched_game_pass_moves(client):
    _register_and_login(client)
    moves = [
        {"color": "black", "vertex": "D4"},
        {"color": "white", "vertex": "PASS"},
    ]
    _simulate_game(client, moves=moves, result="B+5.5")
    game_id = client.get("/api/my_games").get_json()["games"][0]["id"]

    parsed_moves = client.get(f"/api/my_games/{game_id}").get_json()["game"]["moves"]
    assert len(parsed_moves) == 2
    assert parsed_moves[1]["vertex"] == "PASS"


def test_fetched_game_metadata(client):
    _register_and_login(client, username="alice")
    _simulate_game(client, human_color="black", result="B+Resign")
    game_id = client.get("/api/my_games").get_json()["games"][0]["id"]

    gi = client.get(f"/api/my_games/{game_id}").get_json()["game"]["game_info"]
    assert gi["black"] == "alice"
    assert gi["white"] == "KataGo"
    assert gi["result"] == "B+Resign"
    assert gi["board_size"] == 9


def test_fetch_game_not_found(client):
    _register_and_login(client)
    resp = client.get("/api/my_games/99999")
    assert resp.status_code == 404


def test_fetch_game_requires_login(client):
    resp = client.get("/api/my_games/1")
    assert resp.status_code == 401


def test_cannot_access_other_users_game(client):
    """User A cannot fetch User B's game."""
    from app import app
    # Register user A, play a game
    with app.test_client() as c_a:
        c_a.post("/api/register", json={"username": "userA", "password": "pass1234"})
        import app as app_module
        app_module.game_state.update({
            "running": False, "game_over": True, "mode": "vs_ai",
            "board_size": 9, "human_color": "black", "ai_color": "white",
            "komi": 7.5, "result": "B+Resign", "move_history": [],
            "captures": {"black": 0, "white": 0}, "consecutive_passes": 0, "difficulty": "easy",
        })
        app_module._record_game_result("B+Resign")
        game_id = c_a.get("/api/my_games").get_json()["games"][0]["id"]

    # Register user B, try to fetch user A's game
    _register_and_login(client, username="userB")
    resp = client.get(f"/api/my_games/{game_id}")
    assert resp.status_code == 404


# ── Stats are also updated alongside recording ──────────────────────────────

def test_stats_updated_with_game_record(client):
    _register_and_login(client)
    _simulate_game(client, human_color="black", result="B+Resign")  # win
    _simulate_game(client, human_color="black", result="W+5.5")     # loss

    me = client.get("/api/me").get_json()["user"]
    assert me["games_played"] == 2
    assert me["games_won"] == 1

    games = client.get("/api/my_games").get_json()["games"]
    assert len(games) == 2
