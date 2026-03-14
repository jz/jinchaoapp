#!/usr/bin/env python3
"""
自对弈30轮测试 — 验证提子功能。
人类执黑，AI执白，脚本驱动黑棋下30轮，观察被吃棋子是否从棋盘消失。
"""
import sys
import requests

BASE_URL = "http://localhost:5000"

# 9x9 常见开局及中盘手，刻意制造战斗
MOVES = [
    "E5", "D4", "F6", "D6", "F4", "D3", "F3", "C3", "G3",
    "C4", "B4", "C5", "B5", "C6", "B6", "B3", "A3", "A4",
    "A5", "A6", "C2", "B2", "D2", "E2", "F2", "G2", "H2",
    "H3", "H4", "H5",
]

# 备用手：当预设手非法时轮流尝试
FALLBACK = [
    "G4", "G5", "G6", "G7", "H6", "H7", "E3", "E4", "E6",
    "E7", "F5", "F7", "D5", "D7", "C7", "B7", "A7", "A8",
    "B8", "C8", "D8", "E8", "F8", "G8", "H8", "A9", "B9",
    "C9", "D9", "E9",
]

def play(vertex):
    r = requests.post(f"{BASE_URL}/api/play", json={"vertex": vertex}, timeout=90)
    return r.status_code, r.json()


def main():
    print("=== 自对弈30轮提子测试 ===")
    print(f"服务器: {BASE_URL}\n")

    # 开局 9x9，入门难度（最快）
    r = requests.post(f"{BASE_URL}/api/new_game", json={
        "board_size": 9,
        "human_color": "black",
        "difficulty": "beginner",
        "komi": 7.5,
    }, timeout=30)
    data = r.json()
    if "error" in data:
        print(f"开局失败: {data['error']}")
        return 1

    if data.get("ai_move"):
        print(f"AI (白) 先手: {data['ai_move']['vertex']}")

    prev_b, prev_w = 0, 0
    captures_b = 0   # 白方被提子数（黑提白）
    captures_w = 0   # 黑方被提子数（白提黑）
    rounds_played = 0
    fallback_idx = 0
    move_queue = list(MOVES)

    for round_num in range(1, 31):
        # 选手
        if move_queue:
            vertex = move_queue.pop(0)
        elif fallback_idx < len(FALLBACK):
            vertex = FALLBACK[fallback_idx]
            fallback_idx += 1
        else:
            vertex = "PASS"

        status, resp = play(vertex)

        # 如果非法，尝试备用手
        if status == 400 and resp.get("error") in ("Illegal move", "Not your turn"):
            tried = [vertex]
            for fb in FALLBACK[fallback_idx:fallback_idx + 10]:
                fallback_idx += 1
                s2, r2 = play(fb)
                tried.append(fb)
                if s2 == 200:
                    vertex, status, resp = fb, s2, r2
                    break
            else:
                # 全都不行就 PASS
                vertex = "PASS"
                status, resp = play("PASS")

        if status != 200:
            print(f"轮 {round_num:2d}: 错误 — {resp}")
            break

        game = resp.get("game", {})
        board = resp.get("board_stones", {})
        ai_mv = resp.get("ai_move") or {}

        b_now = len(board.get("black", []))
        w_now = len(board.get("white", []))

        # 理论预期：双方各落1子，被提子则减少
        # Δ黑 = b_now - prev_b  应 ≥ +1（我们落了1子）；若更小说明黑子被提
        # Δ白 = w_now - prev_w  AI也落了1子；若 Δ白 < +1 说明白子被提
        db = b_now - prev_b
        dw = w_now - prev_w

        cap_note = ""
        if dw < 1 and prev_w > 0:   # AI落子后白反而没增加 → 黑提了白
            taken = 1 - dw
            captures_b += taken
            cap_note += f"  ⚡ 黑提白 {taken} 子"
        if db < 1 and prev_b > 0:   # 我落子后黑反而没增加 → 白提了黑
            taken = 1 - db
            captures_w += taken
            cap_note += f"  ⚡ 白提黑 {taken} 子"

        ai_vertex = ai_mv.get("vertex", "—") if ai_mv else "—"
        print(
            f"轮 {round_num:2d}: 黑={vertex:4s}  白={ai_vertex:4s} | "
            f"棋子 黑:{b_now:2d} 白:{w_now:2d} | Δ 黑:{db:+d} 白:{dw:+d}"
            f"{cap_note}"
        )

        prev_b, prev_w = b_now, w_now
        rounds_played += 1

        if game.get("game_over"):
            result = game.get("result", "?")
            print(f"\n对局结束: {result}")
            break

    print(f"\n=== 结果摘要 ===")
    print(f"实际对局轮数: {rounds_played}")
    print(f"黑提白: {captures_b} 子")
    print(f"白提黑: {captures_w} 子")
    print(f"终局棋盘: 黑 {prev_b} 子，白 {prev_w} 子")

    if captures_b + captures_w > 0:
        print("\n✅ 提子功能正常：被提棋子已从棋盘消失")
    else:
        print("\n⚠️  本局未发生提子（可能需要更激烈的手顺）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
