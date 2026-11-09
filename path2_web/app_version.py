"""app 版本指纹 app_ver:一条反馈记下来时 app 是哪一版(spec 6.13「记录」的 app_ver 条)。

只记出处:反馈的答案不因 app 改版而过期,界面上也不因它显示任何「过期」「旧版」提示。

取法:app 包目录(`path2_apps/<app>/`,即 dag_spec 模块所在目录)下全部 `.py`(递归,排除 `__pycache__`),
加 app 的默认参数文件(模块的 DEFAULT_YAML_PATH);按相对 app 包目录的路径排序,把路径和内容一起喂 sha256,
取前 16 位十六进制。不含 `mapping.yaml`(会话写的对照与记账,记账不算改版)和另存的参数文件。
框架(`path2/`)与 `path2_apps/` 顶层的共用代码不在内:指纹只认这个 app 自己的声明。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

APP_VER_LEN = 16   # 取 sha256 十六进制的前几位


def default_params_path(mod) -> Path | None:
    """app 的默认参数文件:dag_spec 模块(或它的 params 子模块)上的 DEFAULT_YAML_PATH;都没有为 None。
    与单股预览参数文件层取参数目录的写法一致(path2_web/api.py 的 _params_dir)。"""
    p = getattr(mod, "DEFAULT_YAML_PATH", None) \
        or getattr(getattr(mod, "params", None), "DEFAULT_YAML_PATH", None)
    return Path(p) if p is not None else None


def app_ver(mod) -> str:
    """app 的版本指纹(16 位十六进制)。mod 是 `path2_apps.<app>.dag_spec` 模块(registry 注册的那个)。

    喂进哈希的文件:包目录下递归的全部 `.py`(路径里有 `__pycache__` 的不算)+ 默认参数文件(存在时)。
    每个文件按「相对包目录的路径(posix 写法)、内容长度、内容」依次喂入,路径按字符串排序;
    默认参数文件若不在包目录里,路径照样相对包目录写(可能带 `..`)。改任何一个 `.py`、改默认参数文件、
    增删 `.py` 都会变;改 `mapping.yaml`、另存的参数文件、`__pycache__` 不变。
    """
    root = Path(mod.__file__).resolve().parent
    files = {p for p in root.rglob("*.py") if "__pycache__" not in p.relative_to(root).parts and p.is_file()}
    yaml_path = default_params_path(mod)
    if yaml_path is not None and yaml_path.is_file():
        files.add(yaml_path.resolve())
    entries = sorted((Path(os.path.relpath(p, root)).as_posix(), p) for p in files)
    h = hashlib.sha256()
    for rel, p in entries:
        data = p.read_bytes()
        name = rel.encode("utf-8")
        h.update(len(name).to_bytes(8, "big"))
        h.update(name)
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()[:APP_VER_LEN]
