"""HTTP 路由 + SSE 扫描编排。create_app 注入 registry/config/outputs_root。"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
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


class ParamsSaveRequest(BaseModel):
    pattern_id: str
    name: str          # app 目录下文件名,白名单 ^[A-Za-z0-9_\-]+\.yaml$
    params: dict


class WcMirrorRequest(BaseModel):
    """WC 镜像落盘请求(探索态诊断用):前端修改 WC 时把当前 WC 落盘 wc.json,供终端读。"""
    pid: str
    scan_ts: str
    win_start: str
    win_end: str
    start_date: str
    end_date: str
    wc: dict          # WC.currentDict(完整 Params dict,容忍探索改坏,不走 strict 校验)
    enabled: bool     # WC.enabled(终端据此判断探索态:enabled=false 忽略 wc.json)


class WcClearRequest(BaseModel):
    """WC 镜像清理请求:discardWorkingCopy 触发,删 wc.json。"""
    pid: str


_PARAM_FILE_RE = re.compile(r"^[A-Za-z0-9_\-]+\.yaml$")

# \w 含中文; 允许小数点(调参脚本产物如 tune-bo-exceed_threshold-0.01-buf250),
# 但禁首点 → 排除 . / .. / 隐藏文件; \w 天然排除 / \ 空格(防穿越)
_SCAN_NAME_RE = re.compile(r"^(?!\.)[\w\-.]+$", re.UNICODE)


def _validate_scan_name(name: str) -> None:
    """扫描结果文件名 stem 白名单校验。非法 → 400。默认时间戳名也满足。"""
    if not name or not _SCAN_NAME_RE.fullmatch(name):
        raise HTTPException(400, f"非法扫描名称: {name!r}(仅允许字母/数字/下划线/连字符/中文)")


class ScanRequest(BaseModel):
    pattern_ids: list[str] = Field(..., min_length=1)
    start_date: str
    end_date: str
    workers: int = 8
    ticker_regex: str | None = None
    label_horizon: int = 20
    # 按值通道:pid → 完整参数 dict。语义 = 前端会话态 Working Copy(磁盘上无对应物,只能整份传)
    params_overrides: dict[str, dict] | None = None
    # 按引用通道:pid → app 目录下的 yaml 文件名(白名单 ^[A-Za-z0-9_\-]+\.yaml$)。
    # 语义 = 磁盘具名文件,后端自读自校验;文件身份落盘进 params_provenance
    params_files: dict[str, str] | None = None
    price_min: float | None = None      # match 级:end_node 事件日收盘价下限(闭区间)
    price_max: float | None = None      # match 级:end_node 事件日收盘价上限(闭区间)
    volume_min: float | None = None     # 股票级预筛:扫描区间内日均成交量必须严格大于此值
    note: str | None = None                             # scan 备注(命名实验)
    # 首次穿越方向(分类量):per-match 注入 + ticker-scoped 随机日基线 + 集合级 stats
    first_passage_enabled: bool = True                  # 开关(False=不算首穿、向后兼容)
    first_passage_k: float = 5.0                        # 几何对称阈值倍数(上行 P(1+kM)、下行 P/(1+kM))

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


class RenameRequest(BaseModel):
    name: str


def require_eval_meta(mod, params=None) -> dict:
    """读 app 模块 eval_meta() 协议。params 显式传入时用之(override 场景 head_buffer
    必须按 override 参数算,否则缓冲不足导致漏检伪装成"参数没起效");否则回退 load_params()
    (现状行为)。铁律下 discovery 已闸过滤,api 调到此处不可能 None。
    若仍 None / 字段不全 → ValueError(防御性,非业务路径)。
    """
    fn = getattr(mod, "eval_meta", None)
    if not callable(fn):
        raise ValueError("eval_meta missing or non-callable (discovery gate failed)")
    if params is None:
        load_params = getattr(mod, "load_params", None)
        params = load_params() if callable(load_params) else None
    meta = fn(params) if params is not None else fn()
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

    @router.get("/scans/{name}")
    def scan_load_flat(name: str):
        _validate_scan_name(name)
        try:
            data = scan_mod.load_scan_flat(name, outputs_root)
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
                pattern_spec["debug_enabled_nodes"] = fresh["debug_enabled_nodes"]  # v4 backfill:老 scan 文件补齐 non-optional 字段
        return data

    @router.delete("/scans/{name}")
    def scan_delete_flat(name: str):
        _validate_scan_name(name)
        try:
            scan_mod.delete_scan_flat(name, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")
        return {"ok": True}

    @router.post("/scans/{name}/rename")
    def scan_rename(name: str, req: RenameRequest):
        new_name = req.name.strip()
        _validate_scan_name(name)
        _validate_scan_name(new_name)
        if new_name == name:
            return {"name": new_name}
        try:
            scan_mod.rename_scan_flat(name, new_name, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")
        except FileExistsError:
            raise HTTPException(409, f"名称已存在: {new_name}")
        return {"name": new_name}

    @router.get("/diagnose")
    def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                     scope: Optional[str] = None,
                     src_node: Optional[str] = None, dst_node: Optional[str] = None,
                     node: Optional[str] = None, event_id: Optional[str] = None,
                     src_event_id: Optional[str] = None, dst_event_id: Optional[str] = None,
                     edge_id: Optional[str] = None,
                     start_bar: Optional[int] = None, end_bar: Optional[int] = None,
                     anchor_kind: Optional[str] = None,
                     params_override: Optional[str] = None):
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
        try:
            mod = registry.get(pattern_id)
            if mod is None:
                raise HTTPException(404, f"unknown pattern: {pattern_id}")
            cfg = get_config()
            pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
            if not pkl.exists():
                raise HTTPException(404, f"pkl not found: {symbol}")
            win = slice_window(pd.read_pickle(pkl), start, end)
            if params_override:
                # A5:params_override 存在时用它闭合 spec(Working Copy 直诊断,不落 yaml)。
                try:
                    _p = mod.Params.from_dict(json.loads(params_override), strict=False)
                except (ValueError, json.JSONDecodeError) as e:
                    raise HTTPException(400, f"params_override 非法: {e}") from e
                spec = mod.build_pattern(_p)
            else:
                # 现状路径:诊断每次都重新 build_pattern(load_params())——与 /scan 同口径(yaml SSoT 热加载)。
                # 不能复用 mod.PATTERN_DAG(它是 import 时一次性 build,Params.default() 闭合,与 yaml 漂移)。
                spec = mod.build_pattern(mod.load_params())
            if scope is None:
                # legacy 路径:无 scope 参数 → 字节等价,前端旧 api.ts::getDiagnose 不用改。
                return diagnose_symbol(spec, win, None, symbol=symbol, pattern_id=pattern_id)
            # A' 按 scope 分派(见 docs/research/2026-07-18_debug-double-pause-analysis/final_report.md §3.1):
            # scope=nodes 只需 diag · scope=time/pair 只需 result(+ gate_failures) · 三 scope 数据依赖完全正交
            # (derive_response 三 branch 逐字核实无 hidden cross-dep)· 只跑该 scope 需要的那 pass 消双 pause。
            query = Query(symbol=symbol, scope=scope, src_node=src_node, dst_node=dst_node,
                         node=node, event_id=event_id,
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
        finally:
            os.environ.pop("DEBUG_BAR_RANGE", None)
            os.environ.pop("DEBUG_ANCHOR_KIND", None)   # ★ v3 · 无条件 pop 兜底

    @router.get("/preview")
    def get_preview(pattern_id: str, symbol: str, start: str, end: str,
                    label_horizon: int = 20, params_override: Optional[str] = None):
        """单股临时计算 — 复刻 multi-scan worker 的 buffered+label 链路,不落盘,单 pattern。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        cfg = get_config()
        pkl = Path(cfg["dataset_dir"]) / f"{symbol}.pkl"
        if not pkl.exists():
            raise HTTPException(404, f"pkl not found: {symbol}")

        try:
            if params_override:
                # A5:params_override 存在时闭合 analyze/eval_meta 同一份 params
                # (head_buffer 必须按 override 算,否则缓冲不足导致漏检伪装成"参数没起效")。
                try:
                    p = mod.Params.from_dict(json.loads(params_override), strict=False)
                except (ValueError, json.JSONDecodeError) as e:
                    raise HTTPException(400, f"params_override 非法: {e}") from e
            else:
                _load = getattr(mod, "load_params", None)
                p = _load() if callable(_load) else None
            meta = require_eval_meta(mod, params=p)
            end_node = meta["end_node"]
            head_buf = meta["head_buffer_trading_days"]
            start_ts, end_ts = pd.to_datetime(start), pd.to_datetime(end)
            buf_start = str((start_ts - pd.Timedelta(days=round(head_buf * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())
            buf_end   = str((end_ts   + pd.Timedelta(days=round(label_horizon * scan_mod.TRADING_TO_CALENDAR_RATIO))).date())

            # 复刻 worker 单 pattern 调用(含样本消费窗截取,口径与 scan worker 一致)
            df = pd.read_pickle(pkl)
            win = slice_window(df, buf_start, buf_end)
            res = mod.analyze(win, p)
            from path2_web.serialize import serialize_per_pattern_result
            lo = int(win["date"].searchsorted(start_ts, "left"))
            hi = int(win["date"].searchsorted(end_ts, "right")) - 1
            out = serialize_per_pattern_result(
                res, end_node=end_node, label_horizon=label_horizon,
                win=win, start_ts=start_ts, end_ts=end_ts,
                sample_window=(lo, hi))
            pattern_spec = serialize_pattern(mod.build_pattern(p if p is not None else mod.load_params()))
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

    # ── 参数文件层:app 目录多 yaml(dev 式 File 层) ─────────────────────────
    def _params_dir(mod) -> Path:
        """pattern 的参数目录 = DEFAULT_YAML_PATH 所在目录(即 path2_apps/<app>/)。"""
        yaml_path = getattr(mod, "DEFAULT_YAML_PATH", None) \
            or getattr(getattr(mod, "params", None), "DEFAULT_YAML_PATH", None)
        if yaml_path is None:
            raise HTTPException(500, "pattern 无 DEFAULT_YAML_PATH")
        return Path(yaml_path).parent

    def _checked_param_path(mod, name: str) -> Path:
        """文件名白名单校验(防路径穿越)后拼绝对路径。fullmatch(非 match):Python
        正则 `$` 会放过「结尾换行前」,match() 会让 "a.yaml\n" 这类名字漏网——写路径
        (Task 2)会因此在磁盘建出带换行的文件,且与前端 Save As 校验(JS `$` 无 m
        flag、不放过尾换行)语义分叉,违反三处共用白名单的约定。"""
        if not _PARAM_FILE_RE.fullmatch(name):
            raise HTTPException(400, f"非法参数文件名: {name}")
        return _params_dir(mod) / name

    @router.get("/params/files")
    def get_params_files(pattern_id: str):
        """列 app 目录下 *.yaml 文件名。params.yaml 恒第一,其余字典序。用与
        /params/file 相同的白名单正则过滤:glob 比白名单宽,不过滤会列出
        /params/file 打不开(400)的文件(如含空格/非 ASCII 字符的文件名)。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        names = sorted(p.name for p in _params_dir(mod).glob("*.yaml")
                       if _PARAM_FILE_RE.fullmatch(p.name))
        if "params.yaml" in names:
            names.remove("params.yaml")
            names.insert(0, "params.yaml")
        return {"files": names}

    @router.get("/params/file")
    def get_params_file(pattern_id: str, name: str):
        """读单个参数文件为原始 dict(safe_load,不经 Params 校验——编辑区允许装载
        任意 yaml,严格校验发生在 Apply(前端)与 /params/save、/scan(后端)。手写坏
        的 yaml 语法是这个端点的预期输入,解析失败包成 400(而非裸 500)。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        p = _checked_param_path(mod, name)
        if not p.exists():
            raise HTTPException(404, f"参数文件不存在: {name}")
        import yaml as _yaml
        try:
            data = _yaml.safe_load(p.read_text())
        except _yaml.YAMLError as e:
            raise HTTPException(400, f"{name} 解析失败: {e}") from e
        if not isinstance(data, dict):
            raise HTTPException(400, f"{name} 根必须是映射")
        return {"params": data}

    @router.get("/params_diff")
    def get_params_diff(pattern_id: str, scan_ts: str):
        """snapshot(scan file 内嵌 per_pattern[pid].params_snapshot)vs 该次扫描实际
        所用参数文件当前内容的字段级 diff(锚由 params_provenance 决定:"file:X" → X,
        否则 params.yaml)。前端 hash mismatch dot 数据源。老 scan(无 snapshot)→
        has_snapshot=False,不 crash。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        try:
            data = scan_mod.load_scan_flat(scan_ts, outputs_root)
        except FileNotFoundError:
            raise HTTPException(404, "scan not found")
        entry = (data.get("per_pattern") or {}).get(pattern_id, {})
        snap = entry.get("params_snapshot")
        # provenance 是这次扫描用了哪份参数的唯一记录;"yaml" ≡ "file:params.yaml"(白名单
        # 不含冒号,前缀可靠反解)。缺字段的老 scan 一律回 params.yaml。
        prov = entry.get("params_provenance")
        anchor_file = (prov[len("file:"):]
                       if isinstance(prov, str) and prov.startswith("file:")
                       else "params.yaml")
        if snap is None:
            return {"has_snapshot": False, "match": False, "diffs": [],
                    "anchor_file": anchor_file}
        if anchor_file == "params.yaml":
            _load = getattr(mod, "load_params", None)
            current = _load().to_dict() if callable(_load) else {}
        else:
            import yaml as _yaml
            path = _checked_param_path(mod, anchor_file)
            if not path.exists():
                # 锚缺失是 diff 合法状态(snapshot 在、锚没了),复用 has_snapshot:false 的 200 先例,
                # 诚实标记 anchor_missing 让前端显灰"?"dot,而非抛 400 被静默吞或退化到 params.yaml。
                return {"has_snapshot": True, "anchor_missing": True, "match": False,
                        "diffs": [], "anchor_file": anchor_file}
            try:
                current = mod.Params.from_yaml(path).to_dict() if hasattr(mod, "Params") else {}
            except (ValueError, _yaml.YAMLError) as e:
                raise HTTPException(400, f"锚参数文件 {anchor_file} 读取失败: {e}") from e
        diffs = []
        for section in sorted(set(snap) | set(current)):
            s_sect, c_sect = snap.get(section) or {}, current.get(section) or {}
            for key in sorted(set(s_sect) | set(c_sect)):
                sv, cv = s_sect.get(key), c_sect.get(key)
                if sv != cv:
                    diffs.append({"path": f"{section}.{key}", "snapshot": sv, "current": cv})
        return {"has_snapshot": True, "match": not diffs, "diffs": diffs,
                "anchor_file": anchor_file}

    @router.post("/params/save")
    def post_params_save(req: ParamsSaveRequest):
        """参数存盘(dev 式 Save/Save As 共用):strict 校验后写 app 目录下 <name>。
        目标已存在 → ruamel round-trip 只改值保注释(safe_dump 整文件覆盖会杀光
        注释——params.yaml 的注释是字段语义 SSoT,禁用);新文件 → safe_dump。
        name=params.yaml 即原「晋升基线」语义(该端点吸收已删除的 /params/apply)。"""
        mod = registry.get(req.pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {req.pattern_id}")
        try:
            validated = mod.Params.from_dict(req.params, strict=True)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        p = _checked_param_path(mod, req.name)
        existing_text = p.read_text() if p.exists() else ""   # 只在 exists() 为真时读,避免"文件不存在"分支读坏
        if existing_text.strip():
            from ruamel.yaml import YAML
            from ruamel.yaml.comments import CommentedMap
            from ruamel.yaml.error import YAMLError
            ry = YAML()   # round-trip 模式(默认):保注释/保键序
            ry.preserve_quotes = True
            try:
                doc = ry.load(existing_text)
            except YAMLError as e:
                # 与 GET /params/file 的坏 yaml→400 惯例对称。Save As 之后用户可能手改坏
                # 实验文件再点 Save,是可预期输入;此处无数据丢失风险(load 发生在
                # open(p,"w") 截断之前)。
                raise HTTPException(400, f"{req.name} 解析失败: {e}") from e
            if not isinstance(doc, dict):
                # F-D:与 GET /params/file 的根非映射守卫对称。doc 可能是 CommentedSeq(顶层是
                # list)、标量或 None(ry.load("null")/全 null 文档)——不挡的话下面 `doc[section] = ...`
                # 对 list/None/标量取下标会抛 TypeError,逃出 handler 变成裸 500。
                raise HTTPException(400, f"{req.name} 根必须是映射")
            for section, fields in validated.to_dict().items():
                if not isinstance(fields, dict) or not fields:
                    continue                      # edges 空 section 不写入
                if section not in doc or doc[section] is None:
                    doc[section] = CommentedMap()
                for k, v in fields.items():
                    doc[section][k] = v
            with open(p, "w") as f:
                ry.dump(doc, f)
        else:
            import yaml as _yaml
            out = {s: f for s, f in validated.to_dict().items()
                   if isinstance(f, dict) and f}   # 空 section(edges)同样不写
            with open(p, "w") as f:
                _yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False)
        return {"ok": True, "path": str(p)}

    @router.delete("/params/file")
    def param_file_delete(pattern_id: str, name: str):
        """删 app 目录下的具名参数文件。与 GET /params/file 同 query(对称)。
        params.yaml 是 CLI/新扫描缺省源,显式硬拒(白名单放行它,不能靠白名单挡)。
        硬 unlink;不存在 → 404(幂等,与 delete_scan_flat 一致);异常对齐 scan 删除
        (只 catch FileNotFoundError→404,其余走 FastAPI 默认 500,不为权限错加分支)。"""
        mod = registry.get(pattern_id)
        if mod is None:
            raise HTTPException(404, f"unknown pattern: {pattern_id}")
        if name == "params.yaml":
            raise HTTPException(400, "params.yaml 不可删除(基线)")
        p = _checked_param_path(mod, name)
        try:
            p.unlink()
        except FileNotFoundError:
            raise HTTPException(404, f"参数文件不存在: {name}")
        return {"ok": True}

    @router.post("/params/wc-mirror")
    def post_wc_mirror(req: WcMirrorRequest):
        """WC 镜像落盘:前端"修改 WC"操作(fork/ensure/update/setEnabled/restore)触发,
        把当前 WC(currentDict+enabled)写到 outputs/path2_web/wc.json(单一覆盖,不入 git)。
        localStorage 行为不变,本端点只是额外镜像,供终端诊断探索态读 WC。
        不走 strict 校验(WC 是任意探索 dict,容忍改坏);scan_ts 校验格式防脏数据。"""
        if not re.match(_TS_PATTERN, req.scan_ts):
            raise HTTPException(400, f"scan_ts 格式非法: {req.scan_ts}")
        out_dir = Path(outputs_root)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "wc.json"
        payload = {"pid": req.pid, "scan_ts": req.scan_ts,
                   "win_start": req.win_start, "win_end": req.win_end,
                   "start_date": req.start_date, "end_date": req.end_date,
                   "wc": req.wc, "enabled": req.enabled,
                   "written_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        p.write_text(json.dumps(payload, ensure_ascii=False))
        return {"ok": True, "path": str(p)}

    @router.post("/params/wc-clear")
    def post_wc_clear(req: WcClearRequest):
        """WC 镜像清理:discardWorkingCopy 触发,删 wc.json(不存在不报错)。"""
        p = Path(outputs_root) / "wc.json"
        if p.exists():
            p.unlink()
        return {"ok": True}

    @router.post("/scan")
    async def post_scan(req: ScanRequest):           # async:在 event loop 线程跑,get_running_loop 可用
        # 校验所有 pattern_id 在 registry
        for pid in req.pattern_ids:
            if registry.get(pid) is None:
                raise HTTPException(404, f"unknown pattern: {pid}")
        cfg = get_config()
        scan_ts = time.strftime("%Y%m%dT%H%M%S")
        import yaml as _yaml

        specs: dict = {}
        module_paths: dict = {}
        end_nodes: dict = {}
        head_bufs: list = []
        pattern_params_dicts: dict = {}
        provenance: dict = {}
        for pid in req.pattern_ids:
            mod = registry.get(pid)
            ov = (req.params_overrides or {}).get(pid)
            fname = (req.params_files or {}).get(pid)
            if ov is not None and fname is not None:
                # 显式拒绝 > 悄悄挑一个:两个字段是两种来源,不是叠加
                raise HTTPException(
                    400, f"{pid}: params_files 与 params_overrides 互斥,只能指定一个参数源")
            if ov is not None and hasattr(mod, "Params"):
                try:
                    p = mod.Params.from_dict(ov, strict=True)   # 扫描入口严格校验
                except ValueError as e:
                    raise HTTPException(400, f"params_overrides[{pid}]: {e}") from e
                provenance[pid] = "working_copy"
            elif fname is not None and fname != "params.yaml" and hasattr(mod, "Params"):
                # 归一化在后端:fname == "params.yaml" 落到 else 分支,与「不传」逐字等价
                try:
                    path = _checked_param_path(mod, fname)      # 白名单校验,防路径穿越
                except HTTPException as e:
                    raise HTTPException(400, f"params_files[{pid}]: {e.detail}") from e
                if not path.exists():
                    raise HTTPException(400, f"params_files[{pid}]: 参数文件不存在: {fname}")
                try:
                    p = mod.Params.from_yaml(path)              # 与 load_params 同一校验路径
                except (ValueError, _yaml.YAMLError) as e:
                    raise HTTPException(400, f"params_files[{pid}]={fname}: {e}") from e
                provenance[pid] = f"file:{fname}"
            else:
                _load = getattr(mod, "load_params", None)
                p = _load() if callable(_load) else None
                provenance[pid] = "yaml"
            spec_json = serialize_pattern(mod.build_pattern(p) if p is not None
                                          else mod.build_pattern(mod.load_params()))
            specs[pid] = spec_json
            module_paths[pid] = registry.module_path(pid)
            meta = require_eval_meta(mod, params=p)
            end_nodes[pid] = meta["end_node"]
            head_bufs.append(meta["head_buffer_trading_days"])
            pattern_params_dicts[pid] = p.to_dict() if (p is not None and hasattr(p, "to_dict")) else None
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
                pattern_params_dicts=pattern_params_dicts, params_provenance=provenance, note=req.note,
                name=name,
                price_min=req.price_min, price_max=req.price_max,
                volume_min=req.volume_min,
                first_passage_enabled=req.first_passage_enabled,
                first_passage_k=req.first_passage_k,
            )

        def done_meta(result):
            s = result["scan"]
            return {"pattern_ids": req.pattern_ids, "scan_ts": scan_ts,
                    "name": name,
                    "hits": s["hits"], "errors": s["errors"], "total": s["scanned"],
                    "partial": bool(s.get("partial", False))}

        name = (req.note or "").strip() or scan_ts
        _validate_scan_name(name)
        if (Path(outputs_root) / "scans" / f"{name}.json").exists():
            raise HTTPException(409, f"扫描名称已存在: {name}，请改名后重试")
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
