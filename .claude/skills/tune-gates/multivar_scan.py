# -*- coding: utf-8 -*-
"""多维稳健区 v2 · 扫描端:每股一次反转循环 → 候选长表(parquet 分片)+ 逐日基线 + 台账。
用法:不直接跑本文件,由 tune.scan(app, ...) 调用本模块的 run(app, cfg, out_dir)。

输出目录 <out_dir> = outputs/tune_gates/<app>/<window>,下列各目录的分片号一致(同号分片是同一批股票):
  longtable/part-NNNN.parquet  候选长表;run 级口径写进 longtable/run_meta.json,compare / region 读之(单源)
  baseline/part-NNNN.parquet   逐日基线(完整标签模式):过了股票级过滤的股票在扫描区间内每个合格日一行
  segments/part-NNNN.parquet   买点事件表(延迟标签模式):symbol, seg_id, span_key(JSON 文本)
  labels/part-NNNN.parquet     延迟标签:正式验证时由 compute_deferred_labels 现算,与 segments 同号

标签模式:扫描区间(连同其后的标签窗)碰到留作最后验证的数据时只能走延迟标签模式——只记买点事件,
不算任何标签,也不写逐日基线(基线同样是标签);标签留到正式验证过了确认窗守卫之后再按买点事件表现算。

分片提交:同一批股票的各目录分片都写完后,往 shards_committed.csv 追加分片名,这一步才算提交。
续跑开始时先删掉不在提交清单里的分片(上次写到一半被打断的那批)再算 done 集——否则基线片已落盘、
长表片还没写的那批股票会经基线进 done 集,长表行永久丢失;延迟模式下则会留下没有长表对应的买点事件片。

断点续跑:按股——done 集 = 已提交的 longtable 分片 symbol ∪ 已提交的 baseline 分片 symbol ∪
filtered_symbols.csv(空窗口 / 量能未达标)∪ empty_symbols.csv(进了 detector 但既无长表行也无基线行)。
异常(err)不计入 done,下次会自动重试(不想让暂时性失败被永久跳过)。
"""
from __future__ import annotations

import json, os, subprocess, sys, time, traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from itertools import islice
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
# 显式 REPO 相对路径,不用 Path(__file__).parent——REPO 由 git 顶层推,不依赖进程 cwd,
# 写法更稳固(与 region_find.py 同款写法)。
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))

from multivar_core import (LABEL_MODES, STATES, ScanConfig, apply_overrides, classify, col_of,  # noqa: E402
                           detection_combos, loosest_level, row_columns, scan_one_stock, seg_id_of,
                           span_key_json, stock_scales)

SHARD_DIRS = ("longtable", "baseline", "segments")
COMMIT_FILE = "shards_committed.csv"
BASELINE_COLS = ["symbol", "date", "M", "c0_atr_pct", *STATES]
SEGMENT_COLS = ["symbol", "seg_id", "span_key"]
FP_COLS = [f"fp_{s}" for s in STATES]
LABEL_TABLE_COLS = ["symbol", "seg_id", *FP_COLS]


def _fold_cols(buy_date: pd.Series) -> tuple:
    d = pd.to_datetime(buy_date)
    return d.dt.year.astype(str), d.dt.year.astype(str) + "H" + np.where(d.dt.month <= 6, "1", "2")


def _shrink_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """落盘前把列类型压到够用为止(原地改 df 并返回它)。长表每行 396B 里有 230B 是四个字符串
    列,整数列又一律 int64——压完约 85B/行。这是所有"读长表"开销的共同放大器:验证端按行读
    明细、断点续跑扫 symbol 列、识别端读谓词列,都按这个系数付钱。

    **浮点列一律不动**,这条是红线不是保守:
    - 真扫维(combo)里的浮点列参与**精确相等**匹配(`region_core.prepare` 用
      `pd.Categorical(df[c], categories=档位表)`,档位值是 classification.json 里的 float64)。
      收成 float32 后 `.codes` 全 −1 → 全行被丢 → 直接抛"0 行保留"。
    - `fr` 被 `compare_longtable._worker` 以 `round(float(...), 12)` 与引擎侧 float64 逐字比较,
      收窄必然打破 `mismatch=0` 红线。
    - 过滤型/where 维的浮点列走不等式(`v < 档位值`),float32 的表示误差会让恰好等于档位值的
      行翻到另一档,还可能触发"紧档必须是松档子集"的数据侧校验。
    - `dd`(前瞻回撤)当前只写不读,但它与首次穿越率正交互补,保留原样不是为了省内存。

    整数列用 `downcast="integer"` 统一收窄——整数没有表示误差,精确相等与不等式都不受影响
    (`burst.gap_max` 这类档位值、bar 索引、四态计数都在 int8/int16/int32 值域内)。
    唯一例外 `seg_id`:它是 64 位摘要,固定 int64——某片的值恰好都落在小值域时 downcast 会把它收窄,
    各片 dtype 就不一致了。
    """
    for c in ("symbol", "fold_Y", "fold_6M"):
        if c in df.columns:
            df[c] = df[c].astype("category")
    if "buy_date" in df.columns:
        df["buy_date"] = pd.to_datetime(df["buy_date"])   # 注意:_fold_cols 必须在本函数之前调用
    if "seg_id" in df.columns:
        df["seg_id"] = df["seg_id"].astype("int64")
    for c in df.columns:
        if c in ("fr", "dd", "seg_id") or not str(df[c].dtype).startswith("int"):
            continue
        df[c] = pd.to_numeric(df[c], downcast="integer")
    return df


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """先写临时文件再改名:进程中途被杀不会留下半截分片(半截分片读不开,又会被 glob 当成已完成)。"""
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def committed_shards(out: Path) -> set | None:
    """提交清单里的分片名集合;清单文件不存在 → None(区别于「有清单、一片都没提交」的空集)。
    被截断的半行不是任何合法分片名,自然不算提交。"""
    p = Path(out) / COMMIT_FILE
    if not p.exists():
        return None
    return {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()}


def commit_shard(out: Path, name: str) -> None:
    """往提交清单追加一行分片名并落盘。上次追加若被截断留下半行,先补换行封口,免得本行粘在它后面。"""
    p = Path(out) / COMMIT_FILE
    head = "" if p.exists() and p.stat().st_size > 0 else "shard\n"
    if not head:
        with p.open("rb") as f:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                head = "\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(head + name + "\n")
        f.flush()
        os.fsync(f.fileno())


def write_shard(out: Path, n_shard: int, tables: dict) -> str:
    """一批股票落成同一个分片号:tables = {子目录名: DataFrame},逐个写完后追加提交清单。返回分片名。"""
    name = f"part-{n_shard:04d}.parquet"
    for sub, df in tables.items():
        _write_parquet(df, Path(out) / sub / name)
    commit_shard(out, name)
    return name


def drop_uncommitted(out: Path, shard_dirs=SHARD_DIRS) -> list:
    """删掉各分片目录里不在提交清单里的分片与残留临时文件(上次写到一半被打断的那批),返回删掉的路径。

    有分片却没有提交清单 → 拒绝(判断不了哪些分片是完整写完的,不自动删任何东西)。"""
    out = Path(out)
    committed = committed_shards(out)
    found = [p for d in shard_dirs for p in sorted((out / d).glob("part-*.parquet"))]
    if committed is None:
        if found:
            raise SystemExit(f"{out} 里有扫描分片却没有提交清单,判断不了哪些分片是完整写完的;"
                             "不自动删除,请换一个输出窗口重新扫描")
        committed = set()
    orphans = [p for p in found if p.name not in committed]
    orphans += [p for d in shard_dirs for p in sorted((out / d).glob("part-*.parquet.tmp"))]
    if orphans:
        names = sorted({p.name.removesuffix(".tmp") for p in orphans})
        print(f"[续跑] 上次扫描写到一半被打断,这批结果不完整({', '.join(names)}),先删掉,这批股票会重新扫描")
        for p in orphans:
            p.unlink()
    return orphans


def _window_bounds(start_date, end_date, head_buffer: int, label_horizon: int) -> tuple:
    """(买点区间起点, 终点, 切窗起点, 切窗终点)。扫描与延迟标签共用同一个切窗口径。"""
    from path2_web.scan import TRADING_TO_CALENDAR_RATIO
    s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
    buf_start = str((s - pd.Timedelta(days=round(head_buffer * TRADING_TO_CALENDAR_RATIO))).date())
    buf_end = str((e + pd.Timedelta(days=round(label_horizon * TRADING_TO_CALENDAR_RATIO))).date())
    return s, e, buf_start, buf_end


def load_stock(pkl_path, buf_start, buf_end, start_date, end_date, volume_min):
    """切窗 + 股票级过滤:窗口为空,或买点区间内平均成交量不过 volume_min → None;否则返回窗口。"""
    from path2_web.data import slice_window
    win = slice_window(pd.read_pickle(pkl_path), buf_start, buf_end)
    if len(win) == 0:
        return None
    if volume_min is not None:
        s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
        sw = win[(win["date"] >= s) & (win["date"] <= e)]
        if len(sw) == 0 or sw["volume"].mean() <= volume_min:
            return None
    return win


def daily_baseline(symbol: str, daily: pd.DataFrame, c0, price_min, price_max) -> pd.DataFrame:
    """逐日基线行:daily = daily_first_passage 的输出(合格日 = 前瞻窗完整、M 有效),再只留收盘价落在
    [price_min, price_max] 的日子;c0 = 同一窗口 stock_scales 的第二项。列 = BASELINE_COLS。"""
    keep = np.ones(len(daily), dtype=bool)
    if price_min is not None:
        keep &= daily["close"].to_numpy() >= price_min
    if price_max is not None:
        keep &= daily["close"].to_numpy() <= price_max
    d = daily[keep]
    return d.assign(symbol=symbol, c0_atr_pct=c0[d["idx"].to_numpy()])[BASELINE_COLS]


def _worker(pkl_path, cfg: ScanConfig, buf_start, buf_end, start_date, end_date, volume_min):
    """一只股票:切窗 → 股票级过滤 → 反转循环;完整标签模式另算逐日基线。

    返回 (symbol, rows, segs, base, err, t_ms):被过滤的股票 rows=None;延迟标签模式 base 恒为 None。
    逐日基线 = 扫描区间内每个合格日(daily_first_passage:前瞻窗完整、M 有效)里收盘价落在
    [price_min, price_max] 的日子;波动率两列与长表行取自同一个 stock_scales。"""
    from path2 import config
    from path2.eval import daily_first_passage
    symbol = Path(pkl_path).stem
    try:
        config.set_runtime_checks(True)
        win = load_stock(pkl_path, buf_start, buf_end, start_date, end_date, volume_min)
        if win is None:
            return (symbol, None, None, None, None, None)
        s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
        t0 = time.perf_counter()
        rows, segs = scan_one_stock(symbol, win, s, e, cfg)
        t_ms = (time.perf_counter() - t0) * 1000.0
        base = None
        if cfg.label_mode == "full":
            M, c0 = stock_scales(win)
            base = daily_baseline(symbol, daily_first_passage(win, s, e, cfg.label_horizon, cfg.fp_k, M=M), c0,
                                  cfg.price_min, cfg.price_max)
        return (symbol, rows, segs, base, None, t_ms)
    except Exception as ex:  # noqa: BLE001
        # 全宇宙跑若因共性 bug 集体失败,无栈的 "ERR sym Xxx: msg" 刷屏也定位不到根因;
        # traceback 末几行足够定位到出错的具体代码行。
        tb_tail = "".join(traceback.format_exc().splitlines(keepends=True)[-6:]).rstrip("\n")
        return (symbol, None, None, None, f"{type(ex).__name__}: {ex}\n{tb_tail}", None)


def _scan_pool(pkls, worker, worker_args: tuple, workers: int, on_result) -> None:
    """按股并行:worker(item, *worker_args) 在子进程跑,on_result(返回值) 在主进程串行回调。

    有界提交,不一次性 submit 全宇宙:Future 会一直持有 worker 的返回值,外层容器对每个 Future
    都是强引用,消费过也不释放——等于把「每股扫出来的所有行」全留在主进程内存里直到本轮结束
    (实测 4096 格网格扫到第 2580 股时主进程 23.4GB,被 OOM killer 杀掉)。滑动窗口只保留在途的
    那几股,峰值内存与已扫股数解耦。回调顺序 = 完成顺序,调用方不得依赖它。"""
    with ProcessPoolExecutor(max_workers=workers) as ex:
        it = iter(pkls)
        pending = {ex.submit(worker, p, *worker_args) for p in islice(it, workers * 2)}
        while pending:
            fresh, pending = wait(pending, return_when=FIRST_COMPLETED)
            pending |= {ex.submit(worker, p, *worker_args) for p in islice(it, len(fresh))}
            for fut in fresh:
                on_result(fut.result())
            fresh = None   # 处理完立刻断开对这批 Future 的引用,返回值随调用方落盘一起释放


def _parquet_symbols(d: Path, committed: set) -> set:
    out: set = set()
    for part in sorted(Path(d).glob("part-*.parquet")):
        if part.name in committed:
            out |= set(pd.read_parquet(part, columns=["symbol"])["symbol"].unique())
    return out


def _read_symbols_csv(p: Path) -> list:
    # keep_default_na=False:裸 read_csv 会把字符串 "NA" 解析成 NaN,而数据目录里真的有 NA.pkl。
    return (pd.read_csv(p, keep_default_na=False)["symbol"].tolist()
            if p.exists() and p.stat().st_size > 0 else [])


def _done_symbols(out: Path, symbol_dirs=("longtable", "baseline")) -> tuple[set, dict]:
    """断点续跑的 done 集 = 各结果目录已提交分片的 symbol ∪ 两个名单 csv;parts 按来源给出各自的
    symbol(台账与续写 csv 用)。未提交的分片不算——调用前应先 drop_uncommitted。"""
    committed = committed_shards(out) or set()
    parts = {d: _parquet_symbols(out / d, committed) for d in symbol_dirs}
    parts["filtered"] = _read_symbols_csv(out / "filtered_symbols.csv")
    parts["empty"] = _read_symbols_csv(out / "empty_symbols.csv")
    done = set().union(*(parts[d] for d in symbol_dirs)) | set(parts["filtered"]) | set(parts["empty"])
    # 回归锁:"NA" 型 ticker 若被某处读成缺失值,会以 NaN 混进这个本应全是字符串的集合——直接炸,
    # 不依赖"这只股票恰好有没有 match"这类数据巧合。
    assert not any(pd.isna(x) for x in done), "done 集混入 NaN——read_csv 把 'NA' 之类 ticker 读成缺失值了"
    return done, parts


def _next_shard(out: Path, shard_dirs=SHARD_DIRS) -> int:
    """下一个分片号 = (各输出目录已有分片 ∪ 提交清单)的最大序号 + 1。按最大序号而非个数:删掉中间某片
    再续跑时,按个数起号会撞上没删的旧分片、静默覆盖。提交清单也要算进来:已提交分片的文件被手动删掉后
    若复用它的号,之后写到一半被打断的新分片会被误认成已提交。"""
    names = [p.name for sub in shard_dirs for p in (Path(out) / sub).glob("part-*.parquet")]
    names += sorted(committed_shards(out) or ())
    nums = [int(n.split("-")[1].split(".")[0]) for n in names]
    return max(nums) + 1 if nums else 0


def prepare_resume(out: Path, shard_dirs=SHARD_DIRS, symbol_dirs=("longtable", "baseline")) -> tuple[set, dict, int]:
    """续跑准备:删掉未提交的孤儿分片 → done 集 → 下一个分片号(清理之后算)。"""
    drop_uncommitted(out, shard_dirs)
    done, parts = _done_symbols(out, symbol_dirs)
    return done, parts, _next_shard(out, shard_dirs)


def run_meta_of(app: str, cfg, cl: dict, label_mode: str) -> dict:
    """run_meta.json 的内容。cfg 是 tune.Settings,cl 是窗口的 classification。

    ticker_regex 记本次扫描的股票范围(None = 全宇宙),供状态推导判断扫没扫完;它不是口径——先用小正则
    试跑、再放开全宇宙续跑是支持的用法——所以不进 study_io.RUN_CALIBER,每次运行按本次值重写。"""
    return {"app": app, "start_date": cfg.start_date, "end_date": cfg.end_date, "head_buffer": cfg.head_buffer,
            "label_horizon": cfg.label_horizon, "first_passage_k": cfg.first_passage_k,
            "price_min": cfg.price_min, "price_max": cfg.price_max, "volume_min": cfg.volume_min,
            "ticker_regex": cfg.ticker_regex,
            "study_fingerprint": cl["fingerprints"]["study"], "git_head": cl["git_head"],
            "source_fingerprint": cl["fingerprints"]["source"]["hash"],
            "base_fingerprint": cl["fingerprints"]["base"],
            "ruler_fingerprint": cl["fingerprints"]["ruler"],
            "label_mode": label_mode,
            "written_at": pd.Timestamp.now().isoformat(timespec="seconds")}


def run(app: str, cfg, out_dir: str, *, label_mode: str = "full") -> None:
    """扫描出候选长表。断点续跑:已完成的股票从既有分片与 csv 里认出来。

    cfg 是 tune.Settings;out_dir 相对 repo root。参数全部由调用方(tune.scan)通过 cfg /
    out_dir 传入,本函数不读任何常量文件;run 级口径写进 run_meta.json 供 compare/region 读。

    label_mode="full" 先过确认窗守卫:app 还没做开局核对 → 原样拒绝;扫描区间碰到留作验证的数据 →
    自动改走 "deferred" 并说明。显式传 "deferred" 不过守卫(不读任何标签)。
    """
    import holdout
    import study_io as S
    if label_mode not in LABEL_MODES:
        raise ValueError(f"未知标签模式 {label_mode!r}(合法 {LABEL_MODES})")
    APP = app
    cfg_in = cfg                                     # 下面 cfg 会被换成 ScanConfig,run_meta 取调用方原值
    DATA_DIR = cfg.data_dir
    START_DATE, END_DATE = cfg.start_date, cfg.end_date
    HEAD_BUFFER = cfg.head_buffer                    # ★ 写进 run_meta.json,compare/region 读之
    LABEL_HORIZON, FIRST_PASSAGE_K = cfg.label_horizon, cfg.first_passage_k
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = cfg.price_min, cfg.price_max, cfg.volume_min
    TICKER_REGEX = cfg.ticker_regex
    SHARD_STOCKS = cfg.shard_stocks
    WORKERS = cfg.workers
    OUT_DIR = out_dir

    from path2_web.scan import _list_pkls
    S.require(APP, "APP")
    if label_mode == "full":
        try:
            holdout.guard_label_access(APP, START_DATE, END_DATE, "scan")
        except holdout.HoldoutLocked as e:
            if e.reason != "confirm_overlap":
                raise
            label_mode = "deferred"
            print(f"[multivar_scan] {e}\n[multivar_scan] 所以这次扫描只记录买点事件,不算涨跌结果,也不算逐日基线;"
                  "涨跌结果留到正式验证时再算。")
    deferred = label_mode == "deferred"
    print(f"[multivar_scan] app={APP} → {OUT_DIR} (窗 {START_DATE}..{END_DATE}, HEAD_BUFFER={HEAD_BUFFER}, "
          f"WORKERS={WORKERS}, 标签模式 {label_mode})")
    WINDOW = Path(OUT_DIR).name                      # 输出目录 outputs/tune_gates/<app>/<window>
    study_path = S.study_path(APP, WINDOW)
    study = S.load_study(study_path); mod = S.import_app(study)
    cl = S.load_classification(APP, WINDOW); S.check_study_matches(cl, study_path)
    base_yaml = mod.Params.from_yaml(S.app_dir(mod) / study.BASE_YAML).to_dict()
    base = S.base_snapshot(mod, study)               # == cl["ref_params"]
    p0 = mod.Params.from_dict(base, strict=True)
    end_node = mod.eval_meta(params=p0)["end_node"]
    cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
    n_combo = len(detection_combos(study.SCAN_GRID, cls, cl["design"], cl["ref_point"]))
    print("参数分类:"); [print(f"  {col_of(d):32s} {k}") for d, k in cls.kinds.items()]
    print(f"研究设计 {cl['design']},检测组合数(detection_combos):{n_combo}")
    cfg = ScanConfig(module_path=study.APP_MODULE, base_dict=base, wide_overrides=study.WIDE_OVERRIDES,
                     scan_grid=study.SCAN_GRID, where_levels=study.WHERE_LEVELS, end_node=end_node,
                     label_horizon=LABEL_HORIZON, fp_k=FIRST_PASSAGE_K, price_min=PRICE_MIN, price_max=PRICE_MAX,
                     design=cl["design"], ref_point=cl["ref_point"], label_mode=label_mode)
    filter_min = {d: loosest_level(study.SCAN_GRID[d], cls.filter_fields[d][2])
                  for d in study.SCAN_GRID if cls.kinds[d] == "F"}
    # 列集必须与 scan_one_stock 实际产行的 spec 同源,故此处用同一套 override 配方(base ⊕
    # wide_overrides ⊕ F 维最松档)再造一次 spec0——不能省这步图省事直接传 base_yaml/未套
    # filter_min 的 spec:若某 app 的 build_pattern 按参数值增删边/节点(去 app 化后本工具
    # 不假设 spec 拓扑与参数值无关),两份 spec 的列集就可能不一致,row_columns 算出的列要么
    # 漏列(KeyError)要么多出恒 NaN 的幽灵列(parquet 严格 schema 下直接报错)。
    spec0 = mod.build_pattern(mod.Params.from_dict(apply_overrides(base_yaml, study.WIDE_OVERRIDES, filter_min), strict=True))
    columns = row_columns(cfg, cls, spec0) + ["fold_Y", "fold_6M"]

    out = REPO / OUT_DIR
    lt, base_dir, seg_dir = out / "longtable", out / "baseline", out / "segments"
    lt.mkdir(parents=True, exist_ok=True)
    (seg_dir if deferred else base_dir).mkdir(exist_ok=True)
    S.write_run_meta(lt, run_meta_of(APP, cfg_in, cl, label_mode))
    done, parts0, n_shard = prepare_resume(out)
    filtered, empty = parts0["filtered"], parts0["empty"]
    n_done0 = len(done)
    _, _, buf_start, buf_end = _window_bounds(START_DATE, END_DATE, HEAD_BUFFER, LABEL_HORIZON)
    pkls = [p for p in _list_pkls(str(REPO / DATA_DIR), TICKER_REGEX) if p.stem not in done]
    print(f"股票 {len(pkls)} 待扫(已完成 {len(done)}),窗 {buf_start}..{buf_end},HEAD_BUFFER={HEAD_BUFFER}")

    t0 = time.time(); cpu0 = time.process_time()
    buf, base_buf, seg_buf, per_ms = [], [], [], []
    n_done = n_det = n_skip = n_hit = n_rows = n_base = n_err = 0

    def flush():
        """把缓冲里的这批股票落成同一个分片号并提交;filtered / empty 名单在提交之后重写。"""
        nonlocal n_shard
        if buf or base_buf or seg_buf:
            tables = {}
            if seg_buf:
                tables["segments"] = pd.DataFrame(seg_buf, columns=SEGMENT_COLS).astype({"seg_id": "int64"})
            if base_buf:
                b = pd.concat(base_buf, ignore_index=True)
                b["symbol"] = b["symbol"].astype("category")
                tables["baseline"] = b
            if buf:
                df = pd.DataFrame(buf, columns=columns[:-2]); df["fold_Y"], df["fold_6M"] = _fold_cols(df["buy_date"])
                tables["longtable"] = _shrink_dtypes(df)
            write_shard(out, n_shard, tables)
            n_shard += 1; buf.clear(); base_buf.clear(); seg_buf.clear()
        # 只在非空时写:空 DataFrame.to_csv 写出的文件下一轮 read_csv 会抛 EmptyDataError
        if filtered:
            pd.DataFrame({"symbol": filtered}).to_csv(out / "filtered_symbols.csv", index=False)
        if empty:
            pd.DataFrame({"symbol": empty}).to_csv(out / "empty_symbols.csv", index=False)

    def on_result(res):
        nonlocal n_done, n_det, n_skip, n_hit, n_rows, n_base, n_err
        symbol, rows, segs, base_rows, err, t_ms = res
        n_done += 1
        if err:
            n_err += 1; print("ERR", symbol, err)          # 不计入 done,下次自动重试
        elif rows is None:
            n_skip += 1; filtered.append(symbol)            # 空窗口/量能未达标,已处理但无行
        else:
            n_det += 1; per_ms.append(t_ms)
            if rows:
                n_hit += 1; n_rows += len(rows); buf.extend(rows)
                if deferred:
                    seg_buf.extend((symbol, sid, span_key_json(sk)) for sid, sk in segs.items())
            if base_rows is not None and len(base_rows):
                n_base += len(base_rows); base_buf.append(base_rows)
            elif not rows:
                empty.append(symbol)                        # 进了 detector,既无长表行也无基线行
        if n_done % SHARD_STOCKS == 0 or n_done == len(pkls):
            flush()
        if n_done % 200 == 0:
            print(f"  {n_done}/{len(pkls)} 股 · {n_rows} 行 · {time.time() - t0:.0f}s")

    _scan_pool([str(p) for p in pkls], _worker, (cfg, buf_start, buf_end, START_DATE, END_DATE, VOLUME_MIN),
               WORKERS, on_result)
    flush()
    wall = time.time() - t0

    # 每股 scan_one_stock 耗时分布 + 每检测组合均摊(本轮;台账自证项;n_combo 全程实算,不手写)
    per_ms_arr = np.array(per_ms, dtype=float)
    p50 = float(np.percentile(per_ms_arr, 50)) if len(per_ms_arr) else float("nan")
    p90 = float(np.percentile(per_ms_arr, 90)) if len(per_ms_arr) else float("nan")
    avg_combo_ms = float(per_ms_arr.sum() / (n_det * n_combo)) if n_det and n_combo else float("nan")

    # run_stats.jsonl 每轮追加一行:「股数/耗时/每股 p50-p90-均摊」全是本轮计数器,resume 全跳过时会被
    # 清零;改为 append-only 历史 + 每次全量重算累计,同时保留"本轮"两组数,两者互不覆盖。
    run_stats_path = out / "run_stats.jsonl"
    run_entry = {"ts": pd.Timestamp.now().isoformat(), "n_pending_start": len(pkls),
                 "n_det": n_det, "n_skip": n_skip, "n_hit": n_hit, "n_err": n_err, "n_rows": n_rows,
                 "wall_s": wall, "cpu_s": time.process_time() - cpu0,
                 "worker_sum_ms": float(per_ms_arr.sum()), "per_ms": per_ms}
    # 补写前置换行:上一轮若被 kill/磁盘满截断、文件末字节不是 "\n",裸追加会把本轮整行拼到上轮
    # 半行尾部形成一条烂行,本轮统计会跟着被当成损坏行丢弃。先补一个换行把上轮的半行封口。
    if run_stats_path.exists() and run_stats_path.stat().st_size > 0:
        with run_stats_path.open("rb") as f:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                with run_stats_path.open("a") as f2:
                    f2.write("\n")
    with run_stats_path.open("a") as f:
        f.write(json.dumps(run_entry) + "\n")
    # 半行容错:append 后 kill/磁盘满可能截断末行(全宇宙一轮的 per_ms 单行 ≈150KB),跳过损坏行,不整体崩。
    hist = []
    for ln in run_stats_path.read_text().splitlines():
        if not ln.strip():
            continue
        try:
            hist.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    n_runs = len(hist)
    cum_det = sum(h["n_det"] for h in hist); cum_skip = sum(h["n_skip"] for h in hist)
    cum_hit = sum(h["n_hit"] for h in hist); cum_err = sum(h["n_err"] for h in hist)
    cum_wall = sum(h["wall_s"] for h in hist); cum_cpu = sum(h["cpu_s"] for h in hist)
    cum_worker_ms = sum(h["worker_sum_ms"] for h in hist)
    cum_per_ms_arr = np.array([x for h in hist for x in h["per_ms"]], dtype=float)
    cum_p50 = float(np.percentile(cum_per_ms_arr, 50)) if len(cum_per_ms_arr) else float("nan")
    cum_p90 = float(np.percentile(cum_per_ms_arr, 90)) if len(cum_per_ms_arr) else float("nan")
    cum_avg_combo_ms = float(cum_per_ms_arr.sum() / (cum_det * n_combo)) if cum_det and n_combo else float("nan")
    n_universe = n_done0 + len(pkls)   # done0∪pkls = 本轮启动时的全宇宙(TICKER_REGEX 命中数),裁定用此算总股数

    # 台账 + fold 计数分布(真扫格粒度、宽进 where)。两个数字各用最省的路子拿,**不把全部分片
    # concat 成一张表**:整表要按全部列付内存(3522 万行 ≈ 14GB,坑见 reference.md §6 坑 11)。
    parts = sorted(lt.glob("part-*.parquet"))
    combo_cols = [col_of(d) for d in study.SCAN_GRID if cls.kinds[d] != "F"]
    # 累计行数:只读 parquet 文件元数据。不用 sum(run_stats 的 n_rows)——被 OOM killer 杀掉的轮次
    # 写了分片却没活到写 run_stats,其行数贡献会永久丢失;元数据口径是「盘上有什么就数什么」。
    # 本轮结束时盘上分片全部已提交(未提交的在续跑准备时已删、本轮写的都提交过)。
    n_rows_all = sum(pq.ParquetFile(p).metadata.num_rows for p in parts)
    side_dir = seg_dir if deferred else base_dir
    n_side_all = sum(pq.ParquetFile(p).metadata.num_rows for p in sorted(side_dir.glob("part-*.parquet")))
    side_line = (f"买点事件表行(盘上分片元数据) {n_side_all}" if deferred
                 else f"逐日基线行(本轮 {n_base};盘上分片元数据累计 {n_side_all})")
    # 格 × fold 分布:逐片只读需要的那几列、逐片 groupby 再累加。峰值只剩一片的这几列。
    cnt = pd.Series([], dtype=int)
    for _p in parts:
        c = pd.read_parquet(_p, columns=combo_cols + ["fold_Y"]).groupby(combo_cols + ["fold_Y"], observed=True).size()
        cnt = c if not len(cnt) else cnt.add(c, fill_value=0)
    cnt_line = (f"min {cnt.min():.0f} / p50 {cnt.median():.0f} / max {cnt.max():.0f}" if len(cnt) else "(暂无数据)")
    lines = [f"# multivar_scan 台账 · {APP}", "",
             f"- 窗:{START_DATE}..{END_DATE};HEAD_BUFFER={HEAD_BUFFER};LABEL_HORIZON={LABEL_HORIZON};FIRST_PASSAGE_K={FIRST_PASSAGE_K};标签模式 {label_mode}",
             f"- 过滤:price [{PRICE_MIN},{PRICE_MAX}],volume_min {VOLUME_MIN};底座 {study.BASE_YAML}(base 指纹 {cl['fingerprints']['base'][:12]});宽进 {study.WIDE_OVERRIDES}",
             f"- study 指纹 {cl['fingerprints']['study'][:12]};源码指纹 {cl['fingerprints']['source']['hash'][:12]};尺子指纹 {cl['fingerprints']['ruler'][:12]};classification 生成于 {cl['generated_at']} @ {cl['git_head']}",
             f"- SCAN_GRID:{cl['scan_grid']}", f"- WHERE_LEVELS:{cl['where_levels']}",
             f"- 分类:{ {col_of(d): k for d, k in cls.kinds.items()} }", f"- where 轴:{ {col_of(d): v for d, v in cls.where_fields.items()} }",
             f"- 研究设计 {cl['design']};检测组合数(detection_combos 实算,F 维不进组合):{n_combo}",
             f"- 断点续跑:本轮启动时 done 集共 {n_done0} 股 = 长表分片 symbol({len(parts0['longtable'])}) ∪ 基线分片 symbol({len(parts0['baseline'])}) ∪ filtered_symbols.csv({len(parts0['filtered'])}) ∪ empty_symbols.csv({len(parts0['empty'])});err 不计入 done、下次自动重试;总股数(TICKER_REGEX 命中全宇宙) {n_universe}",
             f"- 股数(本轮):待扫 {len(pkls)} / 进 detector {n_det} / 过滤 {n_skip} / 有 match {n_hit} / 异常 {n_err};累计行(盘上分片元数据) {n_rows_all};{side_line}",
             f"- 股数(累计跨 {n_runs} 轮 run_stats.jsonl):进 detector {cum_det} / 过滤 {cum_skip} / 有 match {cum_hit} / 异常事件 {cum_err} 次(同一 symbol 每轮重试各计一次,不去重)",
             f"- 耗时(本轮):wall {wall:.0f}s @ {WORKERS} workers;worker 侧 scan_one_stock 累计 {per_ms_arr.sum() / 1000:.1f}s(≈总计算量,单线程 detector/solve 无 I/O 等待,CPU·s 量级);本进程(编排调度)cpu {time.process_time() - cpu0:.1f}s",
             f"- 耗时(累计跨 {n_runs} 轮):wall {cum_wall:.0f}s;worker 侧累计 {cum_worker_ms / 1000:.1f}s;本进程 cpu 累计 {cum_cpu:.1f}s",
             f"- 每股 scan_one_stock 耗时 ms(本轮 {len(per_ms)} 股):p50 {p50:.1f} / p90 {p90:.1f};每检测组合均摊 {avg_combo_ms:.3f}ms/股",
             f"- 每股 scan_one_stock 耗时 ms(累计 {len(cum_per_ms_arr)} 股):p50 {cum_p50:.1f} / p90 {cum_p90:.1f};每检测组合均摊 {cum_avg_combo_ms:.3f}ms/股",
             f"- 宽进 where 下真扫格 × 年折的 match 数分布:{cnt_line}", ""]
    (out / "ledger.md").write_text("\n".join(lines))
    print("\n".join(lines))


# ---------------------------------------------------------------- 延迟标签
def _label_worker(item, seg_dir, data_dir, buf_start, buf_end, start_date, end_date, horizon, k):
    """一只股票的延迟标签:按扫描同口径重切窗口,对买点事件表里本股的每个买点事件现算首次穿越四态。

    item = (symbol, 分片文件名)。返回 (分片文件名, symbol, DataFrame | None, err)。
    重算的 seg_id 必须与表里记录的一致、区间不得超出窗口——对不上说明表坏了或数据文件与扫描时不同。"""
    from path2.eval import spans_first_passage
    from path2_web.data import slice_window
    symbol, shard = item
    try:
        segs = pd.read_parquet(Path(seg_dir) / shard, filters=[("symbol", "==", symbol)])
        win = slice_window(pd.read_pickle(Path(data_dir) / f"{symbol}.pkl"), buf_start, buf_end)
        s, e = pd.to_datetime(start_date), pd.to_datetime(end_date)
        lo = int(win["date"].searchsorted(s, "left"))
        hi = int(win["date"].searchsorted(e, "right")) - 1
        M, _ = stock_scales(win)
        out = []
        for sid, sk in zip(segs["seg_id"].tolist(), segs["span_key"].tolist()):
            spans = [(int(a), int(b)) for a, b in json.loads(sk)]
            if seg_id_of(spans) != sid:
                raise ValueError(f"买点事件表里 seg_id={sid} 与它记录的区间 {sk} 对不上,表已损坏")
            if max(b for _, b in spans) >= len(win):
                raise ValueError(f"买点事件区间 {sk} 超出重切的窗口(共 {len(win)} 根):数据文件与扫描时不同")
            fp = spans_first_passage(win, spans, horizon, k, sample_window=(lo, hi), M=M)
            out.append((symbol, sid, *(fp[st] for st in STATES)))
        df = pd.DataFrame(out, columns=LABEL_TABLE_COLS).astype({"seg_id": "int64", **dict.fromkeys(FP_COLS, "int32")})
        return (shard, symbol, df, None)
    except Exception as ex:  # noqa: BLE001
        tb_tail = "".join(traceback.format_exc().splitlines(keepends=True)[-6:]).rstrip("\n")
        return (shard, symbol, None, f"{type(ex).__name__}: {ex}\n{tb_tail}")


def compute_deferred_labels(app: str, window: str, cfg, *, manifest_hash: str, confirm_window: str) -> Path:
    """正式验证时给延迟标签模式的扫描结果补算标签,写 <window>/labels/part-NNNN.parquet(与 segments 同号)。

    先过确认窗守卫(purpose="validate",带验证清单与要打开的那一段);不放行 → HoldoutLocked,一个标签
    都不算、labels 目录也不建。逐股按 run_meta 同口径重切窗口(首部缓冲、标签窗长同扫描),对买点事件表
    里每个买点事件用 spans_first_passage 现算首次穿越四态。cfg 只提供 data_dir 与 workers。
    断点续跑:已有 labels 分片的 segments 分片整片跳过;某片里任一只股票失败,该片不落盘,全部跑完后
    报错,排除问题后重跑即从断点接着算。返回 labels 目录。
    """
    import holdout
    import study_io as S
    out = REPO / "outputs" / "tune_gates" / app / window
    meta = S.load_run_meta(out / "longtable")
    if meta["app"] != app:
        raise SystemExit(f"{out} 的扫描结果属于 app {meta['app']!r},不是 {app!r}")
    if meta.get("label_mode") != "deferred":
        raise SystemExit(f"{app}/{window} 的扫描结果在扫描时就已经算好了涨跌结果,不需要补算")
    holdout.guard_label_access(app, meta["start_date"], meta["end_date"], "validate",
                               manifest_hash=manifest_hash, confirm_window=confirm_window)
    seg_dir, lab_dir = out / "segments", out / "labels"
    committed = committed_shards(out)
    if committed is None:
        raise SystemExit(f"{out} 没有分片提交清单,判断不了哪些买点事件片是完整写完的,不能补算")
    lab_dir.mkdir(exist_ok=True)
    _, _, bs, be = _window_bounds(meta["start_date"], meta["end_date"], meta["head_buffer"], meta["label_horizon"])
    left, got, failed, items = {}, {}, set(), []
    for p in sorted(seg_dir.glob("part-*.parquet")):
        if p.name not in committed or (lab_dir / p.name).exists():
            continue
        syms = pd.read_parquet(p, columns=["symbol"])["symbol"].unique().tolist()
        if not syms:
            _write_parquet(pd.DataFrame(columns=LABEL_TABLE_COLS), lab_dir / p.name)
            continue
        left[p.name], got[p.name] = len(syms), []
        items += [(sym, p.name) for sym in syms]
    print(f"[延迟标签] {app}/{window}:待补算 {len(left)} 片 / {len(items)} 只股票")
    n_err = 0

    def on_result(res):
        nonlocal n_err
        shard, symbol, df, err = res
        if err:
            n_err += 1; failed.add(shard); print("ERR", symbol, err)
        else:
            got[shard].append(df)
        left[shard] -= 1
        if left[shard] == 0:
            if shard not in failed:
                _write_parquet(pd.concat(got[shard], ignore_index=True), lab_dir / shard)
            del got[shard]

    _scan_pool(items, _label_worker, (str(seg_dir), str(REPO / cfg.data_dir), bs, be, meta["start_date"],
                                      meta["end_date"], meta["label_horizon"], meta["first_passage_k"]),
               cfg.workers, on_result)
    if n_err:
        raise SystemExit(f"[延迟标签] {n_err} 只股票补算失败(见上方 ERR),所在的 {len(failed)} 片没有落盘;"
                         "其余已保存,排除问题后重跑会从断点接着算")
    return lab_dir


def read_with_labels(longtable_dir, columns) -> Iterator[pd.DataFrame]:
    """逐片读延迟标签模式的长表,按 (symbol, seg_id) 接上 labels 里的四态列(fp_up/fp_down/fp_both/fp_none)。

    columns = 要输出的列(顺序即输出顺序),四态列取自 labels、其余取自长表。只读已提交的长表分片;
    没有提交清单、同号 labels 分片缺失,或任一行找不到标签 → ValueError(标签没补算完就读,计数会
    静默偏少)。每片产出一个 DataFrame,交给 region_core.prepare 逐片处理。"""
    lt = Path(longtable_dir)
    lab = lt.parent / "labels"
    committed = committed_shards(lt.parent)
    if committed is None:
        raise ValueError(f"{lt.parent} 没有分片提交清单,判断不了哪些长表分片是完整写完的,不能读")
    table_cols = list(dict.fromkeys([c for c in columns if c not in FP_COLS] + ["symbol", "seg_id"]))
    for part in sorted(p for p in lt.glob("part-*.parquet") if p.name in committed):
        lp = lab / part.name
        if not lp.exists():
            raise ValueError(f"{lp} 不存在:这一片的标签还没补算,先跑 compute_deferred_labels")
        df = pd.read_parquet(part, columns=table_cols)
        labels = pd.read_parquet(lp)
        sym_dtype = df["symbol"].dtype
        df["symbol"] = df["symbol"].astype(str)
        labels["symbol"] = labels["symbol"].astype(str)
        merged = df.merge(labels, on=["symbol", "seg_id"], how="left", validate="many_to_one")
        miss = merged["fp_up"].isna()
        if miss.any():
            raise ValueError(f"{part.name} 有 {int(miss.sum())} 行找不到标签(如 symbol={merged.loc[miss, 'symbol'].iat[0]} "
                             f"seg_id={merged.loc[miss, 'seg_id'].iat[0]}):标签不全,不能读")
        merged[FP_COLS] = merged[FP_COLS].astype("int64")
        merged["symbol"] = merged["symbol"].astype(sym_dtype)
        yield merged[list(columns)]
