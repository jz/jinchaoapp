"use strict";

// ================================================================== //
// Go board rendering + game logic (pure vanilla JS, no dependencies)  //
// ================================================================== //

// --- Column labels (GTP uses A-T, skipping I) ---
const COL_LABELS = "ABCDEFGHJKLMNOPQRST";

// --- Board colors ---
const BOARD_BG   = "#dcb76a";
const LINE_COLOR = "#8b6914";
const HOSHI_COLOR = "#8b6914";
const BLACK_STONE = "#111";
const WHITE_STONE = "#f4f4f4";
const LAST_MOVE_DOT = "#e74c3c";
const HOVER_BLACK = "rgba(30,30,30,0.45)";
const HOVER_WHITE = "rgba(220,220,220,0.55)";

// --- State ---
let state = {
  boardSize: 19,
  humanColor: "black",
  aiColor: "white",
  turn: "black",       // whose turn it is
  myTurn: true,        // is it the human's turn?
  gameRunning: false,
  gameOver: false,
  stones: [],          // 2D array [row][col]: null | "black" | "white"
  lastMove: null,      // {row, col} or null
  moveHistory: [],
  hoverCell: null,
};

// --- DOM refs ---
const canvas  = document.getElementById("goboard");
const ctx     = canvas.getContext("2d");
const thinking = document.getElementById("thinking-indicator");

const setupSection  = document.getElementById("setup-section");
const gameSection   = document.getElementById("game-section");
const resultSection = document.getElementById("result-section");

const btnNewGame  = document.getElementById("btn-new-game");
const btnPass     = document.getElementById("btn-pass");
const btnResign   = document.getElementById("btn-resign");
const btnEndGame  = document.getElementById("btn-end-game");
const btnAgain    = document.getElementById("btn-again");

const infoHumanColor = document.getElementById("info-human-color");
const infoTurn       = document.getElementById("info-turn");
const infoCapBlack   = document.getElementById("info-cap-black");
const infoCapWhite   = document.getElementById("info-cap-white");
const infoMoves      = document.getElementById("info-moves");
const resultText     = document.getElementById("result-text");
const moveLog        = document.getElementById("move-log");

// ================================================================== //
// Board geometry
// ================================================================== //

const PADDING_RATIO = 1.8;  // padding in units of cell size
let cellSize = 30;
let padding  = cellSize * PADDING_RATIO;

function computeLayout(n) {
  // Pick cellSize so board fits nicely, max ~600px
  const maxCanvas = Math.min(window.innerWidth - 300, 620);
  cellSize = Math.floor((maxCanvas - 2 * 30) / (n - 1));
  cellSize = Math.max(cellSize, 22);
  padding = Math.round(cellSize * PADDING_RATIO * 0.6);
  const size = padding * 2 + cellSize * (n - 1);
  canvas.width  = size;
  canvas.height = size;
}

function cellToXY(row, col) {
  return {
    x: padding + col * cellSize,
    y: padding + row * cellSize,
  };
}

function xyToCell(x, y) {
  const col = Math.round((x - padding) / cellSize);
  const row = Math.round((y - padding) / cellSize);
  if (row < 0 || col < 0 || row >= state.boardSize || col >= state.boardSize) return null;
  // Only snap if close enough
  const { x: cx, y: cy } = cellToXY(row, col);
  const dist = Math.hypot(x - cx, y - cy);
  if (dist > cellSize * 0.5) return null;
  return { row, col };
}

// ================================================================== //
// Drawing
// ================================================================== //

function draw() {
  const n = state.boardSize;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Background
  ctx.fillStyle = BOARD_BG;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Grid lines
  ctx.strokeStyle = LINE_COLOR;
  ctx.lineWidth = 1;
  for (let i = 0; i < n; i++) {
    // horizontal line: row i, from col 0 to col n-1
    const { x, y }   = cellToXY(i, 0);
    const { x: x2 }  = cellToXY(i, n - 1);
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y); ctx.stroke();
    // vertical line: col i, from row 0 to row n-1
    const { x: xv, y: yv } = cellToXY(0, i);
    const { y: y2 }        = cellToXY(n - 1, i);
    ctx.beginPath(); ctx.moveTo(xv, yv); ctx.lineTo(xv, y2); ctx.stroke();
  }

  // Hoshi (star points)
  drawHoshi(n);

  // Row/col labels
  drawLabels(n);

  // Stones
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      const s = state.stones[r] && state.stones[r][c];
      if (s) drawStone(r, c, s, r === state.lastMove?.row && c === state.lastMove?.col);
    }
  }

  // Hover stone (preview)
  if (state.hoverCell && state.myTurn && state.gameRunning && !state.gameOver) {
    const { row, col } = state.hoverCell;
    if (!state.stones[row][col]) {
      const { x, y } = cellToXY(row, col);
      const r = cellSize * 0.46;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = state.humanColor === "black" ? HOVER_BLACK : HOVER_WHITE;
      ctx.fill();
    }
  }
}

function drawStone(row, col, color, isLast) {
  const { x, y } = cellToXY(row, col);
  const r = cellSize * 0.46;

  // Shadow
  ctx.shadowColor = "rgba(0,0,0,0.4)";
  ctx.shadowBlur = 4;
  ctx.shadowOffsetX = 2;
  ctx.shadowOffsetY = 2;

  const grad = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, r * 0.1, x, y, r);
  if (color === "black") {
    grad.addColorStop(0, "#555");
    grad.addColorStop(1, BLACK_STONE);
  } else {
    grad.addColorStop(0, "#fff");
    grad.addColorStop(1, "#c8c8c8");
  }

  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.shadowColor = "transparent";
  ctx.shadowBlur = 0;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 0;

  // Last move dot
  if (isLast) {
    ctx.beginPath();
    ctx.arc(x, y, r * 0.2, 0, Math.PI * 2);
    ctx.fillStyle = color === "black" ? "#aaa" : LAST_MOVE_DOT;
    ctx.fill();
  }
}

function drawHoshi(n) {
  let hoshi = [];
  if (n === 19) hoshi = [[3,3],[3,9],[3,15],[9,3],[9,9],[9,15],[15,3],[15,9],[15,15]];
  else if (n === 13) hoshi = [[3,3],[3,9],[6,6],[9,3],[9,9]];
  else if (n === 9)  hoshi = [[2,2],[2,6],[4,4],[6,2],[6,6]];

  ctx.fillStyle = HOSHI_COLOR;
  for (const [r, c] of hoshi) {
    const { x, y } = cellToXY(r, c);
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawLabels(n) {
  ctx.fillStyle = "#6b4f1a";
  ctx.font = `${Math.max(10, cellSize * 0.32)}px monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let i = 0; i < n; i++) {
    const colLabel = COL_LABELS[i];
    const rowLabel = String(n - i);
    const { x } = cellToXY(0, i);
    const { y } = cellToXY(i, 0);
    // Column label: top and bottom
    ctx.fillText(colLabel, x, padding * 0.45);
    ctx.fillText(colLabel, x, canvas.height - padding * 0.45);
    // Row label: left and right
    ctx.fillText(rowLabel, padding * 0.45, y);
    ctx.fillText(rowLabel, canvas.width - padding * 0.45, y);
  }
}

// ================================================================== //
// GTP coordinate helpers
// ================================================================== //

function cellToGTP(row, col, n) {
  // GTP: col letter + row number from bottom
  const colLabel = COL_LABELS[col];
  const rowNum   = n - row;
  return colLabel + rowNum;
}

function gtpToCell(vertex, n) {
  if (!vertex || vertex.toLowerCase() === "pass" || vertex.toLowerCase() === "resign") return null;
  const col = COL_LABELS.indexOf(vertex[0].toUpperCase());
  const row = n - parseInt(vertex.slice(1), 10);
  if (col < 0 || row < 0 || row >= n || col >= n) return null;
  return { row, col };
}

// ================================================================== //
// API calls
// ================================================================== //

async function apiPost(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || resp.statusText);
  }
  return resp.json();
}

// ================================================================== //
// Game flow
// ================================================================== //

function initStones(n) {
  state.stones = Array.from({ length: n }, () => Array(n).fill(null));
}

function placeStoneFromGTP(color, vertex) {
  const cell = gtpToCell(vertex, state.boardSize);
  if (cell) {
    state.stones[cell.row][cell.col] = color;
    state.lastMove = cell;
  }
}

async function startNewGame() {
  const boardSize   = parseInt(document.getElementById("board-size").value, 10);
  const humanColor  = document.getElementById("human-color").value;
  const komi        = parseFloat(document.getElementById("komi").value);

  btnNewGame.disabled = true;
  showThinking(true);

  try {
    const data = await apiPost("/api/new_game", { board_size: boardSize, human_color: humanColor, komi });

    state.boardSize   = boardSize;
    state.humanColor  = humanColor;
    state.aiColor     = data.game.ai_color;
    state.turn        = data.game.turn;
    state.myTurn      = (data.game.turn === humanColor);
    state.gameRunning = true;
    state.gameOver    = false;
    state.lastMove    = null;
    state.moveHistory = [];

    initStones(boardSize);
    computeLayout(boardSize);

    // Update UI
    setupSection.classList.add("hidden");
    gameSection.classList.remove("hidden");
    resultSection.classList.add("hidden");
    moveLog.innerHTML = "";

    infoHumanColor.textContent = humanColor === "black" ? "⚫ 黑棋" : "⚪ 白棋";
    updateInfo(data.game);

    // AI may have already moved (if AI plays black)
    if (data.ai_move) {
      applyAIMove(data.ai_move);
    }

    draw();
  } catch (e) {
    showToast("开局失败：" + e.message);
  } finally {
    btnNewGame.disabled = false;
    showThinking(false);
  }
}

async function humanPlay(row, col) {
  if (!state.myTurn || !state.gameRunning || state.gameOver) return;
  if (state.stones[row][col]) return;  // occupied

  const vertex = cellToGTP(row, col, state.boardSize);
  await sendMove(vertex);
}

async function humanPass() {
  if (!state.myTurn || !state.gameRunning || state.gameOver) return;
  await sendMove("PASS");
}

async function humanResign() {
  if (!state.gameRunning || state.gameOver) return;
  try {
    const data = await apiPost("/api/resign", {});
    endGame(data.result || "认输");
  } catch (e) {
    showToast("请求失败：" + e.message);
  }
}

async function sendMove(vertex) {
  state.myTurn = false;
  setControls(false);
  showThinking(true);

  // Show the human stone immediately — don't wait for AI response
  placeStoneFromGTP(state.humanColor, vertex);
  draw();

  try {
    const data = await apiPost("/api/play", { vertex });

    appendLog(state.humanColor, vertex, state.moveHistory.length + 1);
    state.moveHistory.push({ color: state.humanColor, vertex });

    updateInfo(data.game);

    if (data.ai_move) {
      applyAIMove(data.ai_move);
    }

    if (data.game.game_over) {
      endGame(data.game.result || data.final_score || "");
      return;
    }

    state.myTurn = data.game.turn === state.humanColor;
    setControls(true);
    draw();
  } catch (e) {
    // Undo optimistic stone placement on error
    const cell = gtpToCell(vertex, state.boardSize);
    if (cell) state.stones[cell.row][cell.col] = null;
    showToast("落子失败：" + e.message);
    state.myTurn = true;
    setControls(true);
    draw();
  } finally {
    showThinking(false);
  }
}

function applyAIMove(aiMove) {
  const { color, vertex } = aiMove;
  if (aiMove.resign) {
    const winner = color === "black" ? "白" : "黑";
    endGame(`${winner}胜（AI认输）`);
    return;
  }
  placeStoneFromGTP(color, vertex);
  appendLog(color, vertex, state.moveHistory.length + 1);
  state.moveHistory.push({ color, vertex });
  draw();
}

function endGame(result) {
  state.gameOver    = true;
  state.gameRunning = false;
  state.myTurn      = false;
  gameSection.classList.add("hidden");
  resultSection.classList.remove("hidden");
  resultText.textContent = formatResult(result);
  draw();
}

function formatResult(result) {
  if (!result) return "对局结束";
  if (result.startsWith("B+")) return `黑胜 ${result.slice(2)}`;
  if (result.startsWith("W+")) return `白胜 ${result.slice(2)}`;
  return result;
}

// ================================================================== //
// UI helpers
// ================================================================== //

function updateInfo(game) {
  const turnLabel = game.turn === state.humanColor ? "你" : "AI";
  const turnColor = game.turn === "black" ? "⚫" : "⚪";
  infoTurn.textContent     = `${turnColor} ${turnLabel}`;
  infoCapBlack.textContent = game.captures?.black ?? 0;
  infoCapWhite.textContent = game.captures?.white ?? 0;
  infoMoves.textContent    = (game.move_history || []).length;
}

function appendLog(color, vertex, num) {
  const label = color === "black" ? "⚫" : "⚪";
  const line  = document.createElement("div");
  line.textContent = `${String(num).padStart(3, " ")}. ${label} ${vertex}`;
  moveLog.appendChild(line);
  moveLog.scrollTop = moveLog.scrollHeight;
}

function setControls(enabled) {
  btnPass.disabled   = !enabled;
  btnResign.disabled = !enabled;
}

function showThinking(show) {
  thinking.classList.toggle("hidden", !show);
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3000);
}

// ================================================================== //
// Canvas interaction
// ================================================================== //

function getCanvasPos(e) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width  / rect.width;
  const scaleY = canvas.height / rect.height;
  const clientX = e.touches ? e.touches[0].clientX : e.clientX;
  const clientY = e.touches ? e.touches[0].clientY : e.clientY;
  return {
    x: (clientX - rect.left) * scaleX,
    y: (clientY - rect.top)  * scaleY,
  };
}

canvas.addEventListener("mousemove", (e) => {
  if (!state.gameRunning || state.gameOver) return;
  const pos  = getCanvasPos(e);
  const cell = xyToCell(pos.x, pos.y);
  if (JSON.stringify(cell) !== JSON.stringify(state.hoverCell)) {
    state.hoverCell = cell;
    draw();
  }
});

canvas.addEventListener("mouseleave", () => {
  state.hoverCell = null;
  draw();
});

canvas.addEventListener("click", (e) => {
  const pos  = getCanvasPos(e);
  const cell = xyToCell(pos.x, pos.y);
  if (cell) humanPlay(cell.row, cell.col);
});

canvas.addEventListener("touchend", (e) => {
  e.preventDefault();
  const pos  = getCanvasPos(e.changedTouches[0] ? { clientX: e.changedTouches[0].clientX, clientY: e.changedTouches[0].clientY } : e);
  const cell = xyToCell(pos.x, pos.y);
  if (cell) humanPlay(cell.row, cell.col);
});

// ================================================================== //
// Button handlers
// ================================================================== //

btnNewGame.addEventListener("click", startNewGame);
btnPass.addEventListener("click", humanPass);
btnResign.addEventListener("click", humanResign);

btnEndGame.addEventListener("click", () => {
  state.gameRunning = false;
  state.gameOver    = true;
  gameSection.classList.add("hidden");
  setupSection.classList.remove("hidden");
  resultSection.classList.add("hidden");
});

btnAgain.addEventListener("click", () => {
  resultSection.classList.add("hidden");
  setupSection.classList.remove("hidden");
});

// ================================================================== //
// Responsive resize
// ================================================================== //

window.addEventListener("resize", () => {
  if (state.boardSize) {
    computeLayout(state.boardSize);
    draw();
  }
});

// ================================================================== //
// Init
// ================================================================== //

(function init() {
  computeLayout(19);
  initStones(19);
  draw();
})();
