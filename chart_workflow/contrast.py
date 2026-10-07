"""命令:生成对照清单(普通 / 盲看)。

    uv run python -m chart_workflow.contrast --list-id <id> (--app <pid> [--params <yaml>] | --rule <path>) [--blind]

普通模式:summary(「全部」+ 每个训练年份 + 扎堆度 + 毕业判定);分组「赢」= dir=+1 中
随机抽 n_win 个,「输」= dir=−1 中随机抽 n_lose 个,「全部命中」= 随机抽至多 max_all 个后
按日期排(seed 固定)。
盲看模式:不写 summary,也不写任何和结果有关的字段;只有「命中样例」一组,随机抽
n_blind 个;图窗截到决策日之后 view.blind_after_bars 个交易日为止。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from chart_workflow.config import REPO_ROOT, load_config
from chart_workflow.control import Control, summarize
from chart_workflow.dataerrors import load_pool
from chart_workflow.listfile import deep_link, make_item, new_list, write_list
from chart_workflow.rules import (hits_from_app, hits_from_rule, join_panel, rule_fingerprint)


def _sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if len(df) <= n:
        return df
    return df.sample(n=n, random_state=seed)


def _rule_label(rule: str | None, app: str | None, params: str | None) -> str:
    if rule:
        p = Path(rule).resolve()
        try:
            shown = str(p.relative_to(REPO_ROOT))
        except ValueError:
            shown = str(p)
        return f"{shown}@{rule_fingerprint(p)}"
    return f"app:{app}" + (f"@{Path(params).name}" if params else "")


def build_list(panel: pd.DataFrame, hits: pd.DataFrame, cfg: dict, list_id: str, blind: bool,
               rule_label: str, title: str | None = None, errata_info: dict | None = None) -> dict:
    """hits:(symbol, date) 命中。和面板连接后只留池内、有有效标签的股票日。
    panel 应已按数据错误登记排除过(load_pool),同日对照与统计都在它上面算。"""
    ccfg = cfg["contrast"]
    seed = int(ccfg["seed"])
    joined = join_panel(hits, panel).sort_values(["date", "symbol"]).reset_index(drop=True)
    kind = "contrast_blind" if blind else "contrast"
    doc = new_list(list_id, kind, title or (("盲看：" if blind else "对照：") + rule_label), cfg,
                   {"rule": rule_label, "n_raw_hits": int(len(hits)),
                    "n_pool_hits": int(len(joined)),
                    **({"data_errors": errata_info} if errata_info is not None else {})})
    if blind:
        pick = _sample(joined, int(ccfg["n_blind"]), seed).sort_values(["date", "symbol"])
        doc["items"] = [make_item(r, cfg, blind=True) for _, r in pick.iterrows()]
        doc["groups"] = [{"key": "sample", "title": f"命中样例（随机 {len(pick)}）",
                          "item_ids": [it["item_id"] for it in doc["items"]]}]
        return doc

    control = Control(panel, cfg["control"])
    rows = control.rows_of(joined)
    doc["summary"] = summarize(control, rows, cfg)
    win = _sample(joined[joined["dir"] == 1], int(ccfg["n_win"]), seed).sort_values("date")
    lose = _sample(joined[joined["dir"] == -1], int(ccfg["n_lose"]), seed).sort_values("date")
    allh = _sample(joined, int(ccfg["max_all"]), seed).sort_values(["date", "symbol"])
    items: dict[str, dict] = {}
    groups = []
    for key, title_, part in (("win", f"赢（随机 {len(win)}）", win),
                              ("lose", f"输（随机 {len(lose)}）", lose),
                              ("all", f"全部命中（{len(allh)}/{len(joined)}，按日期）", allh)):
        ids = []
        for _, r in part.iterrows():
            it = make_item(r, cfg)
            items.setdefault(it["item_id"], it)
            ids.append(it["item_id"])
        groups.append({"key": key, "title": title_, "item_ids": ids})
    doc["items"] = list(items.values())
    doc["groups"] = groups
    return doc


def _fmt(x, signed=True):
    if x is None:
        return "—"
    return f"{x:+.3f}" if signed else f"{x:.3f}"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="生成对照清单")
    ap.add_argument("--list-id", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--app", help="path2 pattern_id")
    src.add_argument("--rule", help="规则文件路径(定义 signal(df))")
    ap.add_argument("--params", help="app 方式的参数 yaml")
    ap.add_argument("--blind", action="store_true", help="盲看模式:不露任何结果")
    ap.add_argument("--title", default=None)
    ap.add_argument("--refresh-panel", action="store_true")
    args = ap.parse_args(argv)
    if args.params and not args.app:
        ap.error("--params 只能和 --app 一起用")
    cfg = load_config()
    panel, errata = load_pool(cfg, refresh=args.refresh_panel)
    symbols = sorted(panel["symbol"].unique())
    if args.rule:
        hits = hits_from_rule(args.rule, symbols, cfg)
    else:
        hits = hits_from_app(args.app, args.params, symbols, cfg)
    label = _rule_label(args.rule, args.app, args.params)
    doc = build_list(panel, hits, cfg, args.list_id, args.blind, label, args.title,
                     errata_info=errata)
    path = write_list(doc, cfg)
    print(f"写入 {path}")
    print(f"原始命中 {doc['params']['n_raw_hits']},池内有效 {doc['params']['n_pool_hits']}")
    for g in doc["groups"]:
        print(f"  {g['title']}")
    if "summary" in doc:
        print("范围   命中  股票  方向领先  偶然波动  幅度领先  偶然波动")
        for r in doc["summary"]["rows"]:
            print(f"{r['scope']:<5} {r['n_hits']:>5} {r['n_stocks']:>5}  {_fmt(r['dir_lead'])}"
                  f"    {_fmt(r['dir_noise'], False)}     {_fmt(r['mag_lead'])}"
                  f"    {_fmt(r['mag_noise'], False)}")
        g = doc["summary"]["graduation"]
        print("毕业判定:", "通过" if g["passed"] else "未通过", g["checks"])
    print("打开:", deep_link(args.list_id))


if __name__ == "__main__":
    main()
