"""compare 用的 mapping 文件(暂行的最小形式):会话为验证 V-S1 手工写,说明一个标注里的 pattern 用哪个 app、
app 的哪个 node 认用户的哪个特征,另可附几句给用户看的说明(notes)。不写特征的级。

为什么放在 app 目录里
--------------------
mapping 随 app 进 git,不进标注文件:标注文件只由工具写,会话不写;app 改版时 mapping 跟着改。

文件位置与格式
--------------
`path2_apps/<app>/mapping.yaml`,和这个 app 的 `dag_spec.py` 在同一个目录。有这个文件,这个 app 就是文件里
那个 pattern 的 app;一个 app 最多对一个 pattern。

    # compare 用的 mapping(暂行)
    pattern: 放量突破          # 标注里的 pattern 名,和顶栏 pattern 下拉里的一字不差
    features:                 # 特征编号: 认它的 node(app 的 node_id)
      w-pc-3: bo
      w-pc-7: tb_seg
    notes:                    # 可选。node 或 node.where 名: 一句给用户看的话
      bo: 放量突破那一根
      bo.vol_big: 放量

- 特征编号是词表里的编号(`w-<机器名>-<n>`),不是特征名:用户改特征名不影响 mapping。会话从
  `path2_web.annotation.store.read_annotations(load_config())["state"]["features"]` 查编号;
- 一个特征只对一个 node;几个特征可以对同一个 node;
- mapping 只决定框轨挨着哪组 band、表头写什么,不决定画不画:compare 的副图就是主视图那张,app 的每个 node
  照常各占一条 band;没写进 features 的 node 照样画,只是不挨着任何框轨(表头挂 app_only);
- notes 只是附注,不影响谁认哪个特征:界面上 where 名、node 名是 app 的英文标识符,用户对不上自己定义里的词,
  notes 用用户定义里的原话(或一句只描述 app 当前做法的话)写给它们,前端在 compare 的 diagnose 与框的 level 行里
  node 名、条件名旁显示。
  键是 node_id(说这个 node),或 `node_id.where 名`(说这个 node 上的一条 where;where 名即 NodeSpec.where
  的 clause_id,同名 where 挂在几个 node 上时各写各的)。不写数字(实测值、门槛),说明里只给类别。

compare 怎么用它(前端):当前 pattern 恰好有一个没有问题的 mapping 时,`compare` / `app` 两档可用;
compare 把 map 了的特征轨放在它对的 node 那组 band(这个 node 及其子 node)正上方,轨标题写 `⇣ node`;
样本、框和 app 怎么对、认没认出,按样本日 / 框终点那天配对那一格读(path2_web_ui/src/stores/compare.ts)。
app 模式与 compare 的 band 表头都在 node 名后写对到它的特征名。

读的时候查出来的问题(problem,一句话;有问题的 mapping 不能用):
- 文件读不懂、pattern 不是非空字符串、features 不是「字符串 → 字符串」;
- features 里的 node 不在这个 app 的 dag 里;
- notes 不是「非空字符串 → 非空字符串」,或键指向 dag 里没有的 node / 那个 node 上没有的 where;
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


def _dag_index(mod) -> dict[str, set[str]]:
    """app 的 dag:全部 node_id(含子结构 node)→ 这个 node 上 where 的名字,按当前参数文件建 dag。"""
    load = getattr(mod, "load_params", None)
    spec = mod.build_pattern(load()) if callable(load) else mod.PATTERN_DAG
    out: dict[str, set[str]] = {n.node_id: set() for n in spec.to_topology().nodes}
    for n in getattr(spec, "nodes", ()):
        if n.node_id in out:
            out[n.node_id] = {cid for cid, _ in getattr(n, "where", ())}
    return out


def _note_key_ok(key: str, dag: dict[str, set[str]]) -> bool:
    """notes 的键:node_id,或 `node_id.where 名`。node_id 本身不含点时才能这样拆;先整串当 node_id 查。"""
    if key in dag:
        return True
    node, sep, where = key.partition(".")
    return bool(sep) and node in dag and where in dag[node]


def _read_one(app: str, mod) -> dict | None:
    """读一个 app 的 mapping 文件;没有文件返回 None。"""
    path = mapping_path(mod)
    if not path.is_file():
        return None
    out = {"app": app, "pattern": None, "features": {}, "notes": {}, "problem": None}
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
    notes = raw.get("notes")
    if notes is not None and (not isinstance(notes, dict) or not all(
            isinstance(k, str) and k and isinstance(v, str) and v.strip() for k, v in notes.items())):
        out["problem"] = "notes must map node ids or node.where names to non-empty text"
        return out
    out["notes"] = dict(notes or {})
    dag = _dag_index(mod)
    unknown = sorted(set(feats.values()) - set(dag))
    if unknown:
        out["problem"] = f"node not in app {app}: {', '.join(unknown)}"
        return out
    bad = sorted(k for k in out["notes"] if not _note_key_ok(k, dag))
    if bad:
        out["problem"] = f"notes refer to nothing in app {app}: {', '.join(bad)}"
    return out


def read_mappings(registry) -> list[dict]:
    """全部已注册 app 的 mapping 文件,按 app 名排:[{app, pattern, features, notes, problem}]。
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
