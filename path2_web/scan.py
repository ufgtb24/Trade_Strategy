"""并发扫描:每只股读 pkl → slice_window → analyze → 命中则序列化 → 聚合落盘。

_scan_ticker 模块级(ProcessPool pickle 安全);_aggregate 纯聚合(可注入迭代器单测);
run_scan 起池(执行器可注入,测试用线程池免起进程)。worker 用
module.analyze(win, module.load_params())——读 app 同目录 params.yaml(SSoT,
改 yaml 下一次 /scan 即生效,无需重启 web)。
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

from path2.eval import match_forward_returns
from path2_web.data import slice_window
from path2_web.serialize import serialize_analysis, summarize

TRADING_TO_CALENDAR_RATIO = 1.65   # 交易日→日历日(与 scripts/path2_eval_bottom_breakout_burst.py 同源同值)


class ScanCancelled(Exception):
    """run_scan 检测到 cancel_event 已 set,主动退出。"""


def analyze_single(*, pkl_path, module_path, start_date, end_date,
                   end_role=None, label_horizon=None,
                   buf_start=None, buf_end=None):
    """单股 analyze 的纯函数(_scan_ticker 与 /preview 共用)。

    返回 (analysis_dict, summary_dict, scan_meta_dict)。
    空窗 / 0 命中 → analysis={"events":[],"matches":[],"role_index":{}}, summary={"events":0,"matches":0}
    (注:返回空集而非 None,/preview 端要看到"调参后无 match"的合法结果;
     _scan_ticker 在外层判断 matches==[] 转 None,保持"0 命中跳过"的 scan 语义)

    协议:
      - end_role=None → 严格 [start_date, end_date] 切窗,不过滤、不算 label
        (此时 buf_start/buf_end 应为 None,内部用 start_date/end_date 切窗)
      - end_role 非 None → 调用方必须传 buf_start/buf_end(预先 TRADING_TO_CALENDAR_RATIO 推宽);
        analyze 用 [buf_start, buf_end] 切窗;match 按 [start_date, end_date] 过滤;注入 forward_return
    """
    df = pd.read_pickle(pkl_path)
    mod = importlib.import_module(module_path)
    buffered = end_role is not None

    if buffered:
        win = slice_window(df, buf_start, buf_end)
        win_start, win_end = buf_start, buf_end
    else:
        win = slice_window(df, start_date, end_date)
        win_start, win_end = start_date, end_date

    def meta_template():
        return {"start_date": start_date, "end_date": end_date,
                "win_start": win_start, "win_end": win_end,
                "end_role": end_role, "label_horizon": label_horizon}

    if len(win) == 0:
        return ({"events": [], "matches": [], "role_index": {}},
                {"events": 0, "matches": 0}, meta_template())

    # worker 内每次重新 load_params 读 yaml(SSoT) → 真热加载,改 yaml 不重启 web。
    # mod 缺 load_params(如测试 fake_eval_app)→ fallback,走 analyze 的 params=None 默认。
    _load = getattr(mod, "load_params", None)
    res = mod.analyze(win, _load() if callable(_load) else None)

    if not buffered:
        analysis = serialize_analysis(res)
        summary = summarize(res)
        return (analysis, summary, meta_template())

    # ── 缓冲链路:窗口过滤 + label(口径与 eval 脚本一致) ──
    start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
    ret_by_id: dict = {}
    for m in res.matches:
        ev = m.role_index[end_role]
        buy_date = win["date"].iat[ev.start_idx]
        if not (start_ts <= buy_date <= end_ts):
            continue
        ret_by_id[m.event_id] = match_forward_returns(m, end_role, win, [label_horizon])[label_horizon]
    analysis = serialize_analysis(res)           # events 全集照旧(缓冲段灰色层数据源)
    analysis["matches"] = [
        {**md, "forward_return": ret_by_id[md["event_id"]]}
        for md in analysis["matches"] if md["event_id"] in ret_by_id
    ]
    summary = summarize(res)
    summary["matches"] = len(analysis["matches"])    # 徽章口径 = 窗内 match 数
    return (analysis, summary, meta_template())


def _scan_ticker(pkl_path: str, module_path: str, start, end,
                 buf_start=None, buf_end=None, end_role=None, label_horizon=None):
    """Worker:读 pkl → analyze_single → 0 命中跳过返 None,异常 → err 字符串。

    end_role 为 None → 老行为:严格 [start, end] 切窗,不过滤、不算 label。
    end_role 非 None(eval_meta 链路)→ [buf_start, buf_end] 缓冲切窗;match 按
    「end_role event 起点日期 ∈ [start, end](双端含)」过滤(同 eval 脚本口径,
    不按买点去重——web 以 match 为展示单位,spec D6),每个保留 match 注入
    forward_return = match_forward_returns(m, end_role, win, [label_horizon])[label_horizon]。
    空窗/过滤后 0 命中 → analysis=None,err=None(跳过);异常 → err 字符串(绝不抛)。"""
    symbol = Path(pkl_path).stem
    try:
        analysis, summary, _ = analyze_single(
            pkl_path=pkl_path, module_path=module_path,
            start_date=start, end_date=end,
            end_role=end_role, label_horizon=label_horizon,
            buf_start=buf_start, buf_end=buf_end)
        if not analysis["events"] and not analysis["matches"]:
            return (symbol, None, None, None)       # 空窗 → 跳过
        if not analysis["matches"]:
            return (symbol, None, None, None)       # 0 命中 → 跳过(scan 语义)
        return (symbol, analysis, summary, None)
    except Exception as e:
        return (symbol, None, None, f"{type(e).__name__}: {e}")


def _aggregate(results_iter, total: int, on_progress) -> dict:
    """聚合 worker 结果(纯逻辑,不起进程)。on_progress(scanned,total,hits,errors) 每 ticker 调一次。"""
    results, scanned, hits, errors = [], 0, 0, 0
    for symbol, analysis, summary, err in results_iter:
        scanned += 1
        if err is not None:
            errors += 1
        elif analysis is not None:
            hits += 1
            results.append({"symbol": symbol, "summary": summary, "analysis": analysis})
        on_progress(scanned, total, hits, errors)
    results.sort(key=lambda r: r["symbol"])
    return {"results": results, "scanned": scanned, "hits": hits, "errors": errors}


def _list_pkls(data_dir: str, ticker_regex):
    pkls = sorted(Path(data_dir).glob("*.pkl"))
    if ticker_regex:
        pat = re.compile(ticker_regex)
        pkls = [p for p in pkls if pat.match(p.stem)]
    return pkls


def run_scan(*, data_dir, module_path, pattern_spec_json, pattern_id,
             start_date, end_date, workers, ticker_regex, scan_ts,
             end_role=None, head_buffer_trading_days=None, label_horizon=None,
             outputs_root="outputs/path2_web", on_progress=lambda *a: None,
             executor_factory=None, cancel_event=None, save_event=None) -> dict:
    """并发扫 data_dir/*.pkl,聚合 + 落盘 §7.3 结果文件,返回结果 dict(含 scan 元信息)。
    executor_factory(workers)->Executor 可注入(默认 ProcessPoolExecutor;测试传 ThreadPoolExecutor)。

    end_role/head_buffer_trading_days/label_horizon 三者同有同无(api 层保证):
    全 None = 老行为(严格窗);有值 = 双端缓冲(公式与 eval 脚本一致),结果文件
    scan 节记录 win_start/win_end(实际切窗日期)/label_horizon/end_role。

    cancel_event set 时:若 save_event 也 set → break 优雅退出(用已聚 result 落盘,
    scan.partial=True);否则 → 抛 ScanCancelled(老行为)。"""
    if executor_factory is None:
        executor_factory = lambda w: ProcessPoolExecutor(max_workers=w)
    pkls = _list_pkls(data_dir, ticker_regex)
    total = len(pkls)

    buffered = end_role is not None
    if buffered:
        start_ts, end_ts = pd.to_datetime(start_date), pd.to_datetime(end_date)
        buf_start = start_ts - pd.Timedelta(days=round(head_buffer_trading_days * TRADING_TO_CALENDAR_RATIO))
        buf_end = end_ts + pd.Timedelta(days=round(label_horizon * TRADING_TO_CALENDAR_RATIO))
        win_start, win_end = str(buf_start.date()), str(buf_end.date())
    else:
        win_start, win_end = str(start_date), str(end_date)

    def _iter():
        ex = executor_factory(max(1, workers))
        try:
            futs = [ex.submit(_scan_ticker, str(p), module_path, start_date, end_date,
                              win_start if buffered else None, win_end if buffered else None,
                              end_role, label_horizon) for p in pkls]
            for fut in as_completed(futs):
                if cancel_event is not None and cancel_event.is_set():
                    # ── 强制终止 worker(SIGKILL + waitpid 死亡确认)──
                    # 早期版本用 proc.terminate()(SIGTERM)+shutdown(wait=False)→ race:
                    # shutdown 把 ex._processes 置 None,terminate 循环可能只覆盖子集,
                    # 且 SIGTERM 在 C extension(numpy/pandas)长 op 中虽可被 kernel 杀,
                    # 但 try/except 静默吞掉了 ProcessLookupError/AttributeError race,
                    # 用户观察到 worker 残留 CPU 100% 满载。
                    # fix(by tom 诊断):shutdown 之前抓 pid snapshot → SIGKILL(不可被任何
                    # 用户态拦截、kernel 直接 reap)→ shutdown 标记取消 pending →
                    # waitpid 阻塞确认死亡(防僵尸 + 防"已 cancel 但 ps 还看得见")。
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
                        break                       # 优雅退出,_aggregate 拿现有结果
                    raise ScanCancelled()           # 老行为
                yield fut.result()
        finally:
            ex.shutdown(wait=False)

    agg = _aggregate(_iter(), total, on_progress)
    partial = save_event is not None and save_event.is_set()
    result = {
        "pattern_id": pattern_id,
        "pattern_spec": pattern_spec_json,                       # §7.1 快照——结果文件自包含
        "scan": {
            "scan_ts": scan_ts, "start_date": str(start_date), "end_date": str(end_date),
            "workers": workers, "scanned": agg["scanned"], "hits": agg["hits"],
            "errors": agg["errors"], "dataset_dir": str(data_dir), "params": "default",
            "win_start": win_start, "win_end": win_end,
            "label_horizon": label_horizon if buffered else None, "end_role": end_role,
            "partial": partial,
        },
        "results": agg["results"],
    }
    write_result_file(result, pattern_id, scan_ts, outputs_root)
    return result


def write_result_file(result: dict, pattern_id: str, scan_ts: str, outputs_root: str) -> Path:
    out_dir = Path(outputs_root) / pattern_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{scan_ts}.json"
    path.write_text(json.dumps(result, ensure_ascii=False))
    return path


def list_scans(pattern_id: str, outputs_root: str = "outputs/path2_web") -> list[dict]:
    """[{scan_ts, hits, total, size, partial}, ...],按 scan_ts 倒序。
    单文件读 json 取 scan.hits / scan.scanned / scan.partial;读不出 → hits=total=None, partial=False。"""
    d = Path(outputs_root) / pattern_id
    if not d.exists():
        return []
    rows = []
    for p in d.glob("*.json"):
        try:
            scan_section = json.loads(p.read_text())["scan"]
            hits = scan_section.get("hits")
            total = scan_section.get("scanned")
            partial = bool(scan_section.get("partial", False))
        except (json.JSONDecodeError, KeyError, OSError):
            hits = total = None
            partial = False
        rows.append({"scan_ts": p.stem, "hits": hits, "total": total,
                     "size": p.stat().st_size, "partial": partial})
    rows.sort(key=lambda r: r["scan_ts"], reverse=True)
    return rows


def load_scan(pattern_id: str, scan_ts: str, outputs_root: str = "outputs/path2_web") -> dict:
    path = Path(outputs_root) / pattern_id / f"{scan_ts}.json"
    return json.loads(path.read_text())


def delete_scan(pattern_id: str, scan_ts: str, outputs_root: str = "outputs/path2_web") -> None:
    """删除单个结果文件;不存在 → FileNotFoundError(原生)。"""
    # 注:并发场景下,delete_scan 与正在写文件的 run_scan 之间无原子保护。dialog 在 currentScanId 上 disable 已防 80%,但跨会话场景未防;production 部署需补 lock。
    path = Path(outputs_root) / pattern_id / f"{scan_ts}.json"
    path.unlink()
