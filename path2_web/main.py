"""入口(无 argparse;参数在 main() 顶部声明,CLAUDE.md 入口规范)。

    uv run python -m path2_web.main
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))     # 子进程 import path2_apps/path2_web


_OUTPUTS_ROOT = str(REPO / "outputs" / "path2_web")     # 锚到 repo root,避免受启动 CWD 影响


def make_app():
    """uvicorn 工厂入口。reload=True 要求传 import string(以便 spawn 子进程重新
    import),import string 走零参 factory,故 outputs_root 只能落在这里而非 main()。"""
    from path2_web.app import create_app
    return create_app(outputs_root=_OUTPUTS_ROOT)


def main() -> None:
    from path2_web.config import load_config
    cfg = load_config()
    # ===== 参数(在此处直接改) =====
    HOST = "127.0.0.1"
    # DEBUG_MODE=1: 调试模式(PyCharm Debug main.py 时用),后端起在 backend_port_dbg、
    # reload=False(reload=True 会 fork worker、pydevd trace 断在主进程,断点不命中)。
    # 另:重启后首次 debug fire 断点不命中(第二次起正常)为环境性现象(IDE/pydevd
    # 窗口组合,代码侧已实证无根因)——详见 path2/debug_ctx.py debug_break docstring ⚠ 节。
    # 未设: 日常模式,后端 backend_port + reload=True(改代码自动重启)。
    # 与 run_path2_web.py 起的主实例并存时:只在 PyCharm Debug config 里设 DEBUG_MODE=1,
    # 主实例走默认分支,两端口 8001/8002 互不冲突。
    DEBUG_MODE = os.environ.get("DEBUG_MODE") == "1"
    PORT = int(cfg["backend_port_dbg"] if DEBUG_MODE else cfg["backend_port"])
    RELOAD = not DEBUG_MODE
    # ================================
    uvicorn.run("path2_web.main:make_app", factory=True,
                host=HOST, port=PORT, reload=RELOAD)


if __name__ == "__main__":
    main()
