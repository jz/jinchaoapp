"""
Pikafish UCI interface for Chinese Chess (象棋) AI.
https://github.com/official-pikafish/Pikafish

Board coordinate mapping
─────────────────────────
Internal (row, col):  row 0–9 top→bottom,  col 0–8 left→right
Pikafish UCI:         file 'a'–'i' (=col),  rank 0–9 where rank = 9 − row

Examples
  red  general start (row 9, col 4) → e0
  black general start (row 0, col 4) → e9
  red soldier advance (6,4)→(5,4) → e3e4
"""

import os
import subprocess
import threading
import time
import logging

logger = logging.getLogger(__name__)

# ── Piece → FEN character ──────────────────────────────────────────────────
_P2F = {
     1: 'R', -1: 'r',
     2: 'N', -2: 'n',
     3: 'B', -3: 'b',
     4: 'A', -4: 'a',
     5: 'K', -5: 'k',
     6: 'C', -6: 'c',
     7: 'P', -7: 'p',
}

MOVETIME_MS = {'easy': 500, 'medium': 1500, 'hard': 3000}


# ── Coordinate helpers ─────────────────────────────────────────────────────

def board_to_fen(board, red_turn: bool) -> str:
    """Convert internal board + side-to-move to Pikafish FEN."""
    rows = []
    for r in range(10):          # row 0 (black back) → row 9 (red back)
        empty = 0
        s = ''
        for c in range(9):
            p = board[r][c]
            if p == 0:
                empty += 1
            else:
                if empty:
                    s += str(empty)
                    empty = 0
                s += _P2F[p]
        if empty:
            s += str(empty)
        rows.append(s)
    side = 'w' if red_turn else 'b'
    return f"{'/'.join(rows)} {side} - - 0 1"


def move_to_uci(fr: int, fc: int, tr: int, tc: int) -> str:
    return f"{chr(ord('a') + fc)}{9 - fr}{chr(ord('a') + tc)}{9 - tr}"


def uci_to_move(s: str) -> tuple:
    """'e3e4' → (fr, fc, tr, tc)."""
    fc = ord(s[0]) - ord('a')
    fr = 9 - int(s[1])
    tc = ord(s[2]) - ord('a')
    tr = 9 - int(s[3])
    return fr, fc, tr, tc


# ── Engine ─────────────────────────────────────────────────────────────────

class PikafishError(Exception):
    pass


class PikafishUCI:
    DEFAULT_BIN   = './pikafish_bin/pikafish'
    DEFAULT_MODEL = './pikafish_bin/pikafish.nnue'

    def __init__(self):
        self.binary = os.environ.get('PIKAFISH_PATH',  self.DEFAULT_BIN)
        self.model  = os.environ.get('PIKAFISH_MODEL', self.DEFAULT_MODEL)
        self._proc  = None
        self._lock  = threading.Lock()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        return os.path.isfile(self.binary) and os.access(self.binary, os.X_OK)

    def start(self):
        if not self.is_available():
            raise PikafishError(f"Pikafish binary not found: {self.binary}")

        self._proc = subprocess.Popen(
            [self.binary],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

        self._send('uci')
        self._wait('uciok', timeout=10)

        # Low-memory settings for 1 GB VPS
        self._send('setoption name Threads value 1')
        self._send('setoption name Hash value 32')
        if os.path.isfile(self.model):
            self._send(f'setoption name EvalFile value {os.path.abspath(self.model)}')
            logger.info('Pikafish: using model %s', self.model)

        self._send('isready')
        self._wait('readyok', timeout=30)
        logger.info('Pikafish ready (pid=%d, binary=%s)', self._proc.pid, self.binary)

    def stop(self):
        if self._proc:
            try:
                self._send('quit')
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
            self._proc = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def new_game(self):
        """Signal a new game (clears hash table)."""
        self._send('ucinewgame')

    # ── move generation ────────────────────────────────────────────────────

    def get_move(self, board, red_turn: bool, difficulty: str = 'medium'):
        """
        Return (fr, fc, tr, tc) for the best move, or None if no move found.
        Blocks until the engine responds (up to movetime + 10 s).
        """
        movetime = MOVETIME_MS.get(difficulty, 1500)
        with self._lock:
            if not self.is_running():
                raise PikafishError('Pikafish is not running')
            fen = board_to_fen(board, red_turn)
            self._send(f'position fen {fen}')
            self._send(f'go movetime {movetime}')
            line = self._wait('bestmove', timeout=movetime / 1000 + 10)

        parts = line.split()
        if len(parts) >= 2 and parts[0] == 'bestmove':
            uci = parts[1]
            if uci != '(none)':
                return uci_to_move(uci)
        return None

    # ── internals ──────────────────────────────────────────────────────────

    def _send(self, cmd: str):
        self._proc.stdin.write(cmd + '\n')
        self._proc.stdin.flush()

    def _wait(self, token: str, timeout: float = 10.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self._proc.stdout.readline().rstrip('\n')
            if token in line:
                return line
        raise PikafishError(f"Timeout waiting for '{token}' from Pikafish")
