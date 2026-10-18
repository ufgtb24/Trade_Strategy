"""命令:账本追加与汇总(<状态根>/ledger.jsonl,每轮一行 JSON;状态根见 state.py)。

    uv run python -m chart_workflow.ledger add --kind rule --rule-id quietbase --version v2 \\
        --source annotation:20261008T101500 --change "加了条件:…" --list-id r003-contrast-quietbase-v2
    uv run python -m chart_workflow.ledger show

对照页(contrast)与大涨段(bigmoves)每生成一份清单都自动追加一行(auto = true),不靠手敲;
手动 add 保留,但清单已有自动记账行时拒绝重复记。
算成绩的那一刻就记账:对照统计(control.summarize)算完立刻调 record_round 追加一行,不给记账上下文
就拒绝算——会话在脚本里直接调统计函数,也拿不到不记账的成绩。这一行在清单写盘之前写,所以
record_round 拒绝已经存在的清单名(同名重新生成会覆盖旧清单,账本对不上);check_new_list_id
供命令行在开工前先查(清单文件已存在、或账本里已有这个清单名,都拒绝)。

add 自动从清单里读 summary 的「全部」行(盲看清单没有 summary,记 null)和生成清单时生效的
数据错误登记条数(n_data_errors)与跨源比对「一致 / 不一致 / 取不到」各多少段(xcheck),
清单里没记就是 null。
轮次号不落盘:read_ledger 读时按时间(同一秒按行序)重算。账本按行合并(.gitattributes merge=union),
两台机器各自追加再合并时,落盘的轮次号会重复,读时重算就不会;每行另有全局唯一的 entry_id。
每行都带 provenance(能不能原样重跑):当前 git 提交号 commit、chart_workflow/ 与 path2/ 有没有
未提交改动 dirty、当时生效配置的指纹 config_sha 与全文存档 config_archive(<状态根>/config_archive/
<指纹>.json,内容相同不重复写)、数据错误登记指纹 data_errors_sha(清单里记了才有)、截断副本
snapshot {dir, cutoff, created_at, sha(副本清单的指纹), fingerprint(整份副本按内容的指纹,见 snaplock)}。
source 是 shape:<shape_id>@v<版本> 时(规则来自哪张形态卡的哪个版本),从形态卡读那个版本,
写入 conditions:每个要素项与触发一项。按要素记,一律取卡这一版建立时那条要素的那一版(卡上记下的要素
编号与版本号),之后要素修订、被合并都不改变账本记的东西:
  要素项 {"cond_id", "kind": "ingredient", "element"(卡上引用的编号), "element_resolved"(现在合并后解析到的,
          只作参考), "element_version"(卡上记下的版本),
          "element_origin", "element_suggested_by", "element_has_said",   # 要素本身是谁提的
          "definition_origin", "definition_suggested_by", "definition_has_said",   # 那一版的定义是谁定的
          "fact_rows", "angle_by": "preset | user | null", "angle_ops",   # 它读的事实行是谁提的角度
          "role", "origin", "suggested_by", "has_said_first_match", "root_origin", "root_suggested_by"}
          # 后面这几项是「角色是谁定的」(卡上这一项的来源记录)
  触发   {"cond_id", "kind": "trigger", "term", "origin", "suggested_by", "has_said_first_match",
          "root_origin", "root_suggested_by"}
root_* 是沿 own_library 的 root 递归到底后的来源(不是 own_library 时就是它自己的来源)。
angle_by = user:要素读的事实行是用户提的角度(facts.ROWS 的 source 指向的「提出角度」日志条目真在、且排在
那一版定义建立之前),angle_ops 是那条日志——这种要素不算系统推荐;null:那一版待写代码,还没读任何事实行。
账本里不预先合并成几类,怎么划、各算谁的留给流程骨架。卡、版本或卡上引用的要素不存在就报错。
来源写形态卡的行,账本记账时自己把规则和卡核对一遍(rulecheck.check_rule_against_shape:声明一致、样本一致、
样本股与随机抽的一批股票逐日一致),不收调用方传来的核对结果;通过后把结果记进 rule_implements,不过就拒绝记。核对要用规则本身
(规则文件或 app),并且要和清单实际用的规则同一条(按清单 params.rule_identity 的指纹比,见 rules.rule_identity);
手动 add 不带规则,所以形态卡来源只能经对照页命令记账。
新字段一律可选,旧行照常读。
自动记账的行另有:rule_sha(规则文件或参数文件的 sha256)、rule_archive(存档位置,相对状态根)、
app_commit / app_dirty(app 方式:当时的 git 提交、app 目录有没有未提交改动)、years(这次统计与
图集用了哪些年份)。kind:bigmoves(大涨段,不算尝试)/ rule / mined / blind(盲看轮;算不算尝试由流程
骨架定,show 暂按尝试计,保守)。
show 打印 Markdown 表(「条件来源」一列按来源计数,只是展示),末尾给累计尝试次数(大涨段轮不算尝试)。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from chart_workflow import mode
from chart_workflow import state as _state
from chart_workflow.config import REPO_ROOT, dataset_dir, load_config, root_dir
from chart_workflow.control import ALL_SCOPE
from chart_workflow.loader import SNAPSHOT_FILE, NotASnapshot, check_snapshot
from chart_workflow.state import StateRootMissing, state_root

KINDS = ("bigmoves", "rule", "mined", "blind")
SOURCE_RE = re.compile(r"^(annotation:\S+|mining|literature|user-text|shape:s\d{3,}@v\d+|bigmoves)$")
SHAPE_SOURCE_RE = re.compile(r"^shape:(s\d{3,})@v(\d+)$")
SOURCE_HELP = ("source 必须是 annotation:<batch_id> / mining / literature / user-text / "
               "shape:<shape_id>@v<版本> / bigmoves")
CTX_REQUIRED = ("kind", "rule_id", "version", "source", "change", "list_id")
DIRTY_DIRS = ("chart_workflow", "path2")


def ledger_path() -> Path:
    """账本在状态根里(记账类文件唯一的家)。"""
    return state_root() / "ledger.jsonl"


def read_ledger() -> list[dict]:
    """读全部行,按时间排好(同一秒按行序),round 读时重算(不信落盘的轮次号)。"""
    p = ledger_path()
    if not p.exists():
        return []
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    order = sorted(range(len(rows)), key=lambda i: (str(rows[i].get("ts") or ""), i))
    out = []
    for k, i in enumerate(order, 1):
        rows[i]["round"] = k
        out.append(rows[i])
    return out


def list_path(cfg: dict, list_id: str) -> Path:
    return root_dir(cfg) / "lists" / f"{list_id}.json"


def check_new_list_id(cfg: dict, list_id: str) -> None:
    """新清单名不得已存在:清单文件在、或账本里已有这个清单名 → ValueError。
    清单名和模式对不上(调试模式要 dbg- 开头,正式模式不收它)→ mode.ModeError(ValueError 的子类)。"""
    mode.check_list_id(list_id)
    if list_path(cfg, list_id).exists():
        raise ValueError(f"清单 {list_id} 已存在:同名重新生成会覆盖旧清单、账本对不上,换一个清单名")
    if any(r.get("list_id") == list_id for r in read_ledger()):
        raise ValueError(f"账本里已有清单 {list_id} 的记录,换一个清单名")


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _sha16(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def archive_config(cfg: dict, root: Path) -> tuple[str, str]:
    """生效配置全文按指纹存进 <状态根>/config_archive/<指纹>.json(内容相同不重复写)。
    返回 (指纹, 相对状态根的路径)。"""
    raw = json.dumps(cfg, sort_keys=True, ensure_ascii=False, indent=1, default=str) + "\n"
    sha = _sha16(raw.encode())
    rel = f"config_archive/{sha}.json"
    dst = root / rel
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        tmp.write_text(raw)
        tmp.replace(dst)
    return sha, rel


def provenance(cfg: dict, root: Path, params: dict | None = None) -> dict:
    """这一轮能不能原样重跑要的东西(见模块说明)。git 不可用时对应字段为 null。"""
    head = _git("rev-parse", "HEAD")
    dirty = {}
    for d in DIRTY_DIRS:
        out = _git("status", "--porcelain", "--", f"{d}/")
        dirty[d] = None if out is None else bool(out.strip())
    cfg_sha, cfg_rel = archive_config(cfg, root)
    snap = None
    ddir = dataset_dir(cfg)
    try:
        man = check_snapshot(ddir)
        try:
            shown = str(Path(ddir).relative_to(REPO_ROOT))
        except ValueError:
            shown = str(ddir)
        from chart_workflow.snaplock import fingerprint
        snap = {"dir": shown, "cutoff": man.get("cutoff"), "created_at": man.get("created_at"),
                "sha": _sha16((Path(ddir) / SNAPSHOT_FILE).read_bytes()),
                "fingerprint": fingerprint(ddir)["sha"]}
    except (NotASnapshot, OSError):
        pass
    de = (params or {}).get("data_errors") or {}
    return {"commit": head.strip() if head else None, "dirty": dirty, "config_sha": cfg_sha,
            "config_archive": cfg_rel, "data_errors_sha": de.get("sha"), "snapshot": snap}


def _xcheck_counts(doc: dict) -> dict | None:
    x = (doc.get("params") or {}).get("xcheck")
    if not x:
        return None
    return {"ok": x.get("ok"), "mismatch": x.get("mismatch"), "unavailable": x.get("unavailable")}


def _resolve_root(rec: dict) -> dict:
    """沿 own_library 的 root 递归到底:返回真正的来源记录。"""
    seen = 0
    while rec.get("suggested_by") == "own_library" and isinstance(rec.get("root"), dict) and seen < 50:
        rec, seen = rec["root"], seen + 1
    return rec


def _ingredient_condition(it: dict, els: dict, ops: list[dict]) -> dict:
    from chart_workflow import elements as E

    root = _resolve_root(it)
    out = {"cond_id": it["ing_id"], "kind": "ingredient", "role": it.get("role"),
           "origin": it.get("origin"), "suggested_by": it.get("suggested_by"),
           "has_said_first_match": bool(str(it.get("said_first_match") or "").strip()),
           "root_origin": root.get("origin"), "root_suggested_by": root.get("suggested_by")}
    eid = it.get("element")
    if eid is None:                                # 旧格式的要素项(引用事实行编号)
        return {**out, "term": it.get("term")}
    if eid not in els:
        raise FileNotFoundError(f"要素 {eid} 不在要素库里")
    el = els[eid]                                  # 卡上引用的那条,不跟合并
    ver = E.element_version(els, eid, it["element_version"]) if it.get("element_version") \
        else el["versions"][-1]                    # 旧卡没记版本:取这条要素自己的当前版本
    d, do = ver.get("definition"), ver.get("definition_origin") or {}
    who, angle_ops = E.angle(ver, ops)
    return {**out, "element": eid, "element_resolved": E.resolve(els, eid), "element_version": ver["version"],
            "element_origin": el.get("origin"), "element_suggested_by": el.get("suggested_by"),
            "element_has_said": bool(str(el.get("said_first_match") or "").strip()),
            "definition_origin": do.get("origin"), "definition_suggested_by": do.get("suggested_by"),
            "definition_has_said": bool(str(do.get("said_first_match") or "").strip()),
            "fact_rows": [d["row"]] if d else [], "angle_by": who, "angle_ops": angle_ops}


def shape_conditions(source: str) -> list[dict]:
    """source = shape:<id>@v<n> → 那个版本每个要素项与触发的来源。先重走全部操作日志的校验(不合格 →
    ShapeValidationError,是 ValueError),卡与要素从日志重算,不读磁盘上的卡与要素文件。
    卡、版本或引用的要素不存在 → FileNotFoundError。"""
    from chart_workflow.shapes import checked_state

    m = SHAPE_SOURCE_RE.fullmatch(source)
    ops, cards, els = checked_state()
    card = cards.get(m.group(1))
    if card is None:
        raise FileNotFoundError(f"形态卡不存在: {m.group(1)}")
    n = int(m.group(2))
    ver = next((v for v in card["versions"] if v["version"] == n), None)
    if ver is None:
        raise FileNotFoundError(f"形态卡 {m.group(1)} 没有版本 v{n}")
    out = [_ingredient_condition(it, els, ops) for it in ver["card"].get("ingredients", [])]
    for it in ver["card"].get("triggers", []):
        root = _resolve_root(it)
        out.append({"cond_id": it["trig_id"], "kind": "trigger", "term": it.get("term"),
                    "origin": it.get("origin"), "suggested_by": it.get("suggested_by"),
                    "has_said_first_match": bool(str(it.get("said_first_match") or "").strip()),
                    "root_origin": root.get("origin"), "root_suggested_by": root.get("suggested_by")})
    return out


def check_source(source: str) -> list[dict] | None:
    """source 格式不对 → ValueError;是形态卡来源时返回条件构成(卡或版本不存在 → FileNotFoundError)。"""
    if not SOURCE_RE.fullmatch(source):
        raise ValueError(SOURCE_HELP)
    return shape_conditions(source) if SHAPE_SOURCE_RE.fullmatch(source) else None


def _summary_all(summary: dict | None) -> tuple[dict | None, bool | None]:
    if not summary:
        return None, None
    r = next((x for x in summary["rows"] if x["scope"] == ALL_SCOPE), None)
    summary_all = None if r is None else {k: r.get(k) for k in
                                          ("n_hits", "dir_lead", "dir_noise", "mag_lead", "mag_noise")}
    return summary_all, bool(summary.get("graduation", {}).get("passed", False))


def _entry(cfg: dict, root: Path, *, kind: str, rule_id: str, version: str, source: str, change: str,
           list_id: str, note: str, params: dict | None) -> dict:
    """一行的公共部分(不含 round:读时重算)。kind / source 不合法 → ValueError。"""
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一: {kind!r}")
    conditions = check_source(source)
    now = datetime.now()
    entry = {
        "entry_id": f"{now.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(4)}",
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "kind": kind, "rule_id": rule_id, "version": version, "source": source,
        "change": change, "list_id": list_id,
        "summary_all": None, "graduated": None,
        "n_data_errors": ((params or {}).get("data_errors") or {}).get("n_entries"),
        "xcheck": _xcheck_counts({"params": params or {}}),
        "note": note,
        "provenance": provenance(cfg, root, params),
    }
    if conditions is not None:
        entry["conditions"] = conditions
    return entry


def _append(root: Path, entry: dict) -> dict:
    """追加一行并记进水位;返回带读时轮次号的这一行。"""
    p = root / "ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _state.advance(root)
    rnd = next((r["round"] for r in read_ledger() if r.get("entry_id") == entry["entry_id"]), None)
    return {**entry, "round": rnd}


def _shape_check(cfg: dict, source: str, rule: str | None, app: str | None, app_params: str | None,
                 list_params: dict | None) -> dict | None:
    """来源是形态卡时,账本自己核对规则和卡(见模块说明);不是形态卡 → None。没给规则、核对用的规则和清单
    实际用的规则(list_params.rule_identity)对不上、核对不过 → ValueError。"""
    if not SHAPE_SOURCE_RE.fullmatch(source):
        return None
    if not (rule or app):
        raise ValueError(f"来源写的是形态卡 {source}:记账时要给出规则(规则文件或 app),账本自己核对规则和卡一致;"
                         f"手动记账不收形态卡来源")
    from chart_workflow.rules import rule_identity
    want, have = (list_params or {}).get("rule_identity"), rule_identity(rule, app, app_params)
    if want != have:
        raise ValueError(f"来源写的是形态卡 {source}:核对用的规则({have})和清单实际用的规则"
                         f"({want or '清单没记规则指纹'})对不上,只能拿生成这份清单的那条规则核对")
    from chart_workflow import rulecheck             # 函数内导入:rulecheck 依赖本模块
    return rulecheck.check_rule_against_shape(source, cfg, rule=rule, app=app, params=app_params)


def add_round(cfg: dict, *, kind: str, rule_id: str, version: str, source: str, change: str,
              list_id: str, note: str = "", auto: bool = False, rule_sha: str | None = None,
              rule_archive: str | None = None, app_commit: str | None = None,
              app_dirty: bool | None = None, years: list[str] | None = None,
              rule: str | None = None, app: str | None = None, app_params: str | None = None) -> dict:
    """追加一行(清单已写好:大涨段、盲看、手动记账)。auto:命令自动记账;手动记账时清单已有自动行就拒绝。
    rule / app / app_params:这一轮用的规则文件、或 app 与它的参数 yaml(来源是形态卡时必填,账本拿它自己核对)。"""
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一: {kind!r}")
    check_source(source)
    mode.check_list_id(list_id)
    lp = list_path(cfg, list_id)
    if not lp.exists():
        raise FileNotFoundError(f"清单不存在: {lp}")
    doc = json.loads(lp.read_text())
    foreign = mode.foreign_reason(doc, "清单")
    if foreign:
        raise mode.ModeError(f"{foreign}:{list_id}")
    implements = _shape_check(cfg, source, rule, app, app_params, doc.get("params"))
    rows = read_ledger()
    if not auto and any(r.get("list_id") == list_id and r.get("auto") for r in rows):
        raise ValueError(f"这份清单已自动记账: {list_id}")
    root = state_root()
    entry = _entry(cfg, root, kind=kind, rule_id=rule_id, version=version, source=source,
                   change=change, list_id=list_id, note=note, params=doc.get("params"))
    entry["summary_all"], entry["graduated"] = _summary_all(doc.get("summary"))
    if implements is not None:
        entry["rule_implements"] = implements
    if auto:
        entry.update({"auto": True, "rule_sha": rule_sha, "rule_archive": rule_archive,
                      "app_commit": app_commit, "app_dirty": app_dirty, "years": years})
    return _append(root, entry)


def record_round(cfg: dict, ctx: dict, *, summary: dict, years: list[str],
                 other_years_reason: str | None = None) -> dict:
    """算成绩的那一刻记账(由 control.summarize 调用,清单还没写盘)。
    ctx:记账上下文 {kind, rule_id, version, source, change, list_id, note?, params?(清单 params,
    取数据错误登记与跨源比对条数), rule_sha?, rule_archive?, app_commit?, app_dirty?,
    rule? / app? / app_params?(这一轮用的规则;来源是形态卡时必填,账本拿它自己核对,见 add_round)}。
    缺字段、清单名已存在(文件在或账本里有)→ ValueError。"""
    if not isinstance(ctx, dict):
        raise ValueError("记账上下文必须是 dict")
    missing = [k for k in CTX_REQUIRED if not str(ctx.get(k) or "").strip()]
    if missing:
        raise ValueError(f"记账上下文缺 {missing}")
    check_new_list_id(cfg, ctx["list_id"])
    implements = _shape_check(cfg, ctx["source"], ctx.get("rule"), ctx.get("app"), ctx.get("app_params"),
                              ctx.get("params"))
    root = state_root()
    entry = _entry(cfg, root, kind=ctx["kind"], rule_id=ctx["rule_id"], version=ctx["version"],
                   source=ctx["source"], change=ctx["change"], list_id=ctx["list_id"],
                   note=ctx.get("note") or "", params=ctx.get("params"))
    entry["summary_all"], entry["graduated"] = _summary_all(summary)
    if implements is not None:
        entry["rule_implements"] = implements
    entry.update({"auto": True, "rule_sha": ctx.get("rule_sha"), "rule_archive": ctx.get("rule_archive"),
                  "app_commit": ctx.get("app_commit"), "app_dirty": ctx.get("app_dirty"),
                  "years": [str(y) for y in years]})
    if other_years_reason:
        entry["other_years_reason"] = other_years_reason
    return _append(root, entry)


def _f(x, signed=True):
    if x is None:
        return "—"
    return f"{x:+.3f}" if signed else f"{x:.3f}"


def _xc(x) -> str:
    return "—" if not x else f"{x['ok']}/{x['mismatch']}/{x['unavailable']}"


# 条件来源的展示分类(只是展示,账本里存的是逐条原样):
#   要素项按那一版的定义是谁定的计(没记定义来源的旧行按要素本身是谁提的)——用户定的算「你说的」;
#   不是用户定的、但读的事实行是用户提的角度,算「你提的角度」(不算系统推荐);其余按推荐来自谁。
#   旧格式的要素项按卡上的来源计。
#   角色:卡上这一项沿 own_library 递归到底是用户定的,算「你定的」。
#   触发按递归到底的来源计。
_BY_LABEL = {"detector": "事实表", "session": "会话", "llm": "大模型", "general_knowledge": "常识"}


def _who(origin, by) -> str:
    return "你说的" if origin == "user_written" else _BY_LABEL.get(by, "其他")


def _conds(r: dict) -> str:
    cs = r.get("conditions")
    if not cs:
        return "—"
    ing = {"你说的": 0, "你提的角度": 0, "事实表": 0, "会话": 0}
    trig = {"你说的": 0, "事实表": 0}
    n_ing = role_user = 0
    for c in cs:
        if c.get("kind") == "trigger":
            key = _who(c.get("root_origin"), c.get("root_suggested_by"))
            trig[key] = trig.get(key, 0) + 1
            continue
        n_ing += 1
        role_user += c.get("root_origin") == "user_written"
        if "element" not in c:
            key = _who(c.get("root_origin"), c.get("root_suggested_by"))
        else:
            o, by = ((c["definition_origin"], c.get("definition_suggested_by")) if c.get("definition_origin")
                     else (c.get("element_origin"), c.get("element_suggested_by")))
            if o == "user_written":
                key = "你说的"
            elif c.get("angle_by") == "user":
                key = "你提的角度"
            else:
                key = _who(o, by)
        ing[key] = ing.get(key, 0) + 1
    fmt = lambda d: " / ".join(f"{k} {n}" for k, n in d.items())
    return f"要素 {fmt(ing)}；角色你定的 {role_user}/{n_ing}；触发 {fmt(trig)}"


def render(rows: list[dict]) -> str:
    head = ("| 轮次 | 时间 | 类型 | 规则 | 版本 | 来源 | 改了什么 | 清单 | 命中数 | 方向领先 "
            "| 方向偶然波动 | 幅度领先 | 幅度偶然波动 | 是否毕业 | 数据错误登记 "
            "| 跨源比对(一致/不一致/取不到) | 条件来源 |")
    sep = "|" + "---|" * 17
    lines = [head, sep]
    for r in rows:
        s = r.get("summary_all") or {}
        grad = {True: "毕业", False: "未毕业", None: "—"}[r.get("graduated")]
        change = str(r.get("change", "")).replace("|", "\\|")
        lines.append(
            f"| {r['round']} | {r['ts']} | {r['kind']}{'(自动)' if r.get('auto') else ''}"
            f"{'(含内圈外年份)' if r.get('other_years_reason') else ''} "
            f"| {r['rule_id']} | {r['version']} "
            f"| {r['source']} | {change} | {r['list_id']} | {s.get('n_hits', '—')} "
            f"| {_f(s.get('dir_lead'))} | {_f(s.get('dir_noise'), False)} "
            f"| {_f(s.get('mag_lead'))} | {_f(s.get('mag_noise'), False)} | {grad} "
            f"| {'—' if r.get('n_data_errors') is None else r['n_data_errors']} "
            f"| {_xc(r.get('xcheck'))} | {_conds(r)} |")
    attempts = sum(1 for r in rows if r["kind"] != "bigmoves")
    lines.append("")
    if mode.is_debug():
        lines.insert(0, f"**{mode.DEBUG_LABEL}**（这是调试账，下面的轮次都不算尝试）\n")
        lines.append(f"调试账共 {len(rows)} 轮（不算尝试）")
    else:
        lines.append(f"累计尝试次数：{attempts}（共 {len(rows)} 轮，大涨段轮不计入）")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="账本")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--kind", required=True, choices=KINDS)
    a.add_argument("--rule-id", required=True)
    a.add_argument("--version", required=True)
    a.add_argument("--source", required=True)
    a.add_argument("--change", required=True)
    a.add_argument("--list-id", required=True)
    a.add_argument("--note", default="")
    sub.add_parser("show")
    args = ap.parse_args(argv)
    cfg = load_config()
    if args.cmd == "add":
        try:
            e = add_round(cfg, kind=args.kind, rule_id=args.rule_id, version=args.version,
                          source=args.source, change=args.change, list_id=args.list_id,
                          note=args.note)
        except (ValueError, FileNotFoundError, StateRootMissing) as ex:
            print(f"错误:{ex}", file=sys.stderr)
            sys.exit(2)
        print(f"已记第 {e['round']} 轮 → {ledger_path()}")
    else:
        try:
            print(render(read_ledger()))
        except StateRootMissing as ex:
            print(f"错误:{ex}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
