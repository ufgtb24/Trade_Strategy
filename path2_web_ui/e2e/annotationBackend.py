"""e2e 专用的后端:标注目录换成测试给的临时目录,机器名固定,其余配置照 configs/path2_web.yaml(读同一份训练段副本)。

标注 e2e 会写批次文件,绝不能写进用户的标注目录(annotations/,两台机器同步、只增不删):
e2e/annotate-boxes.spec.ts 起一个这样的后端,把页面发往后端的请求都转到它这里。

    python path2_web_ui/e2e/annotationBackend.py <端口> <标注目录> <机器名> [<mapping 目录>]

由测试调起、不给人手动运行,所以从命令行取参数。标注目录必须已存在、且不在仓库的 annotations/ 下。
给了 mapping 目录时,app 的 mapping 文件改从那里读(<mapping 目录>/<app>.yaml,格式见 path2_web/mapping.py),
不读 path2_apps/<app>/mapping.yaml:compare 的 e2e 用手写的 mapping,不往 path2_apps/ 里写文件。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> None:
    import uvicorn

    from path2_web.app import create_app
    from path2_web.config import annotation_dir, load_config

    port, adir, machine = int(sys.argv[1]), Path(sys.argv[2]).resolve(), sys.argv[3]
    if len(sys.argv) > 4:
        from path2_web import mapping

        mdir = Path(sys.argv[4]).resolve()
        mapping.mapping_path = lambda mod: mdir / f"{mod.__name__.split('.')[-2]}.yaml"
    real = annotation_dir(load_config()).resolve()
    if not adir.is_dir() or adir == real or real in adir.parents:
        raise SystemExit(f"标注目录不合格(必须是已存在的临时目录,不能是 {real}):{adir}")
    cfg = {**load_config(), "annotation_dir": str(adir), "machine": machine}
    app = create_app(config_override=cfg, outputs_root=str(adir.parent / "outputs"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
