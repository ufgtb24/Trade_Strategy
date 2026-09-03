# -*- coding: utf-8 -*-
"""app 退出(删除某 app 全部耦合物)的 dry-run 原型 —— 仅为验证清单构造与路径安全,不是实现。

只做两件事:①按三条精确来源构造删除集;②打印分组清单。**不执行任何删除**。
用法:改 main() 顶部常量后 `uv run python <路径>/app_purge_prototype.py`(无 argparse)。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
APPS_DIR = REPO / ".claude/skills/tune-gates/apps"
OUTPUTS_DIR = REPO / "outputs/tune_gates"


def validate_app_name(app) -> str:
    """app 名进任何路径拼接之前必过:非空、不含分隔符、不是 . / .. 。

    实测动机:Path('outputs/tune_gates') / '' == Path('outputs/tune_gates')(删掉全部 app 的
    输出);Path(x) / '/' == Path('/')。只靠拼完再 is_relative_to(REPO) 拦不住——
    'outputs/tune_gates/..' 解析后是 'outputs/',仍在 repo 内。"""
    if not isinstance(app, str) or not app.strip():
        raise SystemExit(f"APP 非法(空/非字符串): {app!r}")
    if app in (".", "..") or "/" in app or "\\" in app or app != app.strip():
        raise SystemExit(f"APP 非法(含分隔符或相对段): {app!r}")
    return app


def safe_child(parent: Path, app: str) -> Path:
    """白名单子目录:结果必须恰好是 parent 的直接子项且 name == app。"""
    p = (parent / app).resolve()
    if p.parent != parent.resolve() or p.name != app:
        raise SystemExit(f"路径安全断言失败: {p}")
    return p


def du(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def human(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f}{u}"
        n /= 1024


def find_longtables_by_run_meta(app: str, roots: list) -> list:
    """来源(iii):扫 run_meta.json,只认 json['app'] 与 app **精确相等** 的。绝不按目录名 glob。"""
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for rm in root.rglob("run_meta.json"):
            try:
                meta = json.loads(rm.read_text())
            except Exception:
                continue
            if meta.get("app") == app:          # 精确相等,不是 in / startswith
                hits.append(rm.parent)
    return sorted(set(hits))


def find_orphan_longtables(roots: list) -> list:
    """含 part-*.parquet 但没有 run_meta.json 的目录 = 归属不明,只报不删。"""
    out = []
    for root in roots:
        if not root.exists():
            continue
        for d in {p.parent for p in root.rglob("part-*.parquet")}:
            if not (d / "run_meta.json").exists():
                out.append(d)
    return sorted(set(out))



def study_consts(study_path: Path) -> dict:
    """纯 AST 读 study.py 的顶层字面量常量。不 import——删除场景下 app 可能已经坏了。"""
    import ast
    out = {}
    try:
        tree = ast.parse(study_path.read_text())
    except Exception:
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:
                pass
    return out


def regenerable(app: str, lt: Path) -> tuple:
    """长表还能不能用当前代码重跑出来?返回 (可再生?, 理由)。

    三链核对,全程不 import app(删除场景下 app 可能已坏):
      ① run_meta.study_fingerprint == classification.fingerprints.study
         —— 确认这份 classification 就是扫该长表时用的那份,否则它的 source 指纹不可用;
      ② classification.fingerprints.study == sha256(当前 study.py)  —— 网格有没有改;
      ③ 用 classification.fingerprints.source.files 记录的**文件清单**重算 source 指纹
         —— 这一步不需要 import:source_fingerprint 只是按序读这些文件的字节。detector
         源码被改(本例 throwback_v1.py 重写)在这里就能抓到;
      ④ study.py 的 BASE_YAML 指向的底座文件还在不在。

    为什么必须走 classification 这一跳:`run_meta.json` 只持久化了 study_fingerprint,
    没留 source/base 的副本。指纹链本身是覆盖 source 的(app_setup MODE=check 就在比它),
    但从**长表侧**出发拿不到——所以要借 classification 补上这一跳。

    单向可靠(设计原则,不是缺陷):报「不可再生」一定对;报「可再生」只是没发现问题。
    漏报只会让东西留下来,永远不会造成删除。
    """
    import hashlib as _h, json as _j
    rm = lt / "run_meta.json"
    if not rm.exists():
        return (None, "无 run_meta.json,无法判定")
    meta = _j.loads(rm.read_text())
    sp = APPS_DIR / app / "study.py"
    if not sp.exists():
        return (False, f"{sp.relative_to(REPO)} 不存在")
    cp = APPS_DIR / app / "classification.json"
    reasons = []

    cur_study = _h.sha256(sp.read_bytes()).hexdigest()
    if cur_study != meta.get("study_fingerprint"):
        reasons.append("study.py 已改(网格/底座声明变了)")

    if not cp.exists():
        reasons.append("classification.json 不存在,source 指纹无从核对")
    else:
        cl = _j.loads(cp.read_text())
        fps = cl.get("fingerprints", {})
        if fps.get("study") != meta.get("study_fingerprint"):
            reasons.append("classification 与长表不同源(study 指纹不符),source 指纹不可用")
        else:
            old = fps.get("source", {})
            h, missing = _h.sha256(), []
            for r in old.get("files", []):
                f = REPO / r
                if not f.exists():
                    missing.append(r); continue
                h.update(r.encode() + b"\0" + f.read_bytes() + b"\0")
            if missing:
                reasons.append(f"源码指纹范围内文件已删除: {missing}")
            elif h.hexdigest() != old.get("hash"):
                reasons.append(f"源码指纹不符(detector/app 源码已改;范围 {len(old.get('files', []))} 个文件)")

    c = study_consts(sp)
    mod, base_yaml = c.get("APP_MODULE"), c.get("BASE_YAML")
    if mod and base_yaml:
        by = REPO.joinpath(*mod.split(".")[:-1]) / base_yaml
        if not by.exists():
            reasons.append(f"底座 {by.relative_to(REPO)} 不存在(重跑会 FileNotFoundError)")

    tail = f";长表记录的 git_head={meta.get('git_head')}"
    if reasons:
        return (False, "；".join(reasons) + tail)
    return (True, "study/source 指纹均一致且底座在位" + tail)


SIBLING_ARTIFACTS = ("random_baseline.csv", "filtered_symbols.csv", "run_stats.jsonl",
                     "cells.csv", "compare_longtable.log")


def git_tracked(p: Path) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(p)], cwd=REPO,
                       capture_output=True)
    return r.returncode == 0


def dirty(p: Path) -> list:
    if not p.exists():
        return []
    r = subprocess.run(["git", "status", "--porcelain", str(p)], cwd=REPO,
                       capture_output=True, text=True)
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def main() -> None:
    APP = "bb_v1"
    SEARCH_ROOTS = [REPO / "docs/research", OUTPUTS_DIR]

    app = validate_app_name(APP)
    print(f"=== app 退出 dry-run · APP={app!r} · worktree={REPO} ===\n")

    # ---- 组 1a/1b:apps/<app>/ 夹内分两类(不是整夹一刀切) ----
    d1 = safe_child(APPS_DIR, app)
    # 跨轮沉淀:内容语义是「对这批数据做过什么」,不随 app 消失 → 点名确认,默认保留
    NAMED = {"notes.md": "跨轮实测沉淀;通用区有引用指向它",
             "exposure.jsonl": "跨轮暴露史(resume 方案);记'在这批数据上看过几次'"}
    print("【组 1a · 必删】app 配置(进 git,删错可 `git checkout HEAD -- <路径>` 找回)")
    named_hits = []
    if d1.exists():
        for f in sorted(d1.rglob("*")):
            if not f.is_file():
                continue
            if f.name in NAMED:
                named_hits.append(f); continue
            print(f"    {f.relative_to(REPO)}  {human(du(f))}  {'tracked' if git_tracked(f) else 'UNTRACKED'}")
        dd = dirty(d1)
        print(f"  工作树{'不干净 → 未提交改动删了找不回,应拒绝或二次确认' if dd else '干净'}")
        for ln in dd:
            print(f"    ! {ln}")
    else:
        print("    (不存在)")

    print("\n【组 1b · 点名确认】跨轮沉淀(默认**保留**;要删须各自单独开关)")
    for f in named_hits:
        n = sum(1 for _ in f.open()) if f.suffix == ".jsonl" else None
        extra = f"  {n} 条记录" if n is not None else ""
        print(f"    {f.relative_to(REPO)}  {human(du(f))}{extra}  ← {NAMED[f.name]}")
    if not named_hits:
        print("    (无)")

    # ---- 组 2:单列确认(重产物,gitignore,可重跑) ----
    # 分流轴不是「进不进 git」,是「能不能用当前代码再生」——见 regenerable()
    ok_groups, bad_groups = [], []
    o = safe_child(OUTPUTS_DIR, app)
    if o.exists():
        (ok_groups if regenerable(app, o / "longtable")[0] else bad_groups).append((o, "outputs 默认目录"))
    for lt in find_longtables_by_run_meta(app, SEARCH_ROOTS):
        can, why = regenerable(app, lt)
        bundle = [lt]
        for name in SIBLING_ARTIFACTS:
            for cand in (lt.parent / name, lt.parent.parent / name):
                if cand.exists() and not git_tracked(cand):
                    bundle.append(cand)
        (ok_groups if can else bad_groups).append((bundle, why))

    print("\n【组 2 · 单列确认】可再生的重产物(gitignore;删错=重跑,不丢信息)")
    printed = False
    for item, why in ok_groups:
        for q in (item if isinstance(item, list) else [item]):
            print(f"    {q.relative_to(REPO)}  {human(du(q))}"); printed = True
        print(f"      ↳ 可再生:{why}")
    if not printed:
        print("    (无)")

    print("\n【组 2X · 降级为绝不自动删】**不可再生**的重产物(未进 git + 当前代码跑不出来 = 删了就没了)")
    printed = False
    for item, why in bad_groups:
        for q in (item if isinstance(item, list) else [item]):
            print(f"    {q.relative_to(REPO)}  {human(du(q))}"); printed = True
        print(f"      ↳ 不可再生:{why}")
    if not printed:
        print("    (无)")

    # ---- 组 3:只报不删 ----
    print("\n【组 3 · 只报不删】归属不明的长表(有 part-*.parquet、无 run_meta.json → 反查不到 app)")
    for p in find_orphan_longtables(SEARCH_ROOTS):
        print(f"    {p.relative_to(REPO)}  {human(du(p))}")

    print("\n【组 4 · 绝不自动删】研究记录 / skill 自测资产 / app 包本身")
    for p in [REPO / "path2_apps" / app, APPS_DIR.parent / "fixtures"]:
        print(f"    {p.relative_to(REPO)}  {'存在' if p.exists() else '不存在'}  ← 不在删除集")
    refs = 0
    for f in (APPS_DIR.parent / "SKILL.md", APPS_DIR.parent / "reference.md"):
        refs += f.read_text().count("apps/<app>/notes.md")
    others = [d.name for d in sorted(APPS_DIR.iterdir()) if d.is_dir() and d.name != "_template" and d.name != app]
    last = not others
    print(f"\n【删除后果一行提示】{'这是最后一个 app;' if last else f'剩余 app: {others};'}"
          f"通用区 {refs} 处指向 `apps/<app>/notes.md` 的举例将悬空")
    print(f"【收尾提醒】删除后需把 current.py 的 APP 置回 None(否则下次跑 app_setup 会 SystemExit)")
    print("\n(dry-run 结束,未删除任何东西)")


if __name__ == "__main__":
    main()
