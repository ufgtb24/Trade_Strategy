"""并发扫描(多 pattern):每只股读 pkl 一次 → slice_window → 对每 pattern analyze → 聚合 → 落盘。

铁律:所有 pattern 必须经 discovery eval_meta 闸,故扫描永远走 buffered 路径,
end_role/head_buffer/label_horizon 三者永远非 None。删除旧非缓冲分支。

结果文件 schema MultiScanResultFile(spec §3.1):
  {pattern_ids, per_pattern: {pid: {pattern_spec, end_role}},
   scan: {...win_*/label_horizon/scanned/hits/errors/...},
   results: [{symbol, per_pattern: {pid: {summary, analysis, max_forward_return}}}, ...]}
"""
from __future__ import annotations

import importlib
import json
import os
import re
import signal
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from path2_web.data import slice_window
from path2_web.serialize import serialize_per_pattern_result

TRADING_TO_CALENDAR_RATIO = 1.65   # 交易日 → 日历日(与 scripts/path2_eval_bottom_breakout_burst.py 同源)


class ScanCancelled(Exception):
    """run_scan_multi 检测到 cancel_event 已 set,主动退出。"""


def _scan_ticker_multi(pkl_path, module_paths, start_date, end_date,
                       buf_start, buf_end, end_roles, label_horizon):
    """单股多 pattern worker(模块级,ProcessPool pickle 安全)。

    返回 (symbol, per_pattern_dict | None, err | None):
      per_pattern_dict 为 None = 该股不入选并集(所有 pattern matches 全空)。
      err 非 None = 该股扫描异常,errors++,不进 results。

    每股 read_pkl 一次,buf_win 切一次,然后逐 pattern import+analyze+投影。
    """
    symbol = Path(pkl_path).stem
    try:
        df = pd.read_pickle(pkl_path)
        win = slice_window(df, buf_start, buf_end)
        if len(win) == 0:
            return (symbol, None, None)
        start_ts = pd.to_datetime(start_date)
        end_ts   = pd.to_datetime(end_date)

        per_pattern: dict = {}
        any_match = False
        for pid, mod_path in module_paths.items():
            mod = importlib.import_module(mod_path)
            _load = getattr(mod, "load_params", None)
            res = mod.analyze(win, _load() if callable(_load) else None)
            out = serialize_per_pattern_result(
                res, end_role=end_roles[pid], label_horizon=label_horizon,
                win=win, start_ts=start_ts, end_ts=end_ts)
            per_pattern[pid] = out
            if out["summary"]["matches"] > 0:
                any_match = True

        if not any_match:
            return (symbol, None, None)
        return (symbol, per_pattern, None)
    except Exception as e:           # noqa: BLE001
        return (symbol, None, f"{type(e).__name__}: {e}")


def _aggregate_multi(results_iter, total: int, pattern_ids: list,
                     on_progress) -> dict:
    """聚合 worker 结果(纯逻辑,不起进程)。on_progress(scanned,total,hits,errors) 每 ticker 调一次。"""
    results, scanned, hits, errors = [], 0, 0, 0
    for symbol, per_pattern, err in results_iter:
        scanned += 1
        if err is not None:
            errors += 1
        elif per_pattern is not None:
            hits += 1
            results.append({"symbol": symbol, "per_pattern": per_pattern})
        on_progress(scanned, total, hits, errors)
    results.sort(key=lambda r: r["symbol"])
    return {"results": results, "scanned": scanned, "hits": hits, "errors": errors}


def _list_pkls(data_dir: str, ticker_regex):
    pkls = sorted(Path(data_dir).glob("*.pkl"))
    if ticker_regex:
        pat = re.compile(ticker_regex)
        pkls = [p for p in pkls if pat.match(p.stem)]
    return pkls


def run_scan_multi(*, data_dir,
                   pattern_specs_json: dict,
                   module_paths: dict,
                   pattern_ids: list,
                   end_roles: dict,
                   head_buffer_trading_days: int,
                   label_horizon: int,
                   start_date, end_date, workers, ticker_regex, scan_ts,
                   outputs_root="outputs/path2_web",
                   on_progress=lambda *a: None,
                   executor_factory=None,
                   cancel_event=None, save_event=None) -> dict:
    """并发扫 data_dir/*.pkl,多 pattern 同时跑 + 落盘 MultiScanResultFile(spec §3.1)。

    cancel_event set + save_event set → break 优雅退出(已聚结果落盘,scan.partial=True);
    cancel_event set 但 save_event 未 set → 抛 ScanCancelled。
    """
    if executor_factory is None:
        executor_factory = lambda w: ProcessPoolExecutor(max_workers=w)
    pkls = _list_pkls(data_dir, ticker_regex)
    total = len(pkls)

    start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
    buf_start = start_ts - pd.Timedelta(days=round(head_buffer_trading_days * TRADING_TO_CALENDAR_RATIO))
    buf_end   = end_ts   + pd.Timedelta(days=round(label_horizon * TRADING_TO_CALENDAR_RATIO))
    win_start, win_end = str(buf_start.date()), str(buf_end.date())

    def _iter():
        ex = executor_factory(max(1, workers))
        try:
            futs = [ex.submit(_scan_ticker_multi, str(p), module_paths,
                              start_date, end_date, win_start, win_end,
                              end_roles, label_horizon) for p in pkls]
            for fut in as_completed(futs):
                if cancel_event is not None and cancel_event.is_set():
                    # 强制终止 worker(SIGKILL + waitpid 死亡确认)
                    pids = [p.pid for p in list(getattr(ex, "_processes", {}).values())
                            if p.pid is not None]
                    for pid in pids:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    ex.shutdown(wait=False, cancel_futures=True)
                    for pid in pids:
                        try:
                            os.waitpid(pid, 0)
                        except ChildProcessError:
                            pass
                    if save_event is not None and save_event.is_set():
                        break
                    raise ScanCancelled()
                yield fut.result()
        finally:
            ex.shutdown(wait=False)

    agg = _aggregate_multi(_iter(), total, pattern_ids, on_progress)
    partial = save_event is not None and save_event.is_set()
    per_pattern_meta = {pid: {"pattern_spec": pattern_specs_json[pid],
                              "end_role": end_roles[pid]}
                        for pid in pattern_ids}
    result = {
        "pattern_ids": pattern_ids,
        "per_pattern": per_pattern_meta,
        "scan": {
            "scan_ts": scan_ts,
            "start_date": str(start_date), "end_date": str(end_date),
            "workers": workers,
            "scanned": agg["scanned"], "hits": agg["hits"], "errors": agg["errors"],
            "dataset_dir": str(data_dir), "params": "default",
            "win_start": win_start, "win_end": win_end,
            "label_horizon": label_horizon,
            "partial": partial,
        },
        "results": agg["results"],
    }
    write_result_file_flat(result, scan_ts, outputs_root)
    return result


def write_result_file_flat(result: dict, scan_ts: str, outputs_root: str) -> Path:
    out_dir = Path(outputs_root) / "scans"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{scan_ts}.json"
    path.write_text(json.dumps(result, ensure_ascii=False))
    return path


def list_scans_flat(outputs_root: str = "outputs/path2_web") -> list[dict]:
    """[{scan_ts, pattern_ids, hits, total, size, partial}, ...],按 scan_ts 倒序。
    单文件 json 读 pattern_ids / scan.hits / scan.scanned / scan.partial;读不出 → 全 None/False。"""
    d = Path(outputs_root) / "scans"
    if not d.exists():
        return []
    rows = []
    for p in d.glob("*.json"):
        try:
            blob = json.loads(p.read_text())
            pattern_ids = blob.get("pattern_ids", [])
            scan_section = blob["scan"]
            hits = scan_section.get("hits")
            total = scan_section.get("scanned")
            partial = bool(scan_section.get("partial", False))
        except (json.JSONDecodeError, KeyError, OSError):
            pattern_ids, hits, total, partial = [], None, None, False
        rows.append({"scan_ts": p.stem, "pattern_ids": pattern_ids,
                     "hits": hits, "total": total,
                     "size": p.stat().st_size, "partial": partial})
    rows.sort(key=lambda r: r["scan_ts"], reverse=True)
    return rows


def load_scan_flat(scan_ts: str, outputs_root: str = "outputs/path2_web") -> dict:
    path = Path(outputs_root) / "scans" / f"{scan_ts}.json"
    return json.loads(path.read_text())


def delete_scan_flat(scan_ts: str, outputs_root: str = "outputs/path2_web") -> None:
    """删 outputs_root/scans/<scan_ts>.json;不存在 → FileNotFoundError(原生)。"""
    path = Path(outputs_root) / "scans" / f"{scan_ts}.json"
    path.unlink()
