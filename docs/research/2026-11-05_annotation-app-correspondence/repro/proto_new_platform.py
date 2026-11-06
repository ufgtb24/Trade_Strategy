"""原型(可行性探针,不求好用):照用户写的定义粗糙实现「站上新平台」识别器,看它的跨度能不能和用户框对齐。

用户的定义(标注里原文):
  特征「站上新平台」:股价呈现明显的两段台阶走势;稳定到一个比之前稳定价位更高的价位。
  pattern new_step:一根或者几根大幅上涨的强势K线比左右两侧的波动率都高,右侧在企稳后站上新平台。
                    构成跃迁函数的竖线相比于两侧非常强势,大涨幅,放量。

翻成逐日、只看当天及以前的判断(t = 判断日):
  1. 阶跃:连续 1~3 根 K 线,累计涨幅 >= STEP_MIN,且其中最大单日涨幅 >= SPIKE_K × 阶跃前 20 天单日涨跌幅绝对值的中位数
     (「竖线比左侧波动率高」)。阶跃的量比只记录不筛选(属性「平台交界放量」单独核对)。
  2. 旧平台水平 L = 阶跃前 20 天收盘中位数。台阶高度 H = log(阶跃末根收盘 / L)。
  3. 新平台(阶跃末根之后到 t,至少 MIN_RIGHT 根):
     a. 站住:这段里最低收盘没有回落超过台阶高度的一半,即 log(最低收盘 / L) >= 0.5H;
     b. 平:这段里收盘的高低差(取 log)<= FLAT_FRAC × H(「比之前稳定价位更高、且稳定」,平不平按台阶高度量,不按固定百分比);
     c. 没再起飞:t 当天收盘没有比新平台中位数再高出 0.5H(否则是下一级台阶,不算这个新平台)。
  4. 框 = [旧平台起点, t]。旧平台起点:从阶跃前一根往回走,收盘落在 L 上下 0.5H 带内就继续,连续 3 根出带才停
     (「两段台阶」的左段,宽窄也按台阶高度量)。

所有阈值是拍的(STEP_MIN、SPIKE_K、FLAT_FRAC 等),只为回答「能不能对齐、难在哪」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import load_state, load_win, d2i, i2d, EXCLUDED_SAMPLES  # noqa: E402
from path2.calc.volume import calculate_vol_ratio  # noqa: E402

STEP_MIN = np.log(1.25)   # 阶跃累计涨幅下限(拍的)
SPIKE_K = 4.0             # 最大单日涨幅 / 左侧日波动中位数(拍的)
MAX_STEP_BARS = 3
LEFT_N = 20
MIN_RIGHT = 2
FLAT_FRAC = 0.6           # 新平台收盘高低差 <= 0.6 × 台阶高度(拍的)
MAX_RIGHT = 40


def find_steps(lc: np.ndarray):
    """返回 [(s, e)]:阶跃首末根下标。同一段只留累计涨幅最大的那个;相邻候选按末根去重。"""
    r = np.diff(lc, prepend=np.nan)
    out = []
    n = len(lc)
    for e in range(LEFT_N + 1, n):
        best = None
        for k in range(1, MAX_STEP_BARS + 1):
            s = e - k + 1
            if s - LEFT_N < 1:
                break
            gain = lc[e] - lc[s - 1]
            if gain < STEP_MIN:
                continue
            left_abs = np.nanmedian(np.abs(r[s - LEFT_N:s]))
            spike = np.nanmax(r[s:e + 1])
            if left_abs > 0 and spike >= SPIKE_K * left_abs and r[e] > 0:
                if best is None or gain > best[2]:
                    best = (s, e, gain)
        if best:
            out.append(best[:2])
    # 去重:重叠的候选(后一个的 s <= 前一个的 e)只留末根更晚的(阶跃还在继续)
    ded = []
    for s, e in out:
        if ded and s <= ded[-1][1] + 1:
            ded[-1] = (min(ded[-1][0], s), e)
        else:
            ded.append((s, e))
    return ded


def new_platform_days(lc: np.ndarray, s: int, e: int):
    """给定阶跃 [s, e],逐日判断 t 是否「站在新平台上」。返回 (L, H, {t: (ok, reason)}, 旧平台起点)。"""
    L = float(np.median(lc[s - LEFT_N:s]))
    H = float(lc[e] - L)
    res = {}
    for t in range(e + 1, min(e + MAX_RIGHT, len(lc) - 1) + 1):
        seg = lc[e + 1:t + 1]
        if len(seg) < MIN_RIGHT:
            res[t] = (False, "新平台根数不够")
            continue
        if seg.min() - L < 0.5 * H:
            res[t] = (False, "回落超过台阶一半")
            # 跌回去之后不再算这个新平台
            for t2 in range(t + 1, min(e + MAX_RIGHT, len(lc) - 1) + 1):
                res[t2] = (False, "已跌回")
            break
        if seg.max() - seg.min() > FLAT_FRAC * H:
            res[t] = (False, "新平台不平(高低差超过台阶的 0.6)")
            continue
        if lc[t] - float(np.median(seg)) > 0.5 * H:
            res[t] = (False, "再起飞")
            continue
        res[t] = (True, "")
    # 旧平台起点
    band = 0.5 * H
    j, out_run = s - 1, 0
    start = s - 1
    while j > 0:
        if abs(lc[j] - L) <= band:
            start, out_run = j, 0
        else:
            out_run += 1
            if out_run >= 3:
                break
        j -= 1
    return L, H, res, start


def main():
    s_, fname = load_state()
    rows = []
    for c in s_["charts"]:
        sym = c["symbol"]
        win = load_win(sym)
        lc = np.log(win["close"].values.astype(float))
        vr = calculate_vol_ratio(win["volume"], 63).values
        steps = find_steps(lc)
        info = {}
        for (s, e) in steps:
            info[(s, e)] = new_platform_days(lc, s, e)
        # 全历史:每个阶跃之后「站在新平台上」的天数
        n_steps_with_np = sum(1 for k, v in info.items() if any(ok for ok, _ in v[2].values()))
        print(f"\n===== {sym}: 全历史阶跃候选 {len(steps)} 个,其中之后出现过「站在新平台上」的 {n_steps_with_np} 个")
        for b in c["boxes"]:
            if fname[b["feature"]] != "站上新平台":
                continue
            b0, b1 = d2i(win, b["start"]), d2i(win, b["end"])
            cand = [(k, v) for k, v in info.items() if b0 <= k[1] <= b1]
            print(f"  BOX {b['id']} {b['start']}..{b['end']}")
            if not cand:
                print("    框内没有阶跃候选")
                rows.append((sym, b["id"], b["start"], b["end"], None))
                continue
            for (s, e), (L, H, res, start) in cand:
                ok_days = [t for t, (ok, _) in sorted(res.items()) if ok]
                runs = []
                for t in ok_days:
                    if runs and t == runs[-1][1] + 1:
                        runs[-1][1] = t
                    else:
                        runs.append([t, t])
                vmax = np.nanmax(vr[s:e + 1])
                print(f"    阶跃 {i2d(win, s)}..{i2d(win, e)} 涨 {np.exp(lc[e] - lc[s - 1]) - 1:+.0%} 量比max {vmax:.1f}"
                      f" | 旧平台水平 {np.exp(L):.3f} 台阶 {np.exp(H) - 1:+.0%} | 旧平台起点 {i2d(win, start)}"
                      f"(用户框起点 {b['start']},差 {start - b0:+d} 根)")
                print("    站在新平台上的日子: " + ("; ".join(f"{i2d(win, a)}..{i2d(win, z)}" for a, z in runs) or "无"))
                for x in c["samples"]:
                    if x["date"] < b["start"] or b["id"] not in x["members"]:
                        continue
                    t = d2i(win, x["date"])
                    ex = "(已排除)" if (sym, x["date"]) in EXCLUDED_SAMPLES else ""
                    st = res.get(t, (False, "不在阶跃后 40 根内" if t > e else "在阶跃之前"))
                    print(f"      样本 {x['date']}{ex}: {'是' if st[0] else '否'} {st[1]}")
                rows.append((sym, b["id"], b["start"], b["end"], (s, e, start, runs)))
        # 框外的阶跃候选(全历史里还有哪些地方会被认成「站上新平台」)
        boxed = {k for k in info if any(d2i(win, b['start']) <= k[1] <= d2i(win, b['end']) for b in c['boxes'])}
        extra = [(k, v) for k, v in info.items() if k not in boxed and any(ok for ok, _ in v[2].values())]
        print(f"  框外也被认成「站上新平台」的阶跃: " + "; ".join(
            f"{i2d(win, k[0])}..{i2d(win, k[1])}({np.exp(lc[k[1]] - lc[k[0] - 1]) - 1:+.0%})" for k, _ in extra))
    return rows


if __name__ == "__main__":
    main()
