"""通用 app 评估器:全宇宙扫描 + forward_return 统计 / 回归对拍 / 体检(三 mode 共享骨架)。

服务 authoring-path2-app skill 的下游评估(final_report §8.9):
  run_eval        命中数 + 多 horizon forward_return 分布(判据 2)
  run_regress     与改前 baseline(一次 eval 的结果 JSON)按 (symbol, buy_date) 对拍
  run_healthcheck 新建/改动 detector 后的数量级体检 + 目标票命中确认

与 scan.py::run_scan 的分工:run_scan 服务 web UI(全量序列化、单 horizon、按 match
计数);本模块服务设计期评估(轻量 JSON、多 horizon、每 match 一行,meta 双口径
buy_windows/match_windows)。module_path 一律指 app 包
(如 "path2_apps.bottom_burst",经 __init__ 暴露 analyze/Params/eval_meta/
PATTERN_DAG),非 dag_spec 子模块。
"""
from __future__ import annotations

import hashlib
import importlib
import json
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from path2.dag.engine import analyze as _dag_analyze
from path2.debug import set_current_symbol
from path2.eval import _resolve_end_events, match_forward_returns
from path2_web.data import slice_window
from path2_web.gate_collector import attach_and_collect, detach
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls


def _eval_ticker(pkl_path: str, module_path: str, start: str, end: str,
                 horizons: tuple, end_node: str, head_buffer_trading_days: int,
                 param_overrides: Optional[dict]):
    """Worker:读 pkl → 双端缓冲切窗 → analyze → 窗内过滤 → 每 match 一行收益。

    模块级函数(ProcessPool pickle 安全)。base = mod.load_params() 读 app 同目录
    params.yaml(SSoT)。param_overrides 是 **nested dict**(如 {"bo":{"min_relative_height":0.02},
    "burst":{"min_bos":2}}),worker 内逐 section 用 dataclasses.replace 局部 patch
    子 dataclass 后合并(跨进程 pickle 安全)。语义:override 在 yaml base 之上,
    与 web /scan 结果可比。有效性 = 买点起点日期 ∈ [start, end];评估单元 = match
    (每 match 一行,共享 leaf 的多个 match 各占一行,不再按买点去重)。
    逐日消费(returns/n_buy_days/sample_dates/day_returns)按样本消费窗双边截取
    (spec §10):start_ts/end_ts 在 win 内行号 (lo, hi),跨界段只取窗内部分。
    rows 每行含 sample_dates(截窗样本日 str 列表)与 day_returns({date: {horizon:
    日级收益}})——同日跨 match 同值(worker 逐 (symbol,t) 算一次),供聚合层
    dedup_daily 日级去重(B2:重叠日 = 同一物理观测,重复计数 = 伪复制)。
    返回 (symbol, rows, err|None);单股异常捕获返回 err,绝不抛。
    """
    symbol = Path(pkl_path).stem
    set_current_symbol(symbol)
    try:
        df = pd.read_pickle(pkl_path)
        mod = importlib.import_module(module_path)
        base = mod.load_params() if hasattr(mod, "load_params") else mod.Params.default()
        if param_overrides:
            # nested dict:{"bo": {"min_relative_height": 0.02}, "burst": {"min_bos": 2}, ...}
            # 对每个 section 局部 patch 子 dataclass,再合并回顶层 Params。
            section_kwargs = {sect: replace(getattr(base, sect), **sect_overrides)
                              for sect, sect_overrides in param_overrides.items()}
            params = replace(base, **section_kwargs)
        else:
            params = base
        start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
        buf_start = start_ts - pd.Timedelta(
            days=round(head_buffer_trading_days * TRADING_TO_CALENDAR_RATIO))
        buf_end = end_ts + pd.Timedelta(
            days=round(max(horizons) * TRADING_TO_CALENDAR_RATIO))
        win = slice_window(df, buf_start, buf_end)
        if len(win) == 0:
            return (symbol, [], None)
        # 同 scan.py::_scan_ticker_multi 的 worker 双落(Task 15):不直接调 mod.analyze,
        # 自建 spec 换 on_gate collector 挂载窗口。此路径目前无 gate_failures 消费者
        # (eval/regress/healthcheck 报表只读 res.matches),但两 worker 保持同一挂/收
        # 模式,避免未来接入时再补一遍。
        spec = mod.build_pattern(params)
        collector = attach_and_collect(spec)
        try:
            res = _dag_analyze(spec, win, params)
        finally:
            detach(spec)
        res = replace(res, gate_failures=collector.snapshot())
        # 样本消费窗(spec §10 截取):start_ts/end_ts 在 win 内的行号(双边含端)。
        # 机器照常跑满 win(含缓冲),逐日消费(forward_returns/n_buy_days)截到 [start, end]。
        lo = int(win["date"].searchsorted(start_ts, "left"))
        hi = int(win["date"].searchsorted(end_ts, "right")) - 1

        # worker 内日级收益:逐 (symbol, t) 算一次(同日跨 match 同值,天然去重),
        # 供聚合层 dedup_daily 展开;t+n 越界的 horizon 置 None(与 match_forward_returns
        # 的越界跳过同语义,聚合层过滤)。
        day_ret_cache: dict = {}

        def _day_ret(t: int) -> dict:
            if t not in day_ret_cache:
                day_ret_cache[t] = {
                    str(n): (float(win["high"].iloc[t + 1: t + n + 1].max())
                             / float(win["close"].iat[t]) - 1.0
                             if t + n < len(win) else None)
                    for n in horizons}
            return day_ret_cache[t]

        rows: list = []
        for m in res.matches:
            events = _resolve_end_events(m, end_node)   # 路径协议:与 eval/serialize 同函数
            # 因果闸:买点取各 event 的 start_idx,必须 >= 其确认 bar(confirm_idx),否则前瞻。
            # retrospective 跨度事件(burst/trend/platform)confirm_idx=end,若误用其
            # start_idx 当买点会在此 raise(参见 final_report A.3 六倍分差教学例)。
            # 路径下均为确认型段(start==confirm),正常不会 raise。
            for ev in events:
                if ev.start_idx < ev.confirm_idx:
                    raise ValueError(
                        f"因果闸失效:end_node='{end_node}' 买点 start_idx={ev.start_idx} "
                        f"< confirm_idx={ev.confirm_idx}({ev.__class__.__name__});"
                        f"买点应锚在 confirm_idx 或之后"
                    )
            # 买点日期过滤:任一段起点 ∈ [start, end](与 serialize 任一过滤同口径)
            if not any(start_ts <= win["date"].iat[ev.start_idx] <= end_ts
                       for ev in events):
                continue
            # leaf 锚容器(match 身份;与 serialize leaf_by_id 同口径,值=instance_id 字符串;
            # buy_date 锚容器 start=首段 enter)
            # ⚠ 不对称:keep 过滤=任一段在窗(上方 any),buy_date=容器 start(首段)——首段在窗前、
            # 后段在窗内的 match 会保留且 buy_date < start_ts,裁定设计内边缘,勿"修复"
            leaf_ev = m.node_index[end_node.split(".")[0]]
            rets = match_forward_returns(m, end_node, win, list(horizons),
                                         sample_window=(lo, hi))
            # 截窗样本日(升序):跨 end_ts 的段只取窗内部分(spec §10;与 rets 同窗)
            sample_days = sorted({t for ev in events
                                  for t in ev.sample_bar_indices()
                                  if lo <= t <= hi})
            rows.append({
                "symbol": symbol,
                "buy_date": str(win["date"].iat[leaf_ev.start_idx])[:10],
                "buy_end_date": str(win["date"].iat[leaf_ev.end_idx])[:10],
                "n_buy_days": len(sample_days),   # 截窗后各段 span 并集
                "leaf_event_id": leaf_ev.instance_id,
                "upstream_key": _upstream_key(m, end_node, res.events),
                "returns": {str(n): rets[n] for n in horizons},
                "sample_dates": [str(win["date"].iat[t])[:10] for t in sample_days],
                "day_returns": {str(win["date"].iat[t])[:10]: _day_ret(t)
                                for t in sample_days},
            })
        return (symbol, rows, None)
    except Exception as e:
        return (symbol, [], f"{type(e).__name__}: {e}")
    finally:
        set_current_symbol(None)


def _upstream_key(m, end_node: str, events=()) -> str:
    """regress 子行锚:除 end_node 锚 node 外(路径声明取 'node_id' 段)node_index 各
    (node_id, instance_id)按 node_id 排序拼接的 sha1 前 12 位。
    ★ 键值现含 instance_id(实例身份):「单实例节点逐字不变」不变式已放弃——同节点
    不同实例(如 tb_293#0/#1)得到不同 upstream_key,这是改读实例身份的固有结果、
    行为正确(评估按实例锚),此处显式声明不再维持旧不变式。
    实例流:直接读物化标注的 e.instance_id(内存对象直取,已含组内 #idx 后缀,
    不再用 indexer 编号);events 参数保留仅为向后兼容(调用方照旧传 res.events),不再消费。"""
    anchor = end_node.split(".")[0]
    parts = []
    for nid, e in sorted(m.node_index.items()):
        if nid == anchor:
            continue
        parts.append(f"{nid}:{e.instance_id}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _leaf_stats(rows: list) -> dict:
    """买点级统计:buy_windows(按 (symbol, leaf_event_id) 去重,向后兼容语义——leaf_event_id
    是 instance_id 字符串不含股票,跨股票同 instance_id 是不同物理买点,必须带 symbol)/
    match_windows(评估单元=match)/shared_leaf_count(被 >=2 match 共享的买点数,同股票内)/share_ratio。"""
    leaf_hits = Counter((r["symbol"], r["leaf_event_id"]) for r in rows)
    buy_windows = len(leaf_hits)
    shared = sum(1 for c in leaf_hits.values() if c >= 2)
    return {"buy_windows": buy_windows, "match_windows": len(rows),
            "shared_leaf_count": shared,
            "share_ratio": (shared / buy_windows) if buy_windows else None}


def _dedup_daily_stats(rows: list, horizons: Sequence[int]) -> dict:
    """日级去重统计(tb v4 spec B2 裁决):展开全部 rows 的 day_returns,按 (symbol, date)
    去重后逐 horizon 过 _summarize_flat——重叠日 forward return 是同一物理观测,重复
    计数 = 伪复制;实盘触发 = 一股一天一动作,统计单元对齐交易单元。
    consensus_days = 被多 match sample_dates 覆盖的 (symbol, date) 日数(显式字段)。
    同 (symbol, date) 跨 match 的值理论同值(worker 逐 (symbol,t) 算一次),
    setdefault 保留首见;旧 match 级 per_horizon 保留为诊断口径,本视图挂 meta.dedup_daily。"""
    cover = Counter((r["symbol"], d) for r in rows
                    for d in r.get("sample_dates", ()))
    per = {}
    for n in horizons:
        key = str(n)
        vals: dict = {}
        for r in rows:
            for d, rets in (r.get("day_returns") or {}).items():
                v = rets.get(key)
                if v is not None:
                    vals.setdefault((r["symbol"], d), v)
        per[key] = _summarize_flat(list(vals.values()))
    return {**per, "consensus_days": sum(1 for c in cover.values() if c >= 2)}


def _summarize_flat(vals: list) -> dict:
    """给定一组 float, 返回 count/mean/min/q25/median/q75/max/win_rate。
    None 值调用者已过滤;空 vals -> count=0, 其余 None。"""
    if not vals:
        return {"count": 0, "mean": None, "min": None, "q25": None,
                "median": None, "q75": None, "max": None, "win_rate": None}
    s = pd.Series(vals)
    q25, q75 = s.quantile([0.25, 0.75])
    return {
        "count": len(vals),
        "mean": sum(vals) / len(vals),
        "min": float(s.min()),
        "q25": float(q25),
        "median": float(s.median()),
        "q75": float(q75),
        "max": float(s.max()),
        "win_rate": sum(v > 0 for v in vals) / len(vals),
    }


def _summarize(rows: list, horizons: Sequence[int]) -> dict:
    """每 horizon 的 count/mean/min/q25/median/q75/max/win_rate(None 值剔除;空 → 各项 None)。"""
    per = {}
    for n in horizons:
        vals = [r["returns"][str(n)] for r in rows
                if r["returns"][str(n)] is not None]
        per[str(n)] = _summarize_flat(vals)
    return per


def _eval_core(*, module_path: str, start, end, horizons: tuple,
               end_node: str, head_buffer_trading_days: int,
               param_overrides: Optional[dict], data_dir: str, workers: int,
               ticker_regex: Optional[str], executor_factory=None,
               on_progress=lambda *a: None) -> dict:
    """eval 纯核:扫全集聚合,返回 {meta, per_horizon, results},不落盘(供三 mode 共用)。"""
    if executor_factory is None:
        executor_factory = lambda w: ProcessPoolExecutor(max_workers=w)
    pkls = _list_pkls(data_dir, ticker_regex)
    t0 = time.perf_counter()
    results, errors = [], 0
    with executor_factory(max(1, workers)) as ex:
        futs = [ex.submit(_eval_ticker, str(p), module_path, start, end,
                          tuple(horizons), end_node, head_buffer_trading_days,
                          param_overrides) for p in pkls]
        for i, fut in enumerate(as_completed(futs), 1):
            _symbol, rows, err = fut.result()
            if err is not None:
                errors += 1
            results.extend(rows)
            on_progress(i, len(pkls), len(results), errors)
    results.sort(key=lambda r: (r["symbol"], r["buy_date"]))
    mod = importlib.import_module(module_path)
    return {
        "meta": {
            "mode": "eval", "module_path": module_path,
            "pattern_id": mod.PATTERN_DAG.pattern_id,
            "start": str(start), "end": str(end), "horizons": list(horizons),
            "end_node": end_node,
            "head_buffer_trading_days": head_buffer_trading_days,
            "param_overrides": param_overrides or {},
            "scanned": len(pkls), "errors": errors,
            **_leaf_stats(results),
            "dedup_daily": _dedup_daily_stats(results, horizons),
            "tickers_hit": len({r["symbol"] for r in results}),
            "elapsed_s": round(time.perf_counter() - t0, 1),
        },
        "per_horizon": _summarize(results, horizons),
        "results": results,
    }


def _write_json(out: dict, out_path, pattern_id: str, mode: str) -> dict:
    """落盘结果 JSON;out_path=None 时按时间戳落 outputs/path2_eval/。路径写回 meta.out_path。"""
    if out_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        repo = Path(__file__).resolve().parents[1]
        out_path = repo / "outputs" / "path2_eval" / f"{pattern_id}_{mode}_{ts}.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out["meta"]["out_path"] = str(out_path)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def _resolve_meta(module_path: str, end_node, head_buffer_trading_days):
    """end_node/head_buffer 缺省时从 app 的 eval_meta() 协议解析。
    把 mod.load_params() (yaml SSoT) 传给 eval_meta,让 head_buffer 反映本次扫描真用参数。"""
    if end_node is not None and head_buffer_trading_days is not None:
        return end_node, head_buffer_trading_days
    mod = importlib.import_module(module_path)
    params = mod.load_params() if hasattr(mod, "load_params") else None
    meta = mod.eval_meta(params)
    return (end_node or meta["end_node"],
            head_buffer_trading_days or meta["head_buffer_trading_days"])


def run_eval(*, module_path: str, start, end, horizons=(5, 10, 20),
             end_node=None, head_buffer_trading_days=None, param_overrides=None,
             data_dir="datasets/pkls", workers=26, ticker_regex=None,
             out_path=None, executor_factory=None,
             on_progress=lambda *a: None) -> dict:
    """mode=eval:全宇宙命中 + 多 horizon forward_return 分布,落盘 JSON。判据 2(§8.5)。"""
    end_node, head_buffer_trading_days = _resolve_meta(
        module_path, end_node, head_buffer_trading_days)
    out = _eval_core(module_path=module_path, start=start, end=end,
                     horizons=tuple(horizons), end_node=end_node,
                     head_buffer_trading_days=head_buffer_trading_days,
                     param_overrides=param_overrides, data_dir=data_dir,
                     workers=workers, ticker_regex=ticker_regex,
                     executor_factory=executor_factory, on_progress=on_progress)
    return _write_json(out, out_path, out["meta"]["pattern_id"], "eval")


def _diff_results(base_results: list, cur_results: list):
    """按 (symbol, buy_date) 外层 + upstream_key 内层两级对拍(语义锚,跨结构改动稳定)。
    内层子行 diff:cur 独有 = added(同 buy_date 新子行=预期多确认;新 buy_date=新买点,
    由调用方按修改意图判读);base 独有 = removed(真消失)。旧 baseline 行无 upstream_key
    时整组按 (symbol, buy_date) 单行语义对拍(组存在即 unchanged,cur 组内子行也不计
    added),自动向后兼容。"""
    key = lambda r: (r["symbol"], r["buy_date"])
    subkey = lambda r: r.get("upstream_key", r["buy_date"])
    base_idx: dict = {}
    for r in base_results:
        base_idx.setdefault(key(r), {})[subkey(r)] = r
    cur_idx: dict = {}
    for r in cur_results:
        cur_idx.setdefault(key(r), {})[subkey(r)] = r
    added, removed, unchanged = [], [], 0
    for k, base_sub in base_idx.items():
        cur_sub = cur_idx.get(k, {})
        if not cur_sub:
            removed.extend(base_sub.values())
            continue
        # 旧格式 baseline(无 upstream_key):整组单行语义——cur 组存在即 unchanged。
        if any(r.get("upstream_key") is None for r in base_sub.values()):
            unchanged += 1
            continue
        for sk, br in base_sub.items():
            if sk in cur_sub:
                unchanged += 1
            else:
                removed.append(br)
    for k, cur_sub in cur_idx.items():
        base_sub = base_idx.get(k, {})
        if any(r.get("upstream_key") is None for r in base_sub.values()):
            continue   # legacy 组已在上面按单行计 unchanged
        for sk, cr in cur_sub.items():
            if sk not in base_sub:
                added.append(cr)
    return added, removed, unchanged


def run_regress(*, baseline_path: str, param_overrides=None,
                data_dir="datasets/pkls", workers=26, ticker_regex=None,
                out_path=None, executor_factory=None,
                on_progress=lambda *a: None) -> dict:
    """mode=regress:重扫当前代码并与改前 baseline 对拍(§8.8 修改回归关卡)。

    窗口/horizons/end_node/head_buffer/module_path 全部沿用 baseline.meta(同口径保证);
    param_overrides 单独传(当前侧参数)。对拍按 (symbol, buy_date) + upstream_key
    两级锚:同 buy_date 的子行差异不再被覆盖吞掉——added 中「同 buy_date 新子行」=
    预期多确认(共享 leaf 新增上游)、「新 buy_date」= 新买点;removed = 真消失。
    DIFF≠0 不一律算回归——added/removed 的分类(意图内 vs 意外)由调用方按修改
    意图 + 收益信号判读,本函数只出事实。
    """
    base = json.loads(Path(baseline_path).read_text())
    bm = base["meta"]
    cur = _eval_core(module_path=bm["module_path"], start=bm["start"], end=bm["end"],
                     horizons=tuple(bm["horizons"]), end_node=bm["end_node"],
                     head_buffer_trading_days=bm["head_buffer_trading_days"],
                     param_overrides=param_overrides, data_dir=data_dir,
                     workers=workers, ticker_regex=ticker_regex,
                     executor_factory=executor_factory, on_progress=on_progress)
    added, removed, unchanged = _diff_results(base["results"], cur["results"])
    out = {
        "meta": {**cur["meta"], "mode": "regress",
                 "baseline_path": str(baseline_path)},
        "added": added, "removed": removed, "unchanged_count": unchanged,
        "per_horizon_current": cur["per_horizon"],
    }
    return _write_json(out, out_path, cur["meta"]["pattern_id"], "regress")


def run_healthcheck(*, module_path: str, start, end, target_ticker=None,
                    min_tickers=1, max_tickers=500, horizons=(5,),
                    end_node=None, head_buffer_trading_days=None,
                    param_overrides=None, data_dir="datasets/pkls", workers=26,
                    ticker_regex=None, out_path=None, executor_factory=None,
                    on_progress=lambda *a: None) -> dict:
    """mode=healthcheck:新建/改动 detector 后的全宇宙体检(§2(i) 例外 / §8.9)。

    判:命中股数在 [min_tickers, max_tickers] 数量级区间(不是 0、不爆炸),
    目标票(若给)真命中。errors 数随 meta 透出,调用方应一并核查(新 detector
    全宇宙抛异常会表现为 errors 飙高而非命中异常)。
    """
    end_node, head_buffer_trading_days = _resolve_meta(
        module_path, end_node, head_buffer_trading_days)
    cur = _eval_core(module_path=module_path, start=start, end=end,
                     horizons=tuple(horizons), end_node=end_node,
                     head_buffer_trading_days=head_buffer_trading_days,
                     param_overrides=param_overrides, data_dir=data_dir,
                     workers=workers, ticker_regex=ticker_regex,
                     executor_factory=executor_factory, on_progress=on_progress)
    tickers_hit = cur["meta"]["tickers_hit"]
    out = {
        "meta": {**cur["meta"], "mode": "healthcheck"},
        "universe_hit_tickers": tickers_hit,
        "universe_buy_windows": cur["meta"]["buy_windows"],
        "magnitude_ok": min_tickers <= tickers_hit <= max_tickers,
        "target_ticker": target_ticker,
        "target_matches": (any(r["symbol"] == target_ticker for r in cur["results"])
                           if target_ticker else None),
    }
    return _write_json(out, out_path, cur["meta"]["pattern_id"], "healthcheck")
