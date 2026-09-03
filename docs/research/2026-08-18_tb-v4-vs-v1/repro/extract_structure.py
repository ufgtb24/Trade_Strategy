# -*- coding: utf-8 -*-
"""从两个 scan json 提取结构化 event/match 数据 → extracted.json。

v4 scan: outputs/path2_web/scans/20260818T102540.json (bottom_burst, end_node=tb.segments)
v1 scan: outputs/path2_web/scans/20260818T103730.json (bb_v1, end_node=tb)

输出(逐代):
  symbols: {sym: {
    bo:      [(iid, s, e)],
    burst:   [(iid, s, e, confirm_idx)],
    tb:      v1: [(iid, s, e, outcome)];  v4: [(iid, s, e, outcome, machine_outcome, [seg_iid])]
    tb_seg:  v4 only: {seg_iid: (s, e, outcome)},
    matches: [{match_id, burst_iid, tb_iid, fr, dd, leaf}]
  }}
窗口事实:两 scan win_start/win_end 逐字相同(2024-09-19/2026-03-08)→ 同 symbol 的
start_idx 同窗可比,无需 index 换算。
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent / "extracted.json"

SCANS = {
    "v4": (REPO / "outputs/path2_web/scans/20260818T102540.json", "bottom_burst"),
    "v1": (REPO / "outputs/path2_web/scans/20260818T103730.json", "bb_v1"),
}


def extract(scan_path: Path, pid: str, gen: str) -> dict:
    d = json.loads(scan_path.read_text())
    symbols = {}
    for r in d["results"]:
        pb = r["per_pattern"][pid]
        evs = pb["analysis"]["events"]
        by_id = {e["instance_id"]: e for e in evs}
        bo = [(e["instance_id"], e["start_idx"], e["end_idx"])
              for e in evs if e["node_id"] == "bo"]
        burst = [(e["instance_id"], e["start_idx"], e["end_idx"], e["confirm_idx"])
                 for e in evs if e["node_id"] == "burst"]
        if gen == "v4":
            tb = []
            tb_seg = {}
            for e in evs:
                if e["node_id"] != "tb":
                    continue
                seg_ids = list(e.get("child_refs", {}).get("segments", []))
                tb.append((e["instance_id"], e["start_idx"], e["end_idx"],
                           e["outcome"], e["machine_outcome"], seg_ids))
                for sid in seg_ids:
                    s = by_id.get(sid)
                    if s is not None:   # 段事件在 events 全集里
                        tb_seg[sid] = (s["start_idx"], s["end_idx"], s["outcome"])
            tb_field = tb
        else:
            tb_field = [(e["instance_id"], e["start_idx"], e["end_idx"], e["outcome"])
                        for e in evs if e["node_id"] == "tb"]
            tb_seg = {}
        matches = [{
            "match_id": m["match_id"],
            "burst_iid": m["node_index"]["burst"],
            "tb_iid": m["node_index"]["tb"],
            "fr": m["forward_return"],
            "dd": m["forward_drawdown"],
            "leaf": m["leaf"],
        } for m in pb["analysis"]["matches"]]
        symbols[r["symbol"]] = {
            "bo": bo, "burst": burst, "tb": tb_field, "tb_seg": tb_seg,
            "matches": matches,
        }
    return symbols


def main():
    out = {}
    for gen, (path, pid) in SCANS.items():
        out[gen] = extract(path, pid, gen)
        n_sym = len(out[gen])
        n_match = sum(len(v["matches"]) for v in out[gen].values())
        print(f"{gen}: symbols={n_sym} matches={n_match}")
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
