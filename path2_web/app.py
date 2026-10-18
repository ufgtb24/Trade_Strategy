"""create_app:组装 FastAPI 实例(registry + config + router + CORS)。

启动时核对看图下界:后端自己的看图下界(workflow.view_floor,调试视图与看图工作流共用)不得早于
chart_workflow 配置的看图下界,否则拒绝启动(RuntimeError)——受 git 跟踪的 web 配置不能把能看的范围改早。

调试模式(chart_workflow.mode,进程带环境变量 CHART_WORKFLOW_MODE=debug):扫描结果放在 outputs/path2_web
旁边的 outputs/path2_web_debug(传入默认的 outputs/path2_web 时自动换过去);配置只在内存里改——扫描区间的默认值
放进调试段,前端保存配置也不写回 configs/path2_web.yaml(那份是正式模式用的,调试段的日期写进去会改掉正式模式
的默认扫描区间)。"""
from __future__ import annotations

import copy
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from chart_workflow import mode as cw_mode
from path2_web.api import build_router
from path2_web.config import load_config, save_config, DEFAULT_PATH
from path2_web.discovery import PatternRegistry
from path2_web.workflow import _view_floor

_DEFAULT_OUTPUTS_ROOT = str(Path(__file__).resolve().parents[1] / "outputs" / "path2_web")  # 锚 repo root


def debug_config(cfg: dict) -> dict:
    """调试模式下网页配置在内存里的样子:扫描区间的默认起止落在调试段外就换成调试段起止(副本,不改 cfg)。"""
    out = copy.deepcopy(cfg)
    scan = out.setdefault("scan", {})
    lo, hi = cw_mode.DEBUG_START, cw_mode.DEBUG_END
    if not lo <= str(scan.get("start_date") or "") <= hi:
        scan["start_date"] = lo
    if not lo <= str(scan.get("end_date") or "") <= hi:
        scan["end_date"] = hi
    return out


def _cw_view_floor() -> str | None:
    """chart_workflow 配置的看图下界(测试里替换它)。"""
    from chart_workflow.config import load_config as cw_load_config

    return cw_load_config().get("view_floor")


def check_view_floor(cfg: dict) -> None:
    """后端的看图下界早于 chart_workflow 配置的 → RuntimeError(拒绝启动)。"""
    mine, theirs = _view_floor(cfg), _cw_view_floor()
    if theirs and mine < str(theirs):
        raise RuntimeError(f"后端的看图下界 {mine} 早于看图工作流配置的 {theirs}(chart_workflow),拒绝启动;"
                           f"改回不早于 {theirs} 再启动")


class _NoKeepAliveMiddleware(BaseHTTPMiddleware):
    """所有响应加 Connection: close,禁止 chrome keep-alive 复用 socket。

    实测:chrome 同 origin 累积 stale CLOSE-WAIT socket 会占满 6-socket pool,
    后续 fetch/XHR 排队等 stale 释放(可卡 100+s)。让 server 主动声明 close
    可让 chrome 每请求一新 connection,socket 用完就 RST,不进 keep-alive pool。
    单 dev/本地小规模可承受;高 QPS 生产需另做 chrome 客户端兼容。
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Connection"] = "close"
        return response


def create_app(*, config_override=None, config_path=DEFAULT_PATH,
               outputs_root=_DEFAULT_OUTPUTS_ROOT, use_thread_pool=False) -> FastAPI:
    registry = PatternRegistry()
    debug = cw_mode.is_debug()
    state = {"config": config_override if config_override is not None else load_config(config_path)}
    if debug:
        state["config"] = debug_config(state["config"])
        if Path(outputs_root).resolve() == Path(_DEFAULT_OUTPUTS_ROOT).resolve():
            outputs_root = str(cw_mode.debug_variant(_DEFAULT_OUTPUTS_ROOT))
    check_view_floor(state["config"])

    def get_config():
        return state["config"]

    def set_config(cfg):
        state["config"] = cfg
        if config_override is None and not debug:   # 仅在非测试覆盖、正式模式时落盘
            save_config(cfg, config_path)

    app = FastAPI(title="path2_web", version="0.1.0")
    app.add_middleware(_NoKeepAliveMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(build_router(
        registry=registry, config_path=config_path,
        get_config=get_config, set_config=set_config,
        outputs_root=outputs_root, use_thread_pool=use_thread_pool,
    ))
    return app
