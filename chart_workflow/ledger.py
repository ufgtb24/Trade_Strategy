"""命令:账本追加与汇总(<root>/ledger.jsonl,每轮一行 JSON)。

    uv run python -m chart_workflow.ledger add --kind rule --rule-id quietbase --version v2 \\
        --source annotation:20261008T101500 --change "加了条件:…" --list-id r003-contrast-quietbase-v2
    uv run python -m chart_workflow.ledger show

add 自动从清单里读 summary 的「全部」行(盲看清单没有 summary,记 null)和生成清单时生效的
数据错误登记条数(n_data_errors)与跨源比对「一致 / 不一致 / 取不到」各多少段(xcheck),
清单里没记就是 null;轮次号自动加 1。
show 打印 Markdown 表,末尾给累计尝试次数(大涨段轮不算尝试)。
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

KINDS = ("bigmoves", "rule", "mined")
SOURCE_RE = re.compile(r"^(annotation:\S+|mining|literature|user-text)$")


def ledger_path(cfg: dict) -> Path:
    return root_dir(cfg) / "ledger.jsonl"


def read_ledger(cfg: dict) -> list[dict]:
    p = ledger_path(cfg)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _xcheck_counts(doc: dict) -> dict | None:
    x = (doc.get("params") or {}).get("xcheck")
    if not x:
        return None
    return {"ok": x.get("ok"), "mismatch": x.get("mismatch"), "unavailable": x.get("unavailable")}


def add_round(cfg: dict, *, kind: str, rule_id: str, version: str, source: str, change: str,
              list_id: str, note: str = "") -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一: {kind!r}")
    if not SOURCE_RE.fullmatch(source):
        raise ValueError("source 必须是 annotation:<batch_id> / mining / literature / user-text")
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
    rows = read_ledger(cfg)
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
    p = ledger_path(cfg)
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


def render(rows: list[dict]) -> str:
    head = ("| 轮次 | 时间 | 类型 | 规则 | 版本 | 来源 | 改了什么 | 清单 | 命中数 | 方向领先 "
            "| 方向偶然波动 | 幅度领先 | 幅度偶然波动 | 是否毕业 | 数据错误登记 "
            "| 跨源比对(一致/不一致/取不到) |")
    sep = "|" + "---|" * 16
    lines = [head, sep]
    for r in rows:
        s = r.get("summary_all") or {}
        grad = {True: "毕业", False: "未毕业", None: "—"}[r.get("graduated")]
        change = str(r.get("change", "")).replace("|", "\\|")
        lines.append(
            f"| {r['round']} | {r['ts']} | {r['kind']} | {r['rule_id']} | {r['version']} "
            f"| {r['source']} | {change} | {r['list_id']} | {s.get('n_hits', '—')} "
            f"| {_f(s.get('dir_lead'))} | {_f(s.get('dir_noise'), False)} "
            f"| {_f(s.get('mag_lead'))} | {_f(s.get('mag_noise'), False)} | {grad} "
            f"| {'—' if r.get('n_data_errors') is None else r['n_data_errors']} "
            f"| {_xc(r.get('xcheck'))} |")
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
        except (ValueError, FileNotFoundError) as ex:
            print(f"错误:{ex}", file=sys.stderr)
            sys.exit(2)
        print(f"已记第 {e['round']} 轮 → {ledger_path(cfg)}")
    else:
        print(render(read_ledger(cfg)))


if __name__ == "__main__":
    main()
