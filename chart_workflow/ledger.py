"""命令:账本追加与汇总(<状态根>/ledger.jsonl,每轮一行 JSON;状态根见 state.py)。

    uv run python -m chart_workflow.ledger add --kind rule --rule-id quietbase --version v2 \\
        --source annotation:20261008T101500 --change "加了条件:…" --list-id r003-contrast-quietbase-v2
    uv run python -m chart_workflow.ledger show

对照页(contrast)与大涨段(bigmoves)每生成一份清单都自动追加一行(auto = true),不靠手敲;
手动 add 保留,但清单已有自动记账行时拒绝重复记。

add 自动从清单里读 summary 的「全部」行(盲看清单没有 summary,记 null)和生成清单时生效的
数据错误登记条数(n_data_errors)与跨源比对「一致 / 不一致 / 取不到」各多少段(xcheck),
清单里没记就是 null;轮次号自动加 1。
source 是 shape:<shape_id>@v<版本> 时(规则来自哪张形态卡的哪个版本),从形态卡读那个版本,
写入 conditions:每个要素与触发一项
  {"cond_id", "kind": "ingredient | trigger", "term", "role", "origin", "suggested_by",
   "has_said_first_match", "root_origin", "root_suggested_by"}
root_* 是沿 own_library 的 root 递归到底后的来源(不是 own_library 时就是它自己的来源)。
账本里不预先合并成几类,怎么划、各算谁的留给流程骨架。卡或版本不存在就报错。新字段一律可选,
旧行照常读。
自动记账的行另有:rule_sha(规则文件或参数文件的 sha256)、rule_archive(存档位置,相对状态根)、
app_commit / app_dirty(app 方式:当时的 git 提交、app 目录有没有未提交改动)、years(这次统计与
图集用了哪些年份)。kind:bigmoves(大涨段,不算尝试)/ rule / mined / blind(盲看轮;算不算尝试由流程
骨架定,show 暂按尝试计,保守)。
show 打印 Markdown 表(「条件来源」一列按来源计数,只是展示),末尾给累计尝试次数(大涨段轮不算尝试)。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from chart_workflow.config import load_config, root_dir
from chart_workflow.control import ALL_SCOPE
from chart_workflow.state import StateRootMissing, state_root

KINDS = ("bigmoves", "rule", "mined", "blind")
SOURCE_RE = re.compile(r"^(annotation:\S+|mining|literature|user-text|shape:s\d{3,}@v\d+|bigmoves)$")
SHAPE_SOURCE_RE = re.compile(r"^shape:(s\d{3,})@v(\d+)$")
SOURCE_HELP = ("source 必须是 annotation:<batch_id> / mining / literature / user-text / "
               "shape:<shape_id>@v<版本> / bigmoves")


def ledger_path() -> Path:
    """账本在状态根里(记账类文件唯一的家)。"""
    return state_root() / "ledger.jsonl"


def read_ledger() -> list[dict]:
    p = ledger_path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


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


def shape_conditions(source: str) -> list[dict]:
    """source = shape:<id>@v<n> → 那个版本每个要素与触发的来源。卡或版本不存在 → FileNotFoundError。"""
    from chart_workflow.shapes import load_card

    m = SHAPE_SOURCE_RE.fullmatch(source)
    card = load_card(m.group(1))
    n = int(m.group(2))
    ver = next((v for v in card["versions"] if v["version"] == n), None)
    if ver is None:
        raise FileNotFoundError(f"形态卡 {m.group(1)} 没有版本 v{n}")
    out = []
    for kind, items, id_key in (("ingredient", ver["card"].get("ingredients", []), "ing_id"),
                                ("trigger", ver["card"].get("triggers", []), "trig_id")):
        for it in items:
            root = _resolve_root(it)
            out.append({"cond_id": it[id_key], "kind": kind, "term": it.get("term"),
                        "role": it.get("role"), "origin": it.get("origin"),
                        "suggested_by": it.get("suggested_by"),
                        "has_said_first_match": bool(str(it.get("said_first_match") or "").strip()),
                        "root_origin": root.get("origin"), "root_suggested_by": root.get("suggested_by")})
    return out


def check_source(source: str) -> list[dict] | None:
    """source 格式不对 → ValueError;是形态卡来源时返回条件构成(卡或版本不存在 → FileNotFoundError)。"""
    if not SOURCE_RE.fullmatch(source):
        raise ValueError(SOURCE_HELP)
    return shape_conditions(source) if SHAPE_SOURCE_RE.fullmatch(source) else None


def add_round(cfg: dict, *, kind: str, rule_id: str, version: str, source: str, change: str,
              list_id: str, note: str = "", auto: bool = False, rule_sha: str | None = None,
              rule_archive: str | None = None, app_commit: str | None = None,
              app_dirty: bool | None = None, years: list[str] | None = None) -> dict:
    """追加一行。auto:命令自动记账(contrast / bigmoves);手动记账时清单已有自动行就拒绝。"""
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一: {kind!r}")
    conditions = check_source(source)
    list_path = root_dir(cfg) / "lists" / f"{list_id}.json"
    if not list_path.exists():
        raise FileNotFoundError(f"清单不存在: {list_path}")
    doc = json.loads(list_path.read_text())
    summary = doc.get("summary")
    summary_all, graduated = None, None
    if summary:
        r = next((x for x in summary["rows"] if x["scope"] == ALL_SCOPE), None)
        if r is not None:
            summary_all = {k: r.get(k) for k in
                           ("n_hits", "dir_lead", "dir_noise", "mag_lead", "mag_noise")}
        graduated = bool(summary.get("graduation", {}).get("passed", False))
    rows = read_ledger()
    if not auto and any(r.get("list_id") == list_id and r.get("auto") for r in rows):
        raise ValueError(f"这份清单已自动记账: {list_id}")
    entry = {
        "round": (max(r["round"] for r in rows) + 1) if rows else 1,
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "kind": kind, "rule_id": rule_id, "version": version, "source": source,
        "change": change, "list_id": list_id,
        "summary_all": summary_all, "graduated": graduated,
        "n_data_errors": (doc.get("params") or {}).get("data_errors", {}).get("n_entries"),
        "xcheck": _xcheck_counts(doc),
        "note": note,
    }
    if auto:
        entry.update({"auto": True, "rule_sha": rule_sha, "rule_archive": rule_archive,
                      "app_commit": app_commit, "app_dirty": app_dirty, "years": years})
    if conditions is not None:
        entry["conditions"] = conditions
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _f(x, signed=True):
    if x is None:
        return "—"
    return f"{x:+.3f}" if signed else f"{x:.3f}"


def _xc(x) -> str:
    return "—" if not x else f"{x['ok']}/{x['mismatch']}/{x['unavailable']}"


# 条件来源的展示分类:按递归到底的来源计数(只是展示,账本里存的是逐条原样)。
# 用户自己写的算「你说的」(哪怕当时摆着推荐),其余按推荐来自谁。
_BY_LABEL = {"detector": "事实表", "session": "会话", "llm": "大模型", "general_knowledge": "常识"}


def _conds(r: dict) -> str:
    cs = r.get("conditions")
    if not cs:
        return "—"
    counts = {"你说的": 0, "事实表": 0, "会话": 0}
    for c in cs:
        key = ("你说的" if c.get("root_origin") == "user_written"
               else _BY_LABEL.get(c.get("root_suggested_by"), "其他"))
        counts[key] = counts.get(key, 0) + 1
    return " / ".join(f"{k} {n}" for k, n in counts.items())


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
            f"| {r['round']} | {r['ts']} | {r['kind']}{'(自动)' if r.get('auto') else ''} "
            f"| {r['rule_id']} | {r['version']} "
            f"| {r['source']} | {change} | {r['list_id']} | {s.get('n_hits', '—')} "
            f"| {_f(s.get('dir_lead'))} | {_f(s.get('dir_noise'), False)} "
            f"| {_f(s.get('mag_lead'))} | {_f(s.get('mag_noise'), False)} | {grad} "
            f"| {'—' if r.get('n_data_errors') is None else r['n_data_errors']} "
            f"| {_xc(r.get('xcheck'))} | {_conds(r)} |")
    attempts = sum(1 for r in rows if r["kind"] != "bigmoves")
    lines.append("")
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
