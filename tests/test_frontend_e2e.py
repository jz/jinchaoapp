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


def test_api_status_endpoint(page):
    import json
    resp = page.request.get(f"{BASE_URL}/api/status")
    assert resp.ok
    data = resp.json()
    assert "katago_running" in data
    assert "game" in data
