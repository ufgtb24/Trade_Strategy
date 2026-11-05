"""票 04 冒烟：照 diagnose-event 的 SKILL.md 走一遍「某个 tb 为什么没命中」（只读 scan，不读任何行情）。
用法（worktree 根目录）：.venv/bin/python <本文件>
  步骤 1：import skill 自带的 diagnose_env，从 worktree 的 outputs/path2_web/scans 取最新 scan，打印声明；
  步骤 2：声明本来要等用户确认，这里是冒烟，只打印；
  步骤 3：看 provenance（没有 wc.json 时用 scan snapshot）；
  步骤 4：从 reference.md 原样抠出「骨架 A」的代码块执行（只填占位），所以文档里的取键写错了这里就会报错。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
SKILL = ROOT / ".claude/skills/diagnose-event"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SKILL))
from path2_diag_env import diagnose_env, format_declaration, find_latest_scan  # noqa: E402

scan_path = find_latest_scan(str(ROOT / "outputs/path2_web/scans"))
blob = json.loads(scan_path.read_text())
meta = blob["scan"]
print(f"scan 文件 {scan_path.name}；dataset_dir 末段 {Path(meta['dataset_dir']).name}；data_until {meta.get('data_until')}；"
      f"最晚买点日上限 {meta['end_date']}；pattern_ids {blob['pattern_ids']}；hit_stocks {meta['hit_stocks']}")
assert Path(meta["dataset_dir"]).name == "pkls_until_20251231" and meta["data_until"] == "2025-12-31"

PID = "bb_v1"
n_hits = {r["symbol"]: len(r["per_pattern"][PID]["analysis"]["hits"]) for r in blob["results"]}
print("各股 analysis.hits 条数", n_hits)

# 选一个「有事件、但没进任何 hit」的 tb 当诊断目标
SYM = TARGET_TB = None
for r in blob["results"]:
    an = r["per_pattern"][PID]["analysis"]
    in_hit = {iid for h in an["hits"] for iid in h["node_index"].values()}
    for e in an["events"]:
        if e["node_id"] == "tb" and e["instance_id"] not in in_hit:
            SYM, TARGET_TB = r["symbol"], e["instance_id"]
            break
    if SYM:
        break
assert SYM, "这份 scan 里每个 tb 都进了 hit，挑不出诊断目标"
print(f"诊断目标：{SYM} 的 {TARGET_TB}（在 events 里、不在任何 hit 的 node_index 里）")

print("\n--- 步骤 1-2：环境探测与声明")
env = diagnose_env(SYM, TARGET_TB)
print(format_declaration(env))
print("\n--- 步骤 3：探索态检查")
print("provenance", env["provenance"], "；含 working_copy：", "working_copy" in env["provenance"])

print("\n--- 步骤 4：reference.md 的骨架 A")
ref = (SKILL / "reference.md").read_text(encoding="utf-8")
body = ref.split("### 骨架 A:", 1)[1]
code = re.search(r"```python\n(.*?)```", body, re.S).group(1)
for old in ("an['matches']", "dropped_matches"):
    assert old not in code, f"骨架 A 还留着旧键 {old}"
code = re.sub(r"^pid = .*$", f"pid = {PID!r}", code, flags=re.M)
scope = {"SCAN_PATH": str(scan_path), "SYM": SYM, "TARGET_TB": TARGET_TB}
exec(compile(code, "reference.md:骨架A", "exec"), scope)
hits = scope["hits"]
assert isinstance(hits, list), type(hits)
print(f"骨架 A 读出 hits {len(hits)} 条、events {len(scope['events'])} 条；候选 burst {len(scope['cand'])} 个")
print("hit 的键：", sorted(hits[0])[:20] if hits else "（该股无 hit）")
print("scan 里有没有 dropped_hits 键：",
      any("dropped_hits" in r["per_pattern"][PID]["analysis"] or "dropped_hits" in r["per_pattern"][PID] for r in blob["results"]))
txt = scan_path.read_text()
print("scan 文件含旧键字样：", [k for k in ('"matches"', '"match_id"', '"match_fp_counts"') if k in txt])
