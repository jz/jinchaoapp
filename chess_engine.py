"""
Chinese Chess (象棋) engine.

Board: 10 rows × 9 cols.
  Row 0–4: Black's side (top).
  Row 5–9: Red's side (bottom).

Piece codes  (positive = Red, negative = Black):
  ±1 Chariot  ±2 Horse  ±3 Elephant  ±4 Advisor
  ±5 General  ±6 Cannon  ±7 Soldier
"""
import time

CHARIOT, HORSE, ELEPHANT, ADVISOR, GENERAL, CANNON, SOLDIER = 1, 2, 3, 4, 5, 6, 7

PIECE_CHARS = {
    1: '俥', -1: '車',
    2: '傌', -2: '馬',
    3: '相', -3: '象',
    4: '仕', -4: '士',
    5: '帅', -5: '将',
    6: '炮', -6: '砲',
    7: '兵', -7: '卒',
}

PIECE_VALUES = {
    CHARIOT: 1000, HORSE: 400, ELEPHANT: 200,
    ADVISOR: 200,  GENERAL: 10000, CANNON: 450, SOLDIER: 100,
}

INITIAL_BOARD = [
    [-1, -2, -3, -4, -5, -4, -3, -2, -1],
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],
    [ 0, -6,  0,  0,  0,  0,  0, -6,  0],
    [-7,  0, -7,  0, -7,  0, -7,  0, -7],
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],
    [ 7,  0,  7,  0,  7,  0,  7,  0,  7],
    [ 0,  6,  0,  0,  0,  0,  0,  6,  0],
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],
    [ 1,  2,  3,  4,  5,  4,  3,  2,  1],
]

# Horse: (leg_dr, leg_dc, final_dr, final_dc)
_HORSE_DELTAS = [
    (-1, 0, -2, -1), (-1, 0, -2, +1),
    (+1, 0, +2, -1), (+1, 0, +2, +1),
    ( 0,-1, -1, -2), ( 0,-1, +1, -2),
    ( 0,+1, -1, +2), ( 0,+1, +1, +2),
]


def initial_board():
    return [row[:] for row in INITIAL_BOARD]


# ── FEN parser ─────────────────────────────────────────────────────────────

_FEN_TO_P = {
    'R': 1,  'r': -1,
    'N': 2,  'n': -2,
    'B': 3,  'b': -3,
    'A': 4,  'a': -4,
    'K': 5,  'k': -5,
    'C': 6,  'c': -6,
    'P': 7,  'p': -7,
}

INITIAL_FEN = 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1'


def fen_to_board(fen: str):
    """
    Parse a Xiangqi FEN string.
    Returns (board, red_turn) where board is a 10×9 list.
    Raises ValueError on invalid input.
    """
    parts = fen.strip().split()
    if not parts:
        raise ValueError("空 FEN 字符串")

    rows = parts[0].split('/')
    if len(rows) != 10:
        raise ValueError(f"FEN 需要 10 行，实际得到 {len(rows)} 行")

    board = []
    for r, row_str in enumerate(rows):
        row = []
        for ch in row_str:
            if ch.isdigit():
                row.extend([0] * int(ch))
            elif ch in _FEN_TO_P:
                row.append(_FEN_TO_P[ch])
            else:
                raise ValueError(f"未知 FEN 字符：'{ch}'")
        if len(row) != 9:
            raise ValueError(f"第 {r+1} 行有 {len(row)} 格，应为 9 格")
        board.append(row)

    # Validate: exactly one general per side
    red_kings   = sum(1 for r in board for p in r if p ==  GENERAL)
    black_kings = sum(1 for r in board for p in r if p == -GENERAL)
    if red_kings != 1:
        raise ValueError(f"红方应有 1 个帅，实际 {red_kings} 个")
    if black_kings != 1:
        raise ValueError(f"黑方应有 1 个将，实际 {black_kings} 个")

    side = parts[1].lower() if len(parts) > 1 else 'w'
    if side not in ('w', 'b'):
        raise ValueError(f"行棋方应为 'w' 或 'b'，得到 '{side}'")
    red_turn = (side == 'w')
    return board, red_turn


def _ok(r, c):
    return 0 <= r < 10 and 0 <= c < 9


def _palace(r, c, red):
    return (7 <= r <= 9 if red else 0 <= r <= 2) and 3 <= c <= 5


def _same(a, b):
    return (a > 0 and b > 0) or (a < 0 and b < 0)


# --------------------------------------------------------------------------- #
# Pseudo-legal move generation
# --------------------------------------------------------------------------- #

def pseudo_moves(board, r, c):
    p = board[r][c]
    if not p:
        return []
    t, red = abs(p), p > 0
    out = []

    if t == CHARIOT:
        for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
            nr, nc = r+dr, c+dc
            while _ok(nr, nc):
                tgt = board[nr][nc]
                if tgt == 0:
                    out.append((nr, nc))
                else:
                    if not _same(p, tgt):
                        out.append((nr, nc))
                    break
                nr += dr; nc += dc

    elif t == HORSE:
        for ld, le, fd, fe in _HORSE_DELTAS:
            lr, lc = r+ld, c+le
            if not _ok(lr, lc) or board[lr][lc]:
                continue
            nr, nc = r+fd, c+fe
            if _ok(nr, nc) and not _same(p, board[nr][nc]):
                out.append((nr, nc))

    elif t == ELEPHANT:
        for dr, dc in ((-2,-2),(-2,2),(2,-2),(2,2)):
            nr, nc = r+dr, c+dc
            if not _ok(nr, nc):
                continue
            if red and nr < 5:      # cannot cross river
                continue
            if not red and nr > 4:
                continue
            if board[r+dr//2][c+dc//2]:  # elephant eye blocked
                continue
            if not _same(p, board[nr][nc]):
                out.append((nr, nc))

    elif t == ADVISOR:
        for dr, dc in ((-1,-1),(-1,1),(1,-1),(1,1)):
            nr, nc = r+dr, c+dc
            if _palace(nr, nc, red) and not _same(p, board[nr][nc]):
                out.append((nr, nc))

    elif t == GENERAL:
        for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
            nr, nc = r+dr, c+dc
            if _palace(nr, nc, red) and not _same(p, board[nr][nc]):
                out.append((nr, nc))

    elif t == CANNON:
        for dr, dc in ((0,1),(0,-1),(1,0),(-1,0)):
            nr, nc = r+dr, c+dc
            # Slide to empty squares (non-capture)
            while _ok(nr, nc) and not board[nr][nc]:
                out.append((nr, nc))
                nr += dr; nc += dc
            if not _ok(nr, nc):
                continue
            # Jump over exactly one piece to capture
            nr += dr; nc += dc
            while _ok(nr, nc):
                if board[nr][nc]:
                    if not _same(p, board[nr][nc]):
                        out.append((nr, nc))
                    break
                nr += dr; nc += dc

    elif t == SOLDIER:
        if red:
            fwd = [(r-1, c)]
            if r <= 4:  # crossed river
                fwd += [(r, c-1), (r, c+1)]
        else:
            fwd = [(r+1, c)]
            if r >= 5:  # crossed river
                fwd += [(r, c-1), (r, c+1)]
        for nr, nc in fwd:
            if _ok(nr, nc) and not _same(p, board[nr][nc]):
                out.append((nr, nc))

    return out


# --------------------------------------------------------------------------- #
# Check detection
# --------------------------------------------------------------------------- #

def _find_general(board, red):
    target = GENERAL if red else -GENERAL
    for r in range(10):
        for c in range(9):
            if board[r][c] == target:
                return r, c
    return None, None


def _generals_facing(board):
    rr, rc = _find_general(board, True)
    br, bc = _find_general(board, False)
    if rr is None or br is None or rc != bc:
        return False
    for r in range(min(rr, br)+1, max(rr, br)):
        if board[r][rc]:
            return False
    return True


def in_check(board, red):
    gr, gc = _find_general(board, red)
    if gr is None:
        return True
    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if not p or (red and p > 0) or (not red and p < 0):
                continue
            if (gr, gc) in pseudo_moves(board, r, c):
                return True
    return _generals_facing(board)


# --------------------------------------------------------------------------- #
# Legal moves
# --------------------------------------------------------------------------- #

def apply_move(board, fr, fc, tr, tc):
    b = [row[:] for row in board]
    b[tr][tc] = b[fr][fc]
    b[fr][fc] = 0
    return b


def legal_moves(board, red):
    out = []
    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if not p or (red and p < 0) or (not red and p > 0):
                continue
            for tr, tc in pseudo_moves(board, r, c):
                nb = apply_move(board, r, c, tr, tc)
                if not in_check(nb, red):
                    out.append(((r, c), (tr, tc)))
    return out


def legal_moves_from(board, r, c):
    """Legal destinations for the piece at (r, c)."""
    p = board[r][c]
    if not p:
        return []
    red = p > 0
    return [
        (tr, tc) for tr, tc in pseudo_moves(board, r, c)
        if not in_check(apply_move(board, r, c, tr, tc), red)
    ]


# --------------------------------------------------------------------------- #
# Evaluation & AI
# --------------------------------------------------------------------------- #

# Positional tables – index 0 = piece's own back row (high row for red, low for black)
_T_CHARIOT = [
    [14,14,12,18,16,18,12,14,14],
    [16,20,18,24,26,24,18,20,16],
    [12,12,12,18,15,18,12,12,12],
    [12,18,16,22,22,22,16,18,12],
    [12,14,12,18,18,18,12,14,12],
    [12,16,14,20,20,20,14,16,12],
    [ 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [-2, 0, 4,10,-2,10, 4, 0,-2],
    [ 8, 4, 8,16, 8,16, 8, 4, 8],
    [ 4, 8, 8,16,12,16, 8, 8, 4],
]
_T_HORSE = [
    [ 4, 8,16,12, 4,12,16, 8, 4],
    [ 4,10,28,16, 8,16,28,10, 4],
    [12,14,16,20,18,20,16,14,12],
    [ 8,24,18,24,20,24,18,24, 8],
    [ 6,16,14,18,16,18,14,16, 6],
    [ 4,12,16,14,12,14,16,12, 4],
    [ 2, 6, 8, 6,10, 6, 8, 6, 2],
    [ 4, 2, 8, 8, 4, 8, 8, 2, 4],
    [ 0, 2, 4, 4,-2, 4, 4, 2, 0],
    [ 0,-4, 0, 0,-10,0, 0,-4, 0],
]
_T_CANNON = [
    [ 6, 4, 0,-10,-12,-10, 0, 4, 6],
    [ 2, 2, 0, -4,-14, -4, 0, 2, 2],
    [ 2, 6, 4,  0,-10,  0, 4, 6, 2],
    [ 0, 0, 0,  2, -4,  2, 0, 0, 0],
    [ 0, 0, 0,  2,-10,  2, 0, 0, 0],
    [-2, 0, 4,  2, -8,  2, 4, 0,-2],
    [ 0, 0, 0,  4, -4,  4, 0, 0, 0],
    [ 4, 0, 8, 10, 10, 10, 8, 0, 4],
    [ 0, 2, 4,  6,  6,  6, 4, 2, 0],
    [ 0, 0, 2,  6,  6,  6, 2, 0, 0],
]
_T_SOLDIER = [
    [ 0, 0, 0,  0,  0,  0,  0, 0, 0],
    [ 0, 0, 0,  0,  0,  0,  0, 0, 0],
    [ 0, 0, 0,  0,  0,  0,  0, 0, 0],
    [ 0, 0,10, 30, 30, 30, 10, 0, 0],
    [ 0, 0,10, 40, 40, 40, 10, 0, 0],
    [10,20,40, 50, 50, 50, 40,20,10],
    [20,30,50, 60, 60, 60, 50,30,20],
    [40,60,80,100,100,100, 80,60,40],
    [60,80,100,120,120,120,100,80,60],
    [80,100,120,140,140,140,120,100,80],
]
_T_ELEPHANT = [
    [ 0, 0,-2, 0, 0, 0,-2, 0, 0],
    [ 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [-2, 0, 4, 0, 4, 0, 4, 0,-2],
    [ 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [ 0, 0, 4, 0, 6, 0, 4, 0, 0],
    [ 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [ 0, 0, 4, 0, 4, 0, 4, 0, 0],
    [ 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [ 0, 0,-2, 0, 0, 0,-2, 0, 0],
    [ 0, 0, 0, 0, 0, 0, 0, 0, 0],
]
_T_ADVISOR = [
    [0,0,0,2,0,2,0,0,0],
    [0,0,0,0,4,0,0,0,0],
    [0,0,0,2,0,2,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,0],
    [0,0,0,2,0,2,0,0,0],
    [0,0,0,0,4,0,0,0,0],
    [0,0,0,2,0,2,0,0,0],
]
_T_GENERAL = [
    [0,0,0, 0, 0, 0,0,0,0],
    [0,0,0, 0, 0, 0,0,0,0],
    [0,0,0, 0, 0, 0,0,0,0],
    [0,0,0, 0, 0, 0,0,0,0],
    [0,0,0, 0, 0, 0,0,0,0],
    [0,0,0, 0, 0, 0,0,0,0],
    [0,0,0, 0, 0, 0,0,0,0],
    [0,0,0,10,10,10,0,0,0],
    [0,0,0,20,30,20,0,0,0],
    [0,0,0,10,20,10,0,0,0],
]
_TABLES = {
    CHARIOT: _T_CHARIOT, HORSE: _T_HORSE, CANNON: _T_CANNON,
    SOLDIER: _T_SOLDIER, ELEPHANT: _T_ELEPHANT,
    ADVISOR: _T_ADVISOR, GENERAL: _T_GENERAL,
}


def evaluate(board):
    """Static evaluation from Red's perspective (positive → Red ahead)."""
    score = 0
    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if not p:
                continue
            t, red = abs(p), p > 0
            # Table index: 0 = own back row
            ti = (9 - r) if red else r
            val = PIECE_VALUES[t] + _TABLES[t][ti][c]
            score += val if red else -val
    return score


def _order(board, moves):
    """Captures first (by captured value)."""
    def key(mv):
        tgt = board[mv[1][0]][mv[1][1]]
        return -PIECE_VALUES.get(abs(tgt), 0)
    return sorted(moves, key=key)


def _negamax(board, depth, alpha, beta, red, deadline):
    if time.monotonic() > deadline:
        v = evaluate(board)
        return (v if red else -v), None

    if depth == 0:
        v = evaluate(board)
        return (v if red else -v), None

    moves = legal_moves(board, red)
    if not moves:
        return -20000 - depth, None          # no moves = loss

    moves = _order(board, moves)
    best_val = -10**9
    best_move = moves[0]

    for (fr, fc), (tr, tc) in moves:
        nb = apply_move(board, fr, fc, tr, tc)
        val, _ = _negamax(nb, depth-1, -beta, -alpha, not red, deadline)
        val = -val
        if val > best_val:
            best_val = val
            best_move = ((fr, fc), (tr, tc))
        alpha = max(alpha, val)
        if alpha >= beta:
            break

    return best_val, best_move


def get_ai_move(board, red, difficulty='medium'):
    depth  = {'easy': 2, 'medium': 3, 'hard': 4}.get(difficulty, 3)
    budget = {'easy': 3.0, 'medium': 5.0, 'hard': 8.0}.get(difficulty, 5.0)
    deadline = time.monotonic() + budget
    _, move = _negamax(board, depth, -10**9, 10**9, red, deadline)
    return move
