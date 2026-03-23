"""
Web Go game backend — Flask + KataGo GTP
"""
from __future__ import annotations

import os
import re
import json
import logging
import secrets
import urllib.request
import urllib.error
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, session
from dotenv import load_dotenv
from katago_gtp import KataGoGTP, KataGoError
import database as db

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="frontend")
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# Initialize user database
db.init_db()

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
# Auth API
# ------------------------------------------------------------------ #

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    display_name = data.get("display_name", "").strip()

    if not username or len(username) < 2 or len(username) > 20:
        return jsonify({"error": "用户名需要2-20个字符"}), 400
    if not re.match(r"^[\w\u4e00-\u9fff]+$", username):
        return jsonify({"error": "用户名只能包含字母、数字、下划线或中文"}), 400
    if not password or len(password) < 4:
        return jsonify({"error": "密码至少需要4个字符"}), 400

    user = db.create_user(username, password, display_name)
    if not user:
        return jsonify({"error": "用户名已被注册"}), 409

    session["user_id"] = user["id"]
    return jsonify({"status": "ok", "user": user})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "请输入用户名和密码"}), 400

    user = db.authenticate(username, password)
    if not user:
        return jsonify({"error": "用户名或密码错误"}), 401

    session["user_id"] = user["id"]
    return jsonify({"status": "ok", "user": user})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("user_id", None)
    return jsonify({"status": "ok"})


@app.route("/api/me", methods=["GET"])
def api_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None})
    user = db.get_user_by_id(user_id)
    return jsonify({"user": user})


@app.route("/api/auth/config", methods=["GET"])
def api_auth_config():
    """Return public auth configuration (e.g. Google Client ID) to the frontend."""
    return jsonify({"google_client_id": GOOGLE_CLIENT_ID})


@app.route("/api/auth/google", methods=["POST"])
def api_auth_google():
    """Verify a Google ID token and log in (or register) the user."""
    if not GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google 登录未配置"}), 501

    data = request.get_json(silent=True) or {}
    credential = data.get("credential", "")
    if not credential:
        return jsonify({"error": "缺少 credential"}), 400

    # Verify the ID token via Google's tokeninfo endpoint
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_info = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        logger.warning("Google token verification failed: %s", e)
        return jsonify({"error": "Google 登录验证失败"}), 401

    # Validate audience matches our client ID
    if token_info.get("aud") != GOOGLE_CLIENT_ID:
        return jsonify({"error": "Token 无效"}), 401

    google_id = token_info.get("sub")
    email = token_info.get("email", "")
    name = token_info.get("name", "")

    if not google_id:
        return jsonify({"error": "Token 无效"}), 401

    user = db.find_or_create_google_user(google_id, email, name)
    session["user_id"] = user["id"]
    return jsonify({"status": "ok", "user": user})


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
    board_size  = int(data.get("board_size", 19))
    human_color = data.get("human_color", "black").lower()
    komi        = float(data.get("komi", 7.5))
    difficulty  = data.get("difficulty", DEFAULT_DIFFICULTY).lower()
    mode        = data.get("mode", "vs_ai")  # "vs_ai" | "vs_human"

    if board_size not in (9, 13, 19):
        return jsonify({"error": "board_size must be 9, 13, or 19"}), 400
    if human_color not in ("black", "white"):
        return jsonify({"error": "human_color must be 'black' or 'white'"}), 400
    if mode not in ("vs_ai", "vs_human"):
        mode = "vs_ai"
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
        "running":            True,
        "board_size":         board_size,
        "komi":               komi,
        "human_color":        human_color,
        "ai_color":           ai_color,
        "mode":               mode,
        "turn":               "black",
        "move_history":       [],
        "captures":           {"black": 0, "white": 0},
        "game_over":          False,
        "result":             None,
        "consecutive_passes": 0,
        "difficulty":         difficulty,
    })

    response = {"status": "ok", "game": game_state}

    # vs_ai: if AI plays black, let it move first
    if mode == "vs_ai" and ai_color == "black":
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

    mode        = game_state.get("mode", "vs_ai")
    human_color = game_state["human_color"]

    # In vs_ai mode the turn must belong to the human player.
    # In vs_human mode either player may play on their turn.
    color_to_play = game_state["turn"] if mode == "vs_human" else human_color
    if mode == "vs_ai" and game_state["turn"] != human_color:
        return jsonify({"error": "Not your turn"}), 400

    try:
        ok = katago.play(color_to_play, vertex)
    except KataGoError as e:
        return jsonify({"error": str(e)}), 500

    if not ok:
        return jsonify({"error": "Illegal move"}), 400

    game_state["move_history"].append({"color": color_to_play, "vertex": vertex})
    if vertex.upper() == "PASS":
        game_state["consecutive_passes"] += 1
    else:
        game_state["consecutive_passes"] = 0

    response: dict = {"status": "ok", "move": vertex, "game": game_state}

    # Check double-pass (game over by agreement)
    if game_state["consecutive_passes"] >= 2:
        game_state["turn"] = "black"   # reset for display
        return _handle_game_over(response)

    if mode == "vs_human":
        # Flip turn to the other player; no AI response needed.
        game_state["turn"] = "white" if color_to_play == "black" else "black"
        try:
            response["board_stones"] = katago.get_board_stones()
        except Exception:
            pass
        response["game"] = game_state
        return jsonify(response)

    # vs_ai: AI responds
    game_state["turn"] = game_state["ai_color"]
    ai_result = _ai_move()
    if ai_result:
        response["ai_move"] = ai_result
        if ai_result.get("resign") or game_state.get("game_over"):
            return _handle_game_over(response)

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
        score        = katago.final_score()
        dead         = katago.final_status_list("dead")
        board_stones = katago.get_board_stones()
    except KataGoError as e:
        return jsonify({"error": str(e)}), 500

    # KataGo doesn't support black_territory/white_territory in final_status_list.
    # Compute territory by flood-fill: remove dead stones, then find empty regions
    # surrounded by only one color.
    dead_set    = set(v.upper() for v in dead)
    alive_black = [v for v in board_stones["black"] if v.upper() not in dead_set]
    alive_white = [v for v in board_stones["white"] if v.upper() not in dead_set]
    b_territory, w_territory = _compute_territory(
        game_state["board_size"], alive_black, alive_white
    )

    game_state["game_over"] = True
    game_state["running"]   = False
    game_state["result"]    = score
    _record_game_result(score)

    return jsonify({
        "status":       "ok",
        "result":       score,
        "dead_stones":  dead,
        "territory":    {"black": b_territory, "white": w_territory},
        "board_stones": board_stones,
        "game":         game_state,
    })


def _compute_territory(board_size: int, alive_black: list, alive_white: list):
    """
    Flood-fill territory counting.
    Empty intersections (including dead-stone positions) surrounded only by
    one color's alive stones are assigned to that color's territory.
    Returns (black_territory_vertices, white_territory_vertices).
    """
    GTP_COLS = "ABCDEFGHJKLMNOPQRST"

    def v2rc(v):
        return board_size - int(v[1:]), GTP_COLS.index(v[0].upper())

    def rc2v(r, c):
        return GTP_COLS[c] + str(board_size - r)

    grid = [["." for _ in range(board_size)] for _ in range(board_size)]
    for v in alive_black:
        r, c = v2rc(v); grid[r][c] = "B"
    for v in alive_white:
        r, c = v2rc(v); grid[r][c] = "W"

    visited = [[False] * board_size for _ in range(board_size)]
    b_territory, w_territory = [], []

    for sr in range(board_size):
        for sc in range(board_size):
            if visited[sr][sc] or grid[sr][sc] != ".":
                continue
            region, borders, queue = [], set(), [(sr, sc)]
            visited[sr][sc] = True
            while queue:
                r, c = queue.pop(0)
                region.append((r, c))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < board_size and 0 <= nc < board_size:
                        if not visited[nr][nc] and grid[nr][nc] == ".":
                            visited[nr][nc] = True
                            queue.append((nr, nc))
                        elif grid[nr][nc] in ("B", "W"):
                            borders.add(grid[nr][nc])
            if borders == {"B"}:
                b_territory.extend(rc2v(r, c) for r, c in region)
            elif borders == {"W"}:
                w_territory.extend(rc2v(r, c) for r, c in region)
            # else: dame (neutral) — not assigned

    return b_territory, w_territory


@app.route("/api/undo", methods=["POST"])
def api_undo():
    """Undo the last move(s).
    vs_ai:    undo 2 half-moves (human + AI response).
    vs_human: undo 1 half-move (the last stone played).
    """
    global game_state
    if not game_state["running"]:
        return jsonify({"error": "No game in progress"}), 400

    mode    = game_state.get("mode", "vs_ai")
    n_undo  = 1 if mode == "vs_human" else 2
    history = game_state["move_history"]
    if len(history) < n_undo:
        return jsonify({"error": "Nothing to undo"}), 400

    # Record the color of the move about to be undone BEFORE popping
    undone_color = history[-1]["color"] if history else "black"

    try:
        for _ in range(n_undo):
            ok = katago.undo()
            if not ok:
                return jsonify({"error": "Undo failed"}), 500
            game_state["move_history"].pop()
    except KataGoError as e:
        return jsonify({"error": str(e)}), 500

    if mode == "vs_human":
        game_state["turn"] = undone_color   # let that player redo their move
    else:
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
    _record_game_result(game_state["result"])
    return jsonify({"status": "ok", "result": game_state["result"], "game": game_state})


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _gtp_to_sgf_coord(vertex: str, n: int) -> str:
    """Convert a GTP vertex (e.g. 'Q16') to a two-char SGF coordinate (e.g. 'pd').
    Returns '' for PASS."""
    v = vertex.strip().upper()
    if v in ("PASS", ""):
        return ""
    col_letter = v[0]
    if col_letter not in _GTP_COLS:
        return ""
    col = _GTP_COLS.index(col_letter)          # 0 = left
    row = n - int(v[1:])                        # 0 = top
    if col < 0 or col >= n or row < 0 or row >= n:
        return ""
    return chr(ord("a") + col) + chr(ord("a") + row)


def _build_sgf(gs: dict, username: str) -> str:
    """Generate an SGF string from a completed game_state."""
    n = gs.get("board_size", 19)
    komi = gs.get("komi", 7.5)
    result = gs.get("result") or "?"
    human_color = gs.get("human_color", "black")
    black_name = username if human_color == "black" else "KataGo"
    white_name = username if human_color == "white" else "KataGo"
    moves = []
    for m in gs.get("move_history", []):
        color = "B" if m["color"] == "black" else "W"
        coord = _gtp_to_sgf_coord(m["vertex"], n)
        moves.append(f";{color}[{coord}]")
    moves_str = "".join(moves)
    return (
        f"(;FF[4]GM[1]SZ[{n}]"
        f"PB[{black_name}]PW[{white_name}]"
        f"KM[{komi}]RE[{result}]"
        f"{moves_str})"
    )


def _record_game_result(result: str) -> None:
    """Update stats and save the game for the logged-in user."""
    user_id = session.get("user_id")
    if not user_id or game_state.get("mode") != "vs_ai":
        return
    human_color = game_state.get("human_color", "black")  # "black" or "white"
    winner_color = result[0].upper() if result else ""     # "B" or "W"
    human_wins = (human_color == "black" and winner_color == "B") or \
                 (human_color == "white" and winner_color == "W")
    db.update_stats(user_id, won=human_wins)
    user = db.get_user_by_id(user_id)
    username = user["username"] if user else "player"
    sgf = _build_sgf(game_state, username)
    db.save_game(user_id, game_state.get("board_size", 19), human_color, result, sgf)


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
        _record_game_result(game_state["result"])
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
# Classic game replay
# ------------------------------------------------------------------ #

SGF_DIR = Path(__file__).parent / "sgf"
_GTP_COLS = "ABCDEFGHJKLMNOPQRST"


def _sgf_coord_to_gtp(xy: str, n: int) -> str:
    """Convert a two-char SGF coordinate (e.g. 'pd') to a GTP vertex (e.g. 'Q16')."""
    if not xy or len(xy) < 2:
        return "PASS"
    xy = xy.strip().lower()
    if xy in ("tt", ""):
        return "PASS"
    c = ord(xy[0]) - ord("a")   # col: 0=left
    r = ord(xy[1]) - ord("a")   # row: 0=top
    if c < 0 or c >= n or r < 0 or r >= n:
        return "PASS"
    return f"{_GTP_COLS[c]}{n - r}"


def _parse_sgf(text: str) -> dict:
    """Recursive descent SGF parser — follows the main line (first child at each node).
    Handles both flat SGF (all moves at depth 1) and CGoban-style commented SGF
    where the main game continues inside nested (;...) branches.
    """
    pos = [0]
    sz = len(text)

    def skip() -> None:
        while pos[0] < sz and text[pos[0]].isspace():
            pos[0] += 1

    def read_value() -> str:
        """Read a [...] property value. pos[0] points at '['. Returns the inner string."""
        pos[0] += 1  # skip '['
        chars: list[str] = []
        while pos[0] < sz and text[pos[0]] != "]":
            if text[pos[0]] == "\\" and pos[0] + 1 < sz:
                pos[0] += 1
            chars.append(text[pos[0]])
            pos[0] += 1
        if pos[0] < sz:
            pos[0] += 1  # skip ']'
        return "".join(chars)

    def read_node() -> dict:
        """Parse a ;node. pos[0] points at ';'. Returns {KEY: [val, ...]} dict."""
        pos[0] += 1  # skip ';'
        props: dict = {}
        skip()
        while pos[0] < sz and text[pos[0]] not in (";", "(", ")"):
            skip()
            if pos[0] >= sz or text[pos[0]] in (";", "(", ")"):
                break
            key_start = pos[0]
            while pos[0] < sz and text[pos[0]].isupper():
                pos[0] += 1
            key = text[key_start:pos[0]]
            if not key:
                pos[0] += 1
                continue
            vals: list[str] = []
            skip()
            while pos[0] < sz and text[pos[0]] == "[":
                vals.append(read_value())
                skip()
            if vals:
                props[key] = vals
        return props

    def skip_tree() -> None:
        """Skip a complete (...) subtree. pos[0] must point at '('."""
        pos[0] += 1  # skip '('
        depth = 1
        while pos[0] < sz and depth > 0:
            ch = text[pos[0]]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "[":
                pos[0] += 1
                while pos[0] < sz and text[pos[0]] != "]":
                    if text[pos[0]] == "\\":
                        pos[0] += 1
                    pos[0] += 1
            pos[0] += 1

    def read_tree() -> list:
        """Parse a (game_tree). pos[0] must point at '('.
        Always follows the FIRST child branch (main line); skips subsequent children.
        Returns flat list of node-dicts for the main line."""
        pos[0] += 1  # skip '('
        nodes: list[dict] = []
        skip()
        while pos[0] < sz and text[pos[0]] != ")":
            ch = text[pos[0]]
            if ch == ";":
                nodes.append(read_node())
                skip()
            elif ch == "(":
                # First child = main-line continuation
                nodes.extend(read_tree())
                skip()
                # Skip all remaining siblings (variations)
                while pos[0] < sz and text[pos[0]] == "(":
                    skip_tree()
                    skip()
                break  # sequence is finished after children
            else:
                pos[0] += 1
        skip()
        if pos[0] < sz and text[pos[0]] == ")":
            pos[0] += 1
        return nodes

    # ── Entry point ──────────────────────────────────────────────────
    skip()
    if pos[0] >= sz or text[pos[0]] != "(":
        return {"game_info": {}, "moves": []}
    all_nodes = read_tree()
    root = all_nodes[0] if all_nodes else {}

    board_size = 19
    if "SZ" in root:
        try:
            board_size = int(root["SZ"][0].split(":")[0])
        except (ValueError, IndexError):
            pass

    komi = 7.5
    if "KM" in root:
        try:
            komi = float(root["KM"][0])
        except (ValueError, IndexError):
            pass

    game_info = {
        "black":      (root.get("PB") or ["黑方"])[0],
        "white":      (root.get("PW") or ["白方"])[0],
        "black_rank": (root.get("BR") or [""])[0],
        "white_rank": (root.get("WR") or [""])[0],
        "result":     (root.get("RE") or [""])[0],
        "event":      (root.get("EV") or [""])[0],
        "date":       (root.get("DT") or [""])[0],
        "komi":       komi,
        "board_size": board_size,
    }

    moves = []
    for node in all_nodes[1:]:  # skip root
        color = vertex = None
        comment = ""
        if "B" in node:
            color, vertex = "black", _sgf_coord_to_gtp(node["B"][0], board_size)
        elif "W" in node:
            color, vertex = "white", _sgf_coord_to_gtp(node["W"][0], board_size)
        if "C" in node:
            comment = node["C"][0].strip()
        if color:
            moves.append({"color": color, "vertex": vertex, "comment": comment})

    return {"game_info": game_info, "moves": moves}


@app.route("/api/games", methods=["GET"])
def api_list_games():
    """List available classic games from sgf/ directory."""
    games = []
    if not SGF_DIR.exists():
        return jsonify({"status": "ok", "games": []})
    for sgf_path in sorted(SGF_DIR.glob("*.sgf")):
        game_id = sgf_path.stem
        meta_path = sgf_path.with_suffix(".json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["id"] = game_id
                games.append(meta)
                continue
            except Exception:
                pass
        # Fall back to parsing SGF header
        try:
            gi = _parse_sgf(sgf_path.read_text(encoding="utf-8", errors="replace"))["game_info"]
            games.append({
                "id":         game_id,
                "title":      f"{gi['black']} vs {gi['white']}",
                "event":      gi.get("event", ""),
                "date":       gi.get("date", ""),
                "result":     gi.get("result", ""),
                "board_size": gi.get("board_size", 19),
            })
        except Exception:
            games.append({"id": game_id, "title": game_id})
    return jsonify({"status": "ok", "games": games})


@app.route("/api/games/<game_id>", methods=["GET"])
def api_get_game(game_id):
    """Return parsed moves + comments for one classic game."""
    if not re.match(r"^[\w\-]+$", game_id):
        return jsonify({"error": "invalid game id"}), 400
    sgf_path = SGF_DIR / f"{game_id}.sgf"
    if not sgf_path.exists():
        return jsonify({"error": "game not found"}), 404
    try:
        text = sgf_path.read_text(encoding="utf-8", errors="replace")
        data = _parse_sgf(text)
        # Merge JSON metadata if present (for richer titles)
        meta_path = sgf_path.with_suffix(".json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                data["game_info"].update({
                    k: v for k, v in meta.items()
                    if k in ("title", "event", "date", "result", "description")
                })
            except Exception:
                pass
        data["id"] = game_id
        return jsonify({"status": "ok", "game": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------------ #
# User game history
# ------------------------------------------------------------------ #

@app.route("/api/my_games", methods=["GET"])
def api_my_games():
    """List the logged-in user's saved games (newest first)."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "not logged in"}), 401
    games = db.list_user_games(user_id)
    return jsonify({"status": "ok", "games": games})


@app.route("/api/my_games/<int:game_id>", methods=["GET"])
def api_get_my_game(game_id: int):
    """Return the SGF and parsed moves for one of the user's saved games."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "not logged in"}), 401
    record = db.get_user_game(game_id, user_id)
    if not record:
        return jsonify({"error": "game not found"}), 404
    try:
        parsed = _parse_sgf(record["sgf_text"])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    parsed["id"] = game_id
    parsed["played_at"] = record["played_at"]
    return jsonify({"status": "ok", "game": parsed})


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
