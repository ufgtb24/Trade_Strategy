# -*- coding: utf-8 -*-
"""任务1+2:样本结构对齐 + burst 池对齐(纯 scan 侧,不读 pkl)。→ pool_report.json

口径:
- 样本单元:v4 = tb_seg 段 span 逐 bar(3027 bar);v1 = tb 事件 span 逐 bar。
  与各自 eval 口径(end_node 解析出的 event span 逐 bar)一致。
- burst 对齐键 = (symbol, burst.start_idx, burst.end_idx)(两 scan 同窗,index 可比)。
- match 级样本(评估单元):v4=184 / v1=80(scan stats.count)。
"""
import json
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
D = json.loads((HERE / "extracted.json").read_text())


def seg_bars(sym_v4):
    """v4 每 match 的段 span bar 列表(按 match 展开,含段信息)。"""
    rows = []
    for sym, v in sym_v4.items():
        for m in v["matches"]:
            tb = next(t for t in v["tb"] if t[0] == m["tb_iid"])
            segs = tb[5]
            for k, sid in enumerate(segs):
                s, e, outcome = v["tb_seg"][sid]
                rows.append({"symbol": sym, "match_id": m["match_id"],
                             "seg_iid": sid, "seg_ord": k, "n_segs": len(segs),
                             "start": s, "end": e, "outcome": outcome,
                             "burst_iid": m["burst_iid"], "fr": m["fr"]})
    return rows


def v1_bars(sym_v1):
    rows = []
    for sym, v in sym_v1.items():
        for m in v["matches"]:
            tb = next(t for t in v["tb"] if t[0] == m["tb_iid"])
            iid, s, e, outcome = tb
            rows.append({"symbol": sym, "match_id": m["match_id"], "tb_iid": iid,
                         "start": s, "end": e, "outcome": outcome,
                         "burst_iid": m["burst_iid"], "fr": m["fr"]})
    return rows


def burst_span(sym_data, iid):
    for b in sym_data["burst"]:
        if b[0] == iid:
            return (b[1], b[2])
    return None


def main():
    v4, v1 = D["v4"], D["v1"]
    rep = {}

    # ── 任务1:样本结构 ──
    v4_seg_rows = seg_bars(v4)
    v1_rows = v1_bars(v1)
    v4_bars = sum(r["end"] - r["start"] + 1 for r in v4_seg_rows)
    v1_bars_n = sum(r["end"] - r["start"] + 1 for r in v1_rows)
    rep["structure"] = {
        "v4": {"symbols": len(v4), "matches": 184, "segs": len(v4_seg_rows),
               "bars": v4_bars, "segs_per_match": len(v4_seg_rows) / 184,
               "bars_per_match": v4_bars / 184},
        "v1": {"symbols": len(v1), "matches": 80, "tb_events": len(v1_rows),
               "bars": v1_bars_n, "bars_per_match": v1_bars_n / 80},
        "burst_per_symbol_v4": None, "burst_per_symbol_v1": None,
    }

    # ── 任务2:burst 池对齐 ──
    sym4, sym1 = set(v4), set(v1)
    inter = sym4 & sym1
    rep["symbols"] = {"v4_only": sorted(sym4 - sym1), "v1_only": sorted(sym1 - sym4),
                      "both": len(inter)}

    # match 级 burst 键
    def mbursts(data):
        keys = {}
        for sym, v in data.items():
            for m in v["matches"]:
                bs = burst_span(v, m["burst_iid"])
                keys[(sym, bs)] = keys.get((sym, bs), 0) + 1
        return set(keys)

    k4, k1 = mbursts(v4), mbursts(v1)
    common = k4 & k1
    rep["burst_match_keys"] = {"v4": len(k4), "v1": len(k1), "common": len(common),
                               "v4_only": len(k4 - k1), "v1_only": len(k1 - k4),
                               "v1_only_detail": [
                                   {"symbol": s, "burst": list(b)} for s, b in sorted(k1 - k4)],
                               "v4_only_detail_n": len(k4 - k1)}

    # 事件级 burst 池(检出的 burst 事件全集,不论 match)
    def bevents(data):
        out = set()
        for sym, v in data.items():
            for b in v["burst"]:
                out.add((sym, (b[1], b[2])))
        return out

    be4, be1 = bevents(v4), bevents(v1)
    rep["burst_event_pool"] = {
        "v4_events": len(be4), "v1_events": len(be1),
        "common": len(be4 & be1), "v4_only": len(be4 - be1), "v1_only": len(be1 - be4)}

    # v1 match 的 burst 在 v4 侧状态:v4 有 tb match / v4 有 tb 容器(事件)但无 match / 无
    v4_tb_event_bursts = set()
    for sym, v in v4.items():
        for t in v["tb"]:
            m = next((mm for mm in v["matches"] if mm["tb_iid"] == t[0]), None)
            if m is not None:
                v4_tb_event_bursts.add((sym, burst_span(v, m["burst_iid"])))
    # (v4 matches 引用的 burst 就是 k4;v4 无 match 的 burst = be4 - k4 的共同部分)
    n_v1_in_v4match = sum(1 for k in k1 if k in k4)
    n_v1_not_v4 = len(k1) - n_v1_in_v4match
    rep["v1_burst_fate"] = {"v1_bursts": len(k1), "also_v4_tb_match": n_v1_in_v4match,
                            "v4_no_tb": n_v1_not_v4}

    # 反向:v4 match burst 中 v1 判死数
    n_v4_not_v1 = len(k4 - k1)
    rep["v4_burst_fate"] = {"v4_bursts": len(k4), "v1_no_tb": n_v4_not_v1}

    # 段级位置画像素材(供任务3c):v4 段距 burst 末的距离 / 段序
    for r in v4_seg_rows:
        bs = burst_span(v4[r["symbol"]], r["burst_iid"])
        r["dist_from_burst_end"] = r["start"] - bs[1]     # 段 enter 距 burst 末 bar
    for r in v1_rows:
        bs = burst_span(v1[r["symbol"]], r["burst_iid"])
        r["dist_from_burst_end"] = r["start"] - bs[1]

    # 简单分组统计
    rep["v4_seg_dist_buckets"] = dict(Counter(
        "<=20" if r["dist_from_burst_end"] <= 20 else "21-40" if r["dist_from_burst_end"] <= 40 else ">40"
        for r in v4_seg_rows))
    rep["v4_seg_ord"] = dict(Counter("first" if r["seg_ord"] == 0 else "later" for r in v4_seg_rows))
    rep["v1_dist_buckets"] = dict(Counter(
        "<=20" if r["dist_from_burst_end"] <= 20 else ">20" for r in v1_rows))

    (HERE / "pool_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    # 段/事件明细落盘供任务3/4复用
    (HERE / "v4_segs.json").write_text(json.dumps(v4_seg_rows, ensure_ascii=False))
    (HERE / "v1_tbs.json").write_text(json.dumps(v1_rows, ensure_ascii=False))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
