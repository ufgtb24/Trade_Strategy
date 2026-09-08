# -*- coding: utf-8 -*-
"""feature-study 数据构建库:任意声明了 adapter 的 path2_apps app 可 import 使用,
从一份 scan 文件重放出研究用 dataset.csv(不再是「复制脚本改」的模板)。

两个入口:
  - load_adapter(app) —— 按文件路径加载 apps/<app>/adapter.py 声明。
  - build_dataset(adapter, *, scan, out_csv, compute_features, pattern_id=None,
    param_overrides=None) —— 用给定 adapter 重放出 dataset.csv。

列的归属划分:骨架统一注入五个通用列 —— symbol / entry_idx(买点在窗内的 bar
序号)/ entry_date / c0_atr_pct(冷启动通用波动率地板)/ label;app 特异的一切
(node 名、几何算式、已知信号列)封在 adapter.observe() 里,骨架本身不认识任何
具体走势的 node 名,也不出现任何 node 名字面量。

两道自检门(硬闸,不过即 raise,禁止绕过;底座等价先行的机器化):
  1. match 集对齐:重放(经 serialize 同口径窗/价格过滤)match_id 集合 == scan 文件
     match_id 集合(防参数/引擎/数据漂移);
  2. label 对齐:逐 match 官方 API 重算 vs scan forward_return,<1e-12 全数一致,
     覆盖全部通过过滤的 match(不止最终去重后留下的行)。
  任何一项失败 = 底座不等价,后续统计全部无效。

2026-09-08 从原骨架(硬编码单个 app 的复制模板)改造为走势-无关的可 import 库:
pattern 特异部分(node 名、几何算式、已知信号列)搬进
apps/<app>/adapter.py;骨架新增 c0_atr_pct 通用波动率地板(理由见
docs/feature_candidates.md FC-009:forward_return 的优势很大程度是波动率读数,
首轮研究时登记簿「已关闭」段常为空、控制列会退化成空集,这里给一个不依赖登记簿的
冷启动地板);entry_idx/entry_date 取代了原骨架里绑定单个具体 node 的字面时间列,
改用 _resolve_end_events 解析结果的 min(start_idx),对点号路径 end_node(父 node
的某个槽位,一组 child instance_id)同样成立。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import types
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]   # skill 目录 → repo root
sys.path.insert(0, str(REPO))

from path2.calc.atr import calculate_atr             # noqa: E402  与 detector 同源
from path2.dag.engine import analyze as dag_analyze  # noqa: E402
from path2.eval import match_forward_returns          # noqa: E402
from path2_web.serialize import _resolve_end_events    # noqa: E402  与 serialize 同口径过滤
from path2_web.data import slice_window                # noqa: E402

VOL_WINDOW = 14   # 通用波动率控制列的窗口。控制列不需要与 detector 同源,跟着
                  # pattern 参数走会让不同 pattern 的控制列不可比,故固定 14,不从
                  # params 取。

ADAPTER_NAMES = ("APP_MODULE", "PARAM_OVERRIDES", "DEDUP_COLS", "KNOWN_SIGNALS", "observe")

# 骨架统一注入的五个通用列;adapter.observe() 返回值里出现任何一个都是列归属错位。
_SKELETON_COLS = ("symbol", "entry_idx", "entry_date", "c0_atr_pct", "label")


def load_adapter(app: str):
    """从 apps/<app>/adapter.py 按文件路径加载。

    必须按路径加载(importlib.util.spec_from_file_location),不走 sys.path +
    from apps.<app> import adapter——.claude/skills/tune-gates/ 下也有
    apps/<app>/,两个 skill 目录的 apps/ 同时进 sys.path 时 Python 会把两边合并成
    一个命名空间包、互相遮蔽。同款解法见 .claude/skills/tune-gates/study_io.py 的
    load_study()(docstring 原话「不经 sys.path,避免多个 app 的 study.py 同名互相
    遮蔽」)。
    """
    path = Path(__file__).resolve().parent / "apps" / app / "adapter.py"
    spec = importlib.util.spec_from_file_location(f"feature_study_adapter_{app}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    missing = [n for n in ADAPTER_NAMES if not hasattr(mod, n)]
    if missing:
        raise ValueError(f"{path} 缺少声明: {missing}")
    return mod


def _apply_overrides(params, overrides: dict):
    """按 yaml section 分组的双层 dataclasses.replace,支持任意 section(不止一个)。"""
    for section, fields in overrides.items():
        sub = replace(getattr(params, section), **fields)
        params = replace(params, **{section: sub})
    return params


def build_dataset(adapter, *, scan, out_csv, compute_features,
                  pattern_id=None, param_overrides=None) -> pd.DataFrame:
    """从一份 scan 文件重放出研究用 dataset.csv,对任意声明了 adapter 的 app 通用。

    参数:
      adapter: load_adapter() 返回的模块,声明 APP_MODULE / PARAM_OVERRIDES /
        DEDUP_COLS / KNOWN_SIGNALS / observe(约定见 apps/_template/adapter.py)。
      scan: scan 文件路径(str 或 Path)。
      out_csv: 输出 CSV 路径(str 或 Path)。
      compute_features(win, row) -> dict: 每轮研究自己写的特征口径函数;拿到的
        row 已含骨架注入的五个通用列(含 label),返回值合并进最终行——保持这个
        先后顺序(label 先赋值、compute_features 后调用)是既有行为,不要调换。
      pattern_id: scan 里的 pattern id;None 时从 mod.PATTERN_DAG.pattern_id 推导
        (能推导的不让人填),显式传入则以传入为准。
      param_overrides: 覆盖 scan 快照参数,按 yaml section 分组(结构对齐
        Params.from_dict);None 时用 adapter.PARAM_OVERRIDES,传 dict 则整体覆盖
        它——这是给「同一个 app 换一份 vintage 不同的 scan」留的临时口子。

    返回:去重后的 DataFrame(同时写入 out_csv)。

    自检门失败、无一行产出、或 DEDUP_COLS 声明的列缺失,均直接 raise、不落盘
    (见模块 docstring 的两道自检门与红线)。
    """
    scan = Path(scan)
    out_csv = Path(out_csv)

    mod = importlib.import_module(adapter.APP_MODULE)
    build_pattern = mod.build_pattern
    Params = mod.Params
    eval_meta = mod.eval_meta

    blob = json.loads(scan.read_text())
    meta = blob["scan"]
    s, e = pd.to_datetime(meta["start_date"]), pd.to_datetime(meta["end_date"])
    horizon = meta["label_horizon"]
    filters = meta.get("filters", {})
    pmin, pmax = filters.get("price_min"), filters.get("price_max")
    ws, we = pd.to_datetime(meta["win_start"]), pd.to_datetime(meta["win_end"])
    data_dir = Path(meta["dataset_dir"])

    pid = pattern_id if pattern_id is not None else mod.PATTERN_DAG.pattern_id
    overrides = adapter.PARAM_OVERRIDES if param_overrides is None else param_overrides

    # ⚠ Params.from_dict 对快照缺失的键会注入「当前代码默认值」——scan 早于某参数
    # 引入时该参数被静默启用,重放 match 集必失配。overrides 是按当次 scan 快照实情
    # 显式声明的补丁(见 adapter.PARAM_OVERRIDES 的 docstring)。
    params = Params.from_dict(blob["per_pattern"][pid]["params_snapshot"])
    if overrides:
        params = _apply_overrides(params, overrides)

    end_node = eval_meta(params=params)["end_node"]

    # scan 侧观测清单(去重键交给 adapter.DEDUP_COLS 声明,骨架不认识具体身份字段)
    scan_ids: dict[str, set] = {}
    for rr in blob["results"]:
        pp = rr["per_pattern"].get(pid)
        if not pp or not pp["analysis"]["matches"]:
            continue
        scan_ids[rr["symbol"]] = {m["match_id"] for m in pp["analysis"]["matches"]}

    rows, n_lab_fail, n_lab_checked, mset_fail = [], 0, 0, []
    for sym, ids in scan_ids.items():
        win = slice_window(pd.read_pickle(data_dir / f"{sym}.pkl"), ws, we)
        res = dag_analyze(build_pattern(params), win, params)
        lo = int(win["date"].searchsorted(s, "left"))
        hi = int(win["date"].searchsorted(e, "right")) - 1
        # 自检 1 前置:serialize 同口径过滤(任一 end_node 事件起点 ∈ 窗 + 任一起点日
        # 收盘价 ∈ [pmin,pmax] 闭区间;serialize.py:341-351 同款)
        live, kept = set(), []
        for m in res.matches:
            events = _resolve_end_events(m, end_node)
            if not any(s <= win["date"].iat[ev.start_idx] <= e for ev in events):
                continue
            closes = [float(win["close"].iat[ev.start_idx]) for ev in events]
            if not any((pmin is None or c >= pmin) and
                       (pmax is None or c <= pmax) for c in closes):
                continue
            live.add(m.match_id)
            kept.append((m, events))
        if live != ids:
            mset_fail.append((sym, len(live), len(ids)))
            continue

        evs = {ev.instance_id: ev for ev in res.events}
        cols = types.SimpleNamespace(
            high=win["high"].to_numpy(float),
            low=win["low"].to_numpy(float),
            close=win["close"].to_numpy(float),
            open=win["open"].to_numpy(float),
            volume=win["volume"].to_numpy(float),
            atr=calculate_atr(win["high"], win["low"], win["close"],
                              VOL_WINDOW).to_numpy(float),
            n=len(win),
        )
        pp = next(r["per_pattern"][pid] for r in blob["results"] if r["symbol"] == sym)
        scan_lab = {m["match_id"]: m["forward_return"] for m in pp["analysis"]["matches"]}

        # 自检 2:覆盖全部通过窗/价格过滤的 kept match(不止最终留下的行),放在
        # observe() 之前——先证 label 可信,再谈要不要采信这条观测。
        for m, events in kept:
            n_lab_checked += 1
            lab = match_forward_returns(m, end_node, win, [horizon],
                                        sample_window=(lo, hi))[horizon]
            ref = scan_lab.get(m.match_id)
            if lab is None and ref is None:
                continue   # 无 label(scan 窗末端 horizon 不可见),非失配——跳过不统计
            if lab is None or ref is None or abs(lab - ref) >= 1e-12:
                n_lab_fail += 1
                continue
            obs = adapter.observe(m, evs, win, cols)
            if obs is None:
                continue
            clash = [c for c in _SKELETON_COLS if c in obs]
            if clash:
                raise ValueError(
                    f"adapter.observe() 返回值覆盖了骨架通用列: {clash}——"
                    "列的归属是本次改造的核心不变式,不许 app 层覆盖骨架列")
            # 买点在窗内的 bar 序号:必须 min(ev.start_idx for ev in events)、不能写
            # 字面下标——某些 app 的 end_node 是「父 node.槽名」点号路径,
            # _resolve_end_events 解析出一组 child events,裸下标会 KeyError;对
            # end_node 无点号、events 只有一个元素的 app,min(...) 逐值等价于原实现。
            entry_idx = min(ev.start_idx for ev in events)
            entry_date = str(pd.to_datetime(win["date"].iat[entry_idx]).date())
            # 通用波动率地板:买点前一根的 atr/close(前一根保证时点安全,决策时刻
            # 已知)。entry_idx<1、分母<=0、或任一端非有限 → NaN,不丢行。
            if entry_idx < 1:
                c0_atr_pct = np.nan
            else:
                denom = cols.close[entry_idx - 1]
                numer = cols.atr[entry_idx - 1]
                c0_atr_pct = (numer / denom
                             if denom > 0 and np.isfinite(denom) and np.isfinite(numer)
                             else np.nan)
            row = {"symbol": sym, **obs,
                   "entry_idx": entry_idx,
                   "entry_date": entry_date,
                   "c0_atr_pct": c0_atr_pct,
                   "label": float(ref)}
            row.update(compute_features(win, row))
            rows.append(row)

    if mset_fail or n_lab_fail:
        raise AssertionError(
            f"自检门失败:match 集不对齐 {mset_fail or 0} 股"
            f"(先查 param_overrides:快照早于参数引入时 from_dict 注入当前默认,"
            f"再疑引擎/数据漂移),label 不一致 {n_lab_fail} 例。"
            f"底座不等价,禁止进统计。")
    if not rows:
        raise ValueError("一行都没有:全部 match 被 observe() 判 None 或未产出可用观测,"
                         "无法写出 dataset(检查 adapter.observe() 与过滤条件)。")

    df = pd.DataFrame(rows)
    missing_cols = [c for c in adapter.DEDUP_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"adapter.DEDUP_COLS 声明的列不在输出里: {missing_cols}"
                         "(adapter.observe() 或骨架未产出这些列)")
    # 流式 seen 集合去重降级为事后 drop_duplicates;语义等价的前提是 DEDUP_COLS
    # 函数决定 end_node 事件与 observe() 的全部返回值(adapter 文件里写死为注释)。
    df = df.drop_duplicates(list(adapter.DEDUP_COLS), keep="first")
    df.to_csv(out_csv, index=False)

    n_nan_c0 = int(df["c0_atr_pct"].isna().sum())
    print(f"自检门通过(match 集逐股对齐,label 重算 {n_lab_checked} 例全数 <1e-12)")
    print(f"rows={len(df)} symbols={df['symbol'].nunique()} -> {out_csv}")
    print(f"c0_atr_pct NaN 计数={n_nan_c0}")
    return df
