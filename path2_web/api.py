"""HTTP 路由 + SSE 扫描编排。create_app 注入 registry/config/outputs_root。"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as FPath
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from path2.dag import diagnose as _dag_diagnose
from path2.dag.engine import analyze as _dag_analyze_engine
from path2_web import scan as scan_mod
from path2_web.data import slice_window, serialize_ohlc
from path2_web.diagnose import diagnose_symbol, derive_response, Query
from path2_web.gate_collector import attach_and_collect, detach
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
    if not isinstance(meta, dict) or "end_node" not in meta or "head_buffer_trading_days" not in meta:
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
            data = scan_mod.load_scan_flat(scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")
        # 用当前 palette 覆盖历史 scan file 里冻结的 event_styles。颜色是纯 UI 关注点,
        # 不属于扫描结果快照的必要部分——允许调 palette 后不用重扫也生效。
        # pattern 在 registry 缺失(被删/改名)时跳过,保留文件里的原值。
        for pid, meta in (data.get("per_pattern") or {}).items():
            mod = registry.get(pid)
            if mod is None:
                continue
            _load = getattr(mod, "load_params", None)
            spec = mod.build_pattern(_load()) if callable(_load) else mod.PATTERN_DAG
            pattern_spec = meta.get("pattern_spec")
            if isinstance(pattern_spec, dict) and "event_styles" in pattern_spec:
                fresh = serialize_pattern(spec)
                pattern_spec["event_styles"] = fresh["event_styles"]
                pattern_spec["debug_enabled_classes"] = fresh["debug_enabled_classes"]  # v4 backfill:老 scan 文件补齐 non-optional 字段
        return data

    @router.delete("/scans/{scan_ts}")
    def scan_delete_flat(scan_ts: str = FPath(..., pattern=_TS_PATTERN)):
        try:
            scan_mod.delete_scan_flat(scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")
        return {"ok": True}

    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                     scope: Optional[str] = None,
                     src_node: Optional[str] = None, dst_node: Optional[str] = None,
                     event_class: Optional[str] = None, event_id: Optional[str] = None,
                     src_event_id: Optional[str] = None, dst_event_id: Optional[str] = None,
                     edge_id: Optional[str] = None,
                     start_bar: Optional[int] = None, end_bar: Optional[int] = None,
                     anchor_kind: Optional[str] = None):
        # spec 2026-07-14-path2-web-debug-breakpoints §D: time diag 写 DEBUG_BAR_RANGE
        # 供 path2.debug_ctx.debug_break 消费。v2(2026-07-15 event-debug-dual-emit) 契约 #7:
        # handler 结束必 pop env(request 级作用域, 防跨 request 污染 + scan pool 继承挂死)。
        # v3(2026-07-16 node-gated-debug,后更名 anchor_kind) 契约 #7 扩展:双 env 独立
        # (DEBUG_BAR_RANGE + DEBUG_ANCHOR_KIND)· finally 无条件 pop 两 env(即使本次未写
        # DEBUG_ANCHOR_KIND 也 pop 兜底)。
        if start_bar is not None and end_bar is not None:
            os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
        if anchor_kind:                             # ★ v3 · 空串也视同未传
            os.environ["DEBUG_ANCHOR_KIND"] = anchor_kind
        if event_class:                             # ★ v4 · 空串也视同未传
            os.environ["DEBUG_EVENT_CLASS"] = event_class
        try:
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
            if scope is None:
                # legacy 路径:无 scope 参数 → 字节等价,前端旧 api.ts::getDiagnose 不用改。
                return diagnose_symbol(spec, win, None, symbol=symbol, pattern_id=pattern_id)
            # A' 按 scope 分派(见 docs/research/2026-07-18_debug-double-pause-analysis/final_report.md §3.1):
            # scope=nodes 只需 diag · scope=time/pair 只需 result(+ gate_failures) · 三 scope 数据依赖完全正交
            # (derive_response 三 branch 逐字核实无 hidden cross-dep)· 只跑该 scope 需要的那 pass 消双 pause。
            query = Query(symbol=symbol, scope=scope, src_node=src_node, dst_node=dst_node,
                         event_class=event_class, event_id=event_id,
                         src_event_id=src_event_id, dst_event_id=dst_event_id,
                         edge_id=edge_id, start_bar=start_bar, end_bar=end_bar)
            diag = None
            result = None
            if scope == "nodes":
                diag = _dag_diagnose(spec, win, None)
            elif scope in ("time", "pair"):
                collector = attach_and_collect(spec)
                try:
                    result = _dag_analyze_engine(spec, win, None)
                    result = dataclasses.replace(result, gate_failures=collector.snapshot())
                finally:
                    detach(spec)
            # unknown scope 走 derive_response · 由其抛 ValueError → HTTPException(400)
            try:
                return derive_response(query, diag=diag, spec=spec, result=result)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        # ⚠ env is process-wide; concurrent /diagnose calls race — v2 finally-pop 让并发下互相清 env,
        # undefined under concurrency, single-user debug tool.
        # v4(2026-07-17 class-gate)契约扩展:第四 env DEBUG_EVENT_CLASS 同 finally 无条件 pop。
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
            os.environ.pop("DEBUG_ANCHOR_KIND", None)   # ★ v3 · 无条件 pop 兜底
            os.environ.pop("DEBUG_EVENT_CLASS", None)   # ★ v4 · 无条件 pop 兜底(跨 request 隔离)

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
            end_node = meta["end_node"]
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
                res, end_node=end_node, label_horizon=label_horizon,
                win=win, start_ts=start_ts, end_ts=end_ts)
            pattern_spec = serialize_pattern(mod.build_pattern(mod.load_params()))
            scan_meta = {
                "start_date": start, "end_date": end,
                "win_start": buf_start, "win_end": buf_end,
                "label_horizon": label_horizon, "end_node": end_node,
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
        end_nodes: dict = {}
        head_bufs: list = []
        for pid in req.pattern_ids:
            mod = registry.get(pid)
            spec_json = serialize_pattern(mod.build_pattern(mod.load_params()))
            specs[pid] = spec_json
            module_paths[pid] = registry.module_path(pid)
            meta = require_eval_meta(mod)
            end_nodes[pid] = meta["end_node"]
            head_bufs.append(meta["head_buffer_trading_days"])
        head_buffer = max(head_bufs)
        loop = asyncio.get_running_loop()

        def job(on_progress, cancel_event, save_event):
            return scan_mod.run_scan_multi(
                data_dir=cfg["dataset_dir"],
                pattern_specs_json=specs,
                module_paths=module_paths,
                pattern_ids=req.pattern_ids,
                end_nodes=end_nodes,
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
