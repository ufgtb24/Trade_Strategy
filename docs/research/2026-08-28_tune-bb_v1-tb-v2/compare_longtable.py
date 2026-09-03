"""多维稳健区 v2 · 对拍端：候选长表按格谓词聚合 vs 逐格 `engine.analyze` + serialize。

用法：复制到研究目录改 main() 常量后 `uv run python <路径>/compare_longtable.py`。
（本目录原件 `LONGTABLE_DIR=None`，被 `S.require` 硬闸拒绝跑（`SystemExit`）——不会像旧版一次性
脚本那样悄悄把结果写进既有研究目录；复制到研究目录后仍需在 main() 顶部把它填成真实路径。）

**这是 reference.md §4 Step A 的可复用实现**，语义逐字沿用某次端到端实战里一份一次性单进程逐格
脚本（已产出 mismatch=0 的证据日志，作为证据不再改动；那份脚本是一次性研究产物，不在本 skill
目录内，实例与出处见 `apps/<app>/notes.md` §4）；本文件相对它有三处变化：

  1. **按股票并行**（原件单进程）。并行轴选「股票」而非「对拍格」：每个 worker 只需一只股票的
     窗口 + 它自己的长表行，而按格切分则要求每个 worker 都驻留整张长表与全部窗口。全部 plan 项
     对应的 spec 在 worker 初始化时建一次、跨该 worker 处理的所有股票复用（原件是每格建一次、
     跨股票复用，同样是 O(格数) 次 build_pattern）。耗时对照见 `apps/<app>/notes.md` §4。
  2. **`MIN_WIN_BARS` 默认对齐生产判据**（只跳空窗口），见下方常量处的注释。
  3. **零 app 字面量**:网格/where/收紧套/底座/end_node/bound 节点全部来自 apps/<app>/study.py +
     classification.json,label 口径来自长表旁的 run_meta.json(与扫描逐字同源,结构上不可能不一致);
     切面 (a) 的「固定维」推导为「只影响拓扑首 detector 节点的 D 维」并取参照格值,不再写死前两维。

**比较语义未动**：掩码谓词（F/W 维均按 classification 的字段与 op）、比较键（bound 节点 span + fr 12 位
小数 + 四态多重集 + 每股 `match_fp_counts`）、`serialize_per_pattern_result` 的全部入参与原件逐字相同。
把「按格循环 → 内层按股」换成「按股并行 → 内层按格」不改变任何一次比较的内容：所有掩码谓词都是
逐行的（无跨行聚合），先按 symbol 取子集再施掩码，与先施掩码再按 symbol 取子集等价。

红线 `mismatch=0` —— **不得**靠放宽比较键、放宽容差、跳过样本、缩小股票集来达成。
"""
import importlib
import itertools
import random
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from multivar_core import apply_overrides, loosest_level, node_col  # noqa: E402
from path2 import config  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402

_CFG: dict = {}


def _init(cfg: dict) -> None:
    """worker 初始化：每个进程建一次全部 plan 项的 (Params, spec)。

    spec 在原件里就是「每格建一次、跨全部股票复用」，`analyze()` 不改写它；这里改成
    「每 worker 建一次、跨该 worker 的全部股票复用」，build_pattern 调用次数从
    O(格数) 变成 O(格数 × worker 数)，按预算研究实测 0.02 ms/次，可忽略。
    """
    global _CFG
    import study_io as S
    mod = importlib.import_module(cfg["app_module"])
    config.set_runtime_checks(True)
    base = cfg["base_yaml"]; wide = cfg["wide"]
    specs = []
    for tag, cell, wname in cfg["plan"]:
        where = cfg["wheres"][wname]
        p = mod.Params.from_dict(apply_overrides(base, wide, {**cell, **where}), strict=True)
        specs.append((tag, cell, wname, where, p, mod.build_pattern(p)))
    _CFG = {**cfg, "specs": specs}


def _worker(task):
    """对一只股票跑完全部 plan 项。返回 (stem, n_cmp, mismatches, skipped)。

    **不用 try/except 包住 analyze()**：某只股票上抛异常本身就是需要如实暴露的发现，
    吞掉再报绿会让红线失去意义。
    """
    import study_io as S
    stem, pkl_path, g_all = task
    C = _CFG
    win = slice_window(pd.read_pickle(pkl_path), C["bs"], C["be"])
    if len(win) < C["MIN_WIN_BARS"]:
        return stem, 0, [], True
    s, e = C["s"], C["e"]
    lo = int(win["date"].searchsorted(s, "left"))
    hi = int(win["date"].searchsorted(e, "right")) - 1

    n_cmp = 0
    mism = []
    for tag, cell, wname, where, p, spec in C["specs"]:
        g = g_all[S.pred_mask(g_all, {**cell, **where}, C["cl"])]
        res = analyze(spec, win, p)
        out = serialize_per_pattern_result(res, end_node=C["end_node"], label_horizon=C["H"], win=win,
                                           start_ts=s, end_ts=e, price_min=C["PRICE_MIN"], price_max=C["PRICE_MAX"],
                                           first_passage_k=C["K"], sample_window=(lo, hi))
        keep = {x["match_id"]: x for x in out["analysis"]["matches"]}
        ref = sorted((tuple((nid, ev.start_idx, ev.end_idx) for nid, ev in sorted(mm.node_index.items()) if nid in C["key_nodes"]),
                      None if keep[mm.match_id]["forward_return"] is None else round(keep[mm.match_id]["forward_return"], 12),
                      *(keep[mm.match_id]["first_passage"] or {"up": 0, "down": 0, "both": 0, "none": 0}).values())
                     for mm in res.matches if mm.match_id in keep)
        got = sorted((tuple((n, int(r[node_col(n, "start")]), int(r[node_col(n, "end")])) for n in C["key_nodes"]),
                      None if pd.isna(r["fr"]) else round(float(r["fr"]), 12),
                      int(r["fp_up"]), int(r["fp_down"]), int(r["fp_both"]), int(r["fp_none"]))
                     for _, r in g.iterrows())
        n_cmp += 1
        if ref != got or out["match_fp_counts"] != {k: int(g[f"fp_{k}"].sum()) for k in ("up", "down", "both", "none")}:
            mism.append((tag, stem, dict(cell), wname, len(ref), len(got)))
    return stem, n_cmp, mism, False


def main():
    LONGTABLE_DIR = None          # 复制到研究目录后填:multivar_scan 产出的 longtable/(含 run_meta.json)
    TICKER_REGEX = r"^[A-Z][A-C]" # 跨字母抽样(红线要求参与比较的股数 ≥500)
    WORKERS = 16                  # 定标见 reference.md §3.1
    SEED, N_RANDOM_CELLS, N_TIGHT_CELLS = 11, 64, 12
    MIN_WIN_BARS = 1              # 对齐生产 _worker 的"只跳空窗口"
    OUT_LOG = None                # None → <LONGTABLE_DIR 父目录>/compare_longtable.log

    import study_io as S
    S.require(LONGTABLE_DIR, "LONGTABLE_DIR")
    lt = REPO / LONGTABLE_DIR
    meta = S.load_run_meta(lt); APP = meta["app"]
    study_path = S.APPS_DIR / APP / "study.py"
    study = S.load_study(study_path); mod = S.import_app(study)
    cl = S.load_classification(APP); S.check_study_matches(cl, study_path); S.check_run_matches_classification(meta, cl)
    out_log = Path(OUT_LOG) if OUT_LOG else lt.parent / "compare_longtable.log"
    log_f = open(out_log, "w")

    def log(msg):
        print(msg, flush=True); print(msg, file=log_f, flush=True)

    config.set_runtime_checks(True)
    base_yaml = mod.Params.from_yaml(S.app_dir(mod) / study.BASE_YAML).to_dict()
    # ---- 组 plan:(a) 固定上游首节点维于参照格、其余维全网格 (b) 随机格 + 全部角点 (c) 收紧 where ----
    from path2.dag._graph import detector_topo_order
    spec0 = mod.build_pattern(mod.Params.from_dict(S.base_snapshot(mod, study), strict=True))
    first = list(detector_topo_order(spec0.nodes))[0]
    dims = list(study.SCAN_GRID)
    fixed = {d: study.REF_POINT[S.dotted(d)] for d in dims if cl["detector_nodes"][S.dotted(d)] == [first] and cl["kinds"][S.dotted(d)] == "D"}
    free = [d for d in dims if d not in fixed]
    rng = random.Random(SEED)
    cells_a = [{**fixed, **dict(zip(free, v))} for v in itertools.product(*(study.SCAN_GRID[d] for d in free))]
    allc = [dict(zip(dims, v)) for v in itertools.product(*study.SCAN_GRID.values())]
    corners = [c for c in allc if all(c[d] in (study.SCAN_GRID[d][0], study.SCAN_GRID[d][-1]) for d in dims)]
    cells_b = rng.sample(allc, N_RANDOM_CELLS) + corners
    wheres = {"wide": {d: loosest_level(lv, cl["where_fields"][S.dotted(d)][2]) for d, lv in study.WHERE_LEVELS.items()},
              **study.TIGHT_WHERES}
    tight_names = list(study.TIGHT_WHERES)
    plan = ([("a", c, "wide") for c in cells_a] + [("b", c, "wide") for c in cells_b]
            + [("c", c, w) for c in rng.sample(cells_a, N_TIGHT_CELLS) for w in tight_names])

    # ---- 股票池与切窗边界(口径全部来自 run_meta) ----
    H, K = meta["label_horizon"], meta["first_passage_k"]
    s, e = pd.to_datetime(meta["start_date"]), pd.to_datetime(meta["end_date"])
    bs = str((s - pd.Timedelta(days=round(meta["head_buffer"] * TRADING_TO_CALENDAR_RATIO))).date())
    be = str((e + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    filtered_csv = lt.parent / "filtered_symbols.csv"
    filtered = set(pd.read_csv(filtered_csv, keep_default_na=False)["symbol"]) if filtered_csv.exists() else set()
    syms_all = list(_list_pkls(str(REPO / "datasets/pkls"), TICKER_REGEX))
    syms = [p for p in syms_all if p.stem not in filtered]
    log(f"app {APP} · 股票 {len(syms_all)}(排除 filtered_symbols {len(syms_all) - len(syms)} 只后 {len(syms)});"
        f"对拍项 {len(plan)}(a {len(cells_a)} / b {len(cells_b)} / c {N_TIGHT_CELLS}×{len(tight_names)});{WORKERS} workers")

    t0 = time.time()
    df = pd.concat([pd.read_parquet(p) for p in sorted(lt.glob("part-*.parquet"))], ignore_index=True)
    sub = df[df["symbol"].isin({p.stem for p in syms})]
    groups = dict(list(sub.groupby("symbol", sort=False)))
    empty = sub.iloc[0:0]
    tasks = [(p.stem, str(p), groups.get(p.stem, empty)) for p in syms]
    log(f"长表读入 {len(sub)} 行 / {len(groups)} 只有行的股票,{time.time() - t0:.1f}s")

    cfg = dict(app_module=study.APP_MODULE, base_yaml=base_yaml, wide=study.WIDE_OVERRIDES, wheres=wheres, plan=plan,
               cl=cl, bs=bs, be=be, s=s, e=e, H=H, K=K, PRICE_MIN=meta["price_min"], PRICE_MAX=meta["price_max"],
               end_node=cl["end_node"], key_nodes=tuple(cl["bound_nodes"]), MIN_WIN_BARS=MIN_WIN_BARS)

    n_cmp = n_mism = n_skip = n_done = 0
    with ProcessPoolExecutor(max_workers=WORKERS, initializer=_init, initargs=(cfg,)) as ex:
        futs = [ex.submit(_worker, t) for t in tasks]
        for fu in as_completed(futs):
            stem, c, mism, skipped = fu.result()
            n_done += 1
            n_skip += int(skipped)
            n_cmp += c
            for row in mism:
                n_mism += 1
                log(f"MISMATCH {row[0]} {row[1]} {row[3]} ref={row[4]} got={row[5]} cell={row[2]}")
            if n_done % 50 == 0 or n_done == len(tasks):
                log(f"  股 {n_done}/{len(tasks)}(跳过空窗 {n_skip}) · 累计对拍 {n_cmp} · mismatch {n_mism} · {time.time() - t0:.0f}s")

    log(f"对拍 {n_cmp} 股×格({len(tasks) - n_skip} 只有效股 × {len(plan)} 项),mismatch={n_mism},{time.time() - t0:.0f}s")
    log_f.close()


main()
