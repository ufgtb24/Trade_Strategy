"""命令:生成大涨段清单。

    uv run python -m chart_workflow.bigmoves --list-id r001-bigmoves [--top 300]

步骤(阈值都在 config 的 bigmoves 子树,全部待验证):
  1. 候选:面板里每个股票日都是候选,指标是相对涨幅 rel 与涨幅原值 rise
  2. 最低门槛:rel ≥ rel_min
  3. 同一段行情只取一次:每只股票按 rel 从大到小贪心取,取中一个就压掉它前后
     suppress_bars 个交易日内的其他候选(疑似数据出错的段也参与,同一段行情不会
     一半进「待核对」、一半进正常排名)
  4. 疑似数据出错的段单独放进「待核对」组,不参加后面的限量与排序,按涨幅原值降序列出。
     判据(满足任一条):rise > anomaly.rise_max;或从决策日前 anomaly.lookback_bars 个
     交易日到观察窗结束,某天收盘 / 前日收盘 > anomaly.jump_max 或 < 1/anomaly.jump_max
  5. 每周限量:同一 ISO 周最多保留 per_week_max 段(取 rel 最大的)
  6. 总量:全局按 rel 降序取前 top 段
  7. 分组:按涨前状态分四组,另加不分组的「全部」和「待核对」;跳空与量倍数写进 tags,
     待核对的段另加注明触发了哪条判据的 tag
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from chart_workflow.config import load_config
from chart_workflow.features import PRE_STATES
from chart_workflow.listfile import deep_link, make_item, new_list, write_list
from chart_workflow.panel import build_panel

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


def anomaly_reasons(row, acfg: dict) -> list[str]:
    """一段大涨触发了哪几条「疑似数据出错」判据(空 = 正常)。"""
    out = []
    if np.isfinite(row["rise"]) and row["rise"] > acfg["rise_max"]:
        out.append(f"疑似：涨幅超{1 + acfg['rise_max']:g}倍")
    if np.isfinite(row["max_jump"]) and row["max_jump"] > acfg["jump_max"]:
        out.append(f"疑似：单日跳变超{acfg['jump_max']:g}倍")
    return out


def is_anomaly(df: pd.DataFrame, acfg: dict) -> np.ndarray:
    return ((df["rise"] > acfg["rise_max"]) | (df["max_jump"] > acfg["jump_max"])).values


def select_bigmoves(panel: pd.DataFrame, bcfg: dict, top: int
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (正常段, 待核对段)。正常段按 rel 降序取前 top;待核对段不限量,按 rise 降序。"""
    cands = panel[np.isfinite(panel["rel"]) & (panel["rel"] >= bcfg["rel_min"])]
    picked = suppress_same_move(cands, int(bcfg["suppress_bars"]))
    bad = is_anomaly(picked, bcfg["anomaly"])
    review = (picked[bad].sort_values(["rise", "date", "symbol"], ascending=[False, True, True])
              .reset_index(drop=True))
    main = cap_per_week(picked[~bad], int(bcfg["per_week_max"]))
    main = (main.sort_values(["rel", "date", "symbol"], ascending=[False, True, True])
            .head(top).reset_index(drop=True))
    return main, review


def build_list(panel: pd.DataFrame, cfg: dict, list_id: str, top: int, title: str | None = None
               ) -> dict:
    acfg = cfg["bigmoves"]["anomaly"]
    sel, review = select_bigmoves(panel, cfg["bigmoves"], top)
    doc = new_list(list_id, "bigmoves", title or f"大涨段（前 {len(sel)} 段）", cfg,
                   {"bigmoves": {**cfg["bigmoves"], "top": top}})
    items = [make_item(r, cfg) for _, r in sel.iterrows()]
    review_items = []
    for _, r in review.iterrows():
        it = make_item(r, cfg)
        it["tags"] = it["tags"] + anomaly_reasons(r, acfg)
        review_items.append(it)
    doc["items"] = items + review_items
    ids = [it["item_id"] for it in items]
    doc["groups"] = [{"key": "all", "title": f"全部（{len(ids)}）", "item_ids": ids}]
    for state in PRE_STATES:
        g_ids = [it["item_id"] for it, st in zip(items, sel["pre_state"].values) if st == state]
        doc["groups"].append({"key": GROUP_KEYS[state], "title": f"{state}（{len(g_ids)}）",
                              "item_ids": g_ids})
    doc["groups"].append({"key": "review", "title": f"待核对（{len(review_items)}）",
                          "item_ids": [it["item_id"] for it in review_items]})
    return doc


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="生成大涨段清单")
    ap.add_argument("--list-id", required=True)
    ap.add_argument("--top", type=int, default=None, help="总量,默认取 config bigmoves.top")
    ap.add_argument("--title", default=None)
    ap.add_argument("--refresh-panel", action="store_true", help="忽略面板缓存重算")
    args = ap.parse_args(argv)
    cfg = load_config()
    top = args.top if args.top is not None else int(cfg["bigmoves"]["top"])
    panel = build_panel(cfg, refresh=args.refresh_panel)
    doc = build_list(panel, cfg, args.list_id, top, args.title)
    path = write_list(doc, cfg)
    print(f"写入 {path}")
    for g in doc["groups"]:
        print(f"  {g['title']}")
    if doc["items"]:
        it = doc["items"][0]
        print("样例:", it["item_id"], "rel", it["metrics"]["rel"], "rise", it["metrics"]["rise"],
              "图窗", it["view_start"], "→", it["view_end"], "tags", it["tags"])
    print("打开:", deep_link(args.list_id))


if __name__ == "__main__":
    main()
