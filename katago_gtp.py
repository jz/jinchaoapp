"""
KataGo GTP (Go Text Protocol) interface.
Manages a KataGo subprocess and communicates via stdin/stdout.
"""

import subprocess
import threading
import queue
import os
import time
import logging

logger = logging.getLogger(__name__)


class KataGoError(Exception):
    pass


class KataGoGTP:
    def __init__(self, profile_override: str | None = None):
        self.katago_path = os.environ.get("KATAGO_PATH", "./katago_bin/katago")
        self.model_path = os.environ.get("KATAGO_MODEL", "./models/model.bin.gz")
        self.config_path = os.environ.get("KATAGO_CONFIG", "./config/gtp.cfg")
        self.profile_override = profile_override  # e.g. "rank_9k"
        self.process = None
        self.response_queue = queue.Queue()
        self.lock = threading.Lock()
        self.board_size = 19
        self.move_history = []  # list of (color, vertex)

    def start(self):
        """Start the KataGo process."""
        if not os.path.isfile(self.katago_path):
            raise KataGoError(f"KataGo binary not found: {self.katago_path}")
        if not os.path.isfile(self.model_path):
            raise KataGoError(f"Model file not found: {self.model_path}")

        cmd = [
            self.katago_path, "gtp",
            "-model", self.model_path,
            "-config", self.config_path,
        ]
        if self.profile_override:
            cmd += ["-override-config", f"humanSLProfile={self.profile_override}"]
        logger.info("Starting KataGo: %s", " ".join(cmd))
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stderr_lines = []
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        # Wait for KataGo to initialize, checking it doesn't crash
        for i in range(10):
            time.sleep(1)
            if self.process.poll() is not None:
                stderr_output = "\n".join(self._stderr_lines[-20:])
                raise KataGoError(
                    f"KataGo exited with code {self.process.returncode} during startup.\n"
                    f"stderr:\n{stderr_output}"
                )
        logger.info("KataGo started (pid=%d).", self.process.pid)

    def stop(self):
        """Stop the KataGo process."""
        if self.process and self.process.poll() is None:
            try:
                self._send_raw("quit")
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
        self.process = None

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def get_stderr_tail(self, n=20):
        """Return the last n lines of KataGo stderr for debugging."""
        return "\n".join(self._stderr_lines[-n:]) if hasattr(self, '_stderr_lines') else ""

    # ------------------------------------------------------------------ #
    # GTP commands
    # ------------------------------------------------------------------ #

    def set_visits(self, max_visits: int):
        """Dynamically change the search visit count (affects strength & speed)."""
        self._cmd(f"kata-set-param maxVisits {max_visits}")

    def get_board_stones(self) -> dict:
        """
        Return the current board position as two lists of GTP vertices.
        Parses the 'showboard' ASCII output since KataGo doesn't support 'list_stones'.
        Returns {"black": ["D4", ...], "white": ["C3", ...]}
        """
        resp = self._cmd("showboard")
        if resp is None:
            return {"black": [], "white": []}
        text, ok = resp
        if not ok:
            return {"black": [], "white": []}
        return self._parse_showboard(text)

    @staticmethod
    def _parse_showboard(text: str) -> dict:
        """
        Parse KataGo showboard ASCII output to extract stone positions.
        Board lines look like:
          9 . . . . . . . . .
          5 . . . . X1. . . .
          3 . . O2. . . . . .
        Column header looks like:
             A B C D E F G H J
        """
        GTP_COLS = set("ABCDEFGHJKLMNOPQRST")
        lines = text.strip().split("\n")

        # Find header line (contains column letters, only spaces + column letters)
        header_line = None
        header_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and all(c in GTP_COLS or c == " " for c in stripped):
                if "A" in stripped and "B" in stripped:
                    header_line = line
                    header_idx = i
                    break

        if header_line is None:
            return {"black": [], "white": []}

        # Map column letter -> exact character index in the line
        col_positions = {ch: idx for idx, ch in enumerate(header_line) if ch in GTP_COLS}

        black_stones, white_stones = [], []
        for line in lines[header_idx + 1:]:
            stripped = line.strip()
            if not stripped:
                break
            parts = stripped.split()
            if not parts or not parts[0].isdigit():
                break
            row_num = int(parts[0])
            for col_letter, col_pos in col_positions.items():
                if col_pos < len(line):
                    ch = line[col_pos]
                    if ch == "X":
                        black_stones.append(f"{col_letter}{row_num}")
                    elif ch == "O":
                        white_stones.append(f"{col_letter}{row_num}")

        return {"black": black_stones, "white": white_stones}

    def new_game(self, board_size=19, komi=7.5):
        """Reset the board for a new game."""
        self.board_size = board_size
        self.move_history = []
        self._cmd(f"boardsize {board_size}")
        self._cmd("clear_board")
        self._cmd(f"komi {komi}")

    def play(self, color, vertex):
        """
        Play a move. color: 'black'|'white', vertex: 'D4'|'pass'.
        Returns True on success, False on illegal move.
        """
        resp = self._cmd(f"play {color} {vertex}")
        ok = resp is not None and resp[1]
        if ok:
            self.move_history.append((color, vertex))
        return ok

    def genmove(self, color):
        """
        Ask KataGo to generate and play a move.
        Returns the vertex string (e.g. 'D4' or 'pass' or 'resign').
        """
        resp = self._cmd(f"genmove {color}", timeout=60)
        if resp and resp[1]:
            vertex = resp[0].strip()
            if vertex.lower() not in ("resign",):
                self.move_history.append((color, vertex))
            return vertex
        return None

    def undo(self):
        """Undo the last move."""
        resp = self._cmd("undo")
        if resp and resp[1] and self.move_history:
            self.move_history.pop()
        return resp and resp[1]

    def showboard(self):
        """Return the board as ASCII text."""
        resp = self._cmd("showboard")
        return resp[0] if resp else ""

    def final_score(self):
        """Return the final score string, e.g. 'B+3.5'."""
        resp = self._cmd("final_score", timeout=30)
        return resp[0].strip() if resp else ""

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _cmd(self, command, timeout=30):
        """Send a GTP command; return (value, success) or None on error."""
        raw = self._send_raw(command)
        if raw is None:
            return None
        return self._parse(raw)

    def _send_raw(self, command):
        """Write a command line to KataGo stdin and wait for the response."""
        with self.lock:
            if not self.is_running():
                raise KataGoError("KataGo is not running")
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except BrokenPipeError:
                raise KataGoError("KataGo process died")
            try:
                timeout = 60
                return self.response_queue.get(timeout=timeout)
            except queue.Empty:
                raise KataGoError(f"KataGo did not respond to: {command}")

    def _read_stdout(self):
        """Background thread: read KataGo stdout and push responses to queue."""
        buf = []
        for line in self.process.stdout:
            line = line.rstrip("\n")
            if line == "":
                if buf:
                    self.response_queue.put("\n".join(buf))
                    buf = []
            else:
                buf.append(line)
        # Process exited — push whatever is left
        if buf:
            self.response_queue.put("\n".join(buf))

    def _drain_stderr(self):
        """Background thread: consume stderr so the pipe doesn't block."""
        for line in self.process.stderr:
            line = line.rstrip()
            logger.debug("katago stderr: %s", line)
            self._stderr_lines.append(line)
            # Keep only the last 100 lines
            if len(self._stderr_lines) > 100:
                self._stderr_lines = self._stderr_lines[-50:]

    @staticmethod
    def _parse(raw):
        """
        Parse a GTP response.
        Returns (value_str, success_bool).
        """
        if raw.startswith("= "):
            return raw[2:].strip(), True
        if raw.strip() == "=":
            return "", True
        if raw.startswith("? "):
            return raw[2:].strip(), False
        return raw, True
