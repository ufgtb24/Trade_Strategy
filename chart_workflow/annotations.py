"""标注批次的读取:v1 / v2 两种格式统一读成 v2 形状,给数据错误登记、事实脚本、形态卡待处理队列共用。

批次文件 <状态根>/annotations/<batch_id>.json 由 path2_web 后端写入。
  v1(chart_workflow.annotations/1):每条标注一个 buy_date(可空),range_start / range_end 必填,
      批次头没有 list_kind / outcome_visible。
  v2(chart_workflow.annotations/2):每条标注 buy_points = [{"date", "primary"}](至多一个主买点),
      框选起止可空(「数据有误」除外),peeked_before_buy;大涨段清单的改点痕迹 first_buy_points
      (第一次露出结果时的买点,null = 没露出过)与 changed_after_reveal(露出结果后买点改过或清除过);
      批次头有 list_kind 与 outcome_visible(后端按清单文件的 kind 填:盲看清单 false,其余 true)。
      大涨段标注还有 outcome_seen_elsewhere(后端填:决策日之后的走势在第一次露出结果之前是否已经在别处
      露出过,{"level": "careful | in_list" | null, "before", "careful": [出处], "in_list": [出处]},
      见 views.outcome_trail;以哪一级为准由流程骨架定),别的清单种类为 null。
读 v1 时:buy_date 视为一个主买点,outcome_visible 视为 true,list_kind 为 null,peeked_before_buy 为 false。
没有改点痕迹字段的(v1 与早期 v2):first_buy_points 为 null,changed_after_reveal 为 false;
没有 outcome_seen_elsewhere 的为 null(没查过,不等于没露出过)。
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_V1 = "chart_workflow.annotations/1"
SCHEMA_V2 = "chart_workflow.annotations/2"


def _norm_v1(a: dict) -> dict:
    bd = a.get("buy_date")
    return {"ann_id": a.get("ann_id"), "item_id": a.get("item_id"), "symbol": a.get("symbol"),
            "range_start": a.get("range_start"), "range_end": a.get("range_end"),
            "buy_points": [{"date": bd, "primary": True}] if bd else [],
            "label": a.get("label"), "note": a.get("note", ""), "peeked_before_buy": False,
            "first_buy_points": None, "changed_after_reveal": False, "outcome_seen_elsewhere": None,
            "updated_at": a.get("updated_at")}


def _norm_v2(a: dict) -> dict:
    bps = a.get("buy_points") or []
    if not isinstance(bps, list) or not all(isinstance(b, dict) and isinstance(b.get("date"), str)
                                            for b in bps):
        raise ValueError(f"buy_points 格式不对: {a.get('ann_id')}")
    first = a.get("first_buy_points")
    if first is not None and not (isinstance(first, list) and all(
            isinstance(b, dict) and isinstance(b.get("date"), str) for b in first)):
        raise ValueError(f"first_buy_points 格式不对: {a.get('ann_id')}")
    return {"ann_id": a.get("ann_id"), "item_id": a.get("item_id"), "symbol": a.get("symbol"),
            "range_start": a.get("range_start"), "range_end": a.get("range_end"),
            "buy_points": [{"date": b["date"], "primary": bool(b.get("primary"))} for b in bps],
            "label": a.get("label"), "note": a.get("note", ""),
            "peeked_before_buy": bool(a.get("peeked_before_buy", False)),
            "first_buy_points": None if first is None else
            [{"date": b["date"], "primary": bool(b.get("primary"))} for b in first],
            "changed_after_reveal": bool(a.get("changed_after_reveal", False)),
            "outcome_seen_elsewhere": a.get("outcome_seen_elsewhere"),
            "updated_at": a.get("updated_at")}


def read_batch(path) -> dict:
    """读一个批次文件,返回 v2 形状(另带 source_schema 记原格式)。格式不对 → ValueError。"""
    path = Path(path)
    try:
        doc = json.loads(path.read_text())
    except OSError as e:
        raise FileNotFoundError(f"标注批次读不了: {path}({e})") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("annotations"), list):
        raise ValueError(f"标注批次格式不对: {path.name}")
    schema = doc.get("schema", SCHEMA_V1)
    if schema == SCHEMA_V1:
        anns = [_norm_v1(a) for a in doc["annotations"] if isinstance(a, dict)]
        list_kind, visible = None, True
    elif schema == SCHEMA_V2:
        anns = [_norm_v2(a) for a in doc["annotations"] if isinstance(a, dict)]
        list_kind, visible = doc.get("list_kind"), bool(doc.get("outcome_visible", True))
    else:
        raise ValueError(f"不认识的标注批次格式 {schema!r}: {path.name}")
    return {"schema": SCHEMA_V2, "source_schema": schema,
            "batch_id": doc.get("batch_id", path.stem), "created_at": doc.get("created_at"),
            "list_id": doc.get("list_id"), "list_kind": list_kind, "outcome_visible": visible,
            "train_end": doc.get("train_end"), "annotations": anns}


def iter_batches(ann_dir) -> list[tuple[Path, dict | None, str | None]]:
    """按文件名顺序读目录里全部批次:[(路径, v2 形状 或 None, 读不了时的原因)]。"""
    ann_dir = Path(ann_dir)
    out = []
    for p in sorted(ann_dir.glob("*.json")) if ann_dir.exists() else []:
        try:
            out.append((p, read_batch(p), None))
        except (ValueError, FileNotFoundError) as e:
            out.append((p, None, str(e)))
    return out
