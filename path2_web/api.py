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
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from path2_web import scan as scan_mod
from path2_web.data import slice_window, serialize_ohlc
from path2_web.diagnose import diagnose_symbol
from path2_web.serialize import serialize_pattern


class ScanRequest(BaseModel):
    pattern_ids: list[str] = Field(..., min_length=1)
    start_date: str
    end_date: str
    workers: int = 8
    ticker_regex: str | None = None
    label_horizon: int = 20

    @field_validator("pattern_ids")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        seen: set = set()
        out: list = []
        for x in v:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out


def require_eval_meta(mod) -> dict:
    """读 app 模块 eval_meta() 协议。铁律下 discovery 已闸过滤,api 调到此处不可能 None。
    若仍 None / 字段不全 → ValueError(防御性,非业务路径)。
    """
    fn = getattr(mod, "eval_meta", None)
    if not callable(fn):
        raise ValueError("eval_meta missing or non-callable (discovery gate failed)")
    load_params = getattr(mod, "load_params", None)
    meta = fn(load_params()) if callable(load_params) else fn()
    if not isinstance(meta, dict) or "end_role" not in meta or "head_buffer_trading_days" not in meta:
        raise ValueError(f"eval_meta returned invalid dict: {meta!r}")
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

    _TS_PATTERN = r"^\d{8}T\d{6}$"

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

    @router.get("/scans/")
    def scans_list_flat():
        return scan_mod.list_scans_flat(outputs_root)

    @router.get("/scans/{scan_ts}")
    def scan_load_flat(scan_ts: str = FPath(..., pattern=_TS_PATTERN)):
        try:
            return scan_mod.load_scan_flat(scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")

    @router.delete("/scans/{scan_ts}")
    def scan_delete_flat(scan_ts: str = FPath(..., pattern=_TS_PATTERN)):
        try:
            scan_mod.delete_scan_flat(scan_ts, outputs_root)
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
        """单股临时计算 — 复刻 multi-scan worker 的 buffered+label 链路,不落盘,单 pattern。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")

        try:
            meta = require_eval_meta(mod)
            end_role = meta["end_role"]
            head_buf = meta["head_buffer_trading_days"]
            start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
            buf_start = str((start_ts - pd.Timedelta(days=round(head_buf * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())
            buf_end   = str((end_ts   + pd.Timedelta(days=round(label_horizon * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())

            # 复刻 worker 单 pattern 调用
            df = pd.read_pickle(pkl)
            win = slice_window(df, buf_start, buf_end)
            _load = getattr(mod, "load_params", None)
            res = mod.analyze(win, _load() if callable(_load) else None)
            from path2_web.serialize import serialize_per_pattern_result
            out = serialize_per_pattern_result(
                res, end_role=end_role, label_horizon=label_horizon,
                win=win, start_ts=start_ts, end_ts=end_ts)
            pattern_spec = serialize_pattern(mod.build_pattern(mod.load_params()))
            scan_meta = {
                "start_date": start, "end_date": end,
                "win_start": buf_start, "win_end": buf_end,
                "label_horizon": label_horizon, "end_role": end_role,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"{type(e).__name__}: {e}") from e
        return {"analysis": out["analysis"], "summary": out["summary"],
                "pattern_spec": pattern_spec, "scan": scan_meta}

    @router.post("/scan")
    async def post_scan(req: ScanRequest):           # async:在 event loop 线程跑,get_running_loop 可用
        # 校验所有 pattern_id 在 registry
        for pid in req.pattern_ids:
            if registry.get(pid) is None:
                raise HTTPException(404, f"unknown pattern: {pid}")
        cfg = get_config()
        scan_ts = time.strftime("%Y%m%dT%H%M%S")

        specs: dict = {}
        module_paths: dict = {}
        end_roles: dict = {}
        head_bufs: list = []
        for pid in req.pattern_ids:
            mod = registry.get(pid)
            spec_json = serialize_pattern(mod.build_pattern(mod.load_params()))
            specs[pid] = spec_json
            module_paths[pid] = registry.module_path(pid)
            meta = require_eval_meta(mod)
            end_roles[pid] = meta["end_role"]
            head_bufs.append(meta["head_buffer_trading_days"])
        head_buffer = max(head_bufs)
        loop = asyncio.get_running_loop()

        def job(on_progress, cancel_event, save_event):
            return scan_mod.run_scan_multi(
                data_dir=cfg["dataset_dir"],
                pattern_specs_json=specs,
                module_paths=module_paths,
                pattern_ids=req.pattern_ids,
                end_roles=end_roles,
                head_buffer_trading_days=head_buffer,
                label_horizon=req.label_horizon,
                start_date=req.start_date, end_date=req.end_date,
                workers=req.workers, ticker_regex=req.ticker_regex,
                scan_ts=scan_ts, outputs_root=outputs_root,
                on_progress=on_progress, executor_factory=_exec_factory,
                cancel_event=cancel_event, save_event=save_event,
            )

        def done_meta(result):
            s = result["scan"]
            return {"pattern_ids": req.pattern_ids, "scan_ts": scan_ts,
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
