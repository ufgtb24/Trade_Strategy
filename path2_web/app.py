"""create_app:组装 FastAPI 实例(registry + config + router + CORS)。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from path2_web.api import build_router
from path2_web.config import load_config, save_config, DEFAULT_PATH
from path2_web.discovery import PatternRegistry

_DEFAULT_OUTPUTS_ROOT = str(Path(__file__).resolve().parents[1] / "outputs" / "path2_web")  # 锚 repo root


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
    state = {"config": config_override if config_override is not None else load_config(config_path)}

    def get_config():
        return state["config"]

    def set_config(cfg):
        state["config"] = cfg
        if config_override is None:          # 仅在非测试覆盖时落盘
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
