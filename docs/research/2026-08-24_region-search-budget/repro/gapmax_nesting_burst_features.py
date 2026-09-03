"""gap_max 相邻档位:tb 买点窗相同的 match,其所属 burst 与 where 特征是否也相同?
(判断 gap_max 能否像 min_bos 一样事后切:tb 嵌套 ≠ 可事后切,因为可切闸吃的是 burst 特征)
"""
import json
from pathlib import Path


def main():
    SCAN_DIR = Path("outputs/path2_web/scans")
    PID = "bb_v1"
    PAIRS = [("tune-burst-gap_max-4-buf250", "tune-burst-gap_max-8-buf250"),
             ("tune-burst-gap_max-8-buf250", "tune-burst-gap_max-12-buf250")]
    FEATS = ("first_drought", "distinct_pk", "max_bar_vol_ratio", "peak_age_max", "count")

    def table(name):
        b = json.load(open(SCAN_DIR / f"{name}.json"))
        out = {}
        for r in b["results"]:
            pr = (r.get("per_pattern") or {}).get(PID)
            if not pr: continue
            ev = {e["instance_id"]: e for e in pr["analysis"]["events"]}
            for m in pr["analysis"]["matches"]:
                tb = ev[m["node_index"]["tb"]]; bu = ev[m["node_index"]["burst"]]
                k = (r["symbol"], tb["start_idx"], tb["end_idx"])
                out.setdefault(k, []).append(((bu["start_idx"], bu["end_idx"]),
                                              tuple(bu[f] for f in FEATS), m["forward_return"]))
        return out

    for a, b in PAIRS:
        ta, tb_ = table(a), table(b)
        shared = set(ta) & set(tb_)
        same_burst = same_feats = same_fr = 0
        for k in shared:
            sa = {x[0] for x in ta[k]}; sb = {x[0] for x in tb_[k]}
            if sa & sb: same_burst += 1
            fa = {x[1] for x in ta[k]}; fb = {x[1] for x in tb_[k]}
            if fa & fb: same_feats += 1
            if {x[2] for x in ta[k]} & {x[2] for x in tb_[k]}: same_fr += 1
        n = len(shared)
        print(f"{a[-12:]} vs {b[-13:]}: shared tb keys={n}  same burst span={same_burst} ({same_burst/n:.1%})  "
              f"same where-feats={same_feats} ({same_feats/n:.1%})  same forward_return={same_fr} ({same_fr/n:.1%})")


if __name__ == "__main__":
    main()
