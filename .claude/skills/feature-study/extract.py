# -*- coding: utf-8 -*-
"""feature-study 数据构建库:任意声明了 adapter 的 path2_apps app 可 import 使用。

三个入口:
  - load_adapter(app) —— 按文件路径加载 apps/<app>/adapter.py 声明。
  - build_dataset(adapter, *, scan, out_csv, compute_features, pattern_id=None,
    param_overrides=None) —— 从一份 path2_web scan 文件重放出研究用 dataset.csv(新特征用)。
  - build_from_longtable(app, window, combo, *, gate_cols=None, working=None) —— 从 tune-gates 长表
    取一个检测组合的行(闸类字段用,免重放;保留同一买点事件的不同前缀行,供「任一行过闸」聚合)。

观测单位 = 买点事件(买点 node 解析出的事件区间组)。同一段买点被多个 match(不同前缀)共享时,
label 与首次穿越四态完全相同,只算一次。

build_dataset 的列归属:骨架统一注入通用列 —— symbol / entry_idx(买点在窗内的 bar 序号)/ entry_date /
year / c0_atr_pct(冷启动通用波动率地板)/ label(前瞻收益)/ up / down / both / none(买点事件内合格买点 bar
的首次穿越四态计数);app 特异的一切(node 名、几何算式、已知信号列)封在 adapter.observe() 里,骨架本身不认识
任何具体走势的 node 名,也不出现任何 node 名字面量。

build_dataset 两道自检门(硬闸,不过即 raise,禁止绕过;底座等价先行的机器化):
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
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[3]   # skill 目录 → repo root
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from path2.calc.atr import (FP_ATR_WINDOW, calculate_atr, prev_bar_atr_pct,  # noqa: E402  与 detector 同源
                            rolling_atr_pct_nanmedian)
from path2.dag.engine import analyze as dag_analyze  # noqa: E402
from path2.eval import match_first_passage, match_forward_returns  # noqa: E402
from path2_web.serialize import _resolve_end_events    # noqa: E402  与 serialize 同口径过滤
from path2_web.data import slice_window                # noqa: E402
from run_battery import STATES, _cmp, load_tune_gates  # noqa: E402

VOL_WINDOW = 14   # 通用波动率控制列的窗口。控制列不需要与 detector 同源,跟着
                  # pattern 参数走会让不同 pattern 的控制列不可比,故固定 14,不从
                  # params 取。

ADAPTER_NAMES = ("APP_MODULE", "PARAM_OVERRIDES", "DEDUP_COLS", "KNOWN_SIGNALS", "PARAM_FEATURES", "observe")

# 骨架统一注入的通用列;adapter.observe() 返回值里出现任何一个都是列归属错位。
_SKELETON_COLS = ("symbol", "entry_idx", "entry_date", "year", "c0_atr_pct", "label", *STATES)

# 长表四态列名 → 学习端统一列名
LONGTABLE_STATES = {"fp_up": "up", "fp_down": "down", "fp_both": "both", "fp_none": "none"}


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
        DEDUP_COLS / KNOWN_SIGNALS / PARAM_FEATURES / observe(约定见 apps/_template/adapter.py)。
      scan: scan 文件路径(str 或 Path)。
      out_csv: 输出 CSV 路径(str 或 Path)。
      compute_features(win, row) -> dict: 每轮研究自己写的特征口径函数;拿到的
        row 已含骨架注入的通用列(含 label 与四态),返回值合并进最终行——保持这个
        先后顺序(label 先赋值、compute_features 后调用)是既有行为,不要调换。
      pattern_id: scan 里的 pattern id;None 时从 mod.PATTERN_DAG.pattern_id 推导
        (能推导的不让人填),显式传入则以传入为准。
      param_overrides: 覆盖 scan 快照参数,按 yaml section 分组(结构对齐
        Params.from_dict);None 时用 adapter.PARAM_OVERRIDES,传 dict 则整体覆盖
        它——这是给「同一个 app 换一份 vintage 不同的 scan」留的临时口子。

    返回:按买点事件去重后的 DataFrame(同时写入 out_csv)。

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
    fp_k = meta["first_passage_k"]
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

    rows, n_lab_fail, n_lab_compared, n_lab_skipped, mset_fail = [], 0, 0, 0, []
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
        # 通用波动率地板:买点前一根的 atr/close(前一根保证时点安全,决策时刻已知)。
        # t<1、分母<=0、或任一端非有限 → NaN,不丢行。与 tune-gates 长表的同名列同一算式。
        c0 = prev_bar_atr_pct(win["high"], win["low"], win["close"], VOL_WINDOW)
        # 首次穿越的波动率尺度,每股算一次,供逐 match 的四态计数复用
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], FP_ATR_WINDOW).values
        pp = next(r["per_pattern"][pid] for r in blob["results"] if r["symbol"] == sym)
        scan_lab = {m["match_id"]: m["forward_return"] for m in pp["analysis"]["matches"]}

        # 自检 2:覆盖全部通过窗/价格过滤的 kept match(不止最终留下的行),放在
        # observe() 之前——先证 label 可信,再谈要不要采信这条观测。
        for m, events in kept:
            lab = match_forward_returns(m, end_node, win, [horizon],
                                        sample_window=(lo, hi))[horizon]
            ref = scan_lab.get(m.match_id)
            if lab is None and ref is None:
                n_lab_skipped += 1
                continue   # 无 label(scan 窗末端 horizon 不可见),非失配——跳过不统计,
                          # 也不计入下面 <1e-12 的比对分母(与 n_lab_compared 分开数)
            n_lab_compared += 1
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
            # 买点在窗内的 bar 序号:必须与 label 的买点日集合同源——
            # match_forward_returns(path2/eval.py)取买点日走的是
            # `for ev in events for t in ev.sample_bar_indices() if lo<=t<=hi`,
            # entry_idx 须复用同一遍历 + 同一窗过滤,不能写 min(ev.start_idx for ev
            # in events):多段 app 的 end_node 是「父 node.槽名」点号路径(如
            # bottom_burst 的 "tb.segments"),窗过滤(见上)只要求任一段起点 ∈ 窗,
            # 首部缓冲允许更早的段存在——实测 CGTX:min(ev.start_idx)=67 而 lo=72,
            # 那一段一次都没被 label 采样过,取它当买点日会让 c0_atr_pct 算在窗外。
            # 集合必非空:上面的窗过滤已保证至少一个 ev 满足 lo<=ev.start_idx<=hi
            # (searchsorted 语义),而 ev.start_idx 本身就在 ev.sample_bar_indices()
            # 里,min() 拿不到空序列。对 end_node 无点号、events 只有一个元素的 app
            # (如 bb_v1 的 "tb"),这与原来的 min(ev.start_idx) 逐值等价。
            entry_idx = min(t for ev in events for t in ev.sample_bar_indices()
                            if lo <= t <= hi)
            # entry_date 与 path2_web/serialize.py 的 leaf_ev 报日期口径不同:
            # serialize 取的是**容器起点**,这里取的是**采样窗内最早的买点日**——对
            # end_node 无点号的 app 二者相等,对点号路径 app(如 bottom_burst)未必。
            # 真要与 scan JSON 的行对齐,应该用 match_id 做 join,不要用 entry_date。
            entry_ts = pd.to_datetime(win["date"].iat[entry_idx])
            fp = match_first_passage(m, end_node, win, horizon, k=fp_k, sample_window=(lo, hi), M=M)
            row = {"symbol": sym, **obs,
                   "entry_idx": entry_idx,
                   "entry_date": str(entry_ts.date()),
                   "year": int(entry_ts.year),
                   "c0_atr_pct": float(c0[entry_idx]),
                   "label": float(ref),
                   **{st: int(fp[st]) for st in STATES}}
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
    # 按买点事件身份事后去重:同一段买点被多个 match 共享时只留数据原序第一条存活的 match。
    # label 与四态只由买点事件决定,去重不改变它们;observe() 里随前缀变化的列取第一条的值
    # (adapter 文件里写死为注释)。
    df = df.drop_duplicates(list(adapter.DEDUP_COLS), keep="first")
    df.to_csv(out_csv, index=False)

    n_nan_c0 = int(df["c0_atr_pct"].isna().sum())
    # 拆成两个数,不再合并成一个「重算 N 例」——旧版那个数混了「真正参与 <1e-12
    # 比对」与「lab/ref 皆 None、跳过未比对」两类,读者得靠额外一段括号解释才看懂。
    print(f"自检门通过(match 集逐股对齐,label 重算:比对 {n_lab_compared} 例全数 "
         f"<1e-12、无 label 跳过 {n_lab_skipped} 例)")
    print(f"rows={len(df)} symbols={df['symbol'].nunique()} -> {out_csv}")
    print(f"c0_atr_pct NaN 计数={n_nan_c0}")
    return df


# ── 从 tune-gates 长表取数 ──

def longtable_dir(app: str, window: str) -> Path:
    """tune-gates 某 app 某窗口的长表目录(输出根目录由 tune.out_dir_of 单点定义)。"""
    return load_tune_gates("tune").out_dir_of(app, window) / "longtable"


def formal_params(cl: dict) -> dict:
    """正式参数(params.yaml 本身,不套宽进覆盖)的扁平 {section.field: 值}。"""
    S = load_tune_gates("study_io")
    mod = importlib.import_module(cl["app_module"])
    nested = mod.Params.from_yaml(S.app_dir(mod) / cl["base_yaml"]).to_dict()
    return {f"{sec}.{k}": v for sec, kv in nested.items() if isinstance(kv, dict) for k, v in kv.items()}


def gate_axes(cl: dict) -> list[dict]:
    """classification 里的闸轴(过滤型参数 + where 阈值),顺序与 study_io.derived_axes 的谓词轴一致。

    返回 [{"param": 参数键, "column": 长表列名 node.field, "op", "levels": 档位表(下标 0 = 最松), "kind": "F"|"W"}]。
    """
    out = []
    for p, lv in cl["scan_grid"].items():
        if cl["kinds"][p] == "F":
            n, f, op = cl["filter_fields"][p]
            out.append({"param": p, "column": f"{n}.{f}", "op": op, "levels": list(lv), "kind": "F"})
    for p, lv in cl["where_levels"].items():
        n, f, op = cl["where_fields"][p]
        out.append({"param": p, "column": f"{n}.{f}", "op": op, "levels": list(lv), "kind": "W"})
    return out


def working_point(cl: dict, working: dict | None = None) -> dict:
    """闸轴的工作点取值 {长表列名: 值}:正式参数取值,working({参数键: 值})逐项覆盖。"""
    axes = gate_axes(cl)
    working = dict(working or {})
    unknown = sorted(set(working) - {a["param"] for a in axes})
    if unknown:
        raise ValueError(f"{unknown} 不是闸(只能给 where 阈值或过滤型参数的参数键)")
    formal = formal_params(cl)
    return {a["column"]: working.get(a["param"], formal[a["param"]]) for a in axes}


def _self_check(df: pd.DataFrame, RC, combo: dict, preds: list, point: dict, seg: list) -> np.ndarray:
    """工作点格上两套算法的四态每折和必须逐位相等:本模块的「行过闸 → 按买点事件去重」直白版,
    与 region_core 买点事件口径张量(带符号点质量 + 谓词轴后缀累加)。返回 (折数, 4) 的计数。"""
    folds = sorted(df["year"].unique())
    idx, m = [], np.ones(len(df), dtype=bool)
    for col, op, lv in preds:
        v = point[col]
        if v not in lv:
            raise ValueError(f"工作点 {col} = {v!r} 不在档位表 {lv} 里,张量里没有这个格,自检做不了")
        idx.append(lv.index(v))
        m &= _cmp(pd.to_numeric(df[col], errors="coerce").to_numpy(float), op, v)
    straight = (df[m].drop_duplicates(["symbol", "year", *seg]).groupby("year")[list(LONGTABLE_STATES)].sum()
                .reindex(folds, fill_value=0).to_numpy(np.int64))
    prep = RC.prepare(df, {k: [v] for k, v in combo.items()}, preds, "year", folds, segment_cols=seg)
    tensor_counts = RC.tensor(prep)[(0,) * len(combo) + tuple(idx)]
    if not np.array_equal(tensor_counts, straight):
        raise AssertionError(f"自检失败:工作点格上按买点事件去重的四态计数与调参张量不一致"
                             f"(直白版 {straight.tolist()} / 张量 {tensor_counts.tolist()},折 {folds})——"
                             "取数口径与调参端不等价,禁止进统计")
    return straight


def build_from_longtable(app: str, window: str, combo: dict, *, gate_cols=None, working=None) -> pd.DataFrame:
    """从 tune-gates 长表取一个检测组合的行,供闸式判定直接用。

    参数:
      app / window: tune-gates 的 app 与窗口(研究声明与长表按窗口存放)。
      combo: {检测参数键: 档值},必须恰好覆盖全部检测参数,值在扫描档位里。
      gate_cols: 要带出的闸字段列(长表列名 node.field);None = 全部闸轴。
      working: {闸参数键: 值},覆盖自检用的工作点(缺省 = 正式参数取值)。
    返回列:symbol、date(买点日)、year、买点事件键列、闸字段列、M / c0_atr_pct(长表里有才带)、up / down / both / none。

    行为:
      1. 先过确认窗守卫(读取区间 = 长表的买点区间);
      2. 用 pyarrow 按 combo 过滤逐片读取,只读需要的列;
      3. 自检:工作点格上「行过闸 → 按买点事件去重」的四态每折和,与 region_core 买点事件口径张量逐位相等,不等即 raise;
      4. 只丢完全重复的行(买点事件键 + 带出的闸字段 + 四态都相同),保留不同前缀的行供「任一行过闸」聚合。
    不写账本。
    """
    S = load_tune_gates("study_io")
    H = load_tune_gates("holdout")
    RC = load_tune_gates("region_core")
    cl = S.load_classification(app, window)
    lt = longtable_dir(app, window)
    meta = S.load_run_meta(lt)
    H.guard_label_access(app, meta["start_date"], meta["end_date"], "build_from_longtable")

    combo_levels, preds = S.derived_axes(cl)
    if set(combo) != set(combo_levels):
        raise ValueError(f"combo 必须恰好给全部检测参数:缺 {sorted(set(combo_levels) - set(combo))},"
                         f"多 {sorted(set(combo) - set(combo_levels))}")
    for k, v in combo.items():
        if v not in combo_levels[k]:
            raise ValueError(f"检测参数 {k} = {v!r} 不在扫描档位 {combo_levels[k]} 里,长表里没有这个组合")
    pred_cols = [c for c, _, _ in preds]
    gate_cols = pred_cols if gate_cols is None else list(gate_cols)
    unknown = [c for c in gate_cols if c not in pred_cols]
    if unknown:
        raise ValueError(f"{unknown} 不是长表里的闸字段列(可选 {pred_cols})")
    point = working_point(cl, working)

    shards = sorted(Path(lt).glob("part-*.parquet"))
    if not shards:
        raise SystemExit(f"{lt} 下没有长表分片:先扫描这个窗口")
    names = pq.ParquetFile(shards[0]).schema_arrow.names
    seg = S.segment_cols(cl, names)
    optional = [c for c in ("M", "c0_atr_pct") if c in names]
    cols = list(dict.fromkeys(["symbol", *combo, *pred_cols, *seg, "buy_date", *optional, *LONGTABLE_STATES]))
    filters = [(k, "==", v) for k, v in combo.items()]
    parts = []
    for sp in shards:
        t = pq.read_table(sp, columns=cols, filters=filters)
        if t.num_rows:
            part = t.to_pandas()
            part["symbol"] = part["symbol"].astype(str)
            parts.append(part)
    if not parts:
        raise ValueError(f"检测组合 {combo} 在长表里一行都没有")
    df = pd.concat(parts, ignore_index=True)
    del parts
    for c in LONGTABLE_STATES:
        df[c] = df[c].astype(np.int64)
    df["date"] = pd.to_datetime(df["buy_date"])
    df["year"] = df["date"].dt.year.astype(str)

    counts = _self_check(df, RC, combo, preds, point, seg)

    df = df.rename(columns=LONGTABLE_STATES)
    keep = ["symbol", "date", "year", *seg, *gate_cols, *optional, *STATES]
    out = df[list(dict.fromkeys(keep))].drop_duplicates(["symbol", *seg, *gate_cols, *STATES]).reset_index(drop=True)
    n_events = len(out.drop_duplicates(["symbol", *seg]))
    print(f"长表取数:{len(out)} 行 / {n_events} 个买点事件 / {out['symbol'].nunique()} 只股票;"
          f"自检通过(工作点格每折四态 {counts.tolist()})")
    return out
