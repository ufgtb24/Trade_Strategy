"""一次性:看唯一能打开的扫描(bo_only)里有几只股票有 hit、第一只股票的结果长什么样。只读。"""
import json
d = json.load(open("outputs/path2_web/scans/20261103T010617.json"))
print("scan keys:", sorted(d["scan"].keys()))
print("hit_stocks:", d["scan"].get("hit_stocks"), "| per_pattern keys:", list(d["per_pattern"]))
pp = d["per_pattern"]["bo_only"]
print("per_pattern bo_only keys:", sorted(pp.keys()))
print("stats:", {k: pp.get(k) for k in ("hits", "hit_stocks")})
r0 = d["results"][0]
print("first result symbol:", r0.get("symbol"), "| keys:", sorted(r0.keys()))
pr = (r0.get("per_pattern") or {}).get("bo_only") or {}
print("first result bo_only keys:", sorted(pr.keys()) if isinstance(pr, dict) else type(pr))
n_hit = sum(1 for r in d["results"] if ((r.get("per_pattern") or {}).get("bo_only") or {}).get("num"))
print("results with num>0:", n_hit)
