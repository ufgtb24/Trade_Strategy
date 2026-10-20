"""04 幸存者偏差票：数值推演（纯模拟，不读任何真实股票的未来涨跌）。

问题：同日同波动档对照下，数据里缺了「以后会因业绩被摘牌」的股票，
一个 pattern 的「方向领先」（首次穿越：先涨比例 − 先跌比例，减同档对照）会被抬高多少。

两步：
  A. 一只「以后会被摘牌」的股票，在某个买入日之后 40 个交易日里，方向得分比同档幸存股低多少（记 G）。
     用随机游走模拟：日波动 s、窗口内平均下行漂移 mu40；上下线按尺子：close×(1+5M) 与 close/(1+5M)，
     按收盘判先触哪条。s 与 M 的比例取本地数据最高波动档实测的 0.69（04-universe_facts 同口径，只用过去数据）。
     重尾版本用自由度 3 的 t 分布（同方差）做对照。
  B. 偏差 ≈ (h_X − h_q) × G：h_X = pattern 买点里本该有、却因以后被摘牌而缺掉的比例，
     h_q = 同日同档普通股里的同一比例。h 的取值区间来自研究文件里的文献与本地事实，这里只做网格。

运行：uv run python .scratch/selection-pattern/scripts/04-bias_sim.py
输出：同目录 04-bias_sim_out.txt
"""
import os

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "04-bias_sim_out.txt")
H = 40
K = 5.0
SD_OVER_M = 0.69
N_PATH = 200_000
SEED = 4


def direction(mu40, m, tails="normal", n=N_PATH, seed=SEED):
    rng = np.random.default_rng(seed)
    s = SD_OVER_M * m
    if tails == "normal":
        z = rng.standard_normal((n, H))
    else:
        z = rng.standard_t(3, (n, H)) / np.sqrt(3.0)   # 方差归一
    steps = mu40 / H + s * z
    path = np.cumsum(steps, axis=1)
    b = np.log1p(K * m)
    up_hit = path >= b
    dn_hit = path <= -b
    iu = np.where(up_hit.any(1), up_hit.argmax(1), H)
    idn = np.where(dn_hit.any(1), dn_hit.argmax(1), H)
    up = (iu < idn).mean()
    dn = (idn < iu).mean()
    max_up = np.expm1(np.maximum(path.max(1), 0))
    return up, dn, up - dn, float(np.median(max_up))


def main():
    lines = []
    w = lines.append
    w("== A. 以后会被摘牌的股票 vs 幸存股：40 日方向得分与最大涨幅中位（模拟）==")
    w("M = 同档 TR/close 20 日中位；mu40 = 窗口内平均对数漂移（负 = 往下走）")
    for m, label in [(0.086, "最高波动档（本地中位 M≈0.086，上线 +43%、下线 −30%）"),
                     (0.053, "次高档（M≈0.053，上线 +26%、下线 −21%）")]:
        for tails in ["normal", "t3"]:
            w(f"-- {label}，{'正态' if tails == 'normal' else '重尾 t3'} --")
            base = direction(0.0, m, tails)
            w(f"  幸存股（漂移 0）：先涨 {base[0]:.3f} 先跌 {base[1]:.3f} 方向 {base[2]:+.3f} 最大涨幅中位 {base[3]:.3f}")
            for mu40 in [-0.04, -0.08, -0.16, -0.24, -0.32]:
                r = direction(mu40, m, tails)
                w(f"  漂移 {mu40:+.2f}（≈年化 {mu40 * 252 / H:+.1f}）：方向 {r[2]:+.3f}，差 G = {base[2] - r[2]:.3f}；"
                  f"最大涨幅中位 {r[3]:.3f}（差 {base[3] - r[3]:.3f}）")
    w("")
    w("== B. 偏差网格：方向领先被抬高 ≈ (h_X − h_q) × G ==")
    gs = [0.15, 0.25, 0.40]
    w("行：pattern 与同档对照「缺掉的以后摘牌股比例」之差 h_X − h_q；列：G")
    w("            " + "  ".join(f"G={g:.2f}" for g in gs))
    for dh in [-0.05, 0.0, 0.02, 0.05, 0.10, 0.15]:
        w(f"  Δh={dh:+.2f}  " + "  ".join(f"{dh * g:+.3f} " for g in gs))
    w("")
    w("== C. 按买入日到数据末日的距离：同档对照里缺掉的比例 h_q 的推算 ==")
    w("f = 买入日在市、到 2026-10-05 前因业绩被摘牌的比例；c = 这些股里买入日落在最高波动档的比例")
    w("h_q(最高档) ≈ f·c / (f·c + 0.2·(1−f))（档宽 20%，幸存股部分近似占满本档）")
    for f, when in [(0.02, "2026 年初买入（剩 ~0.75 年）"), (0.06, "2024 年中（剩 ~2.3 年）"),
                    (0.10, "2023 年初（剩 ~3.75 年）"), (0.13, "2022 年初（剩 ~4.75 年）")]:
        for c in [0.5, 0.7]:
            hq = f * c / (f * c + 0.2 * (1 - f))
            w(f"  {when}: f={f:.2f} c={c:.1f} → h_q ≈ {hq:.2f}")
    w("")
    w("== D. 大跌后状态 vs 同档：h_X 的推算 ==")
    w("b_s = 幸存股里同档股票日处于大跌后状态的比例（本地实测：最高档 0.42）；")
    w("b_d = 以后被摘牌的股票在同档时处于大跌后状态的比例（假设 0.6 / 0.75 / 0.9）")
    w("h_X = h_q·b_d / (h_q·b_d + (1−h_q)·b_s)")
    b_s = 0.42
    for hq in [0.05, 0.15, 0.25, 0.35]:
        parts = []
        for b_d in [0.6, 0.75, 0.9]:
            hx = hq * b_d / (hq * b_d + (1 - hq) * b_s)
            parts.append(f"b_d={b_d:.2f}: h_X={hx:.2f} Δh={hx - hq:+.2f}")
        w(f"  h_q={hq:.2f}: " + "；".join(parts))

    w("")
    w("== E. 幅度（窗口内最大涨幅的中位）被抬高多少：混合分布中位数直接算 ==")
    w("最高波动档；幸存股漂移 0，以后被摘牌的股票漂移 −1.0/年（mu40=−0.16）；正态")
    rng = np.random.default_rng(SEED)
    m = 0.086
    s = SD_OVER_M * m

    def max_up(mu40, n):
        path = np.cumsum(mu40 / H + s * rng.standard_normal((n, H)), axis=1)
        return np.expm1(np.maximum(path.max(1), 0))

    surv, dead = max_up(0.0, N_PATH), max_up(-0.16, N_PATH)

    def mixed_median(h):
        k = int(round(h * N_PATH))
        return float(np.median(np.concatenate([surv[: N_PATH - k], dead[:k]])))

    # 前四组对应「跌掉七成以上」，后两组对应「跌掉九成以上」（h_X 由第 D 节公式按 b_d=0.45、b_s=0.13 算）
    for hq, hx in [(0.05, 0.09), (0.15, 0.24), (0.25, 0.37), (0.30, 0.45), (0.25, 0.54), (0.30, 0.59)]:
        obs = float(np.median(surv))
        true_gap = mixed_median(hx) - mixed_median(hq)
        w(f"  h_q={hq:.2f} h_X={hx:.2f}: 只看幸存股时两边中位都是 {obs:.3f}（领先 0）；"
          f"补全后 pattern 中位 − 对照中位 = {true_gap:+.4f} → 幅度领先被抬高 {-true_gap:.4f}")

    out = "\n".join(lines)
    print(out)
    with open(OUT, "w") as fh:
        fh.write(out + "\n")


if __name__ == "__main__":
    main()
