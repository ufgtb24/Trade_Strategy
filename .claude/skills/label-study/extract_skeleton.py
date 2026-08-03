"""label-study 数据构建骨架:复制到研究目录后只改「特征口径区」,其余勿动。

产出 CSV:每行 = 一个去重后的 (symbol, tb, anchor_bo) 观测,含:
  - 标准控制列 m1_burst_runup / m2_depth_rel(已知信号,关2 用,勿删)
  - 你的特征列(在 compute_features 里实现,≥3 种口径)
  - label(直接取 match.forward_return,同时强制重算比对)

自检门(硬闸,不过即 raise,禁止绕过):
  1. label 重算:逐观测按 tb 窗重算 forward_return,与文件值 |diff|<1e-9 全数一致;
  2. 引擎不变量:m2_depth_atr >= pullback_min_atr(detector gate 恒成立)——证明索引对齐;
  任何一项失败 = 数据链路损坏,先修再谈统计。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/home/yu/PycharmProjects/Trade_Strategy")
sys.path.insert(0, str(REPO))

from path2.calc.atr import calculate_atr          # noqa: E402  与 detector 同源
from path2_web.data import slice_window           # noqa: E402

# ═══ 任务参数(按研究改) ═══
SCAN = REPO / "outputs/path2_web/scans/20260719T065545.json"
PATTERN_ID = "bottom_burst"
OUT_CSV = Path(__file__).parent / "dataset.csv"
HORIZON = None          # None = 取 scan.label_horizon
ATR_WINDOW = 14         # params.yaml tb.atr_window(引擎不变量自检用)
PULLBACK_MIN_ATR = 1.0  # params.yaml tb.pullback_min_atr(同上)


# ═══ 特征口径区(唯一需要编写的部分) ═══
def compute_features(win: pd.DataFrame, o: dict) -> dict:
    """输入:win(切好的 OHLCV DataFrame)+ o(基础观测,含 bo_idx/tb_start/tb_end/
    first_bo_idx/atr(bo-1 处 ATR14)等)。返回 {特征列名: 值}。

    纪律:
      - 每个概念 ≥3 种口径(相对价格 / ATR 归一 / 比例式等),口径间强弱排序本身是机制信息;
      - 只准用 tb_start 及之前的 bar(买入时点已知);要用更晚信息必须列名加 posthoc_ 前缀;
      - 除法要守护分母(<=0 → np.nan)。
    """
    raise NotImplementedError("在此实现特征口径族")


# ═══ 以下勿改 ═══

def _forward_return(high, close, t0, t1, horizon, n):
    rets = [float(high[t + 1:t + horizon + 1].max()) / float(close[t]) - 1.0
            for t in range(t0, t1 + 1) if t + horizon < n]
    return sum(rets) / len(rets) if rets else None


def main() -> pd.DataFrame:
    blob = json.loads(SCAN.read_text())
    ws, we = blob["scan"]["win_start"], blob["scan"]["win_end"]
    horizon = HORIZON or blob["scan"]["label_horizon"]

    obs: dict = {}
    for rr in blob["results"]:
        pp = rr["per_pattern"].get(PATTERN_ID)
        if not pp or not pp["analysis"]["matches"]:
            continue
        evs = {e["event_id"]: e for e in pp["analysis"]["events"]}
        for md in pp["analysis"]["matches"]:
            tb = evs[md["node_index"]["tb"]]
            burst = evs[md["node_index"]["burst"]]
            bo = evs[tb["anchor_bo_id"]]
            key = (rr["symbol"], tb["event_id"], tb["anchor_bo_id"])
            if key in obs:
                continue
            obs[key] = dict(
                symbol=rr["symbol"], tb_id=tb["event_id"], bo_id=tb["anchor_bo_id"],
                bo_idx=bo["end_idx"], tb_start=tb["start_idx"], tb_end=tb["end_idx"],
                first_bo_idx=evs[burst["child_refs"]["members"][0]]["end_idx"],
                burst_count=burst.get("count"), bo_drought=bo.get("drought"),
                bo_vol_ratio=bo.get("vol_ratio"), label=md["forward_return"],
            )
    print(f"unique obs={len(obs)}  symbols={len({o['symbol'] for o in obs.values()})}")

    by_sym: dict = {}
    for o in obs.values():
        by_sym.setdefault(o["symbol"], []).append(o)

    rows, n_lab_fail, n_gate_fail = [], 0, 0
    for sym, lst in by_sym.items():
        win = slice_window(pd.read_pickle(REPO / "datasets/pkls" / f"{sym}.pkl"), ws, we)
        high = win["high"].to_numpy(float); low = win["low"].to_numpy(float)
        close = win["close"].to_numpy(float)
        atr = calculate_atr(win["high"], win["low"], win["close"], ATR_WINDOW).to_numpy(float)
        n = len(win)
        for o in lst:
            b, t0, t1 = o["bo_idx"], o["tb_start"], o["tb_end"]
            if b < 1 or t0 >= n:
                continue
            a = atr[b - 1]
            if not np.isfinite(a) or a <= 0:
                continue
            o = dict(o, atr=a)
            # 标准控制列(已知信号,勿删)
            peak_high = high[b:t0 + 1].max()
            depth = peak_high - low[t0]
            o["m2_depth_rel"] = depth / peak_high
            o["m2_depth_atr"] = depth / a
            fb = o["first_bo_idx"]
            o["m1_burst_runup"] = close[b] / close[fb - 1] - 1 if fb >= 1 else np.nan
            # 自检 1:label 重算
            lab_re = _forward_return(high, close, t0, t1, horizon, n)
            if not (lab_re is not None and o["label"] is not None
                    and abs(lab_re - o["label"]) < 1e-9):
                n_lab_fail += 1
            # 自检 2:引擎不变量
            if o["m2_depth_atr"] < PULLBACK_MIN_ATR - 1e-9:
                n_gate_fail += 1
            o.update(compute_features(win, o))
            rows.append(o)

    if n_lab_fail or n_gate_fail:
        raise AssertionError(
            f"自检门失败:label 重算不一致 {n_lab_fail} 例,引擎不变量违背 {n_gate_fail} 例。"
            f"数据链路损坏(窗口/索引/参数不对齐),禁止进统计。")
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"自检门通过(label 重算 {len(rows)}/{len(rows)} 一致,不变量 0 违背)")
    print(f"rows={len(df)} -> {OUT_CSV}")
    return df


if __name__ == "__main__":
    main()
