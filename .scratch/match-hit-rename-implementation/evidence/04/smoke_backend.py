"""票 04 冒烟用的后端：照 configs/path2_web.yaml（读训练段副本），标注目录换成临时目录、机器名固定，
扫描落到 worktree 的 outputs/path2_web/scans（diagnose-event 默认从这里找最新 scan）。只起后端，不起前端。
用法（worktree 根目录）：.venv/bin/python <本文件> <端口> <临时标注目录>
"""
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))


def main() -> None:
    import uvicorn

    from path2_web.app import create_app
    from path2_web.config import annotation_dir, load_config

    port, adir = int(sys.argv[1]), Path(sys.argv[2]).resolve()
    real = annotation_dir(load_config()).resolve()
    if not adir.is_dir() or adir == real or real in adir.parents:
        raise SystemExit(f"标注目录不合格:{adir}")
    cfg = {**load_config(), "annotation_dir": str(adir), "machine": "e2e"}
    app = create_app(config_override=cfg)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
