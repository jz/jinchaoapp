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

# Single global KataGo instance (one game at a time on a 1GB VPS)
katago: KataGoGTP | None = None
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
        "game": game_state,
    })


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    global katago, game_state

    data = request.get_json(silent=True) or {}
    board_size = int(data.get("board_size", 19))
    human_color = data.get("human_color", "black").lower()
    komi = float(data.get("komi", 7.5))

    if board_size not in (9, 13, 19):
        return jsonify({"error": "board_size must be 9, 13, or 19"}), 400
    if human_color not in ("black", "white"):
        return jsonify({"error": "human_color must be 'black' or 'white'"}), 400

    ai_color = "white" if human_color == "black" else "black"

    # Start or reuse KataGo
    try:
        if katago is None:
            katago = KataGoGTP()
            katago.start()
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

    return jsonify(response)


@app.route("/api/pass", methods=["POST"])
def api_pass():
    """Human passes."""
    return api_play_vertex("PASS")


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
    app.run(host="0.0.0.0", port=port, debug=debug)
