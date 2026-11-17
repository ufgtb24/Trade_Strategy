"""票 18:用写反馈那一版 new_step(app_ver 1afa716bc5248d4b)算 4 条整族反馈当时那一族的基准 event 起止。

必须在旧版的临时 worktree 里、用那个 worktree 自己的 .venv 运行(本脚本只 import 那一版的代码):
    cd <旧版 worktree> && .venv/bin/python <本票 worktree>/.scratch/annotation-path2-implementation/evidence/18/old_reference.py <输出 json>

做法(与当前页面新建整族反馈时存 reference 同口径,只是 app 换成旧版):
- 跑 app:那一版 path2_web/app_run.py 的 run_app,全历史区间("1900-01-01" 到 TRAIN_END)、label_horizon 20、
  参数取 app 的 load_params()(同 /feedback/status 与 compare 的单股预览);行情经那一版 path2_web/data.py 读
  配置的训练段副本(view_dataset_dir),不读 datasets/pkls;
- 这一族:起点日期等于反馈 family_start 的全部 hit(同前端 stores/feedback.ts 按族起点挑 hit);
- 基准 event:hit 绑定的事件(node_index)本身及其 child 槽里的直接子段(只下一级)中 node_id 为 step 的,
  同当前 path2_web/app_run.py 的 reference_events(旧版没有这个函数,这里照抄它的取法);
- spans:这一族各 hit 的基准 event 起止换成日期,去重、按起止排序、不合并(同前端 referenceSpans)。
另记每个 hit 的买点日与这一族的买点日范围,供核对反馈的 start / end。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

import path2_web
import path2_apps.new_step.dag_spec as mod
from path2.eval import _resolve_end_events
from path2_web.app_run import run_app
from path2_web.app_version import app_ver
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import TRAIN_END
from path2_web.snapshot_fingerprint import read_fingerprint

REFERENCE = "step"     # 当前 path2_apps/new_step/mapping.yaml 声明的基准 node
FIRST_DAY = "1900-01-01"   # 全历史区间的起点,同 /feedback/status 与 compare 的单股预览
LABEL_HORIZON = 20        # 区间终点后多带的交易日数,同上
# 4 条整族反馈:股票、反馈编号、family_start(经当前代码的 read_annotations 读出,写入前会再核一次)
FEEDBACK = [
    ("CRNC", "f-pc-74", "2024-12-11"),
    ("IXHL", "f-pc-90", "2025-08-01"),
    ("LUMN", "f-pc-95", "2024-07-16"),
    ("QBTS", "f-pc-92", "2025-02-21"),
]


def reference_events(events, node: str) -> list:
    """照抄当前 path2_web/app_run.py 的 reference_events:事件本身与 child 槽里的直接子段,按对象身份去重。"""
    seen: dict = {}
    for e in events:
        if e.node_id == node:
            seen.setdefault(id(e), e)
        for slot in e.child_slots().values():
            for c in (slot if isinstance(slot, tuple) else (slot,)):
                if c.node_id == node:
                    seen.setdefault(id(c), c)
    return list(seen.values())


def main(out_path: str) -> None:
    """跑 4 只股票、取各条反馈那一族的基准 event 起止,写成 out_path(JSON)并打印。

    输出记下代码身份(旧版提交号、工作区有没有改动、app_ver)与数据身份(训练段副本的配置路径与指纹),
    不记临时 worktree 的绝对路径。"""
    repo = Path(path2_web.__file__).resolve().parents[1]
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    cfg = load_config()
    out = {"commit": commit, "worktree_dirty": dirty, "app_ver": app_ver(mod),
           "train_end": TRAIN_END, "view_dataset_dir": cfg["view_dataset_dir"],
           "data_fingerprint": read_fingerprint(view_dataset_dir(cfg)), "reference_node": REFERENCE,
           "feedback": []}
    params = mod.load_params()
    for symbol, fid, family_start in FEEDBACK:
        res, win, meta = run_app(mod, cfg, symbol, FIRST_DAY, TRAIN_END, params, LABEL_HORIZON)
        day = pd.to_datetime(win["date"]).dt.strftime("%Y-%m-%d").tolist()
        fam = [h for h in res.hits if day[h.start_idx] == family_start]
        hits, spans, buys = [], set(), set()
        for h in fam:
            refs = reference_events(h.node_index.values(), REFERENCE)
            hs = sorted({(day[e.start_idx], day[e.end_idx]) for e in refs})
            bd = sorted({d for ev in _resolve_end_events(h, meta["end_node"]) for d in day[ev.start_idx:ev.end_idx + 1]})
            hits.append({"start": day[h.start_idx], "end": day[h.end_idx], "spans": [list(s) for s in hs],
                         "buy_days": bd})
            spans.update(hs)
            buys.update(bd)
        out["feedback"].append({
            "symbol": symbol, "id": fid, "family_start": family_start, "end_node": meta["end_node"],
            "window": [meta["win_start"], meta["win_end"]], "n_hits_in_family": len(fam), "hits": hits,
            "family_buy_range": [min(buys), max(buys)] if buys else None,
            "reference": {"node": REFERENCE, "spans": [list(s) for s in sorted(spans)]},
        })
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
