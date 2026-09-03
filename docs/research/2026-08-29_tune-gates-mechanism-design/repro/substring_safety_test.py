# -*- coding: utf-8 -*-
"""子串误伤实测:在假目录树上对比「按名字 glob」与「精确路径 + run_meta 内容反查」。
造树 → 两种发现法各跑一遍 → 打印各自会删掉什么 → 删假树。不碰真实文件。"""
from __future__ import annotations
import json, shutil, tempfile
from pathlib import Path

APP = "bb_v1"
root = Path(tempfile.mkdtemp(prefix="purge_fake_"))

# --- 造假树:三个名字相近的 app + 三个研究目录(其中一个用连字符命名) ---
for a in ("bb_v1", "bb_v10", "bb_v1_test"):
    d = root / ".claude/skills/tune-gates/apps" / a; d.mkdir(parents=True)
    (d / "study.py").write_text(f"# {a}\n")
    o = root / "outputs/tune_gates" / a; o.mkdir(parents=True)
    (o / "longtable").mkdir(); (o / "longtable/run_meta.json").write_text(json.dumps({"app": a}))
research = {
    "2026-08-25_multivar-bb_v1":  "bb_v1",     # 名字含 bb_v1,内容也是 bb_v1
    "2026-08-20_tune-bb-v1":      "bb_v1",     # 名字用连字符 bb-v1,内容是 bb_v1  ← glob 漏
    "2026-08-26_multivar-bb_v10": "bb_v10",    # 名字含 bb_v1 子串,内容是 bb_v10  ← glob 误伤
    "2026-08-27_someones-notes":  "bb_v1",     # 名字完全无关,内容是 bb_v1        ← glob 漏
}
for name, app in research.items():
    lt = root / "docs/research" / name / "longtable"; lt.mkdir(parents=True)
    (lt / "run_meta.json").write_text(json.dumps({"app": app}))
    (lt / "part-0000.parquet").write_bytes(b"x")

def by_glob(app):
    hits = sorted(p for p in (root / "docs/research").glob(f"*{app}*"))
    hits += sorted(p for p in (root / ".claude/skills/tune-gates/apps").glob(f"*{app}*"))
    hits += sorted(p for p in (root / "outputs/tune_gates").glob(f"*{app}*"))
    return hits

def by_exact(app):
    hits = []
    for base in (root / ".claude/skills/tune-gates/apps", root / "outputs/tune_gates"):
        p = base / app
        if p.exists(): hits.append(p)
    for rm in (root / "docs/research").rglob("run_meta.json"):
        if json.loads(rm.read_text()).get("app") == app:
            hits.append(rm.parent)
    return sorted(hits)

truth = {root / ".claude/skills/tune-gates/apps/bb_v1", root / "outputs/tune_gates/bb_v1"} \
      | {root / "docs/research" / n / "longtable" for n, a in research.items() if a == APP}

for name, fn in (("按名字 glob", by_glob), ("精确路径 + run_meta 内容反查", by_exact)):
    got = set(fn(APP))
    print(f"--- {name} ---")
    for p in sorted(got): print(f"    命中 {p.relative_to(root)}")
    wrong = got - truth; miss = truth - got
    print(f"    误伤 {len(wrong)}: {[str(p.relative_to(root)) for p in sorted(wrong)]}")
    print(f"    漏掉 {len(miss)}: {[str(p.relative_to(root)) for p in sorted(miss)]}\n")
shutil.rmtree(root)
print("假树已删除")
