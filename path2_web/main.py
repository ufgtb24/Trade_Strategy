"""入口(无 argparse;参数在 main() 顶部声明,CLAUDE.md 入口规范)。

    uv run python -m path2_web.main
"""
from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))     # 子进程 import path2_apps/path2_web


def main() -> None:
    from path2_web.config import load_config
    cfg = load_config()
    # ===== 参数(在此处直接改) =====
    HOST = "127.0.0.1"
    PORT = int(cfg["backend_port"])   # 改端口请改 configs/path2_web.yaml 的 backend_port
    RELOAD = False
    OUTPUTS_ROOT = "outputs/path2_web"
    # ================================
    from path2_web.app import create_app
    app = create_app(outputs_root=OUTPUTS_ROOT)
    uvicorn.run(app, host=HOST, port=PORT, reload=RELOAD)


if __name__ == "__main__":
    main()
