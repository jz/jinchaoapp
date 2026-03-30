/**
 * Chinese Chess (象棋) – frontend game logic.
 *
 * Board coordinate system (matches server):
 *   row 0-4 = Black's side (top), row 5-9 = Red's side (bottom)
 *   col 0-8 left to right
 */

'use strict';

// -------------------------------------------------------------------------- //
// Constants
// -------------------------------------------------------------------------- //

const CELL      = 58;          // pixels between adjacent intersections
const PAD       = 44;          // padding from canvas edge to first intersection
const PIECE_R   = 24;          // piece circle radius
const COLS      = 9;
const ROWS      = 10;

const CANVAS_W  = (COLS - 1) * CELL + PAD * 2;
const CANVAS_H  = (ROWS - 1) * CELL + PAD * 2;

const BOARD_BG   = '#f0c070';
const BOARD_LINE = '#7a4820';
const RIVER_BG   = '#d9aa50';

// Piece display characters (server sends ints, same mapping as engine)
const PIECE_CHARS = {
   1:'俥', [-1]:'車',
   2:'傌', [-2]:'馬',
   3:'相', [-3]:'象',
   4:'仕', [-4]:'士',
   5:'帅', [-5]:'将',
   6:'炮', [-6]:'砲',
   7:'兵', [-7]:'卒',
};

// -------------------------------------------------------------------------- //
// State
// -------------------------------------------------------------------------- //

const G = {
  board:       null,
  turn:        'red',
  mode:        'vs_ai',
  humanColor:  'red',
  difficulty:  'medium',
  gameOver:    false,
  result:      null,
  resultText:  '',
  inCheck:     false,
  lastMove:    null,   // [fr,fc,tr,tc]
  validMoves:  {},     // { "r,c": [[tr,tc],...] }
  selected:    null,   // [r, c] | null
  thinking:    false,
};

// -------------------------------------------------------------------------- //
// Canvas
// -------------------------------------------------------------------------- //

const canvas = document.getElementById('board');
canvas.width  = CANVAS_W;
canvas.height = CANVAS_H;
const ctx = canvas.getContext('2d');

function px(col) { return PAD + col * CELL; }
function py(row) { return PAD + row * CELL; }

function drawBoard() {
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

  // Background
  ctx.fillStyle = BOARD_BG;
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

  // River highlight
  ctx.fillStyle = RIVER_BG;
  ctx.fillRect(PAD, py(4), (COLS-1)*CELL, CELL);

  // Horizontal lines (all span full width)
  ctx.strokeStyle = BOARD_LINE;
  ctx.lineWidth = 1.2;
  for (let r = 0; r < ROWS; r++) {
    ctx.beginPath();
    ctx.moveTo(px(0), py(r));
    ctx.lineTo(px(COLS-1), py(r));
    ctx.stroke();
  }

  // Vertical lines – border cols go full length; interior cols split at river
  for (let c = 0; c < COLS; c++) {
    if (c === 0 || c === COLS-1) {
      ctx.beginPath();
      ctx.moveTo(px(c), py(0));
      ctx.lineTo(px(c), py(ROWS-1));
      ctx.stroke();
    } else {
      // Black half
      ctx.beginPath();
      ctx.moveTo(px(c), py(0));
      ctx.lineTo(px(c), py(4));
      ctx.stroke();
      // Red half
      ctx.beginPath();
      ctx.moveTo(px(c), py(5));
      ctx.lineTo(px(c), py(ROWS-1));
      ctx.stroke();
    }
  }

  // Palace diagonals – Black (rows 0-2, cols 3-5)
  ctx.beginPath();
  ctx.moveTo(px(3), py(0)); ctx.lineTo(px(5), py(2));
  ctx.moveTo(px(5), py(0)); ctx.lineTo(px(3), py(2));
  ctx.stroke();

  // Palace diagonals – Red (rows 7-9, cols 3-5)
  ctx.beginPath();
  ctx.moveTo(px(3), py(7)); ctx.lineTo(px(5), py(9));
  ctx.moveTo(px(5), py(7)); ctx.lineTo(px(3), py(9));
  ctx.stroke();

  // River text
  ctx.fillStyle = '#5a2f0a';
  ctx.font = `bold ${CELL * 0.45}px 'PingFang SC', 'Microsoft YaHei', serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const riverY = py(4) + CELL / 2;
  ctx.fillText('楚  河', px(2), riverY);
  ctx.fillText('汉  界', px(6), riverY);

  // Small notch marks (cannon / soldier start squares)
  const notches = [
    [2,1],[2,7],[7,1],[7,7],  // cannons
    [3,0],[3,2],[3,4],[3,6],[3,8],  // black soldiers
    [6,0],[6,2],[6,4],[6,6],[6,8],  // red soldiers
  ];
  for (const [r, c] of notches) {
    drawNotch(r, c);
  }

  // Last move highlight
  if (G.lastMove) {
    const [fr, fc, tr, tc] = G.lastMove;
    ctx.fillStyle = 'rgba(0,180,60,0.25)';
    for (const [r, c] of [[fr,fc],[tr,tc]]) {
      ctx.beginPath();
      ctx.arc(px(c), py(r), PIECE_R + 4, 0, Math.PI*2);
      ctx.fill();
    }
  }

  // Valid move highlights
  if (G.selected) {
    const [sr, sc] = G.selected;
    const key = `${sr},${sc}`;
    const dests = G.validMoves[key] || [];
    for (const [tr, tc] of dests) {
      if (G.board[tr][tc] !== 0) {
        // Capture square – red ring
        ctx.strokeStyle = 'rgba(220,50,50,0.85)';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(px(tc), py(tr), PIECE_R + 3, 0, Math.PI*2);
        ctx.stroke();
      } else {
        // Empty square – green dot
        ctx.fillStyle = 'rgba(0,200,80,0.7)';
        ctx.beginPath();
        ctx.arc(px(tc), py(tr), 7, 0, Math.PI*2);
        ctx.fill();
      }
    }

    // Selection highlight
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(px(sc), py(sr), PIECE_R + 4, 0, Math.PI*2);
    ctx.stroke();
  }

  // Pieces
  if (G.board) {
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const p = G.board[r][c];
        if (p !== 0) drawPiece(r, c, p);
      }
    }
  }

  // "Thinking" overlay
  if (G.thinking) {
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 22px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('AI 思考中…', CANVAS_W/2, CANVAS_H/2);
  }
}

function drawNotch(r, c) {
  const x = px(c), y = py(r);
  const s = 6, g = 3;
  ctx.strokeStyle = BOARD_LINE;
  ctx.lineWidth = 1.2;
  if (c > 0) {
    // left notch
    ctx.beginPath();
    ctx.moveTo(x-g, y-s); ctx.lineTo(x-g-s, y-s);
    ctx.moveTo(x-g, y+s); ctx.lineTo(x-g-s, y+s);
    ctx.moveTo(x-g-s, y-s); ctx.lineTo(x-g-s, y+s);
    ctx.stroke();
  }
  if (c < COLS-1) {
    ctx.beginPath();
    ctx.moveTo(x+g, y-s); ctx.lineTo(x+g+s, y-s);
    ctx.moveTo(x+g, y+s); ctx.lineTo(x+g+s, y+s);
    ctx.moveTo(x+g+s, y-s); ctx.lineTo(x+g+s, y+s);
    ctx.stroke();
  }
  if (r > 0) {
    ctx.beginPath();
    ctx.moveTo(x-s, y-g); ctx.lineTo(x-s, y-g-s);
    ctx.moveTo(x+s, y-g); ctx.lineTo(x+s, y-g-s);
    ctx.moveTo(x-s, y-g-s); ctx.lineTo(x+s, y-g-s);
    ctx.stroke();
  }
  if (r < ROWS-1) {
    ctx.beginPath();
    ctx.moveTo(x-s, y+g); ctx.lineTo(x-s, y+g+s);
    ctx.moveTo(x+s, y+g); ctx.lineTo(x+s, y+g+s);
    ctx.moveTo(x-s, y+g+s); ctx.lineTo(x+s, y+g+s);
    ctx.stroke();
  }
}

function drawPiece(r, c, p) {
  const x = px(c), y = py(r);
  const red = p > 0;
  const ch = PIECE_CHARS[p] || '?';

  // Outer ring
  ctx.beginPath();
  ctx.arc(x, y, PIECE_R, 0, Math.PI*2);
  ctx.strokeStyle = red ? '#8b1a1a' : '#1a1a1a';
  ctx.lineWidth = 2.5;
  ctx.fillStyle = '#f5deb3';
  ctx.fill();
  ctx.stroke();

  // Inner ring
  ctx.beginPath();
  ctx.arc(x, y, PIECE_R - 5, 0, Math.PI*2);
  ctx.strokeStyle = red ? '#c0392b' : '#333';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  // Character
  ctx.fillStyle = red ? '#c0392b' : '#1a1a1a';
  ctx.font = `bold ${PIECE_R * 1.05}px 'PingFang SC', 'Microsoft YaHei', serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(ch, x, y + 1);
}

// -------------------------------------------------------------------------- //
// UI helpers
// -------------------------------------------------------------------------- //

const statusText  = document.getElementById('status-text');
const checkBadge  = document.getElementById('check-badge');
const resultOverlay = document.getElementById('result-overlay');
const resultDiv   = document.getElementById('result-text');
const btnUndo     = document.getElementById('btn-undo');

function updateStatus() {
  if (G.gameOver) {
    statusText.textContent = G.resultText || '游戏结束';
    checkBadge.classList.add('hidden');
    resultDiv.textContent = G.resultText;
    resultOverlay.classList.remove('hidden');
    return;
  }
  resultOverlay.classList.add('hidden');

  const turnLabel = G.turn === 'red' ? '红方' : '黑方';
  if (G.thinking) {
    statusText.textContent = 'AI 思考中…';
  } else {
    statusText.textContent = `${turnLabel}走棋`;
  }
  if (G.inCheck) {
    checkBadge.classList.remove('hidden');
  } else {
    checkBadge.classList.add('hidden');
  }

  // Undo button availability
  btnUndo.disabled = false;
}

function applyState(data) {
  G.board       = data.board;
  G.turn        = data.turn;
  G.mode        = data.mode;
  G.humanColor  = data.humanColor;
  G.difficulty  = data.difficulty;
  G.gameOver    = data.gameOver;
  G.result      = data.result;
  G.resultText  = data.resultText;
  G.inCheck     = data.inCheck;
  G.lastMove    = data.lastMove;
  G.validMoves  = data.validMoves || {};
  G.thinking    = false;
  G.selected    = null;

  const badge = document.getElementById('engine-badge');
  if (data.engine && data.mode === 'vs_ai') {
    badge.textContent = `引擎：${data.engine}`;
    badge.className = data.engine === 'Pikafish' ? 'pikafish' : '';
  } else {
    badge.textContent = '';
  }
}

// -------------------------------------------------------------------------- //
// API
// -------------------------------------------------------------------------- //

async function apiNewGame(mode, humanColor, difficulty, fen) {
  const body = {mode, human_color: humanColor, difficulty};
  if (fen) body.fen = fen;
  const res = await fetch('/chess/api/new_game', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return res.json();
}

async function apiValidateFen(fen) {
  const res = await fetch('/chess/api/validate_fen', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({fen}),
  });
  return res.json();
}

async function apiMove(fr, fc, tr, tc) {
  const res = await fetch('/chess/api/move', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({fr, fc, tr, tc}),
  });
  return res.json();
}

async function apiUndo() {
  const res = await fetch('/chess/api/undo', {method: 'POST'});
  return res.json();
}

// -------------------------------------------------------------------------- //
// Game flow
// -------------------------------------------------------------------------- //

async function startGame() {
  const mode       = selectedValue('mode-group');
  const humanColor = selectedValue('color-group');
  const difficulty = selectedValue('diff-group');
  const startMode  = selectedValue('start-group');

  let fen = '';
  if (startMode === 'fen') {
    fen = document.getElementById('fen-input').value.trim();
    if (!fen) {
      showFenError('请输入 FEN 字符串');
      return;
    }
    // Validate before starting
    const v = await apiValidateFen(fen);
    if (v.error) {
      showFenError(v.error);
      return;
    }
  }

  document.getElementById('setup-panel').classList.add('hidden');
  document.getElementById('game-area').classList.remove('hidden');
  resultOverlay.classList.add('hidden');

  G.thinking = true;
  statusText.textContent = '正在初始化…';
  drawBoard();

  const data = await apiNewGame(mode, humanColor, difficulty, fen);
  if (data.error) {
    document.getElementById('setup-panel').classList.remove('hidden');
    document.getElementById('game-area').classList.add('hidden');
    showFenError(data.error);
    return;
  }
  applyState(data);
  drawBoard();
  updateStatus();
}

async function makeMove(fr, fc, tr, tc) {
  G.thinking = true;
  G.selected = null;
  drawBoard();
  updateStatus();

  const data = await apiMove(fr, fc, tr, tc);
  if (data.error) {
    G.thinking = false;
    drawBoard();
    return;
  }
  applyState(data);
  drawBoard();
  updateStatus();
}

async function undoMove() {
  const data = await apiUndo();
  if (data.error) return;
  applyState(data);
  drawBoard();
  updateStatus();
}

// -------------------------------------------------------------------------- //
// Click handling
// -------------------------------------------------------------------------- //

canvas.addEventListener('click', (e) => {
  if (!G.board || G.gameOver || G.thinking) return;

  // In vs_ai mode, ignore clicks when it's not human's turn
  if (G.mode === 'vs_ai' && G.turn !== G.humanColor) return;

  const rect = canvas.getBoundingClientRect();
  const scaleX = CANVAS_W / rect.width;
  const scaleY = CANVAS_H / rect.height;
  const mx = (e.clientX - rect.left) * scaleX;
  const my = (e.clientY - rect.top)  * scaleY;

  // Snap to nearest intersection
  const c = Math.round((mx - PAD) / CELL);
  const r = Math.round((my - PAD) / CELL);
  if (c < 0 || c >= COLS || r < 0 || r >= ROWS) return;

  const dist = Math.hypot(mx - px(c), my - py(r));
  if (dist > PIECE_R + 6) return;   // click too far from intersection

  const piece = G.board[r][c];

  // If a piece is already selected, check if this is a valid destination
  if (G.selected) {
    const [sr, sc] = G.selected;
    const key = `${sr},${sc}`;
    const dests = G.validMoves[key] || [];
    const match = dests.find(([dr, dc]) => dr === r && dc === c);
    if (match) {
      makeMove(sr, sc, r, c);
      return;
    }
  }

  // Try to select a friendly piece
  const isRed   = piece > 0;
  const isBlack = piece < 0;
  const myTurn  = (G.turn === 'red' && isRed) || (G.turn === 'black' && isBlack);
  if (myTurn && (G.validMoves[`${r},${c}`] || []).length > 0) {
    G.selected = [r, c];
  } else {
    G.selected = null;
  }
  drawBoard();
});

// -------------------------------------------------------------------------- //
// Setup panel helpers
// -------------------------------------------------------------------------- //

function selectedValue(groupId) {
  const btn = document.querySelector(`#${groupId} .tog.active`);
  return btn ? btn.dataset.value : null;
}

function showFenError(msg) {
  const el = document.getElementById('fen-error');
  const inp = document.getElementById('fen-input');
  el.textContent = msg;
  el.classList.remove('hidden');
  inp.classList.add('error');
}

function clearFenError() {
  document.getElementById('fen-error').classList.add('hidden');
  document.getElementById('fen-input').classList.remove('error');
}

// Live FEN validation with debounce
let _fenTimer = null;
function onFenInput() {
  clearFenError();
  document.getElementById('fen-turn-label').textContent = '—';
  const fen = document.getElementById('fen-input').value.trim();
  if (!fen) return;
  clearTimeout(_fenTimer);
  _fenTimer = setTimeout(async () => {
    const v = await apiValidateFen(fen);
    if (v.error) {
      showFenError(v.error);
    } else {
      clearFenError();
      document.getElementById('fen-turn-label').textContent =
        v.turn === 'red' ? '红方先走' : '黑方先走';
    }
  }, 500);
}

function initToggleGroups() {
  document.querySelectorAll('.btn-group').forEach(group => {
    group.querySelectorAll('.tog').forEach(btn => {
      btn.addEventListener('click', () => {
        group.querySelectorAll('.tog').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (group.id === 'mode-group') {
          const vsAi = btn.dataset.value === 'vs_ai';
          document.getElementById('color-row').style.display = vsAi ? '' : 'none';
          document.getElementById('diff-row').style.display  = vsAi ? '' : 'none';
        }
        if (group.id === 'start-group') {
          const isFen = btn.dataset.value === 'fen';
          document.getElementById('fen-row').classList.toggle('hidden', !isFen);
          clearFenError();
        }
      });
    });
  });

  document.getElementById('fen-input').addEventListener('input', onFenInput);
}

function showSetup() {
  document.getElementById('game-area').classList.add('hidden');
  document.getElementById('setup-panel').classList.remove('hidden');
}

// -------------------------------------------------------------------------- //
// Wire up buttons
// -------------------------------------------------------------------------- //

document.getElementById('btn-start').addEventListener('click', startGame);
document.getElementById('btn-new').addEventListener('click', showSetup);
document.getElementById('btn-result-new').addEventListener('click', showSetup);
document.getElementById('btn-undo').addEventListener('click', undoMove);

initToggleGroups();
