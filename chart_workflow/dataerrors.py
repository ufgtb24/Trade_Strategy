"""数据错误登记:用户核对后(跨源比对会在图头提示两份数据不一致的日子),把行情有误的段标成「数据有误」,
这里把它们汇总成登记,并从股票池面板里排除受影响的股票日。

工具在生成任何清单、计算任何统计之前都走 `load_pool()`:先重读 <root>/annotations/
下全部标注批次,把 label = "data_error" 的标注汇总写成 <root>/data_errors.json,
再从池内面板里排除受影响的股票日。大涨段、对照清单、同日对照与各项统计用的都是排除后的面板。

排除规则(待验证):对每条登记(股票 S,框选范围 [a, b]),S 的决策日 t 的数据窗口
[t 往前 lookback_bars 个交易日, t+H](面板的 win_start / win_end 两列)只要和 [a, b]
有重叠(win_start ≤ b 且 win_end ≥ a),这个股票日就排除。

登记文件 <root>/data_errors.json(每次重建,手改会被覆盖;要撤销某条登记,改动或删掉
对应的标注批次文件):
{
  "schema": "chart_workflow.data_errors/1",
  "built_at": "YYYY-MM-DDTHH:MM:SS",          # 本次重建时间(本地时间)
  "lookback_bars": 20, "H": 40,               # 本次排除用的窗口参数
  "n_batches": 3,                             # 读到的标注批次文件数(格式坏的不算)
  "skipped_files": ["xxx.json"],              # 读不了而跳过的文件名
  "n_entries": 2,                             # 登记条数(同股同范围合并后)
  "entries": [
    {"symbol": "SMX", "range_start": "2025-11-14", "range_end": "2025-11-20",
     "sources": [                             # 哪些标注提出了这一条(同股同范围合并)
       {"batch_id": "20261008T101500", "list_id": "r002-bigmoves", "item_id": "SMX@2025-11-03",
        "ann_id": "uuid4", "note": "复权有误", "updated_at": "2026-10-08T10:14:02"}]}
  ]
}
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from chart_workflow.config import root_dir
from chart_workflow.panel import build_panel

SCHEMA = "chart_workflow.data_errors/1"
DATA_ERROR_LABEL = "data_error"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def registry_path(cfg: dict) -> Path:
    return root_dir(cfg) / "data_errors.json"


def build_registry(cfg: dict) -> dict:
    """读全部标注批次,汇总「数据有误」标注(同股同范围合并)。不写文件。"""
    ann_dir = root_dir(cfg) / "annotations"
    entries: dict[tuple, dict] = {}
    skipped: list[str] = []
    n_batches = 0
    for p in sorted(ann_dir.glob("*.json")) if ann_dir.exists() else []:
        try:
            doc = json.loads(p.read_text())
            anns = doc["annotations"]
            if not isinstance(anns, list):
                raise ValueError("annotations 不是列表")
        except (OSError, ValueError, KeyError, TypeError):
            skipped.append(p.name)
            continue
        n_batches += 1
        for a in anns:
            if not isinstance(a, dict) or a.get("label") != DATA_ERROR_LABEL:
                continue
            sym, s, e = a.get("symbol"), a.get("range_start"), a.get("range_end")
            if not (isinstance(sym, str) and isinstance(s, str) and isinstance(e, str)
                    and _DATE_RE.match(s) and _DATE_RE.match(e) and s <= e):
                skipped.append(f"{p.name}:{a.get('ann_id')}")
                continue
            ent = entries.setdefault((sym, s, e), {"symbol": sym, "range_start": s,
                                                   "range_end": e, "sources": []})
            ent["sources"].append({
                "batch_id": doc.get("batch_id", p.stem), "list_id": doc.get("list_id"),
                "item_id": a.get("item_id"), "ann_id": a.get("ann_id"),
                "note": a.get("note", ""), "updated_at": a.get("updated_at"),
            })
    ordered = [entries[k] for k in sorted(entries)]
    return {
        "schema": SCHEMA,
        "built_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "lookback_bars": int(cfg["data_errors"]["lookback_bars"]),
        "H": int(cfg["H"]),
        "n_batches": n_batches,
        "skipped_files": skipped,
        "n_entries": len(ordered),
        "entries": ordered,
    }


def write_registry(reg: dict, cfg: dict) -> Path:
    path = registry_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    tmp.replace(path)
    return path


def excluded_mask(panel: pd.DataFrame, entries: list[dict]) -> np.ndarray:
    """面板里哪些行要排除:同股且数据窗口 [win_start, win_end] 与登记范围有重叠。"""
    mask = np.zeros(len(panel), dtype=bool)
    if not entries or len(panel) == 0:
        return mask
    sym = panel["symbol"].values
    ws = pd.to_datetime(panel["win_start"]).values
    we = pd.to_datetime(panel["win_end"]).values
    for e in entries:
        a = np.datetime64(pd.Timestamp(e["range_start"]))
        b = np.datetime64(pd.Timestamp(e["range_end"]))
        mask |= (sym == e["symbol"]) & (ws <= b) & (we >= a)
    return mask


def apply_registry(panel: pd.DataFrame, reg: dict) -> tuple[pd.DataFrame, int]:
    """返回 (排除后的面板, 排除的股票日数)。"""
    m = excluded_mask(panel, reg["entries"])
    return panel[~m].reset_index(drop=True), int(m.sum())


def load_pool(cfg: dict, refresh: bool = False, verbose: bool = True
              ) -> tuple[pd.DataFrame, dict]:
    """清单与统计的统一入口:重建并写出数据错误登记 → 取池内面板 → 排除受影响的股票日。

    返回 (面板, 登记摘要 {n_entries, n_excluded_rows, built_at, registry})。
    """
    reg = build_registry(cfg)
    path = write_registry(reg, cfg)
    panel = build_panel(cfg, refresh=refresh, verbose=verbose)
    panel, n_ex = apply_registry(panel, reg)
    if verbose:
        print(f"[data_errors] 登记 {reg['n_entries']} 条 → 排除 {n_ex} 个股票日({path})")
        if reg["skipped_files"]:
            print(f"[data_errors] 警告:跳过读不了的标注 {reg['skipped_files'][:10]}",
                  file=sys.stderr)
    info = {"n_entries": reg["n_entries"], "n_excluded_rows": n_ex,
            "built_at": reg["built_at"], "registry": path.name}
    return panel, info
