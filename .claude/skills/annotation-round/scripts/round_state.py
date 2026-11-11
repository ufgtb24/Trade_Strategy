"""一轮走到哪了(annotation-round skill 的只读工具)。只打印事实,不写任何文件。

    uv run python .claude/skills/annotation-round/scripts/round_state.py            # 总览:第 0 步用
    uv run python .claude/skills/annotation-round/scripts/round_state.py <R>        # 某一轮:定格后核对、续跑时用

总览打印
--------
- 标注里的 pattern,各有几张样本、几处反馈(反馈只能在 compare 里对着 app 的买点写:反馈不是 0 的 pattern
  一定有过 app);标注的冲突、越界条数,数据指纹是否一致;
- 每个已注册 app 的 mapping:对哪个 pattern、mapping 的问题、会话段的问题、会话段里有没有快照、conditions
  几行、tags 几条;
- 没注册上的 app 及原因;**磁盘上写了 mapping、却没注册上的 app 目录**(它对的 pattern 不是「还没有 app」,
  是 app 导入失败、缺 eval_meta,或被悄悄跳过——后一种「没注册上的 app」那一行不给原因);**已注册、mapping.yaml 却读不出 pattern 的 app**(文件写坏了,同样不是「还没有 app」);
  mapping 写的 pattern 名在标注里找不到的(pattern 可能改过名),在那一行后面提示;
- 每个 pattern 的各轮:round 文件名,有没有处理清单(.plan.md)、报告(.report.md);没有报告的都标「没走完」
  (定格函数见到任何一轮没走完就拒绝再定格);各轮目录里名字不在标注里的子目录(pattern 改名前的各轮)单列。

某一轮打印
----------
- 定格时的 app 与版本指纹;现在写了这个 pattern 的 app、版本指纹、指纹变没变;app 现在读不出时,指出磁盘上
  哪个目录的 mapping 写了这个 pattern;
- 快照已写进会话段: True / False(会话段里的 snapshot 是否就是这个 round 文件里那份);
- 会话段里 conditions 几行、tags 几条(定格前后对一下,防写快照时把它们弄丢);
- 这一轮有没有处理清单、报告;没注册上的 app 及原因。

读标注只经 read_annotations,读 mapping 只经 read_mappings(磁盘上没注册上的那些只读出它写的 pattern 名)。

参数:--apps-pkg(app 所在的包,默认 path2_apps)、--annotation-dir(标注目录,默认读网页配置)、
--rounds-dir(各轮文件的目录,默认是仓库根下的 outputs/annotation_rounds,不随当前目录变)——三个都只给试跑用。
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import yaml


def _disk_mappings(apps_pkg: str) -> dict:
    """app 包目录下每个 `<目录>/mapping.yaml` 写的 pattern 名:{目录名: (文件路径, pattern 或 None)}。"""
    out = {}
    for root in importlib.import_module(apps_pkg).__path__:
        for f in sorted(Path(root).glob("*/mapping.yaml")):
            try:
                raw = yaml.safe_load(f.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                raw = None
            out[f.parent.name] = (f, raw.get("pattern") if isinstance(raw, dict) else None)
    return out


def _session_line(m: dict) -> str:
    """mapping 会话段的概况:有没有快照、conditions 几行、tags 几条。"""
    if m["session_problem"] is not None:
        return "会话段读不出"
    s = m["session"] or {}
    return (f"快照 {'有' if s.get('snapshot') else '没有'}、conditions {len(s.get('conditions') or [])} 行、"
            f"tags {len(s.get('tags') or {})} 条")


def _unregistered(reg, mappings: list, disk: dict) -> list:
    """磁盘上写了 mapping、却不在注册表里的 app 目录:[(目录名, 文件, pattern)]。

    已注册的 app 按「mapping 文件所在的目录」认(注册表的键是 pattern_id,不一定等于目录名)。"""
    from path2_web.mapping import mapping_path
    known = {mapping_path(reg.get(m["app"])).resolve() for m in mappings}
    return [(d, f, pat) for d, (f, pat) in disk.items() if f.resolve() not in known]


def _whole_file_bad(m: dict) -> bool:
    """整份 mapping.yaml 读不出(不是只有会话段坏):这时 pattern、会话段都拿不到。"""
    from path2_web.mapping import MAPPING_FILE
    return m["pattern"] is None and (m["problem"] or "").startswith(f"{MAPPING_FILE} cannot be read")


def _mapping_line(m: dict, patterns=None) -> str:
    """一个已注册 app 的 mapping 概况。整份读不出、pattern 读不出时明说,不打印看着像「没问题」的 None。"""
    if _whole_file_bad(m):
        return (f"- app {m['app']} -> 整份 mapping.yaml 读不出({m['problem']}):"
                "它对哪个 pattern、会话段里有什么,都看不到")
    if m["pattern"] is None:
        return (f"- app {m['app']} -> pattern 读不出({m['problem']}) | "
                f"会话段问题: {m['session_problem']} | 会话段: {_session_line(m)}")
    line = (f"- app {m['app']} -> pattern {m['pattern']} | mapping 问题: {m['problem']} | "
            f"会话段问题: {m['session_problem']} | 会话段: {_session_line(m)}")
    if patterns is not None and m["pattern"] not in patterns:
        line += "  ← 注意: 标注里没有叫这个名字的 pattern(pattern 改过名?)"
    return line


def _disk_line(f: Path, pat) -> str:
    """磁盘上有 mapping、app 却没注册上的一行提示。"""
    what = "读不出它写的 pattern(可能就是你要的这个)" if pat is None else f"写的 pattern 是 {pat!r}"
    return (f"- 磁盘上有 mapping、app 却没注册上: {f} {what}"
            "(这个 app 在,只是没注册上:导入失败、缺 eval_meta,或没被认出来——「没注册上的 app」那一行里没给它原因的,就是没被认出来;"
            "它对的 pattern 不是「还没有 app」)")


def _unreadable_lines(mappings: list) -> list:
    """已注册、mapping.yaml 却读不出 pattern 的 app(文件写坏,或 pattern 那一行丢了):每个一行提示。

    这种 app 对哪个 pattern 现在看不出来,它的 pattern 会被误当成「还没有 app」。"""
    return [f"- 注意: app {m['app']} 的 mapping.yaml 读不出它对哪个 pattern(问题: {m['problem']})。"
            "先把这个文件修到读得出(只动 mapping.yaml),别把它对的 pattern 当成「还没有 app」"
            for m in mappings if m["pattern"] is None]


def overview(cfg: dict, apps_pkg: str, rounds_dir: Path) -> str:
    """总览(各项见模块说明)。"""
    from path2_web.annotation.store import read_annotations
    from path2_web.discovery import PatternRegistry
    from path2_web.mapping import read_mappings

    r = read_annotations(cfg)
    patterns = [p["name"] for p in r["state"]["patterns"]]
    reg = PatternRegistry(apps_pkg)
    mappings = read_mappings(reg)
    counts = {p: [0, 0] for p in patterns}
    for c in r["state"]["charts"]:
        for i, key in enumerate(("samples", "feedback")):
            for o in c.get(key) or []:
                if o.get("pattern") in counts:
                    counts[o["pattern"]][i] += 1
    out = [f"patterns: {patterns}",
           "各 pattern 的标注: " + ("; ".join(f"{p} 样本 {n}、反馈 {k}" for p, (n, k) in counts.items()) or "(没有)"),
           f"标注: 冲突 {len(r['conflicts'])}、越界 {len(r['violations'])}、数据指纹一致 {r['fingerprint']['consistent']}",
           "", "已注册 app 的 mapping:"]
    out += [_mapping_line(m, patterns) for m in mappings] or ["- (没有)"]
    out += _unreadable_lines(mappings)
    out += ["", f"没注册上的 app: {reg.errors() or '没有'}"]
    lost = _unregistered(reg, mappings, _disk_mappings(apps_pkg))
    for d, f, pat in lost:
        out.append(_disk_line(f, pat))
    out += ["", f"各轮({rounds_dir}):"]
    snapped = {m["pattern"] for m in mappings if (m["session"] or {}).get("snapshot")}
    for p in patterns:
        files = sorted((rounds_dir / p).glob("*.json"), key=_round_key) if (rounds_dir / p).is_dir() else []
        if not files:
            out.append(f"- {p}: 还没有跑过任何一轮" + (
                "  ← 注意: 它的 mapping 会话段里已经有快照,这里却一个 round 文件都没有(换过工作目录或清过 outputs)"
                if p in snapped else ""))
            continue
        out += [_round_line(p, f) for f in files]
    gone = sorted(d for d in rounds_dir.iterdir() if d.is_dir() and d.name not in patterns) if rounds_dir.is_dir() else []
    for d in gone:
        out.append(f"- 注意: 各轮目录里有 {d.name},标注里却没有叫这个名字的 pattern(pattern 改过名?):")
        out += ["  " + _round_line(d.name, f, "  ← 没走完(按这个旧名字记的,接不上)")
                for f in sorted(d.glob("*.json"), key=_round_key)]
    return "\n".join(out) + "\n"


def _round_line(pattern: str, f: Path, unfinished: str = "  ← 没走完,续跑") -> str:
    """总览里一轮一行:文件名、有没有处理清单与报告;没有报告的后面跟 unfinished 那句。"""
    stem = f.with_suffix("")
    plan, report = Path(f"{stem}.plan.md").is_file(), Path(f"{stem}.report.md").is_file()
    return (f"- {pattern}: {f.name} | 处理清单 {'有' if plan else '没有'} | 报告 {'有' if report else '没有'}"
            + ("" if report else unfinished))


def _round_key(f: Path):
    """round 文件按「日期、当天第几轮」排(第 10 轮排在第 9 轮后面)。"""
    date, _, n = f.stem.rpartition("-")
    return (date, int(n)) if n.isdigit() else (f.stem, 0)


def one_round(round_path: Path, cfg: dict, apps_pkg: str) -> str:
    """某一轮(各项见模块说明)。"""
    from path2_web.app_version import app_ver
    from path2_web.discovery import PatternRegistry
    from path2_web.mapping import read_mappings

    rnd = json.loads(round_path.read_text(encoding="utf-8"))
    pattern, snap = rnd["pattern"], rnd["snapshot"]
    reg = PatternRegistry(apps_pkg)
    mappings = read_mappings(reg)
    mine = [m for m in mappings if m["pattern"] == pattern]
    out = [f"round 文件: {round_path}(pattern {pattern},定格于 {snap.get('at', '?')})",
           "定格时 app: " + (f"{rnd['app_id']} {rnd['app_ver']}" if rnd["app_id"] else "没有(定格时还没有 app)")]
    if not mine:
        out.append("现在 app: 没有已注册的 app 写这个 pattern")
        for d, f, pat in _unregistered(reg, mappings, _disk_mappings(apps_pkg)):
            if pat == pattern or pat is None:
                out.append(_disk_line(f, pat) + "(原因见末行)")
        out += _unreadable_lines(mappings)
        for m in mappings:
            if m["app"] == rnd["app_id"] and m["pattern"] is not None:
                out.append(f"- 注意: 定格时的 app {m['app']} 现在的 mapping 写的 pattern 是 {m['pattern']!r},"
                           f"不是这一轮的 {pattern!r}(pattern 改过名,或 mapping 写错了)")
        out.append("快照已写进会话段: False(读不到 mapping)")
    for m in mine:
        ver = app_ver(reg.get(m["app"]))
        same = "(定格时没有 app)" if not rnd["app_id"] else ("没变" if ver == rnd["app_ver"] else "变了")
        out.append(f"现在 app: {m['app']} {ver} | 指纹: {same} | mapping 问题: {m['problem']} | "
                   f"会话段问题: {m['session_problem']}")   # pattern 对得上,说明整份文件读得出
        written = (m["session"] or {}).get("snapshot") or {}
        ok = (written.get("seen"), written.get("samples")) == (snap["seen"], snap["samples"])
        out += [f"快照已写进会话段: {ok}", f"会话段: {_session_line(m)}"]
    stem = round_path.with_suffix("")
    out += [f"处理清单 .plan.md: {'有' if Path(f'{stem}.plan.md').is_file() else '没有'}",
            f"报告 .report.md: {'有' if Path(f'{stem}.report.md').is_file() else '没有'}",
            f"没注册上的 app: {reg.errors() or '没有'}"]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="一轮走到哪了(只读)")
    ap.add_argument("round", nargs="?", help="round 文件;不给就出总览")
    ap.add_argument("--apps-pkg", default="path2_apps", help="app 所在的包(试跑用)")
    ap.add_argument("--annotation-dir", help="标注目录(试跑用)")
    ap.add_argument("--rounds-dir", help="各轮文件的目录(试跑用;默认是仓库根下的 outputs/annotation_rounds)")
    a = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:      # 从仓库根以外的目录调起时也找得到 path2_web
        sys.path.insert(0, str(root))
    from path2_web.config import load_config
    cfg = load_config()
    if a.annotation_dir:
        cfg = {**cfg, "annotation_dir": a.annotation_dir}
    if a.round:
        print(one_round(Path(a.round), cfg, a.apps_pkg), end="")
    else:
        rounds = Path(a.rounds_dir) if a.rounds_dir else root / "outputs" / "annotation_rounds"
        print(overview(cfg, a.apps_pkg, rounds), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
