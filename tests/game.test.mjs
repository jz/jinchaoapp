/**
 * Frontend unit tests for pure logic in game.js.
 * Run with: node --test tests/game.test.js
 *
 * Tests the coordinate helpers and board geometry functions
 * without requiring a browser or DOM.
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";

// ── Pure functions extracted from game.js ─────────────────────────────────
// (Re-declared here to avoid DOM initialization at import time)

const COL_LABELS = "ABCDEFGHJKLMNOPQRST";

function cellToGTP(row, col, n) {
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

function formatResult(result) {
  if (!result) return "对局结束";
  if (result.startsWith("B+")) return `黑胜 ${result.slice(2)}`;
  if (result.startsWith("W+")) return `白胜 ${result.slice(2)}`;
  return result;
}

// Board geometry (matches game.js logic)
function computeLayout(n, windowWidth = 1200) {
  const maxCanvas = Math.min(windowWidth - 300, 620);
  let cellSize = Math.floor((maxCanvas - 2 * 30) / (n - 1));
  cellSize = Math.max(cellSize, 22);
  const padding = Math.round(cellSize * 1.8 * 0.6);
  return { cellSize, padding };
}

function cellToXY(row, col, cellSize, padding) {
  return { x: padding + col * cellSize, y: padding + row * cellSize };
}

function xyToCell(x, y, n, cellSize, padding) {
  const col = Math.round((x - padding) / cellSize);
  const row = Math.round((y - padding) / cellSize);
  if (row < 0 || col < 0 || row >= n || col >= n) return null;
  const { x: cx, y: cy } = cellToXY(row, col, cellSize, padding);
  if (Math.hypot(x - cx, y - cy) > cellSize * 0.5) return null;
  return { row, col };
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe("COL_LABELS", () => {
  test("skips I (GTP convention)", () => {
    assert.ok(!COL_LABELS.includes("I"), "I should be absent");
    assert.equal(COL_LABELS[7], "H");
    assert.equal(COL_LABELS[8], "J");
  });

  test("has 19 labels for a 19x19 board", () => {
    assert.equal(COL_LABELS.length, 19);
  });
});

describe("cellToGTP", () => {
  test("top-left corner is A19 on 19x19", () => {
    assert.equal(cellToGTP(0, 0, 19), "A19");
  });

  test("bottom-right corner is T1 on 19x19", () => {
    assert.equal(cellToGTP(18, 18, 19), "T1");
  });

  test("center of 9x9 is E5", () => {
    assert.equal(cellToGTP(4, 4, 9), "E5");
  });

  test("D4 on 19x19 maps correctly", () => {
    // D4: col=3 (D), row=15 (row = 19 - 4 = 15)
    assert.equal(cellToGTP(15, 3, 19), "D4");
  });
});

describe("gtpToCell", () => {
  test("A19 → top-left {row:0, col:0}", () => {
    assert.deepEqual(gtpToCell("A19", 19), { row: 0, col: 0 });
  });

  test("T1 → bottom-right on 19x19", () => {
    assert.deepEqual(gtpToCell("T1", 19), { row: 18, col: 18 });
  });

  test("PASS returns null", () => {
    assert.equal(gtpToCell("PASS", 19), null);
  });

  test("pass (lowercase) returns null", () => {
    assert.equal(gtpToCell("pass", 19), null);
  });

  test("resign returns null", () => {
    assert.equal(gtpToCell("resign", 19), null);
  });

  test("null returns null", () => {
    assert.equal(gtpToCell(null, 19), null);
  });

  test("out-of-board coord returns null", () => {
    assert.equal(gtpToCell("A20", 19), null);
    assert.equal(gtpToCell("U1", 19), null);
  });

  test("round-trips with cellToGTP", () => {
    for (const [r, c] of [[0,0],[4,4],[18,18],[3,15]]) {
      const gtp  = cellToGTP(r, c, 19);
      const cell = gtpToCell(gtp, 19);
      assert.deepEqual(cell, { row: r, col: c }, `round-trip failed for (${r},${c})`);
    }
  });
});

describe("formatResult", () => {
  test("null → 对局结束", () => {
    assert.equal(formatResult(null), "对局结束");
  });

  test("B+Resign → 黑胜 Resign", () => {
    assert.equal(formatResult("B+Resign"), "黑胜 Resign");
  });

  test("W+5.5 → 白胜 5.5", () => {
    assert.equal(formatResult("W+5.5"), "白胜 5.5");
  });

  test("unknown string passes through", () => {
    assert.equal(formatResult("认输"), "认输");
  });
});

describe("computeLayout", () => {
  test("returns positive cellSize and padding", () => {
    const { cellSize, padding } = computeLayout(19);
    assert.ok(cellSize > 0);
    assert.ok(padding > 0);
  });

  test("smaller board → larger cells", () => {
    const { cellSize: c9 }  = computeLayout(9);
    const { cellSize: c19 } = computeLayout(19);
    assert.ok(c9 >= c19, "9x9 should have larger cells than 19x19");
  });

  test("minimum cellSize is 22", () => {
    const { cellSize } = computeLayout(19, 320); // narrow screen
    assert.ok(cellSize >= 22);
  });
});

describe("cellToXY / xyToCell round-trip", () => {
  const { cellSize, padding } = computeLayout(19);

  test("exact cell center maps back to correct cell", () => {
    for (const [r, c] of [[0,0],[9,9],[18,18],[4,3]]) {
      const { x, y } = cellToXY(r, c, cellSize, padding);
      const result = xyToCell(x, y, 19, cellSize, padding);
      assert.deepEqual(result, { row: r, col: c });
    }
  });

  test("point near cell center (< 0.5 cellSize) snaps to cell", () => {
    const { x, y } = cellToXY(5, 5, cellSize, padding);
    const near = xyToCell(x + 1, y + 1, 19, cellSize, padding);
    assert.deepEqual(near, { row: 5, col: 5 });
  });

  test("point far from any center returns null", () => {
    // Place it exactly between four cells
    const { x, y } = cellToXY(5, 5, cellSize, padding);
    const far = xyToCell(x + cellSize * 0.6, y + cellSize * 0.6, 19, cellSize, padding);
    assert.equal(far, null);
  });

  test("out-of-board pixel returns null", () => {
    assert.equal(xyToCell(-1, -1, 19, cellSize, padding), null);
  });
});
