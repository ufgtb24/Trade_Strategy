"""min_bos 事后过滤等价性对拍(用现有 OAT scan 文件,不重扫)。

断言:min_bos=1 的 scan 里按 burst.count >= k 过滤出的 match 集合,与 min_bos=k
单独 scan 的 match 集合,在 (symbol, burst span, tb span, outcome, forward_return)
键上完全一致(instance_id 编号允许不同)。
"""
import json, collections
from pathlib import Path


def main():
    SCAN_DIR = Path("outputs/path2_web/scans")
    FILES = {k: SCAN_DIR / f"tune-burst-min_bos-{k}-buf250.json" for k in (1, 2, 3, 4)}
    PID = "bb_v1"

    blobs = {k: json.load(open(p)) for k, p in FILES.items()}
    # 参数快照只差 min_bos
    snaps = {k: b["per_pattern"][PID]["params_snapshot"] for k, b in blobs.items()}
    for k in (2, 3, 4):
        diff = [(sec, f) for sec in snaps[1] for f in snaps[1][sec]
                if snaps[1][sec][f] != snaps[k][sec].get(f)]
        print(f"snapshot diff 1 vs {k}: {diff}")

    def keyset(blob, min_count):
        keys = set(); ids = []
        for r in blob["results"]:
            pr = (r.get("per_pattern") or {}).get(PID)
            if not pr: continue
            ev_by_id = {e["instance_id"]: e for e in pr["analysis"]["events"]}
            for m in pr["analysis"]["matches"]:
                ni = m["node_index"]
                burst = ev_by_id[ni["burst"]]; tb = ev_by_id[ni["tb"]]
                if burst["count"] < min_count: continue
                keys.add((r["symbol"], burst["start_idx"], burst["end_idx"],
                          tb["start_idx"], tb["end_idx"], tb["outcome"],
                          None if m["forward_return"] is None else round(m["forward_return"], 12)))
                ids.append((r["symbol"], ni["burst"], ni["tb"]))
        return keys, ids

    for k in (2, 3, 4):
        a, ids_a = keyset(blobs[1], k)
        b, ids_b = keyset(blobs[k], 1)
        print(f"k={k}: filtered(min_bos=1)={len(a)}  direct(min_bos={k})={len(b)}  "
              f"onlyA={len(a-b)} onlyB={len(b-a)}  instance_id sets equal={set(ids_a)==set(ids_b)}")
        for x in list(a - b)[:3]: print("   onlyA", x)
        for x in list(b - a)[:3]: print("   onlyB", x)


if __name__ == "__main__":
    main()
