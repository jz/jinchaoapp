"""
Web Go game backend — Flask + KataGo GTP
"""

import os
import logging
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from katago_gtp import KataGoGTP, KataGoError

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="frontend")

# Difficulty presets: (humanSLProfile, maxVisits)
# Visits are kept low because the b18c384 model is large and CPU inference
# is slow (~200-500 ms/visit on a 1 GB VPS). Rule of thumb: 1 visit ≈ 1 move
# of look-ahead at this model size, so even 5 visits plays reasonably.
DIFFICULTY = {
    "beginner": ("rank_9k",   5),   # ~1-3 s
    "easy":     ("rank_5k",  15),   # ~3-7 s
    "medium":   ("rank_1d",  50),   # ~10-25 s
    "hard":     ("rank_9d", 150),   # ~30-75 s
}
DEFAULT_DIFFICULTY = "easy"

# Single global KataGo instance (one game at a time on a 1GB VPS)
katago: KataGoGTP | None = None
current_profile: str | None = None
game_state: dict = {
    "running": False,
    "board_size": 19,
    "human_color": "black",   # human plays black by default
    "ai_color": "white",
    "turn": "black",          # whose turn: 'black' or 'white'
    "move_history": [],       # [(color, vertex), ...]
    "captures": {"black": 0, "white": 0},
    "game_over": False,
    "result": None,
    "consecutive_passes": 0,
}


# ------------------------------------------------------------------ #
# Static files
# ------------------------------------------------------------------ #

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("frontend", filename)


# ------------------------------------------------------------------ #
# API
# ------------------------------------------------------------------ #

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "katago_running": katago is not None and katago.is_running(),
        "katago_stderr": katago.get_stderr_tail() if katago else "",
        "game": game_state,
    })


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    global katago, game_state, current_profile

    data = request.get_json(silent=True) or {}
    board_size = int(data.get("board_size", 19))
    human_color = data.get("human_color", "black").lower()
    komi = float(data.get("komi", 7.5))
    difficulty = data.get("difficulty", DEFAULT_DIFFICULTY).lower()

    if board_size not in (9, 13, 19):
        return jsonify({"error": "board_size must be 9, 13, or 19"}), 400
    if human_color not in ("black", "white"):
        return jsonify({"error": "human_color must be 'black' or 'white'"}), 400
    if difficulty not in DIFFICULTY:
        difficulty = DEFAULT_DIFFICULTY

    profile, visits = DIFFICULTY[difficulty]
    ai_color = "white" if human_color == "black" else "black"

    # (Re)start KataGo if not running or if the difficulty profile changed
    try:
        if katago is None or not katago.is_running() or profile != current_profile:
            if katago is not None:
                katago.stop()
            katago = KataGoGTP(profile_override=profile)
            katago.start()
            current_profile = profile
        katago.set_visits(visits)
        katago.new_game(board_size=board_size, komi=komi)
    except KataGoError as e:
        return jsonify({"error": str(e)}), 500

    game_state.update({
        "running": True,
        "board_size": board_size,
        "komi": komi,
        "human_color": human_color,
        "ai_color": ai_color,
        "turn": "black",
        "move_history": [],
        "captures": {"black": 0, "white": 0},
        "game_over": False,
        "result": None,
        "consecutive_passes": 0,
        "difficulty": difficulty,
    })

    response = {"status": "ok", "game": game_state}

    # If AI plays black, let it move first
    if ai_color == "black":
        ai_result = _ai_move()
        if ai_result:
            response["ai_move"] = ai_result

    return jsonify(response)


@app.route("/api/play", methods=["POST"])
def api_play():
    """Human plays a move."""
    global game_state

    if not game_state["running"]:
        return jsonify({"error": "No game in progress"}), 400
    if game_state["game_over"]:
        return jsonify({"error": "Game is over"}), 400

    data = request.get_json(silent=True) or {}
    vertex = data.get("vertex", "").strip().upper()  # e.g. "D4" or "PASS"
    if not vertex:
        return jsonify({"error": "vertex required"}), 400

    human_color = game_state["human_color"]

    if game_state["turn"] != human_color:
        return jsonify({"error": "Not your turn"}), 400

    # Play human move
    try:
        ok = katago.play(human_color, vertex)
    except KataGoError as e:
        return jsonify({"error": str(e)}), 500

    if not ok:
        return jsonify({"error": "Illegal move"}), 400

    game_state["move_history"].append({"color": human_color, "vertex": vertex})
    if vertex.upper() == "PASS":
        game_state["consecutive_passes"] += 1
    else:
        game_state["consecutive_passes"] = 0

    game_state["turn"] = game_state["ai_color"]

    response: dict = {"status": "ok", "move": vertex, "game": game_state}

    # Check double-pass (game over by agreement)
    if game_state["consecutive_passes"] >= 2:
        return _handle_game_over(response)

    # AI responds
    ai_result = _ai_move()
    if ai_result:
        response["ai_move"] = ai_result
        if ai_result.get("resign") or game_state.get("game_over"):
            return _handle_game_over(response)

    # Always return the authoritative board position so the client can sync
    # captures and any other rule-based stone removals.
    try:
        response["board_stones"] = katago.get_board_stones()
    except Exception:
        pass

    return jsonify(response)


@app.route("/api/pass", methods=["POST"])
def api_pass():
    """Human passes."""
    return api_play_vertex("PASS")


@app.route("/api/score", methods=["POST"])
def api_score():
    """End the game and return final score + dead stones + territory."""
    global game_state
    if not game_state["running"] and not game_state.get("game_over"):
        return jsonify({"error": "No game in progress"}), 400

    try:
        score       = katago.final_score()
        dead        = katago.final_status_list("dead")
        b_territory = katago.final_status_list("black_territory")
        w_territory = katago.final_status_list("white_territory")
        board_stones = katago.get_board_stones()
    except KataGoError as e:
        return jsonify({"error": str(e)}), 500

    game_state["game_over"] = True
    game_state["running"]   = False
    game_state["result"]    = score

    return jsonify({
        "status":      "ok",
        "result":      score,
        "dead_stones": dead,
        "territory":   {"black": b_territory, "white": w_territory},
        "board_stones": board_stones,
        "game":        game_state,
    })


@app.route("/api/undo", methods=["POST"])
def api_undo():
    """Undo the last human move + AI response (2 half-moves)."""
    global game_state
    if not game_state["running"]:
        return jsonify({"error": "No game in progress"}), 400

    history = game_state["move_history"]
    if len(history) < 2:
        return jsonify({"error": "Nothing to undo"}), 400

    try:
        for _ in range(2):
            ok = katago.undo()
            if not ok:
                return jsonify({"error": "Undo failed"}), 500
            game_state["move_history"].pop()
    except KataGoError as e:
        return jsonify({"error": str(e)}), 500

    game_state["turn"] = game_state["human_color"]

    # Recalculate consecutive passes from remaining history
    passes = 0
    for move in reversed(game_state["move_history"]):
        if move["vertex"].upper() == "PASS":
            passes += 1
        else:
            break
    game_state["consecutive_passes"] = passes

    response = {"status": "ok", "game": game_state}
    try:
        response["board_stones"] = katago.get_board_stones()
    except Exception:
        pass
    return jsonify(response)


@app.route("/api/resign", methods=["POST"])
def api_resign():
    """Human resigns."""
    global game_state
    if not game_state["running"]:
        return jsonify({"error": "No game in progress"}), 400

    human_color = game_state["human_color"]
    ai_color = game_state["ai_color"]
    winner = "White" if human_color == "black" else "Black"
    game_state["game_over"] = True
    game_state["running"] = False
    game_state["result"] = f"{winner}+Resign"
    return jsonify({"status": "ok", "result": game_state["result"], "game": game_state})


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def api_play_vertex(vertex):
    """Shared logic for play/pass routes."""
    return app.test_request_context(json={"vertex": vertex}).__enter__() or api_play()


def _ai_move():
    """Ask KataGo for a move and update game state. Returns move info dict."""
    global game_state

    ai_color = game_state["ai_color"]
    try:
        vertex = katago.genmove(ai_color)
    except KataGoError as e:
        logger.error("KataGo genmove error: %s", e)
        return None

    if vertex is None:
        return None

    result = {"color": ai_color, "vertex": vertex}

    if vertex.lower() == "resign":
        result["resign"] = True
        winner = "Black" if ai_color == "white" else "White"
        game_state["game_over"] = True
        game_state["running"] = False
        game_state["result"] = f"{winner}+Resign"
        return result

    game_state["move_history"].append({"color": ai_color, "vertex": vertex})
    if vertex.upper() == "PASS":
        game_state["consecutive_passes"] += 1
    else:
        game_state["consecutive_passes"] = 0

    game_state["turn"] = game_state["human_color"]

    if game_state["consecutive_passes"] >= 2:
        game_state["game_over"] = True
        game_state["running"] = False
        try:
            score = katago.final_score()
            game_state["result"] = score
            result["final_score"] = score
        except Exception:
            pass

    return result


def _handle_game_over(response):
    global game_state
    if not game_state.get("result"):
        try:
            score = katago.final_score()
            game_state["result"] = score
            response["final_score"] = score
        except Exception:
            pass
    game_state["game_over"] = True
    game_state["running"] = False
    response["game"] = game_state
    return jsonify(response)


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    # Start KataGo eagerly so the first game has no cold-start delay.
    # In debug mode the reloader spawns a child process; only start there.
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        try:
            default_profile, _ = DIFFICULTY[DEFAULT_DIFFICULTY]
            katago = KataGoGTP(profile_override=default_profile)
            katago.start()
            current_profile = default_profile
            logger.info("KataGo started successfully.")
        except KataGoError as e:
            logger.error("Could not start KataGo: %s", e)
            katago = None

    app.run(host="0.0.0.0", port=port, debug=debug)
