"""命令:生成大涨段清单。

    uv run python -m chart_workflow.bigmoves --list-id r001-bigmoves [--top 300] [--change "…"]

步骤(阈值都在 config 的 bigmoves 子树,全部待验证):
  0. 看图下界:只取决策日不早于「看图下界 view_floor 之后第 floor_context_bars 个交易日」的
     股票日(按该股自己的交易日算),保证图上留出涨前形态;图窗起点也截到下界(listfile.make_item)。
     --view-floor 可覆盖配置(传 none 关掉,仅供测试)
  1. 候选:面板里每个股票日都是候选,指标是相对涨幅 rel 与涨幅原值 rise
  2. 最低门槛:rel ≥ rel_min
  3. 同一段行情只取一次:每只股票按 rel 从大到小贪心取,取中一个就压掉它前后
     suppress_bars 个交易日内的其他候选
  4. 每周限量:同一 ISO 周最多保留 per_week_max 段(取 rel 最大的)
  5. 总量:全局按 rel 降序取前 top 段
  6. 分组:按涨前状态分四组,另加不分组的「全部」;跳空与量倍数写进 tags

面板先按数据错误登记排除过(见 dataerrors.py);每段带的「最大单日跳变」只作显示,不参与任何判定。
写清单前对每段做跨源比对(见 xcheck.py,--no-xcheck 跳过),只标出不一致,不排除任何段。
生成后自动追加一行账本(kind = source = bigmoves,不算尝试;change 取 --change,默认「生成大涨段清单」)。
开始先找状态根,拿不到就停;追加账本失败就删掉刚写的清单再报错。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

import numpy as np
import pandas as pd

from chart_workflow.config import load_config
from chart_workflow.dataerrors import load_pool
from chart_workflow.features import PRE_STATES
from chart_workflow.ledger import add_round
from chart_workflow.listfile import deep_link, make_item, new_list, write_list
from chart_workflow.loader import trading_dates
from chart_workflow.state import StateRootMissing, state_root
from chart_workflow.xcheck import run_xcheck

GROUP_KEYS = {"深跌": "deep_drop", "已在涨": "rising", "横盘": "flat", "其他": "other"}


def suppress_same_move(cands: pd.DataFrame, bars: int) -> pd.DataFrame:
    """每只股票按 rel 降序贪心:取中一个后,压掉 |bar_idx 差| ≤ bars 的其他候选。"""
    keep = []
    for _, g in cands.groupby("symbol", sort=False):
        g = g.sort_values(["rel", "date"], ascending=[False, True])
        taken: list[int] = []
        for idx, b in zip(g.index, g["bar_idx"].values):
            if all(abs(int(b) - t) > bars for t in taken):
                taken.append(int(b))
                keep.append(idx)
    return cands.loc[keep]


def cap_per_week(df: pd.DataFrame, per_week: int) -> pd.DataFrame:
    iso = pd.DatetimeIndex(df["date"]).isocalendar()
    wk = (iso["year"].astype(str) + "-" + iso["week"].astype(str)).values
    df = df.assign(_wk=wk).sort_values(["rel", "date", "symbol"], ascending=[False, True, True])
    return df.groupby("_wk", sort=False).head(per_week).drop(columns="_wk")


def after_view_floor(panel: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """只留决策日不早于「view_floor 之后第 floor_context_bars 个交易日」的行(按各股自己的交易日)。
    view_floor 为空时原样返回。"""
    floor = cfg.get("view_floor")
    if not floor or len(panel) == 0:
        return panel
    n = int(cfg["bigmoves"]["floor_context_bars"])
    keep = np.zeros(len(panel), dtype=bool)
    dates_col = pd.to_datetime(panel["date"]).values
    for sym, idx in panel.groupby("symbol", sort=False).indices.items():
        dates = trading_dates(cfg, sym)
        after = dates[dates >= pd.Timestamp(floor)]
        if len(after) > n:
            keep[idx] = dates_col[idx] >= after[n].to_datetime64()
    return panel[keep]


def select_bigmoves(panel: pd.DataFrame, bcfg: dict, top: int) -> pd.DataFrame:
    cands = panel[np.isfinite(panel["rel"]) & (panel["rel"] >= bcfg["rel_min"])]
    picked = suppress_same_move(cands, int(bcfg["suppress_bars"]))
    picked = cap_per_week(picked, int(bcfg["per_week_max"]))
    return (picked.sort_values(["rel", "date", "symbol"], ascending=[False, True, True])
            .head(top).reset_index(drop=True))


def build_list(panel: pd.DataFrame, cfg: dict, list_id: str, top: int, title: str | None = None,
               errata_info: dict | None = None) -> dict:
    sel = select_bigmoves(after_view_floor(panel, cfg), cfg["bigmoves"], top)
    extra = {"bigmoves": {**cfg["bigmoves"], "top": top}}
    if errata_info is not None:
        extra["data_errors"] = errata_info
    doc = new_list(list_id, "bigmoves", title or f"大涨段（前 {len(sel)} 段）", cfg, extra)
    items = [make_item(r, cfg) for _, r in sel.iterrows()]
    doc["items"] = items
    ids = [it["item_id"] for it in items]
    doc["groups"] = [{"key": "all", "title": f"全部（{len(ids)}）", "item_ids": ids}]
    for state in PRE_STATES:
        g_ids = [it["item_id"] for it, st in zip(items, sel["pre_state"].values) if st == state]
        doc["groups"].append({"key": GROUP_KEYS[state], "title": f"{state}（{len(g_ids)}）",
                              "item_ids": g_ids})
    return doc


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="生成大涨段清单")
    ap.add_argument("--list-id", required=True)
    ap.add_argument("--top", type=int, default=None, help="总量,默认取 config bigmoves.top")
    ap.add_argument("--title", default=None)
    ap.add_argument("--no-xcheck", action="store_true", help="不做跨源比对(离线时用)")
    ap.add_argument("--refresh-panel", action="store_true", help="忽略面板缓存重算")
    ap.add_argument("--view-floor", default=None,
                    help="覆盖看图下界(YYYY-MM-DD;none = 关掉,仅供测试)")
    ap.add_argument("--change", default="生成大涨段清单", help="账本里这一轮写什么")
    args = ap.parse_args(argv)
    cfg = load_config()
    if args.view_floor is not None:
        cfg["view_floor"] = None if args.view_floor.lower() == "none" else args.view_floor
    try:
        state_root()                          # 拿不到状态根就停,什么都不生成
    except StateRootMissing as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    top = args.top if args.top is not None else int(cfg["bigmoves"]["top"])
    panel, errata = load_pool(cfg, refresh=args.refresh_panel)
    doc = build_list(panel, cfg, args.list_id, top, args.title, errata_info=errata)
    if cfg["xcheck"]["enabled"] and not args.no_xcheck:
        run_xcheck(doc, cfg)
    path = write_list(doc, cfg)
    version = hashlib.sha256(json.dumps({"bigmoves": doc["params"]["bigmoves"],
                                         "view_floor": cfg.get("view_floor")},
                                        sort_keys=True).encode()).hexdigest()[:10]
    try:
        entry = add_round(cfg, kind="bigmoves", rule_id="bigmoves", version=version,
                          source="bigmoves", change=args.change, list_id=args.list_id, auto=True)
    except BaseException as e:
        path.unlink(missing_ok=True)          # 不留没记账的清单
        if isinstance(e, (ValueError, FileNotFoundError, StateRootMissing, OSError)):
            print(f"错误:账本追加失败,已删掉刚写的清单 {path.name}:{e}", file=sys.stderr)
            sys.exit(2)
        raise
    print(f"写入 {path}(账本第 {entry['round']} 轮,大涨段轮不算尝试)")
    for g in doc["groups"]:
        print(f"  {g['title']}")
    if doc["items"]:
        it = doc["items"][0]
        print("样例:", it["item_id"], "rel", it["metrics"]["rel"], "rise", it["metrics"]["rise"],
              "图窗", it["view_start"], "→", it["view_end"], "tags", it["tags"])
    print("打开:", deep_link(args.list_id))


if __name__ == "__main__":
    main()
