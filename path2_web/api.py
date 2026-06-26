"""HTTP 路由 + SSE 扫描编排。create_app 注入 registry/config/outputs_root。"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as FPath
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from path2_web import scan as scan_mod
from path2_web.data import slice_window, serialize_ohlc
from path2_web.diagnose import diagnose_symbol
from path2_web.serialize import serialize_pattern


class ScanRequest(BaseModel):
    pattern_id: str
    start_date: str
    end_date: str
    workers: int = 8
    ticker_regex: str | None = None
    label_horizon: int = 20


def resolve_eval_meta(mod) -> dict | None:
    """读 app 模块可选 eval_meta() 协议;缺失/非 callable/抛异常/键不全 → None(回退老行为)。

    传入当前 yaml 加载的 params (mod.load_params() 若存在),让 head_buffer_trading_days
    反映本次扫描真用的参数值 (yaml SSoT);否则 eval_meta() 内走 Params.default(),
    切出来的缓冲窗与 worker 实际 analyze 不匹配。"""
    fn = getattr(mod, "eval_meta", None)
    if not callable(fn):
        return None
    load_params = getattr(mod, "load_params", None)
    try:
        meta = fn(load_params()) if callable(load_params) else fn()
    except Exception:           # noqa: BLE001  协议防御:任何异常都按缺失处理
        return None
    if not isinstance(meta, dict) or "end_role" not in meta or "head_buffer_trading_days" not in meta:
        return None
    return meta


class ScanManager:
    """每个 scan_id 一个 asyncio.Queue + cancel_event;后台线程跑阻塞 run_scan,
    进度经 call_soon_threadsafe 投递。cancel(scan_id) set cancel_event → run_scan
    检测点抛 ScanCancelled → runner 捕获并发 done {cancelled: true}。"""

    def __init__(self):
        self._scans: dict = {}

    def start(self, loop, scan_id, job, done_meta_fn):
        q: asyncio.Queue = asyncio.Queue()
        cancel_event = threading.Event()
        save_event = threading.Event()
        self._scans[scan_id] = {"queue": q, "done": False, "last": None,
                                "cancel": cancel_event, "save": save_event}

        def on_progress(scanned, total, hits, errors):
            evt = {"scanned": scanned, "total": total, "hits": hits, "errors": errors}
            self._scans[scan_id]["last"] = evt
            loop.call_soon_threadsafe(q.put_nowait, evt)

        def runner():
            try:
                result = job(on_progress, cancel_event, save_event)
                done = {"type": "done", **done_meta_fn(result)}
            except scan_mod.ScanCancelled:
                done = {"type": "done", "cancelled": True, "error": None,
                        "hits": 0, "errors": 0, "total": 0}
            except Exception as e:           # noqa: BLE001
                done = {"type": "done", "error": f"{type(e).__name__}: {e}",
                        "hits": 0, "errors": 0, "total": 0}
            self._scans[scan_id]["last"] = done
            self._scans[scan_id]["done"] = True
            loop.call_soon_threadsafe(q.put_nowait, done)

        loop.run_in_executor(None, runner)

    def cancel(self, scan_id, save: bool = False) -> bool:
        """set cancel_event;save=True 时同时 set save_event,run_scan 检测点会优雅退出并落盘。
        scan_id 已知返 True(幂等);scan_id 未知返 False。"""
        entry = self._scans.get(scan_id)
        if entry is None:
            return False
        if save:
            entry["save"].set()
        entry["cancel"].set()
        return True

    async def stream(self, scan_id):
        entry = self._scans.get(scan_id)
        if entry is None:
            yield {"event": "message", "data": '{"type":"error","msg":"unknown scan_id"}'}
            return
        q = entry["queue"]
        # 晚连补发末态
        if entry["done"] and entry["last"] is not None:
            yield {"event": "message", "data": json.dumps(entry["last"], ensure_ascii=False)}
            return
        while True:
            evt = await q.get()
            yield {"event": "message", "data": json.dumps(evt, ensure_ascii=False)}
            if evt.get("type") == "done":
                return


def build_router(*, registry, config_path, get_config, set_config,
                 outputs_root, use_thread_pool=False) -> APIRouter:
    router = APIRouter()
    manager = ScanManager()
    _exec_factory = ((lambda w: ThreadPoolExecutor(max_workers=w)) if use_thread_pool
                     else (lambda w: ProcessPoolExecutor(max_workers=w)))

    @router.get("/patterns")
    def get_patterns():
        out = []
        for pid in registry.ids():
            mod = registry.get(pid)
            # 与 /scan 同口径:每次重新 build_pattern(load_params()) 反映当前 yaml(SSoT)。
            # mod 缺 load_params → 回退用模块级 PATTERN_DAG(Params.default() 闭合)。
            _load = getattr(mod, "load_params", None)
            spec = mod.build_pattern(_load()) if callable(_load) else mod.PATTERN_DAG
            out.append(serialize_pattern(spec))
        return out

    @router.get("/ohlc")
    def get_ohlc(symbol: str, start: str, end: str):
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")
        win = slice_window(pd.read_pickle(pkl), start, end)
        return serialize_ohlc(symbol, win)

    @router.get("/config")
    def read_config():
        return get_config()

    @router.put("/config")
    def write_config(cfg: dict):
        set_config(cfg)
        return {"ok": True}

    _TS_PATTERN = r"^\d{8}T\d{6}$"

    @router.get("/scans/{pattern_id}")
    def scans_list(pattern_id: str):
        if registry.get(pattern_id) is None:
            raise HTTPException(404, "unknown pattern_id")
        return scan_mod.list_scans(pattern_id, outputs_root)

    @router.get("/scans/{pattern_id}/{scan_ts}")
    def scan_load(
        pattern_id: str,
        scan_ts: str = FPath(..., pattern=_TS_PATTERN),
    ):
        if registry.get(pattern_id) is None:
            raise HTTPException(404, "unknown pattern_id")
        try:
            return scan_mod.load_scan(pattern_id, scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")

    @router.delete("/scans/{pattern_id}/{scan_ts}")
    def scan_delete(
        pattern_id: str,
        scan_ts: str = FPath(..., pattern=_TS_PATTERN),
    ):
        if registry.get(pattern_id) is None:
            raise HTTPException(404, "unknown pattern_id")
        try:
            scan_mod.delete_scan(pattern_id, scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")
        return {"ok": True}

    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str):
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")
        win = slice_window(pd.read_pickle(pkl), start, end)
        # 诊断每次都重新 build_pattern(load_params())——与 /scan 同口径(yaml SSoT 热加载)。
        # 不能复用 mod.PATTERN_DAG(它是 import 时一次性 build,Params.default() 闭合,与 yaml 漂移)。
        spec = mod.build_pattern(mod.load_params())
        return diagnose_symbol(spec, win, None, symbol=symbol, pattern_id=pattern_id)

    @router.get("/preview")
    def get_preview(pattern_id: str, symbol: str, start: str, end: str,
                    label_horizon: int = 20):
        """单股临时计算 — 复刻 /scan 的 buffered+label 链路,不落盘。
        pattern_spec 用 mod.load_params() 实时 build(yaml SSoT,改 yaml 立即反映)。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")

        try:
            meta = resolve_eval_meta(mod)
            if meta:
                end_role = meta["end_role"]
                head_buf = meta["head_buffer_trading_days"]
                start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
                buf_start = str((start_ts - pd.Timedelta(days=round(head_buf * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())
                buf_end   = str((end_ts   + pd.Timedelta(days=round(label_horizon * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())
                analysis, summary, scan_meta = scan_mod.analyze_single(
                    pkl_path=str(pkl), module_path=registry.module_path(pattern_id),
                    start_date=start, end_date=end,
                    end_role=end_role, label_horizon=label_horizon,
                    buf_start=buf_start, buf_end=buf_end)
            else:
                analysis, summary, scan_meta = scan_mod.analyze_single(
                    pkl_path=str(pkl), module_path=registry.module_path(pattern_id),
                    start_date=start, end_date=end,
                    end_role=None, label_horizon=None)
                # 强制 scan_meta 的 label_horizon=null(非 buffered 路径下不算 label)
                scan_meta["label_horizon"] = None

            pattern_spec = serialize_pattern(mod.build_pattern(mod.load_params()))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"{type(e).__name__}: {e}") from e
        return {"analysis": analysis, "summary": summary,
                "pattern_spec": pattern_spec, "scan": scan_meta}

    @router.post("/scan")
    async def post_scan(req: ScanRequest):           # async:在 event loop 线程跑,get_running_loop 可用
        mod = registry.get(req.pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {req.pattern_id}")
        cfg = get_config()
        scan_ts = time.strftime("%Y%m%dT%H%M%S")
        # spec_json 每次 /scan 重新从 yaml build,前端拓扑/where 阈值反映本次扫描真用的参数
        spec_json = serialize_pattern(mod.build_pattern(mod.load_params()))
        meta = resolve_eval_meta(mod)
        loop = asyncio.get_running_loop()

        def job(on_progress, cancel_event, save_event):
            return scan_mod.run_scan(
                data_dir=cfg["dataset_dir"],
                module_path=registry.module_path(req.pattern_id),
                pattern_spec_json=spec_json,
                pattern_id=req.pattern_id,
                start_date=req.start_date, end_date=req.end_date,
                workers=req.workers, ticker_regex=req.ticker_regex,
                end_role=meta["end_role"] if meta else None,
                head_buffer_trading_days=meta["head_buffer_trading_days"] if meta else None,
                label_horizon=req.label_horizon if meta else None,
                scan_ts=scan_ts, outputs_root=outputs_root,
                on_progress=on_progress, executor_factory=_exec_factory,
                cancel_event=cancel_event,
                save_event=save_event,
            )

        def done_meta(result):
            s = result["scan"]
            return {"pattern_id": req.pattern_id, "scan_ts": scan_ts,
                    "hits": s["hits"], "errors": s["errors"], "total": s["scanned"],
                    "partial": bool(s.get("partial", False))}

        manager.start(loop, scan_ts, job, done_meta)
        return {"scan_id": scan_ts}

    @router.get("/scan/{scan_id}/stream")
    async def scan_stream(scan_id: str, request: Request):
        return EventSourceResponse(manager.stream(scan_id))

    @router.post("/scan/{scan_id}/cancel")
    def scan_cancel(scan_id: str, save: bool = False):
        if not manager.cancel(scan_id, save=save):
            raise HTTPException(404, "scan not running or unknown")
        return {"ok": True}

    return router
