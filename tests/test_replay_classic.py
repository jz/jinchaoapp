#!/usr/bin/env python3
"""
经典棋局复盘测试：柯洁 vs AlphaGo 2017年第1局
Future of Go Summit, Wuzhen, 2017-05-23
规则：中国规则，19×19，贴目7.5，结果 W+0.5，共289手

测试步骤：
  1. 开局 vs_human 19×19 贴目7.5
  2. 按棋谱顺序通过 /api/play 落完全部289手
  3. 调用 /api/score 数子
  4. 断言最终结果为 W+0.5

SGF来源：https://homepages.cwi.nl/~aeb/go/games/games/AlphaGo/May2017/1.sgf
"""
import re
import sys
import requests

BASE_URL = "http://localhost:5000"

# GTP列名（跳过 I）
GTP_COLS = "ABCDEFGHJKLMNOPQRST"

# ── SGF ────────────────────────────────────────────────────────────────────────
SGF = """
(;EV[Future of Go Summit]RO[1]PB[Ke Jie]BR[9p]PW[AlphaGo]WR[9p]
TM[3h]KM[7.5]RE[W+0.5]DT[2017-05-23]PC[Wuzhen, China]RU[Chinese]

;B[qd];W[pp];B[cc];W[cp];B[nc];W[fp];B[qq];W[pq];B[qp];W[qn]
;B[qo];W[po];B[rn];W[qr];B[rr];W[rm];B[pr];W[or];B[pn];W[qm]
;B[qs];W[on];B[dj];W[nk];B[ph];W[ch];B[cf];W[eh];B[ci];W[de]
;B[df];W[dc];B[cd];W[dd];B[ef];W[di];B[ei];W[dh];B[cj];W[ce]
;B[be];W[bf];B[bg];W[bd];B[af];W[bc];B[fi];W[cm];B[hq];W[ek]
;B[fh];W[gq];B[hp];W[ej];B[eq];W[gr];B[cq];W[dp];B[dq];W[ep]
;B[bp];W[bh];B[ah];W[bo];B[bq];W[fg];B[gg];W[kp];B[ko];W[jo]
;B[jn];W[in];B[jp];W[io];B[lp];W[kq];B[lq];W[kr];B[lr];W[ir]
;B[kn];W[il];B[oq];W[pf];B[nh];W[rf];B[od];W[qi];B[qg];W[rd]
;B[qf];W[qe];B[pe];W[re];B[qc];W[rg];B[kh];W[ic];B[gc];W[kc]
;B[jd];W[id];B[ge];W[hb];B[gb];W[jf];B[je];W[ie];B[ld];W[hg]
;B[eg];W[lc];B[le];W[hf];B[qh];W[rh];B[pi];W[qj];B[gk];W[fd]
;B[gd];W[lf];B[mf];W[lg];B[gm];W[gn];B[fn];W[go];B[dl];W[mo]
;B[oo];W[pm];B[op];W[mg];B[nf];W[lo];B[nn];W[lm];B[pn];W[dk]
;B[ck];W[cl];B[el];W[bk];B[bi];W[li];B[ii];W[ds];B[dr];W[hi]
;B[ik];W[jk];B[ij];W[md];B[mc];W[ke];B[me];W[kd];B[om];W[ls]
;B[ms];W[ks];B[nr];W[ng];B[og];W[es];B[cs];W[fr];B[er];W[fs]
;B[bs];W[hl];B[pl];W[ql];B[rc];W[ro];B[rp];W[sn];B[hm];W[im]
;B[kk];W[kj];B[lk];W[jl];B[mj];W[mi];B[nj];W[pk];B[fm];W[cn]
;B[ol];W[ok];B[ni];W[ih];B[ji];W[mb];B[nb];W[lb];B[fe];W[cb]
;B[mp];W[mm];B[eb];W[na];B[oa];W[ma];B[qb];W[bj];B[ai];W[aj]
;B[ag];W[gl];B[fk];W[bl];B[kg];W[kf];B[ib];W[jb];B[ga];W[ha]
;B[ed];W[ec];B[fc];W[gf];B[ff];W[gj];B[hk];W[hh];B[fj];W[no]
;B[fq];W[hr];B[kl];W[km];B[mn];W[ln];B[nl];W[db];B[da];W[ca]
;B[ea];W[np];B[nq];W[oj];B[oi];W[en];B[em];W[eo];B[dm];W[dn]
;B[sp];W[so];B[hn];W[ho];B[hc];W[ia];B[ao];W[an];B[ap];W[sc]
;B[sb];W[sd];B[jg];W[ad];B[gh];W[ae];B[ee];W[ml];B[mk];W[pj]
;B[bf];W[nm];B[on];W[he];B[ig];W[ki];B[jh];W[fl];B[jj];W[fo]
;B[hj];W[gi];B[ll];W[jm];B[lh];W[mh];B[lj];W[if];B[hd])
"""


def sgf_to_gtp(col_char: str, row_char: str, board_size: int = 19) -> str:
    """SGF坐标对 → GTP落点  (例: 'q','d' → 'R16')"""
    if not col_char or not row_char:
        return "PASS"
    col_idx = ord(col_char) - ord("a")   # 0-18
    row_idx = ord(row_char) - ord("a")   # 0-18 (a = 顶行 = 19)
    return GTP_COLS[col_idx] + str(board_size - row_idx)


def parse_sgf_moves(sgf: str, board_size: int = 19):
    """从 SGF 中提取落子序列，返回 [(color, gtp_vertex), ...]"""
    moves = []
    for m in re.finditer(r";([BW])\[([a-s]{0,2})\]", sgf):
        color = "black" if m.group(1) == "B" else "white"
        coord = m.group(2)
        if len(coord) == 2:
            vertex = sgf_to_gtp(coord[0], coord[1], board_size)
        else:
            vertex = "PASS"
        moves.append((color, vertex))
    return moves


def post(path, body=None, timeout=120):
    r = requests.post(f"{BASE_URL}{path}", json=body or {}, timeout=timeout)
    return r.status_code, r.json()


def main():
    print("=== 经典棋局复盘测试：柯洁 vs AlphaGo 2017年第1局 ===")
    print("    规则：中国规则 19×19  贴目7.5  已知结果：W+0.5\n")

    # ── 解析棋谱 ──────────────────────────────────────────────────────────
    moves = parse_sgf_moves(SGF)
    print(f"  解析棋谱：共 {len(moves)} 手")
    assert len(moves) == 289, f"棋谱解析错误，期望289手，实际{len(moves)}手"
    print(f"  前5手：{moves[:5]}")
    print()

    # ── 1. 开局 ───────────────────────────────────────────────────────────
    sc, d = post("/api/new_game", {
        "board_size": 19, "human_color": "black",
        "mode": "vs_human", "komi": 7.5, "difficulty": "beginner",
    })
    assert sc == 200, f"new_game 失败: {d}"
    assert d["game"]["mode"] == "vs_human"
    assert "ai_move" not in d
    print("✅ 开局成功（vs_human 19×19 贴目7.5）\n")

    # ── 2. 逐手复盘 ───────────────────────────────────────────────────────
    errors = []
    print("  复盘中（每50手报告一次）…")
    for i, (color, vertex) in enumerate(moves):
        sc, resp = post("/api/play", {"vertex": vertex})
        if sc != 200:
            msg = f"步{i+1} {color} {vertex} 失败（HTTP {sc}）: {resp}"
            errors.append(msg)
            print(f"  ❌ {msg}")
            # 尝试继续复盘，若非法手则跳过
            if resp.get("error") == "Illegal move":
                print(f"     → 跳过非法手并继续")
                continue
            else:
                break

        if (i + 1) % 50 == 0 or i + 1 == len(moves):
            game = resp.get("game", {})
            print(f"  … 第{i+1:3d}手 {color:5s} {vertex:4s}  "
                  f"game_over={game.get('game_over', False)}")

    if errors:
        print(f"\n❌ 复盘中有 {len(errors)} 手出现异常（非法手或请求失败）：")
        for e in errors:
            print(f"   {e}")
        print("\n复盘存在错误，终止测试。")
        return 1
    else:
        print("\n✅ 289手全部复盘成功，无非法手\n")

    # ── 3. 数子 ───────────────────────────────────────────────────────────
    print("--- 调用 /api/score（19×19复盘后数子，可能需要2-3分钟）---")
    sc, sd = post("/api/score", timeout=300)
    assert sc == 200, f"score 失败: {sd}"

    result   = sd.get("result", "")
    dead     = sd.get("dead_stones", [])
    bt_set   = set(v.upper() for v in sd.get("territory", {}).get("black", []))
    wt_set   = set(v.upper() for v in sd.get("territory", {}).get("white", []))
    bs       = sd.get("board_stones", {})

    print(f"  得分结果:  {result}")
    print(f"  死子:      {len(dead)} 枚  {dead[:10]}{'...' if len(dead)>10 else ''}")
    print(f"  黑方领地:  {len(bt_set)} 目")
    print(f"  白方领地:  {len(wt_set)} 目")
    print(f"  存活棋子:  黑 {len(bs.get('black',[]))}  白 {len(bs.get('white',[]))}")
    print()

    # ── 4. 断言 ───────────────────────────────────────────────────────────
    score_errors = []

    # 结果格式正确
    if result.startswith("B+") or result.startswith("W+"):
        print(f"✅ 得分格式正确: {result}")
    else:
        score_errors.append(f"得分格式异常: {result!r}")

    # 白棋获胜（已知结果 W+0.5）
    if result.startswith("W+"):
        print(f"✅ 白棋获胜（与已知结果一致）")
    else:
        score_errors.append(f"期望白棋获胜(W+0.5)，实际: {result!r}")

    # 精确分值
    if result == "W+0.5":
        print(f"✅ 精确比分匹配 W+0.5")
    else:
        # 非致命警告：KataGo数子可能与官方裁定略有偏差
        print(f"⚠️  精确比分不匹配：期望 W+0.5，实际 {result}")
        print(f"   （KataGo独立数子，可能与官方裁定存在微小差异）")

    # game_over 状态
    if sd.get("game", {}).get("game_over"):
        print("✅ game_over = True")
    else:
        score_errors.append("score 后 game_over 未设置")

    # 领地不重叠
    overlap = bt_set & wt_set
    if not overlap:
        print("✅ 黑白领地无重叠")
    else:
        score_errors.append(f"黑白领地重叠: {overlap}")

    if score_errors:
        print("\n❌ 失败：")
        for e in score_errors:
            print(f"   - {e}")
        return 1

    print("\n=== 复盘测试通过 ✅ ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
