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
  deadStones: [],      // GTP vertices judged dead after scoring
  territory: { black: [], white: [] },  // GTP vertices of each color's territory
  vsHuman: false,      // true = local two-player mode
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
const btnUndo     = document.getElementById("btn-undo");
const btnResign   = document.getElementById("btn-resign");
const btnEndGame  = document.getElementById("btn-end-game");
const btnAgain    = document.getElementById("btn-again");

const infoHumanColor = document.getElementById("info-human-color");
const labelMode      = document.getElementById("label-mode");
const difficultyGroup = document.getElementById("difficulty-group");
const infoTurn       = document.getElementById("info-turn");
const infoCapBlack   = document.getElementById("info-cap-black");
const infoCapWhite   = document.getElementById("info-cap-white");
const infoMoves      = document.getElementById("info-moves");
const resultText     = document.getElementById("result-text");
const resultDetail   = document.getElementById("result-detail");
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

  // Territory markers drawn BEFORE grid lines so lines appear on top
  if (state.territory.black.length || state.territory.white.length) {
    const half = cellSize * 0.5;
    const dot  = Math.max(3, cellSize * 0.17);
    for (const vertex of state.territory.black) {
      const cell = gtpToCell(vertex, n); if (!cell) continue;
      const { x, y } = cellToXY(cell.row, cell.col);
      ctx.fillStyle = "rgba(15,15,15,0.42)";
      ctx.fillRect(x - half, y - half, cellSize, cellSize);
      ctx.fillStyle = "rgba(10,10,10,0.78)";
      ctx.fillRect(x - dot,  y - dot,  dot * 2, dot * 2);
    }
    for (const vertex of state.territory.white) {
      const cell = gtpToCell(vertex, n); if (!cell) continue;
      const { x, y } = cellToXY(cell.row, cell.col);
      ctx.fillStyle = "rgba(220,220,220,0.38)";
      ctx.fillRect(x - half, y - half, cellSize, cellSize);
      ctx.fillStyle = "rgba(225,225,225,0.85)";
      ctx.fillRect(x - dot,  y - dot,  dot * 2, dot * 2);
      ctx.strokeStyle = "rgba(160,160,160,0.7)"; ctx.lineWidth = 0.6;
      ctx.strokeRect(x - dot, y - dot, dot * 2, dot * 2);
    }
  }

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

  const deadSet = new Set(state.deadStones.map(v => v.toUpperCase()));

  // Stones
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      const s = state.stones[r] && state.stones[r][c];
      if (s) {
        const vertex  = cellToGTP(r, c, n);
        const isDead  = deadSet.has(vertex.toUpperCase());
        drawStone(r, c, s, r === state.lastMove?.row && c === state.lastMove?.col, isDead);
      }
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
      const hoverColor = state.vsHuman ? state.turn : state.humanColor;
      ctx.fillStyle = hoverColor === "black" ? HOVER_BLACK : HOVER_WHITE;
      ctx.fill();
    }
  }
}

function drawStone(row, col, color, isLast, isDead) {
  const { x, y } = cellToXY(row, col);
  const r = cellSize * 0.46;

  ctx.globalAlpha = isDead ? 0.35 : 1.0;

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
  ctx.globalAlpha = 1.0;

  if (isDead) {
    // Cross mark over dead stone
    ctx.strokeStyle = color === "black" ? "rgba(255,255,255,0.9)" : "rgba(0,0,0,0.7)";
    ctx.lineWidth = Math.max(1.5, cellSize * 0.07);
    const d = r * 0.55;
    ctx.beginPath();
    ctx.moveTo(x - d, y - d); ctx.lineTo(x + d, y + d);
    ctx.moveTo(x + d, y - d); ctx.lineTo(x - d, y + d);
    ctx.stroke();
  } else if (isLast) {
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

// Sync the full board position from the server response (handles captures).
function syncBoardStones(boardStones) {
  if (!boardStones) return;
  const n = state.boardSize;
  // Reset all stones
  state.stones = Array.from({ length: n }, () => Array(n).fill(null));
  for (const vertex of (boardStones.black || [])) {
    const cell = gtpToCell(vertex, n);
    if (cell) state.stones[cell.row][cell.col] = "black";
  }
  for (const vertex of (boardStones.white || [])) {
    const cell = gtpToCell(vertex, n);
    if (cell) state.stones[cell.row][cell.col] = "white";
  }
}

async function startNewGame() {
  const boardSize  = parseInt(document.getElementById("board-size").value, 10);
  const humanColor = document.getElementById("human-color").value;
  const komi       = parseFloat(document.getElementById("komi").value);
  const difficulty = document.getElementById("difficulty").value;
  const mode       = document.getElementById("game-mode").value;

  btnNewGame.disabled = true;
  showThinking(true);

  try {
    const data = await apiPost("/api/new_game", { board_size: boardSize, human_color: humanColor, komi, difficulty, mode });

    state.boardSize   = boardSize;
    state.humanColor  = humanColor;
    state.aiColor     = data.game.ai_color;
    state.turn        = data.game.turn;
    state.vsHuman     = (mode === "vs_human");
    state.myTurn      = state.vsHuman || (data.game.turn === humanColor);
    state.gameRunning = true;
    state.gameOver    = false;
    state.lastMove    = null;
    state.moveHistory = [];
    state.deadStones  = [];
    state.territory   = { black: [], white: [] };

    initStones(boardSize);
    computeLayout(boardSize);

    // Update UI
    setupSection.classList.add("hidden");
    gameSection.classList.remove("hidden");
    resultSection.classList.add("hidden");
    moveLog.innerHTML = "";

    if (state.vsHuman) {
      labelMode.textContent      = "模式：";
      infoHumanColor.textContent = "双人对弈";
    } else {
      labelMode.textContent      = "我执：";
      infoHumanColor.textContent = humanColor === "black" ? "⚫ 黑棋" : "⚪ 白棋";
    }
    updateInfo(data.game);

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
  if (!state.gameRunning || state.gameOver) return;
  if (!state.myTurn) return;
  if (state.stones[row][col]) return;  // occupied

  const vertex = cellToGTP(row, col, state.boardSize);
  await sendMove(vertex);
}

async function humanPass() {
  if (!state.gameRunning || state.gameOver || !state.myTurn) return;
  await sendMove("PASS");
}

async function humanUndo() {
  if (!state.gameRunning || state.gameOver) return;
  if (state.moveHistory.length < 2) return;

  setControls(false);
  showThinking(true);

  try {
    const data = await apiPost("/api/undo", {});

    // Remove last 1 (vs_human) or 2 (vs_ai) entries
    const n = state.vsHuman ? 1 : 2;
    state.moveHistory.splice(-n);
    for (let i = 0; i < n; i++) {
      const last = moveLog.lastElementChild;
      if (last) moveLog.removeChild(last);
    }

    syncBoardStones(data.board_stones);

    // Update lastMove indicator to the new last move
    const hist = data.game.move_history || [];
    const lastEntry = hist[hist.length - 1];
    state.lastMove = lastEntry ? gtpToCell(lastEntry.vertex, state.boardSize) : null;

    state.turn   = data.game.turn;
    state.myTurn = state.vsHuman || (data.game.turn === state.humanColor);
    updateInfo(data.game);
    draw();
  } catch (e) {
    showToast("悔棋失败：" + e.message);
  } finally {
    showThinking(false);
    setControls(true);
  }
}

async function humanResign() {
  if (!state.gameRunning || state.gameOver) return;
  try {
    const data = await apiPost("/api/resign", {});
    endGame(data.result || "认输", null);
  } catch (e) {
    showToast("请求失败：" + e.message);
  }
}

async function sendMove(vertex) {
  state.myTurn = false;
  setControls(false);
  showThinking(!state.vsHuman);   // no spinner in vs_human (instant response)

  // Show the stone immediately for the current player
  const colorPlayed = state.vsHuman ? state.turn : state.humanColor;
  placeStoneFromGTP(colorPlayed, vertex);
  draw();

  try {
    const data = await apiPost("/api/play", { vertex });

    appendLog(colorPlayed, vertex, state.moveHistory.length + 1);
    state.moveHistory.push({ color: colorPlayed, vertex });

    updateInfo(data.game);

    if (!state.vsHuman && data.ai_move) {
      applyAIMove(data.ai_move);
    }

    // Sync authoritative board state (handles captures)
    syncBoardStones(data.board_stones);

    if (data.game.game_over) {
      endGame(data.game.result || data.final_score || "", null);
      return;
    }

    state.turn   = data.game.turn;
    state.myTurn = state.vsHuman || (data.game.turn === state.humanColor);
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
    endGame(`${winner}胜（AI认输）`, null);
    return;
  }
  placeStoneFromGTP(color, vertex);
  appendLog(color, vertex, state.moveHistory.length + 1);
  state.moveHistory.push({ color, vertex });
  draw();
}

async function humanScore() {
  if (!state.gameRunning && !state.gameOver) return;
  setControls(false);
  showThinking(true);
  try {
    const data = await apiPost("/api/score", {});
    state.deadStones = data.dead_stones || [];
    state.territory  = data.territory  || { black: [], white: [] };
    syncBoardStones(data.board_stones);
    endGame(data.result || "", data);
  } catch (e) {
    showToast("数棋失败：" + e.message);
    setControls(true);
  } finally {
    showThinking(false);
  }
}

function endGame(result, scoreData) {
  state.gameOver    = true;
  state.gameRunning = false;
  state.myTurn      = false;
  gameSection.classList.add("hidden");
  resultSection.classList.remove("hidden");
  resultText.textContent = formatResult(result);

  if (scoreData && scoreData.board_stones) {
    const deadList = scoreData.dead_stones || [];
    const bStones  = scoreData.board_stones.black || [];
    const wStones  = scoreData.board_stones.white || [];
    const deadSet  = new Set(deadList.map(v => v.toUpperCase()));
    const bDead    = bStones.filter(v => deadSet.has(v.toUpperCase())).length;
    const wDead    = wStones.filter(v => deadSet.has(v.toUpperCase())).length;
    const bAlive   = bStones.length - bDead;
    const wAlive   = wStones.length - wDead;
    const bTerr    = (scoreData.territory?.black || []).length;
    const wTerr    = (scoreData.territory?.white || []).length;
    const komi     = scoreData.game?.komi ?? 7.5;
    const bTotal   = bAlive + bTerr;
    const wTotal   = wAlive + wTerr + komi;
    const komiFmt  = komi === 0 ? "—" : `+${komi}`;
    const deadNote = deadList.length > 0
      ? `<div class="dead-note">死子 ${deadList.length} 枚（⚫${bDead} ⚪${wDead}）</div>`
      : "";
    resultDetail.innerHTML = `
      <table class="score-table">
        <thead><tr><th></th><th>⚫ 黑棋</th><th>⚪ 白棋</th></tr></thead>
        <tbody>
          <tr><td>子数</td><td>${bAlive}</td><td>${wAlive}</td></tr>
          <tr><td>领地</td><td>${bTerr}</td><td>${wTerr}</td></tr>
          <tr class="komi-row"><td>贴目</td><td>—</td><td>${komiFmt}</td></tr>
          <tr class="total-row"><td>合计</td><td>${bTotal}</td><td>${wTotal}</td></tr>
        </tbody>
      </table>${deadNote}`;
  } else {
    resultDetail.innerHTML = "";
  }

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
  const turnColor = game.turn === "black" ? "⚫" : "⚪";
  let turnLabel;
  if (state.vsHuman) {
    turnLabel = game.turn === "black" ? "黑棋落子" : "白棋落子";
  } else {
    turnLabel = game.turn === state.humanColor ? "你" : "AI";
  }
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
  const minUndo = state.vsHuman ? 1 : 2;
  btnPass.disabled   = !enabled;
  btnUndo.disabled   = !enabled || state.moveHistory.length < minUndo;
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

document.getElementById("game-mode").addEventListener("change", (e) => {
  difficultyGroup.classList.toggle("hidden", e.target.value === "vs_human");
});

btnNewGame.addEventListener("click", startNewGame);
btnPass.addEventListener("click", humanPass);
btnUndo.addEventListener("click", humanUndo);
btnResign.addEventListener("click", humanResign);

btnEndGame.addEventListener("click", humanScore);

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
// Classic game replay + My Games history
// ================================================================== //

const replaySection     = document.getElementById("replay-section");
const myGamesSection    = document.getElementById("my-games-section");
const replayPicker      = document.getElementById("replay-picker");
const replayControls    = document.getElementById("replay-controls");
const replayBlackEl     = document.getElementById("replay-black");
const replayWhiteEl     = document.getElementById("replay-white");
const replayMetaEl      = document.getElementById("replay-meta");
const replayMoveNumEl   = document.getElementById("replay-move-num");
const replayTotalEl     = document.getElementById("replay-total");
const replayCommentEl   = document.getElementById("replay-comment");
const replaySlider      = document.getElementById("replay-slider");
const btnAutoplay       = document.getElementById("btn-autoplay");

let replay = {
  active:      false,
  source:      "classic",  // "classic" | "my-games"
  gameInfo:    null,
  moves:       [],       // [{color, vertex, comment}]
  positions:   [],       // positions[i] = board state after i moves
  currentMove: 0,
  autoPlay:    false,
  autoTimer:   null,
};

// --- Minimal Go rules for board replay (no captures skipped) ---

function _nb(r, c, n) {
  const a = [];
  if (r > 0)   a.push([r - 1, c]);
  if (r < n-1) a.push([r + 1, c]);
  if (c > 0)   a.push([r, c - 1]);
  if (c < n-1) a.push([r, c + 1]);
  return a;
}

function _group(board, r0, c0, n) {
  const color = board[r0][c0];
  const seen = new Set();
  const group = [];
  const stack = [[r0, c0]];
  while (stack.length) {
    const [r, c] = stack.pop();
    const k = r * n + c;
    if (seen.has(k)) continue;
    seen.add(k);
    if (board[r][c] !== color) continue;
    group.push([r, c]);
    for (const [nr, nc] of _nb(r, c, n)) {
      if (!seen.has(nr * n + nc)) stack.push([nr, nc]);
    }
  }
  return group;
}

function _hasLib(board, group, n) {
  for (const [r, c] of group)
    for (const [nr, nc] of _nb(r, c, n))
      if (board[nr][nc] === null) return true;
  return false;
}

function _applyMove(board, color, vertex, n) {
  const b = board.map(row => [...row]);
  const cell = gtpToCell(vertex, n);
  if (!cell) return b;          // PASS
  const { row, col } = cell;
  if (b[row][col]) return b;    // occupied
  b[row][col] = color;
  const opp = color === "black" ? "white" : "black";
  for (const [nr, nc] of _nb(row, col, n)) {
    if (b[nr][nc] === opp) {
      const g = _group(b, nr, nc, n);
      if (!_hasLib(b, g, n)) g.forEach(([gr, gc]) => { b[gr][gc] = null; });
    }
  }
  return b;
}

function buildPositions(moves, boardSize) {
  const n = boardSize;
  const empty = Array.from({ length: n }, () => Array(n).fill(null));
  const positions = [empty];
  for (const { color, vertex } of moves) {
    positions.push(_applyMove(positions[positions.length - 1], color, vertex, n));
  }
  return positions;
}

// --- Replay UI ---

async function loadGameList() {
  const list = document.getElementById("game-list");
  try {
    const data = await fetch("/api/games").then(r => r.json());
    list.innerHTML = "";
    if (!data.games || data.games.length === 0) {
      list.innerHTML = '<p class="replay-loading">暂无棋局</p>';
      return;
    }
    for (const g of data.games) {
      const btn = document.createElement("button");
      btn.className = "game-list-item";
      btn.innerHTML = `
        <span class="gli-title">${g.title || g.id}</span>
        ${g.event ? `<span class="gli-event">${g.event}</span>` : ""}
        <span class="gli-foot">
          <span class="gli-date">${g.date || ""}</span>
          <span class="gli-result">${g.result || ""}</span>
        </span>
        ${g.description ? `<span class="gli-desc">${g.description}</span>` : ""}`;
      btn.addEventListener("click", () => loadReplayGame(g.id));
      list.appendChild(btn);
    }
  } catch (e) {
    list.innerHTML = `<p class="replay-loading">加载失败: ${e.message}</p>`;
  }
}

function _setupReplay(data, source) {
  if (!data.game) throw new Error(data.error || "unknown error");
  const { game_info, moves } = data.game;
  const n = game_info.board_size || 19;

  replay.gameInfo    = game_info;
  replay.moves       = moves;
  replay.positions   = buildPositions(moves, n);
  replay.currentMove = 0;
  replay.active      = true;
  replay.source      = source;  // "classic" | "my-games"

  state.boardSize  = n;
  state.deadStones = [];
  state.territory  = { black: [], white: [] };
  computeLayout(n);

  // Show replay-section with controls
  myGamesSection.classList.add("hidden");
  replaySection.classList.remove("hidden");
  replayPicker.classList.add("hidden");
  replayControls.classList.remove("hidden");

  // Players
  const br = game_info.black_rank ? ` ${game_info.black_rank}` : "";
  const wr = game_info.white_rank ? ` ${game_info.white_rank}` : "";
  replayBlackEl.textContent = `⚫ ${game_info.black}${br}`;
  replayWhiteEl.textContent = `⚪ ${game_info.white}${wr}`;

  // Meta line
  const parts = [];
  if (game_info.event)    parts.push(game_info.event);
  if (game_info.date)     parts.push(game_info.date);
  if (data.game.played_at) parts.push(data.game.played_at.slice(0, 10));
  if (game_info.result)   parts.push(`结果: ${game_info.result}`);
  replayMetaEl.textContent = parts.join(" · ");

  replaySlider.max   = moves.length;
  replaySlider.value = 0;
  replayTotalEl.textContent = `共 ${moves.length} 手`;

  replayGoTo(0);
}

async function loadReplayGame(gameId) {
  replayCommentEl.classList.add("hidden");
  replayCommentEl.textContent = "";
  try {
    const data = await fetch(`/api/games/${gameId}`).then(r => r.json());
    _setupReplay(data, "classic");
  } catch (e) {
    showToast("加载失败：" + e.message);
  }
}

async function loadMyReplayGame(gameId) {
  replayCommentEl.classList.add("hidden");
  replayCommentEl.textContent = "";
  try {
    const data = await fetch(`/api/my_games/${gameId}`).then(r => r.json());
    _setupReplay(data, "my-games");
  } catch (e) {
    showToast("加载失败：" + e.message);
  }
}

function replayGoTo(idx) {
  const total = replay.moves.length;
  idx = Math.max(0, Math.min(total, idx));
  replay.currentMove = idx;

  // Update board
  const n = replay.gameInfo.board_size || 19;
  state.stones = replay.positions[idx].map(row => [...row]);
  state.lastMove = idx > 0 ? gtpToCell(replay.moves[idx - 1].vertex, n) : null;

  // Move number display
  if (idx === 0) {
    replayMoveNumEl.textContent = "开局";
  } else {
    const m = replay.moves[idx - 1];
    const colorLabel = m.color === "black" ? "⚫" : "⚪";
    replayMoveNumEl.textContent = `第 ${idx} 手 ${colorLabel} ${m.vertex}`;
  }

  // Comment
  const comment = idx > 0 ? (replay.moves[idx - 1].comment || "") : "";
  if (comment) {
    replayCommentEl.textContent = comment;
    replayCommentEl.classList.remove("hidden");
  } else {
    replayCommentEl.classList.add("hidden");
  }

  replaySlider.value = idx;
  draw();
}

function stopAutoPlay() {
  if (replay.autoTimer) { clearInterval(replay.autoTimer); replay.autoTimer = null; }
  replay.autoPlay = false;
  btnAutoplay.textContent = "▶ 自动播放";
}

function toggleAutoPlay() {
  if (replay.autoPlay) { stopAutoPlay(); return; }
  replay.autoPlay = true;
  btnAutoplay.textContent = "⏸ 暂停";
  replay.autoTimer = setInterval(() => {
    if (replay.currentMove >= replay.moves.length) { stopAutoPlay(); return; }
    replayGoTo(replay.currentMove + 1);
  }, 700);
}

// Keyboard navigation while replaying
document.addEventListener("keydown", (e) => {
  if (!replay.active) return;
  if (e.key === "ArrowRight" || e.key === "ArrowDown") {
    stopAutoPlay(); replayGoTo(replay.currentMove + 1);
  } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
    stopAutoPlay(); replayGoTo(replay.currentMove - 1);
  } else if (e.key === "Home") {
    stopAutoPlay(); replayGoTo(0);
  } else if (e.key === "End") {
    stopAutoPlay(); replayGoTo(replay.moves.length);
  }
});

// --- Button wiring ---

document.getElementById("btn-go-replay").addEventListener("click", () => {
  setupSection.classList.add("hidden");
  replaySection.classList.remove("hidden");
  replayPicker.classList.remove("hidden");
  replayControls.classList.add("hidden");
  loadGameList();
});

async function loadMyGameList() {
  const list = document.getElementById("my-game-list");
  list.innerHTML = '<p class="replay-loading">加载中…</p>';
  try {
    const data = await fetch("/api/my_games").then(r => r.json());
    if (data.error) { list.innerHTML = `<p class="replay-loading">${data.error}</p>`; return; }
    list.innerHTML = "";
    if (!data.games || data.games.length === 0) {
      list.innerHTML = '<p class="replay-loading">暂无记录，完成一局人机对弈后将自动保存。</p>';
      return;
    }
    data.games.forEach((g, idx) => {
      const gameNum   = data.games.length - idx;
      const resultWin = g.result && ((g.human_color === "black" && g.result.startsWith("B")) ||
                                      (g.human_color === "white" && g.result.startsWith("W")));
      const dateStr   = g.played_at ? g.played_at.replace("T", " ").slice(0, 16) : "";
      const btn = document.createElement("button");
      btn.className = "game-list-item my-game-row";
      btn.innerHTML = `
        <span class="mgl-num">#${gameNum}</span>
        <span class="mgl-result ${resultWin ? "gli-win" : "gli-loss"}">${g.result || "—"}</span>
        <span class="mgl-date">${dateStr}</span>`;
      btn.addEventListener("click", () => loadMyReplayGame(g.id));
      list.appendChild(btn);
    });
  } catch (e) {
    list.innerHTML = `<p class="replay-loading">加载失败: ${e.message}</p>`;
  }
}

document.getElementById("btn-go-my-games").addEventListener("click", () => {
  setupSection.classList.add("hidden");
  myGamesSection.classList.remove("hidden");
  loadMyGameList();
});

document.getElementById("btn-my-games-back").addEventListener("click", () => {
  myGamesSection.classList.add("hidden");
  setupSection.classList.remove("hidden");
});

document.getElementById("btn-replay-back").addEventListener("click", () => {
  stopAutoPlay();
  replay.active = false;
  replaySection.classList.add("hidden");
  if (replay.source === "my-games") {
    myGamesSection.classList.remove("hidden");
  } else {
    setupSection.classList.remove("hidden");
  }
  computeLayout(19);
  initStones(19);
  state.deadStones = [];
  state.territory  = { black: [], white: [] };
  state.lastMove   = null;
  draw();
});

document.getElementById("btn-pick-another").addEventListener("click", () => {
  stopAutoPlay();
  replay.active = false;
  replayControls.classList.add("hidden");
  computeLayout(19);
  initStones(19);
  state.lastMove = null;
  draw();
  if (replay.source === "my-games") {
    replaySection.classList.add("hidden");
    myGamesSection.classList.remove("hidden");
  } else {
    replayPicker.classList.remove("hidden");
  }
});

document.getElementById("btn-r-first").addEventListener("click", () => { stopAutoPlay(); replayGoTo(0); });
document.getElementById("btn-r-prev").addEventListener("click",  () => { stopAutoPlay(); replayGoTo(replay.currentMove - 1); });
document.getElementById("btn-r-next").addEventListener("click",  () => { stopAutoPlay(); replayGoTo(replay.currentMove + 1); });
document.getElementById("btn-r-last").addEventListener("click",  () => { stopAutoPlay(); replayGoTo(replay.moves.length); });
btnAutoplay.addEventListener("click", toggleAutoPlay);
replaySlider.addEventListener("input", (e) => { stopAutoPlay(); replayGoTo(parseInt(e.target.value)); });

// ================================================================== //
// User auth
// ================================================================== //

const authModal      = document.getElementById("auth-modal");
const authForm       = document.getElementById("auth-form");
const authTitle      = document.getElementById("auth-title");
const authUsername    = document.getElementById("auth-username");
const authPassword   = document.getElementById("auth-password");
const authDisplayRow = document.getElementById("auth-display-row");
const authDisplayName = document.getElementById("auth-display-name");
const authError      = document.getElementById("auth-error");
const authSubmit     = document.getElementById("auth-submit");
const authSwitchText = document.getElementById("auth-switch-text");
const authSwitchBtn  = document.getElementById("auth-switch-btn");
const userLoggedOut  = document.getElementById("user-logged-out");
const userLoggedIn   = document.getElementById("user-logged-in");
const userDisplayEl  = document.getElementById("user-display-name");
const userStatsEl    = document.getElementById("user-stats");

let authMode = "login"; // "login" | "register"
let currentUser = null;

function setAuthMode(mode) {
  authMode = mode;
  authError.classList.add("hidden");
  authUsername.value = "";
  authPassword.value = "";
  authDisplayName.value = "";
  if (mode === "register") {
    authTitle.textContent = "注册";
    authSubmit.textContent = "注册";
    authDisplayRow.classList.remove("hidden");
    authSwitchText.textContent = "已有账号？";
    authSwitchBtn.textContent = "登录";
  } else {
    authTitle.textContent = "登录";
    authSubmit.textContent = "登录";
    authDisplayRow.classList.add("hidden");
    authSwitchText.textContent = "没有账号？";
    authSwitchBtn.textContent = "注册";
  }
}

function showAuthModal(mode) {
  setAuthMode(mode);
  authModal.classList.remove("hidden");
  authUsername.focus();
}

function hideAuthModal() {
  authModal.classList.add("hidden");
}

function updateUserUI() {
  const btnMyGames = document.getElementById("btn-go-my-games");
  if (currentUser) {
    userLoggedOut.classList.add("hidden");
    userLoggedIn.classList.remove("hidden");
    userDisplayEl.textContent = currentUser.display_name || currentUser.username;
    const w = currentUser.games_won || 0;
    const p = currentUser.games_played || 0;
    userStatsEl.textContent = p > 0 ? `${w}胜 / ${p}局` : "";
    btnMyGames.classList.remove("hidden");
  } else {
    userLoggedOut.classList.remove("hidden");
    userLoggedIn.classList.add("hidden");
    btnMyGames.classList.add("hidden");
  }
}

async function checkSession() {
  try {
    const data = await fetch("/api/me").then(r => r.json());
    currentUser = data.user || null;
  } catch {
    currentUser = null;
  }
  updateUserUI();
}

// --- Google Sign-In ---
let googleClientId = null;
const googleDivider  = document.getElementById("google-divider");
const googleBtnWrap  = document.getElementById("google-signin-btn");

async function initGoogleSignIn() {
  try {
    const data = await fetch("/api/auth/config").then(r => r.json());
    googleClientId = data.google_client_id || null;
  } catch {
    googleClientId = null;
  }
  if (!googleClientId || typeof google === "undefined") return;

  google.accounts.id.initialize({
    client_id: googleClientId,
    callback: handleGoogleCredential,
  });

  googleDivider.classList.remove("hidden");
  googleBtnWrap.classList.remove("hidden");
  google.accounts.id.renderButton(googleBtnWrap, {
    theme: "filled_black",
    size: "large",
    width: 244,
    text: "signin_with",
    locale: "zh_CN",
  });
}

async function handleGoogleCredential(response) {
  authError.classList.add("hidden");
  try {
    const resp = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      authError.textContent = data.error || "Google 登录失败";
      authError.classList.remove("hidden");
      return;
    }
    currentUser = data.user;
    updateUserUI();
    hideAuthModal();
    showToast("Google 登录成功！");
  } catch {
    authError.textContent = "网络错误";
    authError.classList.remove("hidden");
  }
}

document.getElementById("btn-show-login").addEventListener("click", () => showAuthModal("login"));
document.getElementById("btn-show-register").addEventListener("click", () => showAuthModal("register"));
document.getElementById("auth-close").addEventListener("click", hideAuthModal);
authSwitchBtn.addEventListener("click", () => setAuthMode(authMode === "login" ? "register" : "login"));

authModal.addEventListener("click", (e) => {
  if (e.target === authModal) hideAuthModal();
});

authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authError.classList.add("hidden");
  const username = authUsername.value.trim();
  const password = authPassword.value;

  if (!username || !password) {
    authError.textContent = "请填写所有必填项";
    authError.classList.remove("hidden");
    return;
  }

  const endpoint = authMode === "register" ? "/api/register" : "/api/login";
  const body = { username, password };
  if (authMode === "register") {
    body.display_name = authDisplayName.value.trim();
  }

  try {
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) {
      authError.textContent = data.error || "操作失败";
      authError.classList.remove("hidden");
      return;
    }
    currentUser = data.user;
    updateUserUI();
    hideAuthModal();
    showToast(authMode === "register" ? "注册成功！" : "登录成功！");
  } catch (err) {
    authError.textContent = "网络错误";
    authError.classList.remove("hidden");
  }
});

document.getElementById("btn-logout").addEventListener("click", async () => {
  try {
    await fetch("/api/logout", { method: "POST" });
  } catch {}
  currentUser = null;
  updateUserUI();
  showToast("已退出登录");
});

// ================================================================== //
// Init
// ================================================================== //

(function init() {
  computeLayout(19);
  initStones(19);
  draw();
  checkSession();
  initGoogleSignIn();
})();
