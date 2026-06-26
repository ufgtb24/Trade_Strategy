"""通用 app 评估器:全宇宙扫描 + forward_return 统计 / 回归对拍 / 体检(三 mode 共享骨架)。

服务 authoring-path2-app skill 的下游评估(final_report §8.9):
  run_eval        命中数 + 多 horizon forward_return 分布(判据 2)
  run_regress     与改前 baseline(一次 eval 的结果 JSON)按 (symbol, buy_date) 对拍
  run_healthcheck 新建/改动 detector 后的数量级体检 + 目标票命中确认

与 scan.py::run_scan 的分工:run_scan 服务 web UI(全量序列化、单 horizon、按 match
计数);本模块服务设计期评估(轻量 JSON、多 horizon、按买点去重,口径同
scripts/path2_eval_bottom_breakout_burst.py)。module_path 一律指 app 包
(如 "path2_apps.bottom_breakout_burst",经 __init__ 暴露 analyze/Params/eval_meta/
PATTERN_DAG),非 dag_spec 子模块。
"""
from __future__ import annotations

import importlib
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from path2.eval import match_forward_returns
from path2_web.data import slice_window
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls


def _eval_ticker(pkl_path: str, module_path: str, start: str, end: str,
                 horizons: tuple, end_role: str, head_buffer_trading_days: int,
                 param_overrides: Optional[dict]):
    """Worker:读 pkl → 双端缓冲切窗 → analyze → 窗内过滤 + 按买点去重 → 多 horizon 收益。

    模块级函数(ProcessPool pickle 安全)。base = mod.load_params() 读 app 同目录
    params.yaml(SSoT)。param_overrides 是 **nested dict**(如 {"bo":{"min_relative_height":0.02},
    "burst":{"min_bos":2}}),worker 内逐 section 用 dataclasses.replace 局部 patch
    子 dataclass 后合并(跨进程 pickle 安全)。语义:override 在 yaml base 之上,
    与 web /scan 结果可比。有效性 = 买点起点日期 ∈ [start, end];去重 = 按 end_role
    event_id(评估对象是买点)。返回 (symbol, rows, err|None);单股异常捕获返回 err,绝不抛。
    """
    symbol = Path(pkl_path).stem
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
        res = mod.analyze(win, params)
        rows, seen = [], set()
        for m in res.matches:
            ev = m.role_index[end_role]
            buy_date = win["date"].iat[ev.start_idx]
            if not (start_ts <= buy_date <= end_ts):
                continue
            if ev.event_id in seen:
                continue
            seen.add(ev.event_id)
            rets = match_forward_returns(m, end_role, win, list(horizons))
            rows.append({
                "symbol": symbol,
                "buy_date": str(buy_date)[:10],
                "buy_end_date": str(win["date"].iat[ev.end_idx])[:10],
                "n_buy_days": ev.end_idx - ev.start_idx + 1,
                "returns": {str(n): rets[n] for n in horizons},
            })
        return (symbol, rows, None)
    except Exception as e:
        return (symbol, [], f"{type(e).__name__}: {e}")


def _summarize(rows: list, horizons: Sequence[int]) -> dict:
    """每 horizon 的 count/mean/median/win_rate(None 值剔除;空 → 各项 None)。"""
    per = {}
    for n in horizons:
        vals = [r["returns"][str(n)] for r in rows
                if r["returns"][str(n)] is not None]
        per[str(n)] = {
            "count": len(vals),
            "mean": sum(vals) / len(vals) if vals else None,
            "median": float(pd.Series(vals).median()) if vals else None,
            "win_rate": sum(v > 0 for v in vals) / len(vals) if vals else None,
        }
    return per


def _eval_core(*, module_path: str, start, end, horizons: tuple,
               end_role: str, head_buffer_trading_days: int,
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
                          tuple(horizons), end_role, head_buffer_trading_days,
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
            "end_role": end_role,
            "head_buffer_trading_days": head_buffer_trading_days,
            "param_overrides": param_overrides or {},
            "scanned": len(pkls), "errors": errors,
            "buy_windows": len(results),
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
        out_path = Path("outputs/path2_eval") / f"{pattern_id}_{mode}_{ts}.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out["meta"]["out_path"] = str(out_path)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def _resolve_meta(module_path: str, end_role, head_buffer_trading_days):
    """end_role/head_buffer 缺省时从 app 的 eval_meta() 协议解析。
    把 mod.load_params() (yaml SSoT) 传给 eval_meta,让 head_buffer 反映本次扫描真用参数。"""
    if end_role is not None and head_buffer_trading_days is not None:
        return end_role, head_buffer_trading_days
    mod = importlib.import_module(module_path)
    params = mod.load_params() if hasattr(mod, "load_params") else None
    meta = mod.eval_meta(params)
    return (end_role or meta["end_role"],
            head_buffer_trading_days or meta["head_buffer_trading_days"])


def run_eval(*, module_path: str, start, end, horizons=(5, 10, 20),
             end_role=None, head_buffer_trading_days=None, param_overrides=None,
             data_dir="datasets/pkls", workers=26, ticker_regex=None,
             out_path=None, executor_factory=None,
             on_progress=lambda *a: None) -> dict:
    """mode=eval:全宇宙命中 + 多 horizon forward_return 分布,落盘 JSON。判据 2(§8.5)。"""
    end_role, head_buffer_trading_days = _resolve_meta(
        module_path, end_role, head_buffer_trading_days)
    out = _eval_core(module_path=module_path, start=start, end=end,
                     horizons=tuple(horizons), end_role=end_role,
                     head_buffer_trading_days=head_buffer_trading_days,
                     param_overrides=param_overrides, data_dir=data_dir,
                     workers=workers, ticker_regex=ticker_regex,
                     executor_factory=executor_factory, on_progress=on_progress)
    return _write_json(out, out_path, out["meta"]["pattern_id"], "eval")


def _diff_results(base_results: list, cur_results: list):
    """按 (symbol, buy_date) 对拍(语义锚,跨结构改动稳定;event_id 随结构可能变,不用)。
    返回 (added, removed, unchanged_count);added 行来自 cur、removed 行来自 base(带改前收益)。"""
    key = lambda r: (r["symbol"], r["buy_date"])
    base_idx = {key(r): r for r in base_results}
    cur_idx = {key(r): r for r in cur_results}
    added = [cur_idx[k] for k in sorted(cur_idx.keys() - base_idx.keys())]
    removed = [base_idx[k] for k in sorted(base_idx.keys() - cur_idx.keys())]
    return added, removed, len(base_idx.keys() & cur_idx.keys())


def run_regress(*, baseline_path: str, param_overrides=None,
                data_dir="datasets/pkls", workers=26, ticker_regex=None,
                out_path=None, executor_factory=None,
                on_progress=lambda *a: None) -> dict:
    """mode=regress:重扫当前代码并与改前 baseline 对拍(§8.8 修改回归关卡)。

    窗口/horizons/end_role/head_buffer/module_path 全部沿用 baseline.meta(同口径保证);
    param_overrides 单独传(当前侧参数)。DIFF≠0 不一律算回归——added/removed 的分类
    (意图内 vs 意外)由调用方按修改意图 + 收益信号判读,本函数只出事实。
    """
    base = json.loads(Path(baseline_path).read_text())
    bm = base["meta"]
    cur = _eval_core(module_path=bm["module_path"], start=bm["start"], end=bm["end"],
                     horizons=tuple(bm["horizons"]), end_role=bm["end_role"],
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
                    end_role=None, head_buffer_trading_days=None,
                    param_overrides=None, data_dir="datasets/pkls", workers=26,
                    ticker_regex=None, out_path=None, executor_factory=None,
                    on_progress=lambda *a: None) -> dict:
    """mode=healthcheck:新建/改动 detector 后的全宇宙体检(§2(i) 例外 / §8.9)。

    判:命中股数在 [min_tickers, max_tickers] 数量级区间(不是 0、不爆炸),
    目标票(若给)真命中。errors 数随 meta 透出,调用方应一并核查(新 detector
    全宇宙抛异常会表现为 errors 飙高而非命中异常)。
    """
    end_role, head_buffer_trading_days = _resolve_meta(
        module_path, end_role, head_buffer_trading_days)
    cur = _eval_core(module_path=module_path, start=start, end=end,
                     horizons=tuple(horizons), end_role=end_role,
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
