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

会话段(可选,顶层键 session):会话的账本,由会话写,后端原样带给前端(纯投影,同 notes)。

    session:
      snapshot:                 # 每轮开头定格
        seen: {pc: 171, upc: 0} # 每台机器从 1 起连续到齐的最大批次序号(读标注结果的 machines[机器].through)
        samples: [s-pc-3, s-pc-9]   # 这个 pattern 当时的样本编号
        at: "2026-11-10"        # 可选:定格那天(现实日期,不是行情日期;不加引号也行,带出时转成字符串)
      conditions:               # 由反馈、负样本 note、盲看理由推出的条件
        - {where: plateau.no_chase, from: [f-pc-1], state: unmeasured}   # state 是自由文字
      tags:                     # 还红着或 lost 的反馈的原因标签
        f-pc-1: for_tuning

- 三个子键都可省;snapshot 写了就必须有 seen({机器名: 非负整数})和 samples(编号数组);conditions 每项恰好
  where(非空字符串)、from(编号数组)、state(字符串)三个键;tags 是 {反馈编号: 标签},标签取 SESSION_TAGS
  之一:unhandled 还没处理 / for_tuning 留给调参 / not_worth 量过不值得加 / invisible 当天看不出 /
  accepted 用户说过接受 / redefined 定义改过(挂了它的反馈不再算朱红,见 path2_web/annotation/match.py 的 is_red);
- 形状问题只记进 session_problem(一句英文),不进 problem:会话段写坏了不影响 compare 用这个 mapping;
  这时 session 为 None。没写会话段时 session、session_problem 都是 None;
- 反馈编号、样本编号在不在标注里由前端核对(后端不读标注);where 不对着 dag 查(推出的条件可能还没写进 app)。

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

import datetime as dt
from pathlib import Path

import yaml

MAPPING_FILE = "mapping.yaml"

# 会话段 tags 的原因标签(暂名,待用户认):还没处理 / 留给调参 / 量过不值得加 / 当天看不出 / 用户说过接受 /
# 定义改过。TAG_REDEFINED 由反馈的朱红判法读(path2_web/annotation/match.py 的 is_red),只在这里写一处。
TAG_REDEFINED = "redefined"
SESSION_TAGS = ("unhandled", "for_tuning", "not_worth", "invisible", "accepted", TAG_REDEFINED)
_SESSION_KEYS = {"snapshot", "conditions", "tags"}
_SNAPSHOT_KEYS = {"seen", "samples", "at"}
_CONDITION_KEYS = {"where", "from", "state"}


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


def _str_list(v) -> bool:
    """非空字符串组成的数组(可以是空数组)。"""
    return isinstance(v, list) and all(isinstance(x, str) and x for x in v)


def _session_problem(session) -> str | None:
    """会话段的形状问题(一句英文);形状对时返回 None。规则见模块说明「会话段」。"""
    if not isinstance(session, dict) or not set(session) <= _SESSION_KEYS:
        return "session must be a mapping with keys snapshot / conditions / tags"
    snap = session.get("snapshot")
    if snap is not None:
        if not isinstance(snap, dict) or not {"seen", "samples"} <= set(snap) <= _SNAPSHOT_KEYS:
            return "session.snapshot must have seen and samples (and optionally at)"
        seen = snap["seen"]
        if not isinstance(seen, dict) or not all(
                isinstance(k, str) and k and type(v) is int and v >= 0 for k, v in seen.items()):
            return "session.snapshot.seen must map machine names to batch numbers >= 0"
        if not _str_list(snap["samples"]):
            return "session.snapshot.samples must be a list of sample ids"
        if "at" in snap and not isinstance(snap["at"], (str, dt.date)):
            return "session.snapshot.at must be a date or a string"
    conds = session.get("conditions")
    if conds is not None:
        if not isinstance(conds, list) or not all(
                isinstance(c, dict) and set(c) == _CONDITION_KEYS and isinstance(c["where"], str)
                and c["where"].strip() and _str_list(c["from"]) and isinstance(c["state"], str) for c in conds):
            return "session.conditions must be a list of {where, from, state}"
    tags = session.get("tags")
    if tags is not None:
        if not isinstance(tags, dict) or not all(isinstance(k, str) and k for k in tags):
            return "session.tags must map feedback ids to tags"
        bad = sorted({str(v) for v in tags.values() if v not in SESSION_TAGS})
        if bad:
            return f"session.tags has unknown tags: {', '.join(bad)}"
    return None


def _read_one(app: str, mod) -> dict | None:
    """读一个 app 的 mapping 文件;没有文件返回 None。

    返回 {app, pattern, features, notes, problem, session, session_problem}。会话段在任何别的检查之前读:
    pattern、features 等写坏了(problem 非空)也照样带出会话段;会话段的问题只进 session_problem。"""
    path = mapping_path(mod)
    if not path.is_file():
        return None
    out = {"app": app, "pattern": None, "features": {}, "notes": {}, "problem": None,
           "session": None, "session_problem": None}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        out["problem"] = f"{MAPPING_FILE} cannot be read: {type(e).__name__}"
        return out
    session = raw.get("session") if isinstance(raw, dict) else None
    if session is not None:
        out["session_problem"] = _session_problem(session)
        if out["session_problem"] is None:
            at = (session.get("snapshot") or {}).get("at")
            if isinstance(at, dt.date):   # 不加引号的 at: 2026-11-10 被 YAML 读成日期,转回字符串带出
                session = {**session, "snapshot": {**session["snapshot"], "at": at.isoformat()}}
            out["session"] = session
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
    """全部已注册 app 的 mapping 文件,按 app 名排:[{app, pattern, features, notes, problem, session,
    session_problem}]。problem 为 None 才能用;两个 app 写了同一个 pattern 时,两边都记上问题。
    session / session_problem 见模块说明「会话段」,与 problem 互不影响。"""
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
