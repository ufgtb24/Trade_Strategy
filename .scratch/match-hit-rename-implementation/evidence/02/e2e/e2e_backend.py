"""票 02 跑验收与 e2e 用的主视图后端：被测 checkout 的代码 + 它自己的配置，标注目录换成临时目录（不碰用户的 annotations/）。
用法：python e2e_backend.py <被测 checkout 根目录> <端口> <临时标注目录>"""
import sys
from pathlib import Path

root, port, adir = Path(sys.argv[1]).resolve(), int(sys.argv[2]), Path(sys.argv[3]).resolve()
sys.path.insert(0, str(root))
import uvicorn  # noqa: E402
import path2_web  # noqa: E402
assert Path(path2_web.__file__).resolve().is_relative_to(root), path2_web.__file__
from path2_web.app import create_app  # noqa: E402
from path2_web.config import load_config  # noqa: E402

cfg = {**load_config(root / "configs/path2_web.yaml"), "annotation_dir": str(adir), "machine": "e2e"}
print("path2_web 来自", path2_web.__file__, "端口", port, "标注目录", adir, flush=True)
app = create_app(config_override=cfg, config_path=root / "configs/path2_web.yaml",
                 outputs_root=str(root / "outputs" / "path2_web"))
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
