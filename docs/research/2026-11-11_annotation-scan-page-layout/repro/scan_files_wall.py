"""一次性核对:outputs/path2_web/scans/ 下每份扫描能不能过数据墙(网页能否打开)、扫的是哪些 pattern、多少只股票。只读。"""
import json
from pathlib import Path
from path2_web import scan as scan_mod

d = Path("outputs/path2_web/scans")
for f in sorted(d.glob("*.json")):
    data = json.loads(f.read_text())
    s = data.get("scan") or {}
    print(f.name, "| wall_ok:", scan_mod.within_data_wall(s), "| data_until:", s.get("data_until"),
          "| patterns:", data.get("pattern_ids"), "| results:", len(data.get("results") or []),
          "| range:", s.get("start_date"), "~", s.get("end_date"), "| name:", s.get("name"))
