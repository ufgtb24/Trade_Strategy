# -*- coding: utf-8 -*-
"""多维稳健区 v2 · 扫描端:每股一次反转循环 → 候选长表(parquet 分片)+ 随机日基线 + 台账。
用法:不直接跑本文件,由 tune.scan(app, ...) 调用本模块的 run(app, cfg, out_dir)。
断点续跑:按股——done 集 = 已有 parquet 分片 symbol ∪ random_baseline.csv symbol ∪
filtered_symbols.csv symbol(空窗口/价格量能未达标,不产生 parquet/baseline 行但仍算处理过)。
异常(err)不计入 done,下次会自动重试(不想让暂时性失败被永久跳过)。
run 级口径写进 longtable/run_meta.json,compare_longtable / region_find 读之(单源)。
"""
from __future__ import annotations

import json, subprocess, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
# 显式 REPO 相对路径,不用 Path(__file__).parent——REPO 由 git 顶层推,不依赖进程 cwd,
# 写法更稳固(与 region_find.py 同款写法)。
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))

from multivar_core import (ScanConfig, apply_overrides, classify, col_of, detection_combos,  # noqa: E402
                           loosest_level, row_columns, scan_one_stock)


def _fold_cols(buy_date: pd.Series) -> tuple:
    d = pd.to_datetime(buy_date)
    return d.dt.year.astype(str), d.dt.year.astype(str) + "H" + np.where(d.dt.month <= 6, "1", "2")


def _worker(pkl_path, cfg: ScanConfig, buf_start, buf_end, start_date, end_date, volume_min):
    from path2 import config
    from path2.calc.atr import FP_ATR_WINDOW, rolling_atr_pct_nanmedian
    from path2.eval import random_day_first_passage
    from path2_web.data import slice_window
    symbol = Path(pkl_path).stem
    try:
        config.set_runtime_checks(True)
        win = slice_window(pd.read_pickle(pkl_path), buf_start, buf_end)
        if len(win) == 0:
            return (symbol, None, None, None, None)
        s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
        if volume_min is not None:
            sw = win[(win["date"] >= s) & (win["date"] <= e)]
            if len(sw) == 0 or sw["volume"].mean() <= volume_min:
                return (symbol, None, None, None, None)
        t0 = time.perf_counter()
        rows = scan_one_stock(symbol, win, s, e, cfg)
        t_ms = (time.perf_counter() - t0) * 1000.0
        # 窗口与 multivar_core.scan_one_stock 内部那次独立计算耦合(Task 8 修复轮 1
        # Important——纯浪费非口径分裂:同 win、值恒等,但改一侧不改另一侧会静默分叉尺度)。
        # 窗口本身改引用 path2.calc.atr.FP_ATR_WINDOW 单点导出(复审 I-5),不再是散落的
        # 字面量 20——谁调它,四处一起变。
        M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], FP_ATR_WINDOW).values
        rfp = random_day_first_passage(symbol, win, s, e, cfg.label_horizon, cfg.fp_k, M=M)
        return (symbol, rows, rfp, None, t_ms)
    except Exception as ex:  # noqa: BLE001
        # 全宇宙跑若因共性 bug 集体失败,无栈的 "ERR sym Xxx: msg" 刷屏也定位不到根因
        # (修复轮 1 Minor 8);traceback 末几行足够定位到出错的具体代码行。
        tb_tail = "".join(traceback.format_exc().splitlines(keepends=True)[-6:]).rstrip("\n")
        return (symbol, None, None, f"{type(ex).__name__}: {ex}\n{tb_tail}", None)


def run(app: str, cfg, out_dir: str) -> None:
    """扫描出候选长表。断点续跑:已完成的股票从既有分片与 baseline csv 里认出来。

    cfg 是 tune.Settings;out_dir 相对 repo root。参数全部由调用方(tune.scan)通过 cfg /
    out_dir 传入,本函数不读任何常量文件;run 级口径写进 run_meta.json 供 compare/region 读。
    """
    import study_io as S
    APP = app
    DATA_DIR = cfg.data_dir
    START_DATE, END_DATE = cfg.start_date, cfg.end_date
    HEAD_BUFFER = cfg.head_buffer                    # ★ 写进 run_meta.json,compare/region 读之
    LABEL_HORIZON, FIRST_PASSAGE_K = cfg.label_horizon, cfg.first_passage_k
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = cfg.price_min, cfg.price_max, cfg.volume_min
    TICKER_REGEX = cfg.ticker_regex
    SHARD_STOCKS = cfg.shard_stocks
    WORKERS = cfg.workers
    OUT_DIR = out_dir

    from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls
    S.require(APP, "APP")
    print(f"[multivar_scan] app={APP} → {OUT_DIR} (窗 {START_DATE}..{END_DATE}, HEAD_BUFFER={HEAD_BUFFER}, WORKERS={WORKERS})")
    study_path = S.APPS_DIR / APP / "study.py"
    study = S.load_study(study_path); mod = S.import_app(study)
    cl = S.load_classification(APP); S.check_study_matches(cl, study_path)
    base_yaml = mod.Params.from_yaml(S.app_dir(mod) / study.BASE_YAML).to_dict()
    base = S.base_snapshot(mod, study)               # == cl["ref_params"]
    p0 = mod.Params.from_dict(base, strict=True)
    end_node = mod.eval_meta(params=p0)["end_node"]
    cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
    n_combo = len(detection_combos(study.SCAN_GRID, cls))
    print("参数分类:"); [print(f"  {col_of(d):32s} {k}") for d, k in cls.kinds.items()]
    print(f"检测组合数(detection_combos):{n_combo}")
    cfg = ScanConfig(module_path=study.APP_MODULE, base_dict=base, wide_overrides=study.WIDE_OVERRIDES,
                     scan_grid=study.SCAN_GRID, where_levels=study.WHERE_LEVELS, end_node=end_node,
                     label_horizon=LABEL_HORIZON, fp_k=FIRST_PASSAGE_K, price_min=PRICE_MIN, price_max=PRICE_MAX)
    filter_min = {d: loosest_level(study.SCAN_GRID[d], cls.filter_fields[d][2])
                  for d in study.SCAN_GRID if cls.kinds[d] == "F"}
    # 列集必须与 scan_one_stock 实际产行的 spec 同源,故此处用同一套 override 配方(base ⊕
    # wide_overrides ⊕ F 维最松档)再造一次 spec0——不能省这步图省事直接传 base_yaml/未套
    # filter_min 的 spec:若某 app 的 build_pattern 按参数值增删边/节点(去 app 化后本工具
    # 不假设 spec 拓扑与参数值无关),两份 spec 的列集就可能不一致,row_columns 算出的列要么
    # 漏列(KeyError)要么多出恒 NaN 的幽灵列(parquet 严格 schema 下直接报错)。
    spec0 = mod.build_pattern(mod.Params.from_dict(apply_overrides(base_yaml, study.WIDE_OVERRIDES, filter_min), strict=True))
    columns = row_columns(cfg, cls, spec0) + ["fold_Y", "fold_6M"]

    out = REPO / OUT_DIR; lt = out / "longtable"; lt.mkdir(parents=True, exist_ok=True)
    S.write_run_meta(lt, {"app": APP, "start_date": START_DATE, "end_date": END_DATE, "head_buffer": HEAD_BUFFER,
                          "label_horizon": LABEL_HORIZON, "first_passage_k": FIRST_PASSAGE_K,
                          "price_min": PRICE_MIN, "price_max": PRICE_MAX, "volume_min": VOLUME_MIN,
                          "study_fingerprint": cl["fingerprints"]["study"], "git_head": cl["git_head"],
                          "source_fingerprint": cl["fingerprints"]["source"]["hash"],
                          "base_fingerprint": cl["fingerprints"]["base"],
                          "written_at": pd.Timestamp.now().isoformat(timespec="seconds")})
    done = set()
    for part in sorted(lt.glob("part-*.parquet")):
        done |= set(pd.read_parquet(part, columns=["symbol"])["symbol"].unique())
    n_done0_parquet = len(done)
    rb_path = out / "random_baseline.csv"
    # keep_default_na=False(修复轮 1 Important 2,修复轮 3 订正因果):裸 read_csv 默认把
    # 字符串 "NA" 解析成 NaN(pandas 内置 NA 字符集,"NA" 恰在其中,但 "NAN"/"NAT" 不在),
    # 而 datasets/pkls/ 里真的有 NA.pkl。这个 kwarg 单独**不足以**在所有场景下防回归:若
    # 某 symbol 有 match(如冒烟宇宙里的 "NA" 本身),它会先经 parquet 路径(带类型的列式
    # 格式,字符串原样返回,根本不经过 pandas 的 NA 字符集)进入 done,删掉这个 kwarg 也
    # 不会让"待扫数"变化(修复轮 3 实测坐实)。加这个 kwarg 仍然是对的:它防的是"只落
    # baseline/filtered、没有 match 的 NA 型 symbol"被读错、以及往 random_baseline.csv
    # 反复追加重复行(见报告 Important 2 端到端验证)——真正的回归锁是下面 done 集的
    # NaN 断言,不是这个 kwarg 本身。
    rb_rows = (pd.read_csv(rb_path, keep_default_na=False).to_dict("records")
               if rb_path.exists() and rb_path.stat().st_size > 0 else [])
    done |= {r["symbol"] for r in rb_rows}
    # 被价格/量能/空窗口过滤掉的股票不产生 parquet 行也不产生 random_baseline 行,若不单独记录,
    # done 集追不到它们、每次 resume 都会白读一遍这些 pkl(修复轮:控制方裁定按此修)。
    filtered_path = out / "filtered_symbols.csv"
    filtered = (pd.read_csv(filtered_path, keep_default_na=False)["symbol"].tolist()
                if filtered_path.exists() and filtered_path.stat().st_size > 0 else [])
    done |= set(filtered)
    # done 集完整性断言(修复轮 3·1,真正的回归锁):"NA" 型 ticker 若真被某处 read_csv 读
    # 成 NaN,会作为 float('nan') 混进这个本应全是字符串的集合——不管它是从 parquet(不会,
    # 带类型)、random_baseline.csv 还是 filtered_symbols.csv 进来的,只要 done 里出现 NaN
    # 就在这里直接炸,不依赖"这只股票扫描宇宙里恰好没有 match"这类数据巧合(已用删除两处
    # keep_default_na=False 的反证跑验证:kwarg 在→不触发,kwarg 删→触发)。
    assert not any(pd.isna(x) for x in done), "done 集混入 NaN——read_csv 把 'NA' 之类 ticker 读成缺失值了"
    n_done0 = len(done); n_done0_rb = len(rb_rows); n_done0_filtered = len(filtered)
    s, e = pd.to_datetime(START_DATE), pd.to_datetime(END_DATE)
    buf_start = str((s - pd.Timedelta(days=round(HEAD_BUFFER * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((e + pd.Timedelta(days=round(LABEL_HORIZON * TRADING_TO_CALENDAR_RATIO))).date())
    pkls = [p for p in _list_pkls(str(REPO / DATA_DIR), TICKER_REGEX) if p.stem not in done]
    print(f"股票 {len(pkls)} 待扫(已完成 {len(done)}),窗 {buf_start}..{buf_end},HEAD_BUFFER={HEAD_BUFFER}")

    t0 = time.time(); cpu0 = time.process_time()
    # 按已有分片的最大序号+1(修复轮 1 Minor 4)——用 glob 个数会在"删掉中间某个分片再重
    # 跑"时把新分片编号撞在已有编号上,静默覆盖(如删 part-0001 后新分片仍从"当前个数"起
    # 号、算出 0001,覆盖了没删的旧 0001 数据)。
    existing_shards = sorted(lt.glob("part-*.parquet"))
    n_shard = (max(int(p.stem.split("-")[1]) for p in existing_shards) + 1) if existing_shards else 0
    buf = []
    n_done = n_det = n_skip = n_hit = n_rows = n_err = 0; per_ms = []
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_worker, str(p), cfg, buf_start, buf_end, START_DATE, END_DATE, VOLUME_MIN): p for p in pkls}
        for fut in as_completed(futs):
            symbol, rows, rfp, err, t_ms = fut.result(); n_done += 1
            if err:
                n_err += 1; print("ERR", symbol, err)          # 不计入 done,下次自动重试
            elif rows is None:
                n_skip += 1; filtered.append(symbol)            # 空窗口/价格量能未达标,已处理但无行
            else:
                n_det += 1
                if t_ms is not None:
                    per_ms.append(t_ms)
                if rows:
                    n_hit += 1; n_rows += len(rows); buf.extend(rows)
                rb_rows.append({"symbol": symbol, "n_sampled": rfp["n_sampled"], **rfp["counts"]})
            if n_done % SHARD_STOCKS == 0 or n_done == len(pkls):
                if buf:
                    df = pd.DataFrame(buf, columns=columns[:-2]); df["fold_Y"], df["fold_6M"] = _fold_cols(df["buy_date"])
                    df.to_parquet(lt / f"part-{n_shard:04d}.parquet", index=False); n_shard += 1; buf = []
                # 只在非空时写(修复轮 1 Minor 5a):空 DataFrame.to_csv 写出的文件下一轮
                # read_csv 会抛 EmptyDataError,整个目录从此开不起来、必须手删文件才能续跑。
                if rb_rows:
                    pd.DataFrame(rb_rows).to_csv(rb_path, index=False)
                if filtered:
                    pd.DataFrame({"symbol": filtered}).to_csv(filtered_path, index=False)
            if n_done % 200 == 0:
                print(f"  {n_done}/{len(pkls)} 股 · {n_rows} 行 · {time.time() - t0:.0f}s")
    if buf:
        df = pd.DataFrame(buf, columns=columns[:-2]); df["fold_Y"], df["fold_6M"] = _fold_cols(df["buy_date"])
        df.to_parquet(lt / f"part-{n_shard:04d}.parquet", index=False)
    if rb_rows:
        pd.DataFrame(rb_rows).to_csv(rb_path, index=False)
    if filtered:
        pd.DataFrame({"symbol": filtered}).to_csv(filtered_path, index=False)
    wall = time.time() - t0

    # 每股 scan_one_stock 耗时分布 + 每检测组合均摊(本轮;台账自证项;n_combo 全程实算,不手写)
    per_ms_arr = np.array(per_ms, dtype=float)
    p50 = float(np.percentile(per_ms_arr, 50)) if len(per_ms_arr) else float("nan")
    p90 = float(np.percentile(per_ms_arr, 90)) if len(per_ms_arr) else float("nan")
    avg_combo_ms = float(per_ms_arr.sum() / (n_det * n_combo)) if n_det and n_combo else float("nan")

    # run_stats.jsonl 每轮追加一行(修复轮 1 Important 1):ledger.md 此前每轮无条件
    # write_text 整体覆盖,而「股数/耗时/每股 p50-p90-均摊」全是本轮计数器——resume 全跳
    # 过(0 待扫)时这些数字被清零成 0/NaN,包括本该是唯一失败可见性的「异常 N」;部分
    # resume(跑了一段又中断)也只反映尾段。改为 append-only 历史 + 每次全量重算累计,
    # 同时保留"本轮"两组数,两者互不覆盖。
    run_stats_path = out / "run_stats.jsonl"
    run_entry = {"ts": pd.Timestamp.now().isoformat(), "n_pending_start": len(pkls),
                 "n_det": n_det, "n_skip": n_skip, "n_hit": n_hit, "n_err": n_err, "n_rows": n_rows,
                 "wall_s": wall, "cpu_s": time.process_time() - cpu0,
                 "worker_sum_ms": float(per_ms_arr.sum()), "per_ms": per_ms}
    # 补写前置换行(修复轮 3·3):上一轮若被 kill/磁盘满截断、文件末字节不是 "\n",裸追加
    # 会把本轮整行拼到上轮半行尾部形成一条烂行——那样连"半行容错"都救不了,本轮统计会
    # 跟着上轮的半行一起被当成同一条损坏行整体丢弃、且永久写死进文件。先补一个换行把上
    # 轮的半行"封口"(封口后它仍是损坏 JSON,读侧会照常跳过),再另起一行写本轮。
    if run_stats_path.exists() and run_stats_path.stat().st_size > 0:
        with run_stats_path.open("rb") as f:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                with run_stats_path.open("a") as f2:
                    f2.write("\n")
    with run_stats_path.open("a") as f:
        f.write(json.dumps(run_entry) + "\n")
    # 半行容错(修复轮 2·2):append 后 kill/磁盘满可能截断末行(文本缓冲多次底层 write,
    # 全宇宙一轮的 per_ms 是 8000+ float、单行 ≈150KB),裸 json.loads 会在下一轮渲染台账
    # 时炸,且此时已经跑完全部计算——比读侧的 EmptyDataError 更难受。跳过损坏行,不整体崩。
    hist = []
    for ln in run_stats_path.read_text().splitlines():
        if not ln.strip():
            continue
        try:
            hist.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    n_runs = len(hist)
    # 字段级容错改用 .get(默认值)(修复轮 3·2):原先 except 里挂了个 KeyError 却从不触发
    # ——json.loads 只会因语法错误抛 JSONDecodeError,真正会因缺字段炸的是这里的 h["..."]
    # 取值(一条合法 JSON 但缺 n_det 之类旧字段的行,会在这里而不是上面的 try 里报错)。改
    # 成 .get(k, 0) 才是"兼容未来字段增删"真正落地的地方。
    cum_det = sum(h.get("n_det", 0) for h in hist); cum_skip = sum(h.get("n_skip", 0) for h in hist)
    cum_hit = sum(h.get("n_hit", 0) for h in hist); cum_err = sum(h.get("n_err", 0) for h in hist)
    cum_wall = sum(h.get("wall_s", 0.0) for h in hist); cum_cpu = sum(h.get("cpu_s", 0.0) for h in hist)
    cum_worker_ms = sum(h.get("worker_sum_ms", 0.0) for h in hist)
    cum_per_ms_arr = np.array([x for h in hist for x in h.get("per_ms", [])], dtype=float)
    cum_p50 = float(np.percentile(cum_per_ms_arr, 50)) if len(cum_per_ms_arr) else float("nan")
    cum_p90 = float(np.percentile(cum_per_ms_arr, 90)) if len(cum_per_ms_arr) else float("nan")
    cum_avg_combo_ms = float(cum_per_ms_arr.sum() / (cum_det * n_combo)) if cum_det and n_combo else float("nan")
    n_universe = n_done0 + len(pkls)   # done0∪pkls = 本轮启动时的全宇宙(TICKER_REGEX 命中数),裁定用此算总股数

    # 台账 + fold 计数分布(真扫格粒度、宽进 where;累计行天然来自重读全部分片,本就是累计口径)
    parts = sorted(lt.glob("part-*.parquet"))
    full = (pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True) if parts
            else pd.DataFrame(columns=columns[:-2] + ["fold_Y", "fold_6M"]))  # 空目录守卫(修复轮 1 Minor 5b)
    combo_cols = [col_of(d) for d in study.SCAN_GRID if cls.kinds[d] != "F"]
    cnt = full.groupby(combo_cols + ["fold_Y"]).size() if len(full) else pd.Series([], dtype=int)
    cnt_line = (f"min {cnt.min()} / p50 {cnt.median():.0f} / max {cnt.max()}" if len(cnt) else "(暂无数据)")
    lines = [f"# multivar_scan 台账 · {APP}", "",
             f"- 窗:{START_DATE}..{END_DATE};HEAD_BUFFER={HEAD_BUFFER};LABEL_HORIZON={LABEL_HORIZON};FIRST_PASSAGE_K={FIRST_PASSAGE_K}",
             f"- 过滤:price [{PRICE_MIN},{PRICE_MAX}],volume_min {VOLUME_MIN};底座 {study.BASE_YAML}(base 指纹 {cl['fingerprints']['base'][:12]});宽进 {study.WIDE_OVERRIDES}",
             f"- study 指纹 {cl['fingerprints']['study'][:12]};源码指纹 {cl['fingerprints']['source']['hash'][:12]};classification 生成于 {cl['generated_at']} @ {cl['git_head']}",
             f"- SCAN_GRID:{cl['scan_grid']}", f"- WHERE_LEVELS:{cl['where_levels']}",
             f"- 分类:{ {col_of(d): k for d, k in cls.kinds.items()} }", f"- where 轴:{ {col_of(d): v for d, v in cls.where_fields.items()} }",
             f"- 检测组合数(detection_combos 实算,F 维不进组合):{n_combo}",
             f"- 断点续跑:本轮启动时 done 集共 {n_done0} 股 = 已有 parquet 分片 symbol({n_done0_parquet}) ∪ random_baseline.csv symbol({n_done0_rb}) ∪ filtered_symbols.csv symbol({n_done0_filtered});err 不计入 done、下次自动重试;总股数(TICKER_REGEX 命中全宇宙) {n_universe}",
             f"- 股数(本轮):待扫 {len(pkls)} / 进 detector {n_det} / 过滤 {n_skip} / 有 match {n_hit} / 异常 {n_err};累计行(重读全部分片) {len(full)}",
             f"- 股数(累计跨 {n_runs} 轮 run_stats.jsonl):进 detector {cum_det} / 过滤 {cum_skip} / 有 match {cum_hit} / 异常事件 {cum_err} 次(同一 symbol 每轮重试各计一次,不去重)",
             f"- 耗时(本轮):wall {wall:.0f}s @ {WORKERS} workers;worker 侧 scan_one_stock 累计 {per_ms_arr.sum() / 1000:.1f}s(≈总计算量,单线程 detector/solve 无 I/O 等待,CPU·s 量级);本进程(编排调度)cpu {time.process_time() - cpu0:.1f}s",
             f"- 耗时(累计跨 {n_runs} 轮):wall {cum_wall:.0f}s;worker 侧累计 {cum_worker_ms / 1000:.1f}s;本进程 cpu 累计 {cum_cpu:.1f}s",
             f"- 每股 scan_one_stock 耗时 ms(本轮 {len(per_ms)} 股):p50 {p50:.1f} / p90 {p90:.1f};每检测组合均摊 {avg_combo_ms:.3f}ms/股",
             f"- 每股 scan_one_stock 耗时 ms(累计 {len(cum_per_ms_arr)} 股):p50 {cum_p50:.1f} / p90 {cum_p90:.1f};每检测组合均摊 {cum_avg_combo_ms:.3f}ms/股",
             f"- 宽进 where 下真扫格 × 年折的 match 数分布:{cnt_line}", ""]
    (out / "ledger.md").write_text("\n".join(lines))
    print("\n".join(lines))
