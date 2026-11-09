"""实验：改样本的 judgment / 挪 pattern / 改 pattern 定义之后，read_annotations 能看出「改之前是什么」吗？

在一个临时标注目录里（不碰用户的 annotations/）造一批：建 pattern、框、样本 → 改判 → 挪 pattern → 改 pattern 定义
→ 删样本。然后只经 read_annotations 读，看状态里留下了什么；再列出目录里的批次文件，说明历史只在文件里。
运行：uv run python docs/research/2026-11-09_feedback-scope-annotation-edits/repro/history_visibility.py
"""
import json
import tempfile
from pathlib import Path

from path2_web.config import load_config
from path2_web.annotation.store import append_batch, read_annotations

with tempfile.TemporaryDirectory() as d:
    cfg = {**load_config(), "annotation_dir": d, "machine": "pc"}
    r = read_annotations(cfg)
    n = r["next_seq"]
    b, s = f"b-pc-{n}", f"s-pc-{n + 1}"
    append_batch(cfg, [
        {"kind": "pattern", "id": "P1", "base": None, "value": {"name": "P1", "definition": "原定义"}},
        {"kind": "box", "id": b, "base": None,
         "value": {"id": b, "symbol": "CRNC", "feature": None, "start": "2024-11-01", "end": "2024-11-20"}},
        {"kind": "sample", "id": s, "base": None,
         "value": {"id": s, "symbol": "CRNC", "date": "2024-11-29", "pattern": "P1", "judgment": "pos", "members": [b]}},
    ])

    def cur(kind, oid):
        rr = read_annotations(cfg)
        return rr, rr["revs"][kind].get(oid)

    def sample_value(rr):
        for ch in rr["state"]["charts"]:
            for x in ch["samples"]:
                if x["id"] == s:
                    return {**x, "symbol": ch["symbol"]}
        return None

    # 1) 改判 pos -> neg（成员不变）
    rr, base = cur("sample", s)
    v = sample_value(rr)
    append_batch(cfg, [{"kind": "sample", "id": s, "base": base, "value": {**v, "judgment": "neg"}}])
    # 2) 挪到另一个 pattern（同批新建 P2）
    rr, base = cur("sample", s)
    v = sample_value(rr)
    append_batch(cfg, [{"kind": "pattern", "id": "P2", "base": None, "value": {"name": "P2"}},
                       {"kind": "sample", "id": s, "base": base, "value": {**v, "pattern": "P2"}}])
    # 3) 改 P1 的定义
    rr, base = cur("pattern", "P1")
    append_batch(cfg, [{"kind": "pattern", "id": "P1", "base": base, "value": {"name": "P1", "definition": "新定义"}}])

    rr = read_annotations(cfg)
    print("== read_annotations 给出的样本 ==")
    print(sample_value(rr))
    print("== patterns ==", rr["state"]["patterns"])
    print("== revs（只有最后一次修改的引用）==", rr["revs"]["sample"].get(s), rr["revs"]["pattern"])
    print("== 读结果的顶层键 ==", sorted(rr))
    # 4) 删 P1：pattern 能不能删？（界面没有入口；存储层 value=null 是否放行）
    rr, base = cur("pattern", "P1")
    try:
        append_batch(cfg, [{"kind": "pattern", "id": "P1", "base": base, "value": None}])
        print("== 存储层放行删除 pattern P1；删后 patterns ==", read_annotations(cfg)["state"]["patterns"])
    except Exception as e:  # noqa: BLE001
        print("== 删除 pattern 被拒 ==", e)
    # 5) 样本挂到一个不存在的 pattern 名？
    rr, base = cur("sample", s)
    v = sample_value(rr)
    try:
        append_batch(cfg, [{"kind": "sample", "id": s, "base": base, "value": {**v, "pattern": "不存在的P"}}])
        print("== 存储层放行挂到不存在的 pattern ==", sample_value(read_annotations(cfg))["pattern"])
    except Exception as e:  # noqa: BLE001
        print("== 挂到不存在的 pattern 被拒 ==", e)
    # 6) 已有定义的特征改定义：存储层拦不拦？
    n = read_annotations(cfg)["next_seq"]
    w = f"w-pc-{n}"
    append_batch(cfg, [{"kind": "feature", "id": w, "base": None, "value": {"id": w, "name": "X", "definition": "旧意思"}}])
    base = read_annotations(cfg)["revs"]["feature"][w]
    try:
        append_batch(cfg, [{"kind": "feature", "id": w, "base": base, "value": {"id": w, "name": "X", "definition": "新意思"}}])
        print("== 存储层放行改特征定义 ==", [f for f in read_annotations(cfg)["state"]["features"] if f["id"] == w])
    except Exception as e:  # noqa: BLE001
        print("== 改特征定义被拒 ==", e)

    print("== 批次文件里的历史（文件本身保留全部旧值）==")
    for p in sorted(Path(d).glob("*.json")):
        for op in json.loads(p.read_text())["ops"]:
            if op["kind"] in ("sample", "pattern"):
                val = op["value"]
                short = None if val is None else {k: val.get(k) for k in ("judgment", "pattern", "definition", "name") if k in val}
                print(p.name, op["kind"], op["id"], short)
