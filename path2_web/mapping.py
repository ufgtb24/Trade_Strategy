"""第一段 compare 用的 mapping 文件(暂行):会话为验证 V-S1 手工写,说明一个标注里的 pattern 用哪个 app、
app 的哪个 node 认用户的哪个特征。第二段的正式 mapping(还要写每个特征的级、where 与否定边)会取代它。

为什么放在 app 目录里
--------------------
mapping 随 app 进 git,不进标注文件:标注文件只由工具写,会话不写;app 改版时 mapping 跟着改。

文件位置与格式
--------------
`path2_apps/<app>/mapping.yaml`,和这个 app 的 `dag_spec.py` 在同一个目录。有这个文件,这个 app 就是文件里
那个 pattern 的 app;一个 app 最多对一个 pattern。

    # 第一段 compare 用的 mapping(暂行)
    pattern: 放量突破          # 标注里的 pattern 名,和顶栏 pattern 下拉里的一字不差
    features:                 # 特征编号: 认它的 node(app 的 node_id)
      w-pc-3: bo
      w-pc-7: tb_seg

- 特征编号是词表里的编号(`w-<机器名>-<n>`),不是特征名:用户改特征名不影响 mapping。会话从
  `path2_web.annotation.store.read_annotations(load_config())["state"]["features"]` 查编号;
- 一个特征只对一个 node;几个特征可以对同一个 node;
- 没写进 features 的 node,在 compare 里不画(compare 只把 event 画到用户框所在的轨上)。

compare 怎么用它(前端):当前 pattern 恰好有一个没有问题的 mapping 时,`compare` / `app` 两档可用;
compare 把 node 的 event 画在它对的那个特征的轨上。

读的时候查出来的问题(problem,一句话;有问题的 mapping 不能用):
- 文件读不懂、pattern 不是非空字符串、features 不是「字符串 → 字符串」;
- features 里的 node 不在这个 app 的 dag 里;
- 两个 app 的 mapping 写了同一个 pattern(哪个都不能用,删掉一个)。
特征编号在不在词表里由前端核对(后端不读标注)。

app 要在注册表里(path2_web.discovery):后端启动之后新写的 app,重启后端才认得;mapping 文件每次请求都重读。
"""
from __future__ import annotations

from pathlib import Path

import yaml

MAPPING_FILE = "mapping.yaml"


def mapping_path(mod) -> Path:
    """app 的 mapping 文件:和注册表里的 app 模块(path2_apps/<app>/dag_spec.py)在同一个目录。"""
    return Path(mod.__file__).parent / MAPPING_FILE


def _node_ids(mod) -> set[str]:
    """app 的 dag 里全部 node_id(含子结构 node),按当前参数文件建 dag。"""
    load = getattr(mod, "load_params", None)
    spec = mod.build_pattern(load()) if callable(load) else mod.PATTERN_DAG
    return {n.node_id for n in spec.to_topology().nodes}


def _read_one(app: str, mod) -> dict | None:
    """读一个 app 的 mapping 文件;没有文件返回 None。"""
    path = mapping_path(mod)
    if not path.is_file():
        return None
    out = {"app": app, "pattern": None, "features": {}, "problem": None}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        out["problem"] = f"{MAPPING_FILE} cannot be read: {type(e).__name__}"
        return out
    pattern = raw.get("pattern") if isinstance(raw, dict) else None
    if not isinstance(pattern, str) or not pattern.strip():
        out["problem"] = "pattern must be a non-empty string"
        return out
    out["pattern"] = pattern
    feats = raw.get("features")
    if not isinstance(feats, dict) or not all(
            isinstance(k, str) and k and isinstance(v, str) and v for k, v in feats.items()):
        out["problem"] = "features must map feature ids to node ids"
        return out
    out["features"] = dict(feats)
    unknown = sorted(set(feats.values()) - _node_ids(mod))
    if unknown:
        out["problem"] = f"node not in app {app}: {', '.join(unknown)}"
    return out


def read_mappings(registry) -> list[dict]:
    """全部已注册 app 的 mapping 文件,按 app 名排:[{app, pattern, features, problem}]。
    problem 为 None 才能用;两个 app 写了同一个 pattern 时,两边都记上问题。"""
    out = [m for app in registry.ids() if (m := _read_one(app, registry.get(app))) is not None]
    by_pattern: dict[str, list[str]] = {}
    for m in out:
        if m["pattern"] is not None:
            by_pattern.setdefault(m["pattern"], []).append(m["app"])
    for m in out:
        others = [a for a in by_pattern.get(m["pattern"], []) if a != m["app"]]
        if others and m["problem"] is None:
            m["problem"] = f"pattern also mapped by app {', '.join(others)}"
    return out
