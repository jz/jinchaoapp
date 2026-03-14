#!/usr/bin/env python3
"""
双人对弈 + 数子全流程测试（9x9 棋盘）

棋谱设计（黑白交替，先黑后白）：
  黑棋围住左下角：E1-E5 竖墙 + A5-D5 横墙
    → 黑方领地 A1-D4（16 目）

  白棋围住右上角：F5-J5 横墙 + F6-F9 竖墙
    → 白方领地 G6-J9（12 目）

预期得分（中国规则）：
  黑：9子 + 16目 = 25
  白：9子 + 12目 + 贴目7.5 = 28.5
  白胜 3.5 → W+3.5

验证项：
  1. mode=vs_human，无 ai_move
  2. 每手落子后 turn 正确翻转
  3. 提子时棋子数正确减少（本谱无提子，验证无误报）
  4. 双虚手触发 game_over
  5. /api/score 返回有效得分
  6. 黑方领地包含 A1-D4 部分点
  7. 白方领地包含 G6-J9 部分点
"""
import sys
import requests

BASE_URL = "http://localhost:5000"

# 预期黑方领地（flood-fill 应返回这些点）
EXPECTED_BLACK_TERRITORY = {
    "A1","A2","A3","A4",
    "B1","B2","B3","B4",
    "C1","C2","C3","C4",
    "D1","D2","D3","D4",
}
# 预期白方领地
EXPECTED_WHITE_TERRITORY = {
    "G6","G7","G8","G9",
    "H6","H7","H8","H9",
    "J6","J7","J8","J9",
}

MOVES = [
    # 黑棋建左下角围墙；白棋建右上角围墙
    ("black", "E1"), ("white", "F5"),
    ("black", "E2"), ("white", "G5"),
    ("black", "E3"), ("white", "H5"),
    ("black", "E4"), ("white", "J5"),
    ("black", "E5"), ("white", "F6"),
    ("black", "D5"), ("white", "F7"),
    ("black", "C5"), ("white", "F8"),
    ("black", "B5"), ("white", "F9"),
    ("black", "A5"), ("white", "J1"),   # J1：白棋额外子，不影响围地
    # 双虚手结束
    ("black", "PASS"), ("white", "PASS"),
]


def post(path, body=None):
    r = requests.post(f"{BASE_URL}{path}",
                      json=body or {}, timeout=60)
    return r.status_code, r.json()


def main():
    print("=== 双人对弈 9x9 数子全流程测试 ===\n")

    # ── 1. 开局 ─────────────────────────────────────────────────────────
    sc, d = post("/api/new_game", {
        "board_size": 9, "human_color": "black",
        "difficulty": "beginner", "mode": "vs_human", "komi": 7.5,
    })
    assert sc == 200,                   f"new_game 失败: {d}"
    assert d["game"]["mode"] == "vs_human"
    assert "ai_move" not in d
    assert d["game"]["turn"] == "black"
    print("✅ 开局成功（vs_human 9x9 贴目7.5）\n")

    # ── 2. 落子 ─────────────────────────────────────────────────────────
    prev_b, prev_w = 0, 0
    false_captures = 0
    expected_turn = "black"

    for i, (color, vertex) in enumerate(MOVES):
        assert color == expected_turn, \
            f"步{i+1}: 脚本顺序错误（期望{expected_turn}，写的是{color}）"

        sc, resp = post("/api/play", {"vertex": vertex})
        assert sc == 200, f"步{i+1} {color} {vertex} 失败: {resp}"

        game  = resp["game"]
        board = resp.get("board_stones") or {}
        b_now = len(board.get("black", []))
        w_now = len(board.get("white", []))
        over  = game.get("game_over", False)

        next_color = "white" if color == "black" else "black"

        # turn 应已翻转（游戏结束时 turn 无意义，不检查）
        if not over and vertex.upper() != "PASS":
            assert game["turn"] == next_color, \
                f"步{i+1}: turn 应为 {next_color}，实为 {game['turn']}"

        # 提子检测（双虚手结束的那一手 board_stones 为空，需跳过）
        cap_note = ""
        if b_now == 0 and w_now == 0:
            pass   # game-over 响应不含 board_stones，跳过 delta 检查
        else:
            db, dw = b_now - prev_b, w_now - prev_w
            # 落子后本方棋子 +1（PASS 时 Δ=0 正常）
            if vertex.upper() == "PASS":
                pass
            elif color == "black" and db != 1:
                if dw < 0:
                    cap_note = f"  ⚡ 黑提白 {-dw} 子"
                else:
                    false_captures += 1
                    cap_note = f"  ⚠️ 异常 Δ黑={db}"
            elif color == "white" and dw != 1:
                if db < 0:
                    cap_note = f"  ⚡ 白提黑 {-db} 子"
                else:
                    false_captures += 1
                    cap_note = f"  ⚠️ 异常 Δ白={dw}"
            prev_b, prev_w = b_now, w_now

        print(f"  步{i+1:2d} {color:5s} {vertex:4s} | "
              f"存活 黑{b_now:2d} 白{w_now:2d}{cap_note}")

        expected_turn = next_color
        if over:
            print(f"\n  对局结束（步 {i+1}）")
            break

    assert false_captures == 0, f"检测到 {false_captures} 次异常棋子变化"
    print("\n✅ 落子过程无异常")

    # ── 3. game_over 状态确认 ────────────────────────────────────────────
    r = requests.get(f"{BASE_URL}/api/status", timeout=10)
    assert r.json()["game"]["game_over"], "双pass后 game_over 应为 True"
    print("✅ game_over = True")

    # ── 4. 数子 ─────────────────────────────────────────────────────────
    print("\n--- 调用 /api/score ---")
    sc, sd = post("/api/score")
    assert sc == 200, f"score 失败: {sd}"

    result = sd.get("result", "")
    dead   = sd.get("dead_stones", [])
    bt_set = set(v.upper() for v in sd.get("territory", {}).get("black", []))
    wt_set = set(v.upper() for v in sd.get("territory", {}).get("white", []))
    bs     = sd.get("board_stones", {})

    print(f"  得分结果:  {result}")
    print(f"  死子:      {dead}  ({len(dead)} 枚)")
    print(f"  黑方领地:  {sorted(bt_set)[:8]}... 共 {len(bt_set)} 目")
    print(f"  白方领地:  {sorted(wt_set)[:8]}... 共 {len(wt_set)} 目")
    print(f"  存活棋子:  黑 {len(bs.get('black',[]))}  白 {len(bs.get('white',[]))}")

    # ── 5. 断言 ─────────────────────────────────────────────────────────
    print()
    errors = []

    # 得分格式
    if result.startswith("B+") or result.startswith("W+"):
        print(f"✅ 得分格式正确: {result}")
    else:
        errors.append(f"得分格式异常: {result!r}")

    # game_over
    if sd["game"]["game_over"]:
        print("✅ score 后 game_over = True")
    else:
        errors.append("score 后 game_over 未设置")

    # 黑方领地包含预期的点
    black_hit = bt_set & EXPECTED_BLACK_TERRITORY
    if len(black_hit) >= 8:   # 至少覆盖一半预期点
        print(f"✅ 黑方领地命中预期 {len(black_hit)}/16 点")
    else:
        errors.append(f"黑方领地只命中预期 {len(black_hit)}/16 点: {black_hit}")

    # 白方领地包含预期的点
    white_hit = wt_set & EXPECTED_WHITE_TERRITORY
    if len(white_hit) >= 6:   # 至少覆盖一半预期点
        print(f"✅ 白方领地命中预期 {len(white_hit)}/12 点")
    else:
        errors.append(f"白方领地只命中预期 {len(white_hit)}/12 点: {white_hit}")

    # 领地不重叠
    overlap = bt_set & wt_set
    if not overlap:
        print("✅ 黑白领地无重叠")
    else:
        errors.append(f"黑白领地重叠: {overlap}")

    if errors:
        print("\n❌ 失败：")
        for e in errors:
            print(f"   - {e}")
        return 1

    print("\n=== 全部断言通过 ✅ ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
