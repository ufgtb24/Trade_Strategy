"""feature-study 数据构建骨架:复制到研究目录后只改「特征口径区」,其余勿动。

产出 CSV:每行 = 一个去重后的 (symbol, tb_instance, anchor_bo) 观测,含:
  - 标准控制列 m1_burst_runup / m2_depth_rel(已知信号,关2 用,勿删)
  - 你的特征列(在 compute_features 里实现,≥3 种口径)
  - label(官方 match_forward_returns 重算,并与 scan 文件逐 match 对齐)
  - tb_date(tb_start 对应日期,双维去簇的事件诊断可读用;各股 win 同一切窗,tb_start 序号跨股可比)

自检门(硬闸,不过即 raise,禁止绕过;底座等价先行的机器化):
  1. match 集对齐:重放(经 serialize 同口径窗/价格过滤)match_id 集合 == scan 文件
     match_id 集合(防参数/引擎/数据漂移);
  2. label 对齐:逐 match 官方 API 重算 vs scan forward_return,<1e-12 全数一致。
  任何一项失败 = 底座不等价,后续统计全部无效。

2026-08-20 从 label-study 复活重写:instance-id 寻址(旧 event_id 已消灭)、
label 改官方 match_forward_returns(含 sample_window,旧手写口径已不一致)、
窗口/数据路径/过滤口径直接读 scan 的 win_start/win_end/dataset_dir/filters
(勿手写缓冲,换 scan 时零修改)。首次使用已在 20260818T110622(bb_v1,66 股)
端到端验收:66/66 股 match 集对齐、label 逐 match <1e-12。
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]   # skill 目录 → repo root
sys.path.insert(0, str(REPO))

from path2.calc.atr import calculate_atr          # noqa: E402  与 detector 同源
from path2.dag.engine import analyze as dag_analyze   # noqa: E402
from path2.eval import match_forward_returns       # noqa: E402
from path2_web.serialize import _resolve_end_events   # noqa: E402  与 serialize 同口径过滤
# ↓ pattern 依赖:换 PATTERN_ID 时同步换这两行 import(其余骨架 pattern 无关)
from path2_apps.bb_v1.dag_spec import build_pattern   # noqa: E402
from path2_apps.bb_v1.params import Params         # noqa: E402
from path2_web.data import slice_window            # noqa: E402

# ═══ 任务参数(按研究改) ═══
SCAN = REPO / "outputs/path2_web/scans/20260818T110622.json"
PATTERN_ID = "bb_v1"          # scan 里的 pattern id
END_NODE = "tb"               # pattern 的 end_node(eval_meta 口径;label 买点窗锚)
OUT_CSV = Path(__file__).parent / "dataset.csv"
VOL_WINDOW = 14               # 控制列的 ATR 窗(此处仍用 calculate_atr Wilder RMA,非 tb detector 的 median TR);
                               # 数值沿用 params tb.vol_window(2026-08-25 tb_v1 换代前该参数叫 atr_window)
# ⚠ Params.from_dict 对快照缺失的键会注入「当前代码默认值」——scan 早于某参数引入时
# 该参数被静默启用,重放 match 集必失配。按当次 scan 快照实情显式声明,例:
#   毒药闸(max_day_drop_pct)在 20260818T110622 快照中不存在(引入于 2026-08-18 下午),
#   故显式置 None;你的 scan 若已含该键,删掉此行即可。
TB_OVERRIDES = dict(max_day_drop_pct=None)


# ═══ 特征口径区(唯一需要编写的部分) ═══
def compute_features(win: pd.DataFrame, o: dict) -> dict:
    """输入:win(切好的 OHLCV DataFrame)+ o(基础观测,含 bo_idx/tb_start/tb_end/
    first_bo_idx/atr(bo-1 处 ATR)等)。返回 {特征列名: 值}。

    纪律:
      - 每个概念 ≥3 种口径(相对价格 / ATR 归一 / 比例式等),口径间强弱排序本身是机制信息;
      - 只准用 tb_start 及之前的 bar(买入时点已知);要用更晚信息必须列名加 posthoc_ 前缀;
      - 除法要守护分母(<=0 → np.nan)。
    """
    raise NotImplementedError("在此实现特征口径族")


# ═══ 以下勿改 ═══

def main() -> pd.DataFrame:
    blob = json.loads(SCAN.read_text())
    meta = blob["scan"]
    s, e = pd.to_datetime(meta["start_date"]), pd.to_datetime(meta["end_date"])
    horizon = meta["label_horizon"]
    filters = meta.get("filters", {})
    pmin, pmax = filters.get("price_min"), filters.get("price_max")
    ws, we = pd.to_datetime(meta["win_start"]), pd.to_datetime(meta["win_end"])
    data_dir = Path(meta["dataset_dir"])

    params = Params.from_dict(blob["per_pattern"][PATTERN_ID]["params_snapshot"])
    if TB_OVERRIDES:
        params = replace(params, tb=replace(params.tb, **TB_OVERRIDES))

    # scan 侧观测清单(去重键 = symbol + tb instance + anchor bo)
    scan_ids: dict[str, set] = {}
    for rr in blob["results"]:
        pp = rr["per_pattern"].get(PATTERN_ID)
        if not pp or not pp["analysis"]["matches"]:
            continue
        scan_ids[rr["symbol"]] = {m["match_id"]
                                  for m in pp["analysis"]["matches"]}

    rows, n_lab_fail, mset_fail = [], 0, []
    for sym, ids in scan_ids.items():
        win = slice_window(pd.read_pickle(data_dir / f"{sym}.pkl"), ws, we)
        res = dag_analyze(build_pattern(params), win, params)
        lo = int(win["date"].searchsorted(s, "left"))
        hi = int(win["date"].searchsorted(e, "right")) - 1
        # 自检 1 前置:serialize 同口径过滤(任一 end_node 事件起点 ∈ 窗 + 任一起点日
        # 收盘价 ∈ [pmin,pmax] 闭区间;serialize.py:341-351 同款)
        live, kept = set(), []
        for m in res.matches:
            events = _resolve_end_events(m, END_NODE)
            if not any(s <= win["date"].iat[ev.start_idx] <= e for ev in events):
                continue
            closes = [float(win["close"].iat[ev.start_idx]) for ev in events]
            if not any((pmin is None or c >= pmin) and
                       (pmax is None or c <= pmax) for c in closes):
                continue
            live.add(m.match_id)
            kept.append(m)
        if live != ids:
            mset_fail.append((sym, len(live), len(ids)))
            continue
        evs = {ev.instance_id: ev for ev in res.events}
        high = win["high"].to_numpy(float)
        low = win["low"].to_numpy(float)
        close = win["close"].to_numpy(float)
        atr = calculate_atr(win["high"], win["low"], win["close"],
                            VOL_WINDOW).to_numpy(float)
        n = len(win)
        pp = next(r["per_pattern"][PATTERN_ID] for r in blob["results"]
                  if r["symbol"] == sym)
        scan_lab = {m["match_id"]: m["forward_return"]
                    for m in pp["analysis"]["matches"]}
        seen: set = set()
        for m in kept:
            tb = m.node_index["tb"]
            burst = m.node_index["burst"]
            key = (sym, tb.instance_id, tb.anchor_bo_id)
            if key in seen:
                continue
            seen.add(key)
            bo = evs[tb.anchor_bo_id]
            # members 存完整 BOEvent 对象(breakout.BurstEvent.members)——直接属性访问,
            # 架构再变让它炸 AttributeError,不要 getattr 吞漂移
            first_bo = burst.members[0] if burst.members else bo
            b, t0, t1 = bo.end_idx, tb.start_idx, tb.end_idx
            if b < 1 or t0 >= n:
                continue
            a = atr[b - 1]
            if not np.isfinite(a) or a <= 0:
                continue
            o = dict(symbol=sym, tb_id=tb.instance_id, bo_id=tb.anchor_bo_id,
                     bo_idx=b, tb_start=t0, tb_end=t1,
                     tb_date=str(win["date"].iat[t0]),   # 时间桶诊断可读用(电池用 tb_start 序号)
                     first_bo_idx=first_bo.end_idx,
                     burst_count=getattr(burst, "count", None),
                     bo_drought=getattr(bo, "drought", None),
                     bo_vol_ratio=getattr(bo, "vol_ratio", None),
                     atr=a)
            # 标准控制列(已知信号,勿删;2026-07 tb 几何×label 研究所定)
            peak_high = high[b:t0 + 1].max()
            depth = peak_high - low[t0]
            o["m2_depth_rel"] = depth / peak_high if peak_high > 0 else np.nan
            o["m2_depth_atr"] = depth / a
            fb = o["first_bo_idx"]
            o["m1_burst_runup"] = (close[b] / close[fb - 1] - 1.0
                                   if fb >= 1 else np.nan)
            # 自检 2:label 官方重算 vs scan 值
            lab = match_forward_returns(m, "tb", win, [horizon],
                                        sample_window=(lo, hi))[horizon]
            ref = scan_lab.get(m.match_id)
            if lab is None and ref is None:
                continue   # 无 label(scan 窗口末端 horizon 不可见),非失配——跳过不统计
            if lab is None or ref is None or abs(lab - ref) >= 1e-12:
                n_lab_fail += 1
                continue
            o["label"] = float(ref)
            o.update(compute_features(win, o))
            rows.append(o)

    if mset_fail or n_lab_fail:
        raise AssertionError(
            f"自检门失败:match 集不对齐 {mset_fail or 0} 股"
            f"(先查 TB_OVERRIDES:快照早于参数引入时 from_dict 注入当前默认,"
            f"再疑引擎/数据漂移),label 不一致 {n_lab_fail} 例。"
            f"底座不等价,禁止进统计。")
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"自检门通过(match 集逐股对齐,label 重算 {len(rows)} 例全数 <1e-12)")
    print(f"rows={len(df)} symbols={df['symbol'].nunique()} -> {OUT_CSV}")
    return df


if __name__ == "__main__":
    main()
