"""命令:生成对照清单(普通 / 盲看),并自动记账、存档规则。

    uv run python -m chart_workflow.contrast --list-id <id> (--app <pid> [--params <yaml>] | --rule <path>)
        --source <来源> --change "<这一版改了什么>" [--rule-id …] [--version …] [--note …] [--blind]

内圈年份:命中先按决策日年份过滤到 contrast.inner_years(默认只有 2025,待验证),之后的统计、
三组图集、盲看抽样全部只用过滤后的命中;summary 的逐年行与毕业判定的「逐年都为正」也只看
内圈年份。同日对照仍用整张面板(只取同一天的股票日)。清单 params 记 inner_years 与过滤前后的
命中数(n_raw_hits / n_hits_inner_years / n_pool_hits)。没看过的那年留着,以后量看图挑选把成绩抬高了多少。
普通模式:summary(「全部」+ 内圈每年 + 扎堆度 + 毕业判定);分组「赢」= dir=+1 中
随机抽 n_win 个,「输」= dir=−1 中随机抽 n_lose 个,「全部命中」= 随机抽至多 max_all 个后
按日期排(seed 固定)。
盲看模式:不写 summary,也不写任何和结果有关的字段;只有「命中样例」一组,随机抽
n_blind 个;图窗截到决策日之后 view.blind_after_bars 个交易日为止。
两种模式写清单前都对每段做跨源比对(见 xcheck.py,--no-xcheck 跳过);盲看清单只记条数,
逐段结果不写进清单。

自动记账(不靠手敲):开始先找状态根(拿不到就停,什么都不生成)→ 取命中、生成清单 → 存档规则
→ 写清单 → 追加账本;追加失败就删掉刚写的清单再报错,保证不存在没记账的对照页。存档:规则文件
复制到 <状态根>/rule_archive/<sha256 前 16 位>__<文件名>(内容相同不重复写);app 方式存档参数文件
(给了 --params 时),另记 git HEAD 与 path2_apps/<app>/ 有没有未提交改动。账本 kind:--blind → blind,
source = mining → mined,其余 rule。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from chart_workflow.config import REPO_ROOT, load_config
from chart_workflow.control import Control, summarize
from chart_workflow.dataerrors import load_pool
from chart_workflow.ledger import add_round, check_source
from chart_workflow.listfile import deep_link, make_item, new_list, write_list
from chart_workflow.rules import (app_module_path, hits_from_app, hits_from_rule, join_panel,
                                  rule_fingerprint)
from chart_workflow.state import StateRootMissing, state_root
from chart_workflow.xcheck import run_xcheck


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


def inner_hits(hits: pd.DataFrame, years: list[str]) -> pd.DataFrame:
    """命中按决策日年份过滤到内圈年份。"""
    if len(hits) == 0:
        return hits
    y = pd.to_datetime(hits["date"]).dt.year.astype(str)
    return hits[y.isin(years).values].reset_index(drop=True)


def build_list(panel: pd.DataFrame, hits: pd.DataFrame, cfg: dict, list_id: str, blind: bool,
               rule_label: str, title: str | None = None, errata_info: dict | None = None) -> dict:
    """hits:(symbol, date) 命中。先按决策日年份过滤到内圈年份,再和面板连接,只留池内、
    有有效标签的股票日。panel 应已按数据错误登记排除过(load_pool),同日对照在整张面板上算。"""
    ccfg = cfg["contrast"]
    seed = int(ccfg["seed"])
    years = [str(y) for y in ccfg["inner_years"]]
    hits_in = inner_hits(hits, years)
    joined = join_panel(hits_in, panel).sort_values(["date", "symbol"]).reset_index(drop=True)
    kind = "contrast_blind" if blind else "contrast"
    doc = new_list(list_id, kind, title or (("盲看：" if blind else "对照：") + rule_label), cfg,
                   {"rule": rule_label, "inner_years": years, "n_raw_hits": int(len(hits)),
                    "n_hits_inner_years": int(len(hits_in)), "n_pool_hits": int(len(joined)),
                    **({"data_errors": errata_info} if errata_info is not None else {})})
    if blind:
        pick = _sample(joined, int(ccfg["n_blind"]), seed).sort_values(["date", "symbol"])
        doc["items"] = [make_item(r, cfg, blind=True) for _, r in pick.iterrows()]
        doc["groups"] = [{"key": "sample", "title": f"命中样例（随机 {len(pick)}）",
                          "item_ids": [it["item_id"] for it in doc["items"]]}]
        return doc

    control = Control(panel, cfg["control"])
    rows = control.rows_of(joined)
    doc["summary"] = summarize(control, rows, cfg, years=years)
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_file(src: Path, root: Path) -> tuple[str, str]:
    """把文件按内容指纹存进 <状态根>/rule_archive/<sha256 前 16 位>__<文件名>;已存在且内容相同不重复写。
    返回 (sha256, 相对状态根的存档路径)。"""
    sha = _sha256(src)
    rel = f"rule_archive/{sha[:16]}__{src.name}"
    dst = root / rel
    if dst.exists():
        if _sha256(dst) != sha:
            raise RuntimeError(f"存档 {dst} 已存在但内容不同")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        shutil.copyfile(src, tmp)
        tmp.replace(dst)
    return sha, rel


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                          check=True).stdout


def archive_rule(root: Path, rule: str | None, app: str | None, params: str | None) -> dict:
    """存档这次用的规则,返回账本字段 rule_sha / rule_archive / app_commit / app_dirty。"""
    out = {"rule_sha": None, "rule_archive": None, "app_commit": None, "app_dirty": None}
    if rule:
        out["rule_sha"], out["rule_archive"] = archive_file(Path(rule).resolve(), root)
        return out
    if params:
        out["rule_sha"], out["rule_archive"] = archive_file(Path(params).resolve(), root)
    app_dir = Path(importlib.import_module(app_module_path(app)).__file__).resolve().parent
    rel = app_dir.relative_to(REPO_ROOT)
    out["app_commit"] = _git("rev-parse", "HEAD").strip()
    out["app_dirty"] = bool(_git("status", "--porcelain", "--", f"{rel}/").strip())
    return out


def _default_version(rule: str | None, params: str | None) -> str:
    if rule:
        return rule_fingerprint(Path(rule))
    return rule_fingerprint(Path(params)) if params else "default"


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
    ap.add_argument("--source", required=True,
                    help="规则来源:annotation:<batch_id> / mining / literature / user-text / "
                         "shape:<shape_id>@v<版本>")
    ap.add_argument("--change", required=True, help="一句话说这一版改了什么")
    ap.add_argument("--rule-id", default=None, help="默认规则文件名去掉 .py,或 app:<pattern_id>")
    ap.add_argument("--version", default=None, help="默认规则文件指纹或参数文件指纹")
    ap.add_argument("--note", default="")
    ap.add_argument("--title", default=None)
    ap.add_argument("--no-xcheck", action="store_true", help="不做跨源比对(离线时用)")
    ap.add_argument("--refresh-panel", action="store_true")
    args = ap.parse_args(argv)
    if args.params and not args.app:
        ap.error("--params 只能和 --app 一起用")
    cfg = load_config()
    try:                      # 拿不到状态根就停,什么都不生成;来源不对也先停
        root = state_root()
        check_source(args.source)
    except (StateRootMissing, ValueError, FileNotFoundError) as e:
        print(f"错误:{e}", file=sys.stderr)
        sys.exit(2)
    panel, errata = load_pool(cfg, refresh=args.refresh_panel)
    symbols = sorted(panel["symbol"].unique())
    if args.rule:
        hits = hits_from_rule(args.rule, symbols, cfg)
    else:
        hits = hits_from_app(args.app, args.params, symbols, cfg)
    label = _rule_label(args.rule, args.app, args.params)
    doc = build_list(panel, hits, cfg, args.list_id, args.blind, label, args.title,
                     errata_info=errata)
    if cfg["xcheck"]["enabled"] and not args.no_xcheck:
        run_xcheck(doc, cfg)
    arch = archive_rule(root, args.rule, args.app, args.params)
    path = write_list(doc, cfg)
    kind = "blind" if args.blind else ("mined" if args.source == "mining" else "rule")
    try:
        entry = add_round(cfg, kind=kind,
                          rule_id=args.rule_id or (Path(args.rule).stem if args.rule else f"app:{args.app}"),
                          version=args.version or _default_version(args.rule, args.params),
                          source=args.source, change=args.change, list_id=args.list_id,
                          note=args.note, auto=True, years=doc["params"]["inner_years"], **arch)
    except BaseException as e:
        path.unlink(missing_ok=True)          # 不留没记账的对照页
        if isinstance(e, (ValueError, FileNotFoundError, StateRootMissing, OSError)):
            print(f"错误:账本追加失败,已删掉刚写的清单 {path.name}:{e}", file=sys.stderr)
            sys.exit(2)
        raise
    print(f"写入 {path}(账本第 {entry['round']} 轮,规则存档 {arch['rule_archive'] or '—'})")
    print(f"原始命中 {doc['params']['n_raw_hits']},内圈年份 {doc['params']['inner_years']} "
          f"{doc['params']['n_hits_inner_years']},池内有效 {doc['params']['n_pool_hits']}")
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
