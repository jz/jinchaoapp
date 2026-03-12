"""
Frontend E2E tests using Playwright.
Run against a live server:
    BASE_URL=http://198.252.103.20:5000 venv/bin/pytest tests/test_frontend_e2e.py -v

Requires playwright:
    venv/bin/pip install playwright
    venv/bin/playwright install chromium
"""
import os
import pytest

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def test_page_loads(page):
    page.goto(BASE_URL)
    assert "围棋" in page.title() or page.locator("canvas").is_visible()


def test_canvas_visible(page):
    page.goto(BASE_URL)
    canvas = page.locator("#goboard")
    canvas.wait_for(state="visible", timeout=5000)
    assert canvas.is_visible()


def test_setup_section_visible(page):
    page.goto(BASE_URL)
    setup = page.locator("#setup-section")
    assert setup.is_visible()


def test_game_section_hidden_initially(page):
    page.goto(BASE_URL)
    game = page.locator("#game-section")
    assert not game.is_visible()


def test_board_size_selector_present(page):
    page.goto(BASE_URL)
    select = page.locator("#board-size")
    assert select.is_visible()
    options = select.locator("option").all()
    values = [o.get_attribute("value") for o in options]
    assert "9" in values
    assert "13" in values
    assert "19" in values


def test_new_game_button_starts_game(page):
    """Clicking New Game should show the game section (KataGo must be running)."""
    page.goto(BASE_URL)
    # Select 9x9 for speed
    page.select_option("#board-size", "9")
    page.click("#btn-new-game")
    # Wait for game section to appear (KataGo may take a moment)
    try:
        page.locator("#game-section").wait_for(state="visible", timeout=15000)
        assert page.locator("#game-section").is_visible()
    except Exception:
        # If KataGo isn't running, a toast error appears — still a valid test
        toast = page.locator("#toast")
        if toast.is_visible():
            pytest.skip("KataGo not running on server — skipping game start test")
        raise


def test_game_runs_10_rounds(page):
    """Start a 9x9 game and verify it sustains at least 10 rounds (human move + AI response each)."""
    import json as _json
    _headers = {"Content-Type": "application/json"}

    resp = page.request.post(
        f"{BASE_URL}/api/new_game",
        data=_json.dumps({"board_size": 9, "human_color": "black"}),
        headers=_headers,
    )
    if not resp.ok or not resp.json().get("game", {}).get("running"):
        pytest.skip("KataGo not running — cannot start game")

    # Candidate moves spread across the 9x9 board
    candidates = [
        "A1", "I9", "A9", "I1",
        "E5",
        "C3", "G3", "C7", "G7",
        "E1", "E9", "A5", "I5",
        "B2", "H8", "B8", "H2",
        "D4", "F6", "D6", "F4",
    ]

    occupied = set()
    rounds = 0

    for vertex in candidates:
        if rounds >= 10:
            break
        if vertex in occupied:
            continue

        resp = page.request.post(
            f"{BASE_URL}/api/play",
            data=_json.dumps({"vertex": vertex}),
            headers=_headers,
        )
        if not resp.ok:
            continue  # illegal move — try next candidate

        data = resp.json()
        game = data.get("game", {})
        for move in game.get("move_history", []):
            occupied.add(move["vertex"])

        rounds += 1
        if game.get("game_over"):
            break

    assert rounds >= 10, f"Game ended after only {rounds} rounds"

    status = page.request.get(f"{BASE_URL}/api/status").json()
    total_moves = len(status["game"]["move_history"])
    assert total_moves >= 20, f"Expected >= 20 total moves, got {total_moves}"


def test_api_status_endpoint(page):
    import json
    resp = page.request.get(f"{BASE_URL}/api/status")
    assert resp.ok
    data = resp.json()
    assert "katago_running" in data
    assert "game" in data
