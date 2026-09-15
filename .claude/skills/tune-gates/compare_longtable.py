"""多维稳健区 v2 · 对拍端：候选长表按格谓词聚合 vs 逐格 `engine.analyze` + serialize。

用法：不直接跑本文件，由 tune.compare(app, ...) 调用本模块的 run(app, cfg, longtable_dir)。

**这是 reference.md §2.1 Step A 的可复用实现**，语义逐字沿用某次端到端实战里一份一次性单进程逐格
脚本（已产出 mismatch=0 的证据日志，作为证据不再改动；那份脚本是一次性研究产物，不在本 skill
目录内，实例与出处见 `apps/<app>/notes.md` §4）；本文件相对它有三处变化：

  1. **按股票并行**（原件单进程）。并行轴选「股票」而非「对拍格」：每个 worker 只需一只股票的
     窗口 + 它自己的长表行，而按格切分则要求每个 worker 都驻留整张长表与全部窗口。全部 plan 项
     对应的 spec 在 worker 初始化时建一次、跨该 worker 处理的所有股票复用（原件是每格建一次、
     跨股票复用，同样是 O(格数) 次 build_pattern）。耗时对照见 `apps/<app>/notes.md` §4。
  2. **`MIN_WIN_BARS` 默认对齐生产判据**（只跳空窗口），见下方常量处的注释。
  3. **零 app 字面量**:网格/where/收紧套/底座/end_node/bound 节点全部来自该窗口的研究声明
     apps/<app>/windows/<window>/{study.py, classification.json}(window = 长表目录的父目录名),label
     口径来自长表旁的 run_meta.json(与扫描逐字同源,结构上不可能不一致);切面 (a) 的「固定维」推导为
     「只影响拓扑首 detector 节点的 D 维」并取参照格值,不再写死前两维。抽样格只从研究设计展开出的
     检测组合里取(长表里只有这些)。

**比较语义**：掩码谓词（F/W 维均按 classification 的字段与 op）、比较键（bound 节点 span + fr 12 位
小数 + 四态多重集 + 每股 `match_fp_counts`）、`serialize_per_pattern_result` 的全部入参与原件逐字相同。
四态按买点事件计：serialize 只给同一买点事件（buy_span）的第一条 match 填首次穿越四态，长表每行都带
所在买点事件的满额四态——引擎侧把首次出现时的四态回填给同一买点事件的每条 match，再按行比多重集；
`match_fp_counts` 与长表行按买点事件键（`study_io.segment_cols`）去重后的四态和比较。
把「按格循环 → 内层按股」换成「按股并行 → 内层按格」不改变任何一次比较的内容：所有掩码谓词都是
逐行的（无跨行聚合），先按 symbol 取子集再施掩码，与先施掩码再按 symbol 取子集等价。

红线 `mismatch=0` —— **不得**靠放宽比较键、放宽容差、跳过样本、缩小股票集来达成。
股票覆盖红线见 `MIN_SYMBOLS`:抽样不够时直接拒绝执行,结论行记下股数供筛选与联合识别入口复核。
"""
import importlib
import itertools
import random
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from itertools import islice
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from multivar_core import STATES, apply_overrides, loosest_level, node_col  # noqa: E402
from path2 import config  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402

_CFG: dict = {}

# 股票覆盖红线:真正比过的股票至少这么多只;不到时只有「扫描范围内的股票全部比过」才算数(小范围试扫)。
MIN_SYMBOLS = 500


def compare_symbols(data_dir: str, cmp_regex, scan_regex, filtered: set) -> tuple[list, int]:
    """参与比较的股票与扫描范围的股数。

    扫描范围 = 扫描时的股票范围(scan_regex,None = 全宇宙)里没被扫描过滤掉的股票;参与比较 = 其中代码
    命中 cmp_regex 的。扫描范围外的股票长表里本来就没有行,拿去比只会报出假的对不上。
    返回 (参与比较的 pkl 路径列表, 扫描范围股数)。"""
    universe = {p.stem for p in _list_pkls(data_dir, scan_regex)} - filtered
    return [p for p in _list_pkls(data_dir, cmp_regex) if p.stem in universe], len(universe)


def coverage_ok(n_compared: int, n_sampled: int, n_universe: int) -> bool:
    """股票覆盖红线:真正比过(窗口非空)的股票 >= MIN_SYMBOLS,或抽样已含扫描范围内的全部股票。"""
    return n_compared >= MIN_SYMBOLS or n_sampled == n_universe


def _first_detect_group(spec0) -> set:
    """拓扑序里第一趟 detect 调用产出的全部 node 名。

    一个 detector 可以一趟同时产多条流(如突破检测一趟产 bo 与 pk),它们同属
    一次 detect 调用、由同一批参数驱动,因此在 (a) 组里必须被当成一个整体。
    分组键与引擎的物化键同款:(id(detector), consumes_stream)——id() 在单份
    spec 存活期间是合法的判别式(此处 spec0 全程被强引用)。
    """
    from path2.dag._graph import detector_topo_order
    by_id = {n.node_id: n for n in spec0.nodes}
    first = next(nid for nid in detector_topo_order(spec0.nodes) if by_id[nid].detector is not None)
    fn = by_id[first]
    key = (id(fn.detector), fn.consumes_stream)
    return {n.node_id for n in spec0.nodes
            if n.detector is not None and (id(n.detector), n.consumes_stream) == key}


def _fixed_dims(dims, cl, ref_point, group, dotted) -> dict:
    """(a) 组要钉在参照格上的真扫维:凡「只影响首趟 detect 那组 node」的 D 维。

    判据用 ⊆ 而不是 == [first]:多流 detector 下同一个维会同时影响组里每个 node,
    写死等于首个 node 会让 fixed 落空、(a) 组退化成全网格(bb_v1 实测 3 → 9 格),
    方向虽保守但对拍成本 3×,而对拍是整条流水线的瓶颈步。
    detector_nodes 为空的维排除在外——空集 ⊆ 任何集合,不排除会把 where 维也钉住。
    """
    return {d: ref_point[dotted(d)] for d in dims
            if cl["kinds"][dotted(d)] == "D"
            and cl["detector_nodes"][dotted(d)]
            and set(cl["detector_nodes"][dotted(d)]) <= group}


def _plan_cells(cl: dict, fixed: dict, rng, n_random: int, n_tight: int) -> tuple:
    """对拍抽样格:(a) 钉住固定维、其余维取遍 / (b) 随机格 + 全部角点 / (c) 从 (a) 里抽来配收紧 where。

    候选全集 = 研究设计展开出的检测组合(study_io.design_combos,长表里只有这些)× F 维全部档位
    (F 维按最松档构造、事后切,任何档都在长表里)。候选按各维档位下标的字典序排列——grid 设计下
    与全网格笛卡尔积同序,抽样结果与按全网格抽一致。返回 (cells_a, cells_b, cells_c),格的键为 Dim。
    """
    import study_io as S
    grid = {S.undotted(k): lv for k, lv in cl["scan_grid"].items()}
    dims = list(grid)
    f_dims = [d for d in dims if cl["kinds"][S.dotted(d)] == "F"]
    allc = []
    for combo in S.design_combos(cl):
        fixed_part = {S.undotted(k): v for k, v in combo.items()}
        for fv in itertools.product(*(grid[d] for d in f_dims)):
            c = {**fixed_part, **dict(zip(f_dims, fv))}
            allc.append({d: c[d] for d in dims})
    allc.sort(key=lambda c: tuple(grid[d].index(c[d]) for d in dims))
    cells_a = [c for c in allc if all(c[d] == v for d, v in fixed.items())]
    corners = [c for c in allc if all(c[d] in (grid[d][0], grid[d][-1]) for d in dims)]
    cells_b = rng.sample(allc, min(n_random, len(allc))) + corners
    cells_c = rng.sample(cells_a, min(n_tight, len(cells_a)))
    return cells_a, cells_b, cells_c


def _engine_keys(matches, out_matches: list, key_nodes) -> list:
    """引擎侧逐 match 比较键(已排序):bound 节点 span + fr(12 位)+ 四态。

    serialize 只给同一买点事件(buy_span)的第一条 match 填首次穿越四态、其余为 None;长表每行都带所在
    买点事件的满额四态。这里把首次出现时的四态回填给同一买点事件的每条 match,两侧才能逐行对上。"""
    keep = {x["match_id"]: x for x in out_matches}
    fp_of_span: dict = {}
    for x in out_matches:
        fp_of_span.setdefault(tuple(map(tuple, x["buy_span"])), x["first_passage"])
    zero = dict.fromkeys(STATES, 0)
    rows = []
    for mm in matches:
        x = keep.get(mm.match_id)
        if x is None:
            continue
        fp = fp_of_span[tuple(map(tuple, x["buy_span"]))] or zero
        rows.append((tuple((nid, ev.start_idx, ev.end_idx) for nid, ev in sorted(mm.node_index.items()) if nid in key_nodes),
                     None if x["forward_return"] is None else round(x["forward_return"], 12),
                     *(fp[s] for s in STATES)))
    return sorted(rows)


def _table_keys(g: pd.DataFrame, key_nodes) -> list:
    """长表侧逐行比较键(已排序),与 `_engine_keys` 同构。"""
    return sorted((tuple((n, int(r[node_col(n, "start")]), int(r[node_col(n, "end")])) for n in key_nodes),
                   None if pd.isna(r["fr"]) else round(float(r["fr"]), 12),
                   *(int(r[f"fp_{s}"]) for s in STATES))
                  for _, r in g.iterrows())


def _table_fp_counts(g: pd.DataFrame, seg_cols: list) -> dict:
    """长表侧四态和:同一买点事件的多行只计一次,与 serialize 的 match_fp_counts 同口径。"""
    d = g.drop_duplicates(seg_cols)
    return {s: int(d[f"fp_{s}"].sum()) for s in STATES}


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
        ref = _engine_keys(res.matches, out["analysis"]["matches"], C["key_nodes"])
        got = _table_keys(g, C["key_nodes"])
        n_cmp += 1
        if ref != got or out["match_fp_counts"] != _table_fp_counts(g, C["seg_cols"]):
            mism.append((tag, stem, dict(cell), wname, len(ref), len(got)))
    return stem, n_cmp, mism, False


def run(app: str, cfg, longtable_dir: str) -> None:
    """一致性验证:确认「扫完之后再切档位」与「每个档位真扫一遍」逐格相同。

    红线:mismatch 必须为 0,否则后面读出来的结论都不可信。
    """
    import study_io as S
    APP = app
    LONGTABLE_DIR = longtable_dir
    TICKER_REGEX = cfg.cmp_ticker_regex
    SEED, N_RANDOM_CELLS, N_TIGHT_CELLS = cfg.cmp_seed, cfg.cmp_n_random_cells, cfg.cmp_n_tight_cells
    MIN_WIN_BARS = cfg.min_win_bars
    WORKERS = cfg.workers
    DATA_DIR = cfg.data_dir            # 与扫描端同一个来源;写死 "datasets/pkls" 会让
                                       # worktree(该目录为空,数据在主目录)里一只股都找不到
    OUT_LOG = None        # None → <LONGTABLE_DIR 父目录>/compare_longtable.log

    print(f"[compare_longtable] app={APP} → {LONGTABLE_DIR} (抽样 {TICKER_REGEX}, WORKERS={WORKERS})")
    S.require(LONGTABLE_DIR, "LONGTABLE_DIR")
    lt = REPO / LONGTABLE_DIR
    meta = S.load_run_meta(lt)
    if meta["app"] != APP:
        raise SystemExit(f"扫描结果属于 app {meta['app']!r},但本次传入的是 {APP!r}——"
                         "读 A 的长表按 B 的分类去切会静默出错,拒绝执行")
    if meta.get("label_mode") == "deferred":
        raise SystemExit("这份扫描结果只记录了买点事件、没有算涨跌结果(扫描区间碰到了留作最后验证的数据);"
                         "一致性验证要逐格核对涨跌结果,没有标签就无从核对,拒绝执行")
    import ledger
    WINDOW = lt.parent.name                  # outputs/tune_gates/<app>/<window>/longtable
    study_path = S.study_path(APP, WINDOW)
    study = S.load_study(study_path); mod = S.import_app(study)
    cl = S.load_classification(APP, WINDOW); S.check_study_matches(cl, study_path); S.check_run_matches_classification(meta, cl)
    shards = sorted(lt.glob("part-*.parquet"))
    if not shards:
        raise SystemExit(f"{lt} 下没有扫描分片:先跑扫描")
    seg_cols = S.segment_cols(cl, pq.read_schema(shards[0]).names)

    # ---- 股票池:扫描范围内、命中抽样范围的股票;不够数就在动日志之前拒绝(旧日志原样保留) ----
    filtered_csv = lt.parent / "filtered_symbols.csv"
    filtered = set(pd.read_csv(filtered_csv, keep_default_na=False)["symbol"]) if filtered_csv.exists() else set()
    # run_meta 没记股票范围的旧扫描按全宇宙算:认不出范围就不能声称全部比过
    syms, n_universe = compare_symbols(str(REPO / DATA_DIR), TICKER_REGEX, meta.get("ticker_regex"), filtered)
    if not coverage_ok(len(syms), len(syms), n_universe):
        raise SystemExit(f"一致性验证只抽到 {len(syms)} 只股票,不到 {MIN_SYMBOLS} 只,也没有覆盖这批扫描的全部 "
                         f"{n_universe} 只;抽样太窄,证明不了扫描结果可信,放宽抽样的股票范围后再做")
    out_log = Path(OUT_LOG) if OUT_LOG else lt.parent / "compare_longtable.log"
    log_f = open(out_log, "w")

    def log(msg):
        print(msg, flush=True); print(msg, file=log_f, flush=True)

    # 首行记下这次核对依据的研究声明与尺子(标签 / 基线 / 分层定义代码):换了任一个都要重新核对
    log(f"study_fingerprint={cl['fingerprints']['study']} ruler_fingerprint={ledger.ruler_fingerprint()}")
    config.set_runtime_checks(True)
    base_yaml = mod.Params.from_yaml(S.app_dir(mod) / study.BASE_YAML).to_dict()
    # ---- 组 plan:(a) 固定首趟 detect 那组 node 的 D 维于参照格、其余维全网格 (b) 随机格 + 全部角点 (c) 收紧 where ----
    spec0 = mod.build_pattern(mod.Params.from_dict(S.base_snapshot(mod, study), strict=True))
    fixed = _fixed_dims(list(study.SCAN_GRID), cl, study.REF_POINT, _first_detect_group(spec0), S.dotted)
    cells_a, cells_b, cells_c = _plan_cells(cl, fixed, random.Random(SEED), N_RANDOM_CELLS, N_TIGHT_CELLS)
    wheres = {"wide": {d: loosest_level(lv, cl["where_fields"][S.dotted(d)][2]) for d, lv in study.WHERE_LEVELS.items()},
              **study.TIGHT_WHERES}
    tight_names = list(study.TIGHT_WHERES)
    plan = ([("a", c, "wide") for c in cells_a] + [("b", c, "wide") for c in cells_b]
            + [("c", c, w) for c in cells_c for w in tight_names])

    # ---- 股票池与切窗边界(口径全部来自 run_meta) ----
    H, K = meta["label_horizon"], meta["first_passage_k"]
    s, e = pd.to_datetime(meta["start_date"]), pd.to_datetime(meta["end_date"])
    bs = str((s - pd.Timedelta(days=round(meta["head_buffer"] * TRADING_TO_CALENDAR_RATIO))).date())
    be = str((e + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    log(f"app {APP} · 扫描范围 {n_universe} 只股票(已排除 filtered_symbols),其中命中抽样范围 {len(syms)} 只;"
        f"对拍项 {len(plan)}(a {len(cells_a)} / b {len(cells_b)} / c {len(cells_c)}×{len(tight_names)});{WORKERS} workers")

    t0 = time.time()
    # 只把参与比较的那批股票、且只把 _worker 真正会碰的那些列读进来。两处都是去掉不必要的
    # 物化,不是限流:① 整表读入要按全部 26 列付内存(2026-09-07 实测 396B/行,那天 OOM 卡死
    # 桌面就是这个量级),而这里从来只用 cmp_ticker_regex 命中的约八分之一;② `buy_date` /
    # `dd` / `fold_Y` / `fold_6M` 这四列读进来从头到尾没被用过,而其中三个是字符串列、
    # 恰是最贵的部分。列清单从 cl 推(不写死),少算一列就会在 _worker 里裸 KeyError。
    key_nodes = tuple(cl["bound_nodes"])
    used_cols = (["symbol"]
                 + [c for c in cl["scan_grid"] if cl["kinds"][c] != "F"]          # combo 轴(pred_mask 用)
                 + [node_col(n, f) for (n, f, _) in cl["filter_fields"].values()]  # F 维谓词列
                 + [node_col(n, f) for (n, f, _) in cl["where_fields"].values()]   # W 维谓词列
                 + [node_col(n, x) for n in key_nodes for x in ("start", "end")]   # 逐行比对的 span
                 + seg_cols                                                         # 买点事件键(四态去重)
                 + ["fr", "fp_up", "fp_down", "fp_both", "fp_none"])
    used_cols = list(dict.fromkeys(used_cols))
    keep_syms = {p.stem for p in syms}
    sub = pd.concat([d[d["symbol"].isin(keep_syms)]
                     for d in (pd.read_parquet(sp, columns=used_cols) for sp in shards)],
                    ignore_index=True)
    log(f"长表读入 {len(sub)} 行 × {len(used_cols)} 列(全表 26 列),{time.time() - t0:.1f}s")

    cfg = dict(app_module=study.APP_MODULE, base_yaml=base_yaml, wide=study.WIDE_OVERRIDES, wheres=wheres, plan=plan,
               cl=cl, bs=bs, be=be, s=s, e=e, H=H, K=K, PRICE_MIN=meta["price_min"], PRICE_MAX=meta["price_max"],
               end_node=cl["end_node"], key_nodes=tuple(cl["bound_nodes"]), seg_cols=seg_cols,
               MIN_WIN_BARS=MIN_WIN_BARS)

    n_cmp = n_mism = n_skip = n_done = 0
    with ProcessPoolExecutor(max_workers=WORKERS, initializer=_init, initargs=(cfg,)) as ex:
        # 有界投递 + 边分组边切片:原写法先 `dict(list(sub.groupby("symbol")))` 把命中数据整份
        # 复制一遍、再把全部任务一次性 submit。两者都不必要——每只股票的切片只在它那一个任务
        # 里用一次,投出去之后主进程不该再持有。滑动窗口同扫描端(reference.md §6 坑 11)。
        groups = sub.groupby("symbol", sort=False, observed=True)
        empty = sub.iloc[0:0]
        it = iter(syms)

        def _submit(pk):
            try:
                g = groups.get_group(pk.stem)
            except KeyError:
                g = empty
            return ex.submit(_worker, (pk.stem, str(pk), g))

        pending = {_submit(pk) for pk in islice(it, WORKERS * 2)}
        while pending:
            fresh, pending = wait(pending, return_when=FIRST_COMPLETED)
            pending |= {_submit(pk) for pk in islice(it, len(fresh))}
            for fu in fresh:
                stem, c, mism, skipped = fu.result()
                n_done += 1
                n_skip += int(skipped)
                n_cmp += c
                for row in mism:
                    n_mism += 1
                    log(f"MISMATCH {row[0]} {row[1]} {row[3]} ref={row[4]} got={row[5]} cell={row[2]}")
                if n_done % 50 == 0 or n_done == len(syms):
                    log(f"  股 {n_done}/{len(syms)}(跳过空窗 {n_skip}) · 累计对拍 {n_cmp} · mismatch {n_mism} · {time.time() - t0:.0f}s")
            fresh = None   # 处理完立刻断开对这批 Future 的引用,切片随之可回收

    # 结论行:mismatch 之后的三个股数给入口复核股票覆盖红线(screen.check_consistency)
    log(f"对拍 {n_cmp} 股×格({len(syms) - n_skip} 只有效股 × {len(plan)} 项),mismatch={n_mism},{time.time() - t0:.0f}s;"
        f"compared_symbols={len(syms) - n_skip} sampled_symbols={len(syms)} universe_symbols={n_universe}")
    log_f.close()
