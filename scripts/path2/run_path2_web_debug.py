"""一条命令启动看图工作流的调试模式:看图工作流和调试视图都在调试段 2021-10-01..2022-09-30 上运行。

    uv run python scripts/path2/run_path2_web_debug.py

- 调试段只用来调试看图工作流:看图、建卡、跑对照页都行,不进正式账、不算尝试(见 chart_workflow/mode.py)。
- 记账写调试账:主目录的 outputs/chart_workflow_debug/,不进 git;不存在就先新建(写标记、登记训练数据副本,
  和正式账用同一份副本)。清空重来:uv run python -m chart_workflow.debugroot clear
- 读任何行情都截在 2022-09-30;界面顶上挂着「调试模式：2021-10～2022-09，不进正式账」。前端也知道自己是按
  调试模式启动的:后端没连上时页顶挂「模式未知」并定时重试,后端报的模式和它不一样就报警。
- 端口取 configs/path2_web.yaml 的 debug_mode_backend_port / debug_mode_frontend_port,和正式模式的
  run_path2_web.py 分开,两个网页可以同时开着;启动前清场只清这两个端口上的残留实例。
- 会话在调试时跑命令行工具(大涨段、事实表、形态卡、对照页),每条命令前带上 CHART_WORKFLOW_MODE=debug;
  调试模式的清单名以 dbg- 开头,决定文件写 "mode": "debug"。

参数在 main() 顶部声明(无 argparse,遵循入口规范)。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # 同目录的 run_path2_web


def main() -> None:
    # ===== 参数(在此处直接改) =====
    from path2_web.config import load_config
    cfg = load_config()
    BACKEND_PORT = int(cfg["debug_mode_backend_port"])    # 改端口请改 configs/path2_web.yaml
    FRONTEND_PORT = int(cfg["debug_mode_frontend_port"])
    # ================================
    from chart_workflow import debugroot, mode, state
    from run_path2_web import serve

    os.environ[mode.ENV_VAR] = mode.DEBUG          # 本进程(新建调试账)与前后端子进程都按调试模式
    try:
        root = debugroot.ensure()
    except (debugroot.DebugRootRefused, state.StateRootMissing) as e:
        raise SystemExit(f"[run_path2_web_debug] 调试账用不了:{e}") from None
    print(f"[run_path2_web_debug] {mode.DEBUG_LABEL}")
    print(f"[run_path2_web_debug] 调试账:{root}(清空重来:uv run python -m chart_workflow.debugroot clear)")
    print(f"[run_path2_web_debug] 打开 http://localhost:{FRONTEND_PORT}/")
    serve(BACKEND_PORT, FRONTEND_PORT, backend_env={mode.ENV_VAR: mode.DEBUG},
          frontend_env={"VITE_CHART_WORKFLOW_MODE": mode.DEBUG}, tag="run_path2_web_debug")


if __name__ == "__main__":
    main()
