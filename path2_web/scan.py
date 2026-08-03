"""并发扫描(多 pattern):每只股读 pkl 一次 → slice_window → 对每 pattern analyze → 聚合 → 落盘。

铁律:所有 pattern 必须经 discovery eval_meta 闸,故扫描永远走 buffered 路径,
end_node/head_buffer/label_horizon 三者永远非 None。删除旧非缓冲分支。

结果文件 schema MultiScanResultFile(spec §3.1):
  {pattern_ids,
   per_pattern: {pid: {pattern_spec, end_node, stats, stats_drawdown,
                        [params_snapshot, params_hash, params_provenance]}},  # 后三者仅当调用方传入 pattern_params_dicts[pid] 时存在,老 scan file 没有
   scan: {...win_*/label_horizon/scanned/hits/errors/params_schema_version/note/...},
   results: [{symbol, per_pattern: {pid: {summary, analysis, max_forward_return, min_forward_drawdown}}}, ...]}
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import os
import re
import signal
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUTS_ROOT = str(_REPO_ROOT / "outputs" / "path2_web")   # 锚到 repo root,不受启动 CWD 影响

from path2.dag.engine import analyze as _dag_analyze
from path2.debug import set_current_symbol
from path2_web.data import slice_window
from path2_web.gate_collector import attach_and_collect, detach
from path2_web.serialize import serialize_per_pattern_result

TRADING_TO_CALENDAR_RATIO = 1.65   # 交易日 → 日历日(与 scripts/path2_eval_bottom_breakout_burst.py 同源)


def params_hash(d: dict) -> str:
    """canonical json(sort_keys)的 sha256,scan file 内 per-pattern 参数指纹。"""
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


class ScanCancelled(Exception):
    """run_scan_multi 检测到 cancel_event 已 set,主动退出。"""


def _scan_ticker_multi(pkl_path, module_paths, start_date, end_date,
                       buf_start, buf_end, end_nodes, label_horizon,
                       pattern_params_dicts,
                       price_min=None, price_max=None, volume_min=None,
                       first_passage_enabled=True, first_passage_k=5.0):
    """单股多 pattern worker(模块级,ProcessPool pickle 安全)。

    返回 4-tuple (symbol, per_pattern_dict | None, random_first_passage | None, err | None):
      per_pattern_dict 为 None = 该股不入选并集(所有 pattern matches 全空)。
      random_first_passage = ticker-scoped 随机日基线(全 pattern 共享),仅 any_match
        且 first_passage_enabled 时才算;否则 None。
      err 非 None = 该股扫描异常,errors++,不进 results。

    每股 read_pkl 一次,buf_win 切一次,然后逐 pattern import+analyze+投影。

    pattern_params_dicts:{pid: dict} | None——主进程一次 load 的参数快照,直传每个
    worker(竞态修复:scan 期间改 yaml 不再影响本次 scan)。pid 在其中有值且该 app
    有 Params 类 → from_dict 重建;否则退回旧 load_params()/Params.default() 路径。

    price_min/price_max:match 级价格过滤(闭区间,锚 end_node 事件日收盘价),透传给
    serialize_per_pattern_result。volume_min:股票级预筛——扫描区间内日均成交量必须
    严格大于它,否则整只股跳过、不跑 detector(判定窗是 [start_date, end_date],不是
    buffered win)。

    df 语义:传 win(slice_window 切出的 buf 窗口,已含 horizon 后向缓冲)+ start_ts/end_ts
    (scan 区间)。win 比 scan 区间宽(含缓冲),start_ts/end_ts 在其内过滤出 scan 区间日、
    i+horizon<len(win) 保证 horizon 可见——这是正确口径,不退化(不改成全票 df)。
    """
    from path2.eval import random_day_first_passage

    symbol = Path(pkl_path).stem
    set_current_symbol(symbol)
    try:
        df = pd.read_pickle(pkl_path)
        win = slice_window(df, buf_start, buf_end)
        if len(win) == 0:
            return (symbol, None, None, None)
        start_ts = pd.to_datetime(start_date)
        end_ts   = pd.to_datetime(end_date)

        # 股票级成交量预筛(dev BreakoutStrategy/analysis/scanner.py:350-361 的对应物)。
        # 判定窗是用户指定的扫描区间,不是 buffered win——用缓冲窗会把缓冲期成交量混进
        # 均值,与用户看到的区间不符。<= 即剔除(必须严格大于才通过),边界照搬 dev。
        if volume_min is not None:
            scan_win = win[(win["date"] >= start_ts) & (win["date"] <= end_ts)]
            if len(scan_win) == 0 or scan_win["volume"].mean() <= volume_min:
                return (symbol, None, None, None)

        per_pattern: dict = {}
        any_match = False
        for pid, mod_path in module_paths.items():
            mod = importlib.import_module(mod_path)
            pd_dict = (pattern_params_dicts or {}).get(pid)
            if pd_dict is not None and hasattr(mod, "Params"):
                # 竞态修复:主进程一次 load 的 dict 直达 worker,scan 期间改 yaml 不再影响本次 scan
                params = mod.Params.from_dict(pd_dict)
            else:
                _load = getattr(mod, "load_params", None)
                loaded = _load() if callable(_load) else None
                params = loaded if loaded is not None else mod.Params.default()
            # 不直接调 mod.analyze(win, params)——它内部自建 spec,拿不到 spec 就挂不了
            # on_gate collector(必须在 analyze 跑之前挂)。这里复刻其内部逻辑
            # (build_pattern(p) + engine.analyze(spec, df, p)),换来 attach/detach 窗口。
            spec = mod.build_pattern(params)
            collector = attach_and_collect(spec)
            try:
                res = _dag_analyze(spec, win, params)
            finally:
                detach(spec)
            res = dataclasses.replace(res, gate_failures=collector.snapshot())
            out = serialize_per_pattern_result(
                res, end_node=end_nodes[pid], label_horizon=label_horizon,
                win=win, start_ts=start_ts, end_ts=end_ts,
                price_min=price_min, price_max=price_max,
                first_passage_enabled=first_passage_enabled,
                first_passage_k=first_passage_k)
            per_pattern[pid] = out
            if out["summary"]["matches"] > 0:
                any_match = True

        if not any_match:
            return (symbol, None, None, None)
        # 随机日基线:ticker-scoped,每票算一次、全 pattern 共享;仅 any_match 后才算。
        random_fp = None
        if first_passage_enabled:
            random_fp = random_day_first_passage(
                symbol, win, start_ts, end_ts, label_horizon, first_passage_k)
        return (symbol, per_pattern, random_fp, None)
    except Exception as e:           # noqa: BLE001
        return (symbol, None, None, f"{type(e).__name__}: {e}")
    finally:
        set_current_symbol(None)


def _aggregate_multi(results_iter, total: int, pattern_ids: list,
                     on_progress) -> dict:
    """聚合 worker 结果(纯逻辑,不起进程)。on_progress(scanned,total,hits,errors) 每 ticker 调一次。

    解包 worker 4-tuple (symbol, per_pattern, random_first_passage, err);命中票的
    StockResult 落 random_first_passage 字段(ticker-scoped 随机日基线,全 pattern 共享)。
    """
    results, scanned, hits, errors = [], 0, 0, 0
    for symbol, per_pattern, random_first_passage, err in results_iter:
        scanned += 1
        if err is not None:
            errors += 1
        elif per_pattern is not None:
            hits += 1
            results.append({"symbol": symbol, "per_pattern": per_pattern,
                            "random_first_passage": random_first_passage})
        on_progress(scanned, total, hits, errors)
    results.sort(key=lambda r: r["symbol"])
    return {"results": results, "scanned": scanned, "hits": hits, "errors": errors}


def _aggregate_first_passage(results: list, pattern_ids: list,
                             first_passage_k: float = 5.0) -> dict:
    """集合级首次穿越方向统计(单组,几何对称单 k)。{pid: stats_dict}。

    ① 全局随机基线:跨所有 results 的 random_first_passage.counts(单组)累加。
    ② 每 pattern 从 per_pattern[pid].match_fp_counts(单组)累加买点日四态。
    ③ 每 pattern 一项 stats(含 k 标注)。ratio=up/(up+down);全 0 → None。
    """
    STATES = ("up", "down", "both", "none")
    global_rand = {s: 0 for s in STATES}
    for r in results:
        rfp = r.get("random_first_passage")
        if not rfp:
            continue
        for s in STATES:
            global_rand[s] += rfp.get("counts", {}).get(s, 0)

    out: dict[str, dict] = {}
    for pid in pattern_ids:
        mc = {s: 0 for s in STATES}
        for r in results:
            mfp = r.get("per_pattern", {}).get(pid, {}).get("match_fp_counts")
            if not mfp:
                continue
            for s in STATES:
                mc[s] += mfp.get(s, 0)
        up, down = mc["up"], mc["down"]
        denom = up + down
        ratio = (up / denom) if denom else None
        r_up, r_down = global_rand["up"], global_rand["down"]
        r_denom = r_up + r_down
        random_ratio = (r_up / r_denom) if r_denom else None
        out[pid] = {
            "up": up, "down": down, "both": mc["both"], "none": mc["none"],
            "n_match": up + down + mc["both"] + mc["none"],
            "ratio": ratio,
            "random_up": r_up, "random_down": r_down,
            "random_both": global_rand["both"], "random_none": global_rand["none"],
            "random_n": r_up + r_down + global_rand["both"] + global_rand["none"],
            "random_ratio": random_ratio,
            "k": first_passage_k,
        }
    return out


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
                   end_nodes: dict,
                   head_buffer_trading_days: int,
                   label_horizon: int,
                   first_passage_enabled: bool = True,
                   first_passage_k: float = 5.0,
                   start_date, end_date, workers, ticker_regex, scan_ts,
                   outputs_root=_DEFAULT_OUTPUTS_ROOT,
                   on_progress=lambda *a: None,
                   executor_factory=None,
                   cancel_event=None,
                   pattern_params_dicts: dict | None = None,
                   params_provenance: dict | None = None,
                   note: str | None = None,
                   name: str | None = None,
                   price_min: float | None = None,
                   price_max: float | None = None,
                   volume_min: float | None = None,
                   save_event=None) -> dict:
    """并发扫 data_dir/*.pkl,多 pattern 同时跑 + 落盘 MultiScanResultFile(spec §3.1)。

    cancel_event set + save_event set → break 优雅退出(已聚结果落盘,scan.partial=True);
    cancel_event set 但 save_event 未 set → 抛 ScanCancelled。

    pattern_params_dicts:{pid: dict} | None——主进程一次 load 的参数快照,直传每个
    worker(竞态修复),并落盘为 per_pattern[pid].params_snapshot/params_hash。
    params_provenance:{pid: str} | None——每 pattern 参数来源标注(如 "yaml"/"working_copy"),
    落盘为 per_pattern[pid].params_provenance,缺省("yaml")。
    note:本次 scan 的自由文本备注,落盘为 scan.note。
    price_min/price_max/volume_min:扫描过滤(见 _scan_ticker_multi);三者一并落盘为
    scan.filters,供事后解释命中数差异。
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
                              end_nodes, label_horizon,
                              pattern_params_dicts or {},
                              price_min=price_min, price_max=price_max,
                              volume_min=volume_min,
                              first_passage_enabled=first_passage_enabled,
                              first_passage_k=first_passage_k) for p in pkls]
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
    pattern_params_dicts = pattern_params_dicts or {}
    params_provenance = params_provenance or {}
    per_pattern_meta = {}
    for pid in pattern_ids:
        entry = {"pattern_spec": pattern_specs_json[pid], "end_node": end_nodes[pid]}
        snap = pattern_params_dicts.get(pid)
        if snap is not None:
            entry["params_snapshot"] = snap
            entry["params_hash"] = params_hash(snap)
            entry["params_provenance"] = params_provenance.get(pid, "yaml")
        per_pattern_meta[pid] = entry
    # 每 pattern 全宇宙聚合 stats / stats_drawdown(按 match 计,过滤 None)
    #   stats         → forward_return(mfr,只看涨)
    #   stats_drawdown → forward_drawdown(min_low,mfr 下行镜像,与 stats 并列、同 shape)
    # 延迟导入避免与 eval_runner(反向依赖 scan 的 TRADING_TO_CALENDAR_RATIO/_list_pkls)循环导入
    from path2_web.eval_runner import _summarize_flat
    for pid in pattern_ids:
        matches = [
            m
            for r in agg["results"]
            for m in r["per_pattern"].get(pid, {}).get("analysis", {}).get("matches", [])
        ]
        vals = [m["forward_return"] for m in matches
                if m.get("forward_return") is not None]
        per_pattern_meta[pid]["stats"] = _summarize_flat(vals)
        dd_vals = [m["forward_drawdown"] for m in matches
                   if m.get("forward_drawdown") is not None]
        per_pattern_meta[pid]["stats_drawdown"] = _summarize_flat(dd_vals)
    # 首次穿越方向集合统计(分类量):全局随机基线 + 每 pattern match 侧计数 → ratio/random_ratio
    if first_passage_enabled:
        fp_stats = _aggregate_first_passage(agg["results"], pattern_ids,
                                            first_passage_k=first_passage_k)
        for pid in pattern_ids:
            per_pattern_meta[pid]["first_passage_stats"] = fp_stats.get(pid, {})
    result = {
        "pattern_ids": pattern_ids,
        "per_pattern": per_pattern_meta,
        "scan": {
            "scan_ts": scan_ts,
            "name": name or scan_ts,
            "start_date": str(start_date), "end_date": str(end_date),
            "workers": workers,
            "scanned": agg["scanned"], "hits": agg["hits"], "errors": agg["errors"],
            "dataset_dir": str(data_dir),
            "params_schema_version": 1,
            "note": note,
            "win_start": win_start, "win_end": win_end,
            "label_horizon": label_horizon,
            "first_passage_k": first_passage_k,
            "filters": {"price_min": price_min, "price_max": price_max,
                        "volume_min": volume_min},
            "partial": partial,
        },
        "results": agg["results"],
    }
    write_result_file_flat(result, name or scan_ts, outputs_root)
    return result


def write_result_file_flat(result: dict, name: str, outputs_root: str) -> Path:
    out_dir = Path(outputs_root) / "scans"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(result, ensure_ascii=False))
    return path


def list_scans_flat(outputs_root: str = _DEFAULT_OUTPUTS_ROOT) -> list[dict]:
    """[{name, scan_ts, pattern_ids, hits, total, size, partial}, ...]。
    name = 文件名 stem(标识符);scan_ts = 文件内 scan.scan_ts(创建时间,排序用),
    读不出回退 stem(老文件兼容)。按 scan_ts 倒序。"""
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
            scan_ts = scan_section.get("scan_ts") or p.stem
        except (json.JSONDecodeError, KeyError, OSError):
            pattern_ids, hits, total, partial, scan_ts = [], None, None, False, p.stem
        rows.append({"name": p.stem, "scan_ts": scan_ts,
                     "pattern_ids": pattern_ids, "hits": hits, "total": total,
                     "size": p.stat().st_size, "partial": partial})
    rows.sort(key=lambda r: r["scan_ts"], reverse=True)
    return rows


def load_scan_flat(name: str, outputs_root: str = _DEFAULT_OUTPUTS_ROOT) -> dict:
    path = Path(outputs_root) / "scans" / f"{name}.json"
    return json.loads(path.read_text())


def delete_scan_flat(name: str, outputs_root: str = _DEFAULT_OUTPUTS_ROOT) -> None:
    """删 outputs_root/scans/<name>.json;不存在 → FileNotFoundError(原生)。"""
    path = Path(outputs_root) / "scans" / f"{name}.json"
    path.unlink()


def rename_scan_flat(old_name: str, new_name: str,
                     outputs_root: str = _DEFAULT_OUTPUTS_ROOT) -> None:
    """原子移动 {old}.json → {new}.json,同步更新 JSON 内 scan.note/scan.name。
    old 不存在 → FileNotFoundError;new 已存在 → FileExistsError(由 api 层翻译为 404/409)。"""
    scans_dir = Path(outputs_root) / "scans"
    old_path = scans_dir / f"{old_name}.json"
    new_path = scans_dir / f"{new_name}.json"
    if not old_path.exists():
        raise FileNotFoundError(old_name)
    if new_path.exists():
        raise FileExistsError(new_name)
    old_path.rename(new_path)
    blob = json.loads(new_path.read_text())
    if isinstance(blob.get("scan"), dict):
        blob["scan"]["note"] = new_name
        blob["scan"]["name"] = new_name
        new_path.write_text(json.dumps(blob, ensure_ascii=False))
