# -*- coding: utf-8 -*-
"""tune-gates · Claude 的唯一调用面。

**这个文件存在的理由**:用户只想说「帮我调 X 的参数」,不想知道研究声明 / 分类表 / 扫描口径 / 指纹 / 账本
这些内部机制。所有机制操作从这里发起,机制词不外泄——禁止词清单与人话译法见 SKILL.md。

每个公开函数是薄包装:整理参数 → 调对应模块 → 返回摘要。机械闸与拒绝理由都在被包装的模块里,这里不重复检查。
  status                       状态推导(stages.derive,只读)
  open_round / record_ruling   开局核对(写 open,机械闸 7)/ 人工裁定(写 ruling)
  edge                         优势检查(edge.run)
  propose_ranges / install     定范围(grid_propose.propose_ranges)/ 准入安装窗口声明(grid_propose.install_study)
  setup / scan / compare       重生成分类表 / 扫描(multivar_scan.run)/ 一致性验证(compare_longtable.run)
  screen / find / cell         筛选(screen.run)/ 联合识别(region_find.run)/ 单格查询(region_find.cell_query)
  preregister / validate       冻结验证清单(validate.preregister)/ 在一段确认窗上开窗检验(validate.validate)
  confirm_rows                 学习端在确认窗上检闸的取数口(feature-study fs.run 的缺省 load_rows)
  adopt / retire               定案写入(adopt.adopt)/ app 退役清理
最小关心改进 δ 一律取 `resolve_delta`;窗口天数、对比族大小等口径推导量由被包装的模块从运行口径推出。
危险动作(adopt / retire)默认 confirm=False 只返回 diff 或清单,不动手。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S  # noqa: E402
import holdout  # noqa: E402
import ledger  # noqa: E402

OPEN_PROBE_STOCKS = 400          # 开局核对抽样探测数据覆盖的股票数(不足则全取)
CONFIRM_PREFIX = "confirm_"      # 确认窗扫描的窗口名:confirm_<backward|forward>_<冻结的扫描声明哈希前 8 位>
WINDOW_FOLD = "__window__"       # 确认窗整段合成一折时的临时折列
RULINGS_ON_MANIFEST = ("power_notified", "open_low_power")   # 针对某份验证清单的裁定
FEATURE_STUDY_FS = REPO / ".claude/skills/feature-study/fs.py"
REGISTRY = "docs/feature_candidates.md"                     # 登记簿(相对 repo root)


@dataclass(frozen=True)
class Settings:
    """一跑的口径与预算。数据目录默认取 configs/path2_web.yaml,其余口径默认值迁自改造前的 apps/bb_v1/run.py。

    ★ 标记的字段进 study_io.RUN_CALIBER:它们改了**必须换 window**(新开输出目录),
    write_run_meta 会拒绝把不同口径写进同一目录。未标记的(workers / top_n / b_boot /
    split_half_seeds / cmp_* 等)随便改,不影响已有扫描结果复用。
    """
    # ---- 数据与时间窗 ----
    data_dir: str = str(holdout.default_data_dir())   # configs/path2_web.yaml 的 dataset_dir,导入时读一次
    start_date: str = "2024-01-01"          # ★
    end_date: str = "2026-01-01"            # ★
    head_buffer: int = 250                  # ★
    label_horizon: int = 40                 # ★
    first_passage_k: float = 5.0            # ★
    price_min: float = 0.5                  # ★
    price_max: float = 30.0                 # ★
    volume_min: float = 10000.0             # ★
    ticker_regex: str | None = None         # None = 全宇宙;小正则试跑→放开全宇宙是支持用法
    shard_stocks: int = 200
    workers: int = 16                       # 机器级,不随 app 变;定标见 reference.md §3
    # ---- 一致性验证 ----
    cmp_ticker_regex: str = r"^[A-Z][A-C]"  # 抽样范围;比过的股票须 >= compare_longtable.MIN_SYMBOLS 或含扫描范围全部股票
    cmp_seed: int = 11
    cmp_n_random_cells: int = 64
    cmp_n_tight_cells: int = 12
    min_win_bars: int = 1
    # ---- 识别 ----
    fold_col: str = "fold_Y"
    folds: tuple = ("2024", "2025")
    neighbor_axes: str = "all"
    b_boot: int = 300
    boot_seed: int = 0                      # bootstrap 重采样种子;与 split-half 种子无关
    split_half_seeds: tuple = tuple(range(20))
    top_n: int = 20
    # ---- 预算与筛选 ----
    min_effect_pt: float = 2.0              # 最小关心改进(首次穿越率,点);功效线由它与本窗优势检查实测值反推
    min_segments_floor: int = 30            # 买点事件数下限:少于它的格不下结论
    screen_fdr_q: float = 0.10              # 筛选阶段多重比较的 BH 阈值
    noninferiority_pt: float | None = None  # 删闸非劣效界(点);None = 取 min_effect_pt


def out_dir_of(app: str, window: str, repo: Path | None = None) -> Path:
    """一跑的输出根目录。window 区分同一 app 的多份扫描结果(筛选窗、联合窗、确认窗口径不同,必须分开放)。"""
    return (Path(repo) if repo else REPO) / "outputs" / "tune_gates" / app / window


def _cfg(cfg: Settings | None, overrides: dict) -> Settings:
    cfg = cfg or Settings()
    return replace(cfg, **overrides) if overrides else cfg


def resolve_delta(app: str, cfg: Settings | None = None) -> float:
    """最小关心改进 δ(比例,0.02 = 2 点)的唯一取法:该 app 账本里最近一条 δ 裁定(ruling,topic = "delta",
    取值单位是点);没有裁定时取 Settings 的 min_effect_pt(点)。feature-study 的 fs.resolve_delta 调这里。"""
    for r in reversed(ledger.read(app)):
        if r["kind"] == "ruling" and r["data"]["topic"] == "delta":
            v = r["data"]["value"]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                raise ValueError(f"账本里的最小关心改进裁定取值不是正数(单位点): {v!r}")
            return float(v) / 100
    return float((cfg or Settings()).min_effect_pt) / 100


# ---------------------------------------------------------------- 状态、开局、裁定

def status(app: str, *, cfg: Settings | None = None) -> dict:
    """这个 app 的调参走到哪一步、各阶段的证据还有没有效、下一步做什么(stages.derive)。**不写任何文件。**"""
    import stages
    return stages.derive(app, cfg=cfg)


def open_round(app: str, *, cfg: Settings | None = None) -> dict:
    """开局核对(机械闸 7):从数据文件的实际覆盖划出训练窗前后两段留作最后验证的数据,写一条 open 记录。

    抽样 OPEN_PROBE_STOCKS 只股票探测数据起止与交易日历(不足则全取);训练窗 = Settings 的买点区间(终点取不晚于
    end_date 的最后一个交易日);两段确认窗由 `holdout.confirm_windows` 按首部缓冲与标签窗长推出。
    这个 app 已开局、且那次划出的两段还没都验证过 → 拒绝:重划会让按旧划分做的判断失去依据。
    返回 {"record", "train", "confirm", "data_start", "data_end", "n_probed", "text"}。"""
    cfg = cfg or Settings()
    recs = ledger.read(app)
    opens = [i for i, r in enumerate(recs) if r["kind"] == "open"]
    if opens and ({r["data"]["confirm_window"] for r in recs[opens[-1] + 1:] if r["kind"] == "extrapolate"}
                  != set(ledger.CONFIRM_NAMES)):
        raise SystemExit(f"「{app}」已经做过开局核对,留作最后验证的两段数据还没验证完;现在重新划分,"
                         "之前按这个划分做的判断就失去了依据,不能重做。")
    cov = holdout.probe_coverage(cfg.data_dir, OPEN_PROBE_STOCKS)
    cal = holdout.trading_calendar(cfg.data_dir, OPEN_PROBE_STOCKS)
    train_days = cal[cal <= pd.Timestamp(cfg.end_date)]
    if not len(train_days):
        raise SystemExit(f"数据从 {cov['data_start']} 才开始,训练期截止日 {cfg.end_date} 之前没有交易日")
    w = holdout.confirm_windows(cfg.start_date, train_days[-1], calendar=cal, head_buffer=cfg.head_buffer,
                                horizon=cfg.label_horizon)
    rec = ledger.make_record(
        "open", app, actor="tune.open_round", round=None,
        window={"start": w["train"]["start"], "end": w["train"]["end"]}, label_horizon=cfg.label_horizon,
        head_buffer=cfg.head_buffer, git_head=S._git_head(), base_fingerprint=None, source_fingerprint=None,
        ruler_fingerprint=ledger.ruler_fingerprint(), data={**w, "n_probed": cov["n_probed"]})
    ledger.append(rec)
    t, b, f = w["train"], w["confirm"]["backward"], w["confirm"]["forward"]
    text = (f"训练期买点 {t['start']} 到 {t['end']}(涨跌结果看到 {t['label_end']})。留作最后验证的数据:"
            f"{holdout.WINDOW_WORDS['backward']}是 {b['start']} 到 {b['end']} 的买点,"
            f"{holdout.WINDOW_WORDS['forward']}是 {f['start']} 到 {f['end']} 的买点。"
            f"数据截至 {w['data_end']}(抽查了 {cov['n_probed']} 只股票)。")
    return {"record": rec, "train": t, "confirm": w["confirm"], "data_start": w["data_start"],
            "data_end": w["data_end"], "n_probed": cov["n_probed"], "text": text}


def record_ruling(app: str, topic: str, value, *, manifest_hash: str | None = None, note: str = "") -> dict:
    """写一条人工裁定(ruling),返回写入的记录。topic 取值见 ledger.RULING_TOPICS。value 的约定:
    delta = 最小关心改进(点);delete_gate = {参数键: 关闸值},空 dict 或 None = 决定不删。
    「已告知预期把握」「把握不足也照样打开」两类裁定针对某份验证清单,必须给 manifest_hash。"""
    if topic in RULINGS_ON_MANIFEST and not manifest_hash:
        raise SystemExit("这条裁定针对的是某份冻结的验证清单,要给清单哈希。")
    if topic == "delta" and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
        raise SystemExit(f"最小关心改进要给正数(单位点),实际 {value!r}")
    if topic == "delete_gate" and not (value is None or (isinstance(value, dict) and all(
            isinstance(k, str) and ledger.AXIS_RE.match(k) and not k.startswith("feature:") for k in value))):
        raise SystemExit(f"删闸裁定要给 {{参数键: 关闸值}}(参数键写 section.field;决定不删给空),实际 {value!r}")
    data = {"topic": topic, "value": value, **({"manifest_hash": manifest_hash} if manifest_hash else {})}
    return ledger.append(ledger.make_record(
        "ruling", app, actor="tune.record_ruling", round=None, window=None, label_horizon=None, head_buffer=None,
        git_head=None, base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None, data=data, note=note))


# ---------------------------------------------------------------- 优势检查、定范围、落地

def _latest_wide_overrides(app: str) -> dict:
    studies = sorted((Path(S.APPS_DIR) / app / "windows").glob("*/study.py"), key=lambda p: p.stat().st_mtime)
    if not studies:
        raise SystemExit(f"「{app}」还没有任何窗口声明,不知道优势检查时要放开哪些闸、放到多松;请给出放开值。")
    return S.load_study(studies[-1]).WIDE_OVERRIDES


def edge(app: str, *, wide_overrides: dict | None = None, cfg: Settings | None = None, restart: bool = False) -> dict:
    """优势检查(edge.run):这个走势的买点比同一天、同样波动水平的随机买入日好不好,样本能分辨多小的改进。

    wide_overrides({section: {field: 放开值}})缺省取这个 app 最近写过的窗口声明里的放开值,一个都没有 → 要求显式给。
    δ 取 `resolve_delta`。筛选的对比族大小 m 在筛选之前只能预估 = 2 ×(检测参数个数 × 2 + 在役闸数):检测参数按
    筛选时松一档、紧一档各一个替代档计(定范围里类别为「检测参数」的条数,尺子参数不计),不看定范围给没给出建议档;
    报告与记录里标「预估」。restart=True 清掉上次的扫描结果重扫。
    返回 {"report", "verdicts", "source_note", "delta", "m_estimate": {"m", "detect_params", "gates_in_service"}}。"""
    import edge as E
    import grid_propose as G
    cfg = cfg or Settings()
    wide = _latest_wide_overrides(app) if wide_overrides is None else wide_overrides
    delta = resolve_delta(app, cfg)
    pr = G.propose_ranges(app, E._app_module(app), cfg=cfg)
    n_detect = sum(a["category"] == "检测参数" for a in pr["admission"].values())
    n_gate = sum(a["category"] in (G.CAT_IN_SERVICE, G.CAT_USEFUL) for a in pr["admission"].values())
    m = 2 * (n_detect * 2 + n_gate)
    res = E.run(app, cfg, wide_overrides=wide, delta=delta, m=m, B=cfg.b_boot, seed=cfg.boot_seed, restart=restart)
    return {"report": res["report"], "verdicts": res["verdicts"], "source_note": res["source_note"], "delta": delta,
            "m_estimate": {"m": m, "detect_params": n_detect, "gates_in_service": n_gate}}


def propose_ranges(app: str, *, app_module: str | None = None, base_yaml: str = "params.yaml",
                   cfg: Settings | None = None, sample_stocks: int = 200) -> dict:
    """定范围(grid_propose.propose_ranges):看任何收益之前,把参数能怎么调算清楚——尺子、逐档合法性、学习端准入、
    建议松 / 紧一档、筛选检测组合数与耗时、只读闸清单。**不输出任何收益。**
    app_module 缺省按 path2_apps/<app>/dag_spec.py。六部分原样返回,由 Claude 译成人话给用户增删改。"""
    import edge as E
    import grid_propose as G
    return G.propose_ranges(app, app_module or E._app_module(app), base_yaml=base_yaml, cfg=cfg or Settings(),
                            sample_stocks=sample_stocks)


def install(app: str, *, window: str, stage: str, wide_overrides: dict, scan_grid: dict, where_levels: dict,
            tight_wheres: dict | None = None, app_module: str | None = None, base_yaml: str = "params.yaml",
            cfg: Settings | None = None, apps_dir: Path | None = None) -> dict:
    """网格过准入表(机械闸 3)后落地成这个窗口的研究声明,随即生成分类表(grid_propose.install_study)。

    stage = "screen"(筛选:工作点 + 单翻转 + 两两翻转)| "grid"(联合:笛卡尔积)。准入没过 → 人话列出全部原因,
    一个文件都不写。**写声明会让该窗口已有的扫描结果作废**——调用方须先确认用户知道。"""
    import edge as E
    import grid_propose as G
    return G.install_study(app, window=window, stage=stage, app_module=app_module or E._app_module(app),
                           base_yaml=base_yaml, wide_overrides=wide_overrides, scan_grid=scan_grid,
                           where_levels=where_levels, tight_wheres=tight_wheres or {}, cfg=cfg or Settings(),
                           apps_dir=apps_dir)


def setup(app: str, *, window: str, apps_dir: Path | None = None) -> dict:
    """从 apps/<app>/windows/<window>/study.py 重新生成分类表 classification.json。幂等。

    跑 classify + 全部静态守卫 + 推导 + 四指纹。守卫在这里响亮失败,不等到扫描:
    E 维不许进 SCAN_GRID / DESIGN 取值 / REF_POINT 覆盖范围与取值 / 逐档合法性 /
    TIGHT_WHERES 键在网格内 / negation dst 谓词轴。
    """
    import app_setup  # noqa: F401 —— 仅为触发其模块级 sys.path 设置
    from path2 import config
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    study_path = S.study_path(app, window, apps_dir)
    if not study_path.exists():
        raise SystemExit(f"{study_path} 不存在:该窗口尚未接入,先用 tune.propose_ranges + tune.install 落地网格")
    study = S.load_study(study_path)
    mod = S.import_app(study)
    config.set_runtime_checks(True)
    cl = S.build_classification(app, window, study, mod, study_path)
    S.write_classification(app, window, cl, apps_dir=apps_dir)
    return {"app": app, "window": window, "design": cl["design"],
            "kinds": cl["kinds"], "filter_fields": cl["filter_fields"],
            "where_fields": cl["where_fields"], "end_node": cl["end_node"],
            "bound_nodes": cl["bound_nodes"], "detection_combos": cl["detection_combos"],
            "source_files": cl["fingerprints"]["source"]["files"]}


def retire(app: str, *, confirm: bool = False, delete_notes: bool = False,
           apps_dir: Path | None = None, repo: Path | None = None) -> dict:
    """app 退役清理。**confirm=False 时只返回清单,一个文件都不删。**

    分组按「误删=永久丢失 vs 误留=多几个文件」的不对称设计:notes.md 是跨轮沉淀,意义不随
    app 消失,默认保留、要删须开开关;样本使用账本不在 app 目录里,永不删。
    重产物先过可再生性实检,验不过一律降到 blocked(只报不删)。
    只走精确路径,绝不按 app 名 glob。
    """
    import app_setup
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    repo = Path(repo) if repo else REPO
    plan = app_setup.plan_delete(app, apps_dir, repo, delete_notes)
    app_setup._execute_delete(plan, apps_dir / app, confirm)
    return plan


# ---------------------------------------------------------------- 扫描、核对、识别

def scan(app: str, *, window: str, label_mode: str = "full", cfg: Settings | None = None, **overrides) -> dict:
    """扫描出候选长表(multivar_scan.run,断点续跑)。**这是最贵的一步**,全宇宙可能几十分钟到几小时。

    overrides 直接覆盖 Settings 的字段(如 ticker_regex="^A[A-C]" 先小范围试跑)。★ 口径字段改了必须换 window。
    扫描区间碰到留作验证的数据时自动改走只记买点事件、不算涨跌结果的模式(返回里的 label_mode 是实际模式)。
    返回 {"app", "window", "out_dir", "label_mode", "n_shards"}。"""
    import multivar_scan as MS
    cfg = _cfg(cfg, overrides)
    out = out_dir_of(app, window)
    MS.run(app, cfg, str(out.relative_to(REPO)), label_mode=label_mode)
    lt = out / "longtable"
    return {"app": app, "window": window, "out_dir": str(out), "label_mode": S.load_run_meta(lt)["label_mode"],
            "n_shards": len(list(lt.glob("part-*.parquet")))}


def compare(app: str, *, window: str, cfg: Settings | None = None, **overrides) -> dict:
    """一致性验证(compare_longtable.run)。**红线:mismatch 必须为 0,否则不得读识别结果**(筛选与联合识别入口自己核)。

    ★ 口径字段不从 cfg 取——扫描时写进 run_meta.json、被包装的模块内部读(单一来源);cfg 只提供抽样与并行旋钮。
    返回 {"app", "window", "log", "mismatch"}(日志里没有结论行时 mismatch 为 None)。"""
    import compare_longtable
    cfg = _cfg(cfg, overrides)
    out = out_dir_of(app, window)
    compare_longtable.run(app, cfg, str((out / "longtable").relative_to(REPO)))
    log = out / "compare_longtable.log"
    hits = [ln for ln in log.read_text(encoding="utf-8").splitlines() if "mismatch=" in ln] if log.exists() else []
    return {"app": app, "window": window, "log": str(log),
            "mismatch": int(hits[-1].split("mismatch=")[1].split(",")[0]) if hits else None}


def screen(app: str, *, window: str, working_point: dict | None = None, cfg: Settings | None = None,
           **overrides) -> dict:
    """筛选(screen.run):在工作点附近逐个改一档、逐道关闸,多重比较后看哪些改动分辨得出。δ 取 `resolve_delta`。
    working_point({参数键: 值})用于删闸之后在新工作点上重算,不需要新扫描。返回 screen.run 的摘要。"""
    import screen as SC
    cfg = _cfg(cfg, overrides)
    return SC.run(app, window, cfg, delta=resolve_delta(app, cfg), working_point=working_point)


def find(app: str, *, window: str, cfg: Settings | None = None, **overrides) -> dict:
    """联合识别(region_find.run):筛选里分辨得出的参数放一张网格一起调,找「自己好、邻居也好」的组合并估计挑选偏差。
    window = 联合窗口;一致性验证、筛选记录、功效线等前置检查都在 region_find.run。δ 取 `resolve_delta`。"""
    import region_find
    cfg = _cfg(cfg, overrides)
    return region_find.run(app, cfg, str(out_dir_of(app, window) / "longtable"), delta=resolve_delta(app, cfg))


def cell(app: str, *, window: str, note: str = "", **levels) -> dict:
    """查联合识别结果里的单个组合(region_find.cell_query),每次查询记一次账(机械闸 4)。

    levels 的键一律是参数键(params.yaml 里的 section.field,如 `**{"burst.gap_max": 8}`),本窗网格的每个参数都要给;
    note = 这次查询的用途,原样记进账本。"""
    import region_find
    return region_find.cell_query(app, window, levels, note=note)


# ---------------------------------------------------------------- 冻结清单与独立验证

def _selected_window(app: str) -> str:
    for r in reversed(ledger.read(app)):
        if r["kind"] == "select" and r["data"].get("tool") in ("find", "screen") and r["data"].get("window_name"):
            return r["data"]["window_name"]
    raise SystemExit(f"「{app}」还没做过筛选或联合调参,不知道要验证的改动是在哪批数据上挑出来的;请先筛选。")


def _optimism(app: str, window: str) -> float:
    """这个窗口最近一次联合识别报的挑选偏差(比例);没做过联合识别(只筛选)记 0。"""
    for r in reversed(ledger.read(app)):
        if r["kind"] == "select" and r["data"].get("tool") == "find" and r["data"].get("window_name") == window:
            v = r["data"].get("optimism")
            return float(v) if isinstance(v, (int, float)) and np.isfinite(v) else 0.0
    return 0.0


def _cells(cl: dict, configs: list, combo: dict, preds: list, background: dict | None = None) -> list:
    """配置 [{参数键: 值}, ...] → 格坐标;配置没给的参数取 background(缺省 = 窗口工作点)。"""
    import region_core as RC
    import screen as SC
    axis_of = {p: a for a, p in SC.axis_params(cl).items()}
    bg = cl["ref_point"] if background is None else background
    return [RC.cell_index(combo, preds, {axis_of[p]: v for p, v in {**bg, **c}.items()}) for c in configs]


def _events(prep, cells: list) -> np.ndarray:
    """每个格的买点事件数(各折合并)。"""
    import region_core as RC
    T = RC.segment_tensor(prep)
    return np.array([int(T[c].sum()) for c in cells], dtype=np.int64)


def _train_sums(app: str, window: str, cl: dict, configs: list, cfg, background: dict) -> tuple:
    """训练窗口上每个配置格的每股计数和(各折合并,买点事件口径)与买点事件数。先过确认窗守卫。
    background = 配置没给的参数的取值(覆盖全部轴)。返回 (U, D, N 形状 (股票数, 配置数), 事件数 (配置数,), 股票代码, 扫描口径)。"""
    import pyarrow.parquet as pq
    import region_core as RC
    lt = out_dir_of(app, window) / "longtable"
    meta = S.load_run_meta(lt)
    S.check_study_matches(cl, S.study_path(app, window))
    S.check_run_matches_classification(meta, cl)
    if meta.get("label_mode") == "deferred":
        raise SystemExit("这个窗口的扫描只记了买点事件、没算涨跌结果,不能用来冻结验证清单。")
    holdout.guard_label_access(app, meta["start_date"], meta["end_date"], "preregister")
    shards = sorted(lt.glob("part-*.parquet"))
    if not shards:
        raise SystemExit("这个窗口还没有扫描结果,先扫描。")
    combo, preds = S.derived_axes(cl)
    combo = {k: [v for v in lv if any(c.get(k, background[k]) == v for c in configs)] for k, lv in combo.items()}
    prep = RC.prepare_shards(shards, combo, preds, cfg.fold_col, list(cfg.folds),
                             segment_cols=S.segment_cols(cl, pq.read_schema(shards[0]).names))
    cells = _cells(cl, configs, combo, preds, background)
    U, D, N = RC.stock_sums(prep, cells, fold_mode="pooled")
    return U[:, :, 0], D[:, :, 0], N[:, :, 0], _events(prep, cells), prep.symbols, meta


def _confirm_declaration(cl: dict, configs: dict) -> dict:
    """确认窗怎么扫(冻结进验证清单):底座、放开值同训练窗口;检测参数只扫各配置用到的取值(没改的不进网格,取底座值);
    闸的档位同训练窗口(闸字段列都要在,学习端才能在确认窗上检闸)。键一律参数键。"""
    used = {}
    for vals in configs.values():
        for k, v in vals.items():
            used.setdefault(k, []).append(v)
    scan_grid = {k: ([v for v in lv if v in used[k]] if cl["kinds"][k] == "D" else list(lv))
                 for k, lv in cl["scan_grid"].items() if cl["kinds"][k] != "D" or k in used}
    return {"app_module": cl["app_module"], "base_yaml": cl["base_yaml"], "wide_overrides": cl["wide_overrides"],
            "scan_grid": scan_grid, "where_levels": {k: list(lv) for k, lv in cl["where_levels"].items()}}


def _confirm_name(confirm_window: str, decl: dict) -> str:
    return f"{CONFIRM_PREFIX}{confirm_window}_{S.canonical_hash(decl)[:8]}"


def _install_confirm(app: str, name: str, decl: dict) -> None:
    """按冻结的扫描声明写确认窗的窗口声明并生成分类表;生成失败 → 删掉刚写的声明。

    不过准入表:准入管的是调参网格里能放哪些档,确认窗只是照抄已冻结清单的配置与训练窗口的闸档位——已落地的定案
    (正式值已是改后值)、在役未审定却有多档的旧窗口,在准入表下都会被误拒。工作点仍由正式参数自动推出。"""
    import importlib
    import grid_propose as G
    from multivar_core import apply_overrides, classify
    from path2 import config
    config.set_runtime_checks(True)
    scan_grid = {tuple(k.split(".", 1)): list(lv) for k, lv in decl["scan_grid"].items()}
    where_levels = {tuple(k.split(".", 1)): list(lv) for k, lv in decl["where_levels"].items()}
    mod = importlib.import_module(decl["app_module"])
    formal = mod.Params.from_yaml(S.app_dir(mod) / decl["base_yaml"]).to_dict()
    kinds = classify(mod, apply_overrides(formal, decl["wide_overrides"], {}), scan_grid, where_levels).kinds
    ref_point = G.ref_point_from_base(formal, scan_grid, kinds, where_levels, scope="all")
    study_p = S.study_path(app, name)
    study_p.parent.mkdir(parents=True, exist_ok=True)
    study_p.write_text(G.render_study(app_module=decl["app_module"], base_yaml=decl["base_yaml"],
                                      wide_overrides=decl["wide_overrides"], scan_grid=scan_grid,
                                      where_levels=where_levels, ref_point=ref_point, tight_wheres={}, design="grid"),
                       encoding="utf-8")
    try:
        setup(app, window=name)
    except BaseException:
        study_p.unlink()
        raise


def _confirm_window(app: str, confirm_window: str, decl: dict, cfg, *, fingerprints: dict | None = None) -> tuple:
    """一段确认窗的扫描:按冻结的扫描声明装窗口声明(还没有才装),给了 fingerprints 就核对代码没变,再做延迟标签
    扫描(断点续跑;只记买点事件、不算任何标签,不过守卫)。返回 (窗口名, 输出目录)。"""
    import multivar_scan as MS
    op = ledger.latest(app, "open")
    if op is None:
        raise SystemExit(f"「{app}」还没做开局核对,没有留作验证的数据。")
    seg = op["data"]["confirm"][confirm_window]
    name = _confirm_name(confirm_window, decl)
    if not S.study_path(app, name).exists():
        _install_confirm(app, name, decl)
    if fingerprints is not None:
        now = ledger.current_fingerprints(app, name)
        if any(now[k] != fingerprints[k] for k in ("source_fingerprint", "ruler_fingerprint")):
            raise SystemExit("冻结验证清单之后代码变过(检测逻辑或涨跌结果的算法改了),这份清单检验的已经不是现在的代码;"
                             "请重新冻结验证清单。")
    out = out_dir_of(app, name)
    MS.run(app, replace(cfg, start_date=seg["start"], end_date=seg["end"]), str(out.relative_to(REPO)),
           label_mode="deferred")
    return name, out


def _confirm_prep(out: Path, cl: dict, *, labelled: bool) -> tuple:
    """确认窗扫描结果按买点事件口径离散化(整段合成一折)。labelled=True 逐片接上补算的标签;False 只数买点事件,
    四态占位、不读任何标签。一行都没有 → Prepared 为 None。返回 (Prepared | None, combo_levels, pred_specs)。"""
    import multivar_scan as MS
    import pyarrow.parquet as pq
    import region_core as RC
    combo, preds = S.derived_axes(cl)
    lt = out / "longtable"
    committed = MS.committed_shards(out) or set()
    parts = [p for p in sorted(lt.glob("part-*.parquet")) if p.name in committed]
    if not sum(pq.ParquetFile(p).metadata.num_rows for p in parts):
        return None, combo, preds
    cols = list(dict.fromkeys(["symbol", *combo, *(c for c, _, _ in preds), "seg_id"]))
    frames = (MS.read_with_labels(lt, cols + MS.FP_COLS) if labelled else
              (pd.read_parquet(p, columns=cols).assign(fp_up=0, fp_down=0, fp_both=0, fp_none=1) for p in parts))
    prep = RC.prepare_frames((df.assign(**{WINDOW_FOLD: "all"}) for df in frames), combo, preds, WINDOW_FOLD, ["all"],
                             segment_cols=S.segment_cols(cl, cols))
    return prep, combo, preds


def _window_events(app: str, confirm_window: str, decl: dict, configs: dict, cfg) -> dict:
    """确认窗每个配置格的买点事件数(无标签扫描计数):{配置名: 事件数}。"""
    name, out = _confirm_window(app, confirm_window, decl, cfg)
    cl = S.load_classification(app, name)
    prep, combo, preds = _confirm_prep(out, cl, labelled=False)
    if prep is None:
        return dict.fromkeys(configs, 0)
    return dict(zip(configs, (int(x) for x in _events(prep, _cells(cl, list(configs.values()), combo, preds)))))


def _price_after_train(symbols, data_dir, train_end) -> tuple:
    """每只股票数据末的收盘价,与训练窗末到数据末的涨跌幅(幸存者偏差预检用,只读价格)。"""
    last, move = {}, {}
    end = pd.Timestamp(train_end)
    for sym in symbols:
        p = REPO / data_dir / f"{sym}.pkl"
        if not p.exists():
            continue
        close = pd.read_pickle(p)["close"].dropna()
        if getattr(close.index, "tz", None) is not None:
            close.index = close.index.tz_localize(None)
        if not len(close):
            continue
        last[sym] = float(close.iloc[-1])
        before = close[close.index <= end]
        if len(before) and before.iloc[-1] > 0:
            move[sym] = last[sym] / float(before.iloc[-1]) - 1
    return pd.Series(last, dtype=float), pd.Series(move, dtype=float)


def _survivorship(symbols, U, D, N, k_col: int, base_col: int, train_end, cfg) -> dict:
    """幸存者偏差预检:日后困境股与其余股上「整套改动 − 改前」的差之差(validate.survivorship_bias)。"""
    import validate as V
    from inference import ratio_contrast
    last, move = _price_after_train(symbols, cfg.data_dir, train_end)
    distress = np.isin(np.asarray(symbols, dtype=object), sorted(V.distress_symbols(last, move)))
    if distress.all() or not distress.any():
        return {"flag": False, "text": "训练期的股票分不出日后困境股与其余股,幸存者偏差估不出来,不影响往前那段的确认。"}
    coef = np.zeros(U.shape[1])
    coef[k_col], coef[base_col] = 1.0, -1.0
    est = [ratio_contrast(U[m], D[m], N[m], coef)["est"] for m in (distress, ~distress)]
    try:
        return V.survivorship_bias([est[0]], [est[1]])
    except ValueError as e:
        return {"flag": False, "text": f"幸存者偏差估不出来({e}),不影响往前那段的确认。"}


def _feature_study():
    """按文件路径加载 feature-study 的 fs 模块(两个 skill 目录不并进同一个模块搜索路径,理由见 run_battery.load_tune_gates)。"""
    mod = sys.modules.get("fs")
    if mod is not None:
        if Path(getattr(mod, "__file__", "") or "").resolve() != FEATURE_STUDY_FS.resolve():
            raise ImportError(f"模块名 fs 已被 {getattr(mod, '__file__', None)} 占用,不能再按路径加载 {FEATURE_STUDY_FS}")
        return mod
    spec = importlib.util.spec_from_file_location("fs", FEATURE_STUDY_FS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fs"] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop("fs", None)
        raise
    return mod


def _gate_family(app: str, window: str, changes: dict, extra=None) -> dict | None:
    """学习端闸子族(fs.plan,调参轮内):候选配置 K 下要检验存在性的闸,extra = 用户开工确认时加的闸或同批特征;
    既没有闸也没有同批特征 → None(不并进清单)。"""
    gf = _feature_study().plan(app, window, extra=extra, config=dict(changes), in_round=True)
    return gf if gf["gates"] or gf.get("features") else None


def _formal(cl: dict) -> dict:
    """正式参数现值(params.yaml 本身,不套放开值)的扁平 {参数键: 值}。"""
    import importlib
    mod = importlib.import_module(cl["app_module"])
    nested = mod.Params.from_yaml(S.app_dir(mod) / cl["base_yaml"]).to_dict()
    return {f"{sec}.{k}": v for sec, kv in nested.items() if isinstance(kv, dict) for k, v in kv.items()}


def preregister(app: str, *, changes: dict, window: str | None = None, rule: str = "default", alpha: float = 0.05,
                method: str = "maxT", round_id=None, extra=None, cfg: Settings | None = None) -> dict:
    """冻结验证清单(validate.preregister):开窗之前把「检验什么、怎么检验、预期把握多大」全部定死。

    参数:
        changes: 候选配置 K 的改动 {参数键: 新值}。改前值:新值等于正式参数现值、且账本里该参数最近一条定案的新值
            就是它 → 这是已落地定案的事后验证,改前值取那条定案的旧值(「改前」= 定案前,「整套」= 现值);其余取窗口
            工作点。工作点没写的轴(只写了检测参数的旧窗口)取正式参数现值,落不到档位上 → 拒绝。改前、改后值都要在
            训练窗口的档位上。
        window: 训练窗口(各配置的训练估计从它的扫描结果算);缺省 = 最近一次联合识别或筛选用的窗口。
        rule: 采纳规则(默认:整套 → 按训练 z 从强到弱的每个单项 → 维持改前)。
        alpha / method: 确认子族的族内单侧 α 与校正方法("maxT" | "holm")。round_id: 调参轮次标签(可省)。
        extra: 用户开工确认时加的闸或同批特征,原样交给学习端闸子族(fs.plan 的 extra)。
    步骤:
        1. 改动归类:谓词类参数改到最松档 = 删闸(检验不比改前差),其余 = 检验更好;
        2. 训练窗口上每个配置格的每股计数(买点事件口径)→ 各改动在 K 处的 z → 展开确认子族与决策映射,
           非劣效界 = Settings 的非劣效界;
        3. 确认窗怎么扫冻结进清单;两段确认窗各做一次只记买点事件、不算涨跌结果的扫描,按买点事件数把训练误差
           换算成窗口误差(假定每个买点事件的 bar 数与训练期相同);
        4. 预期把握:往前那段 = 映射第一项同时通过的概率(效应 = 训练估计 − 联合识别报的挑选偏差),
           前向那段 = 整套改动「不比改前差且方向一致」的概率;
        5. 幸存者偏差预检;6. 学习端闸子族有闸或同批特征时并进清单;7. 写 preregister 记录。
    预期把握任一段不到一半 → needs_user_consent=True:开窗之前必须先问用户(本函数不代写「照样打开」的裁定)。
    返回 {"manifest_hash", "expected_power": {"backward", "forward"}, "needs_user_consent", "survivorship",
          "gate_family", "configs", "text", "record"}。"""
    import screen as SC
    import validate as V
    from inference import ratio_contrast
    cfg = cfg or Settings()
    window = window or _selected_window(app)
    cl = S.load_classification(app, window)
    combo, preds = S.derived_axes(cl)
    names = SC.axis_params(cl)
    levels = {names[a]: list(lv) for a, lv in combo.items()}
    levels.update({names[c]: list(lv) for c, _, lv in preds})
    gates = {names[c] for c, _, _ in preds}
    formal = _formal(cl)
    wp = {k: cl["ref_point"].get(k, formal.get(k)) for k in levels}
    off_grid = [f"{k} 的正式值 {wp[k]!r} 不在档位 {levels[k]} 上" for k in levels
                if k not in cl["ref_point"] and wp[k] not in levels[k]]
    if off_grid:
        raise SystemExit("这个窗口的工作点没写这些参数,按正式参数现值补也落不到档位上,冻结不了验证清单:\n- "
                         + "\n- ".join(off_grid))
    landed = {}
    for r in ledger.read(app):
        if r["kind"] == "decide":
            landed.update(r["data"]["params"])
    old, bad = {}, [] if changes else ["没有要验证的改动"]
    for k, v in changes.items():
        if k not in levels:
            bad.append(f"{k} 不在这个窗口的网格上(可选 {sorted(levels)})")
            continue
        d = landed.get(k)
        is_landed = (k in formal and formal[k] == v and type(formal[k]) is type(v)
                     and d is not None and d[1] == v and type(d[1]) is type(v))
        old[k] = d[0] if is_landed else wp[k]
        if v == old[k]:
            bad.append(f"{k} = {v!r} 就是工作点的取值,不算改动")
        elif old[k] not in levels[k] or v not in levels[k]:
            bad.append(f"{k} 的改前值 {old[k]!r}、改后值 {v!r} 要都在这个窗口的档位 {levels[k]} 上,训练期的统计才算得出")
    if bad:
        raise SystemExit("冻结不了验证清单:\n- " + "\n- ".join(bad))
    keys = list(changes)
    full = frozenset(keys)
    subsets = list(dict.fromkeys([frozenset(), full, *(full - {k} for k in keys), *(frozenset({k}) for k in keys)]))
    values = [{k: (changes[k] if k in s else old[k]) for k in keys} for s in subsets]
    designed = S.design_combos(cl)
    unscanned = [v for v in values if {k: {**wp, **v}[k] for k in combo} not in designed]
    if unscanned:
        raise SystemExit(f"这个窗口没扫过验证要比较的检测参数组合 {unscanned},换一个扫过这些组合的窗口。")

    U0, D0, N0, ev0, symbols, meta = _train_sums(app, window, cl, values, cfg, wp)
    col = {s: j for j, s in enumerate(subsets)}

    def z_drop(k):
        coef = np.zeros(len(subsets))
        coef[col[full]], coef[col[full - {k}]] = 1.0, -1.0
        return float(ratio_contrast(U0, D0, N0, coef)["z"])

    kinds = {k: "delete_gate" if k in gates and changes[k] == levels[k][0] else "detect" for k in keys}
    family = V.expand_family([V.Change(k, old[k], changes[k], kinds[k], z_drop(k)) for k in keys],
                             delta=V.noninferiority_margin(cfg), rule=rule)
    configs = family["configs"]
    order = [col[frozenset(k for k in keys if vals[k] == changes[k])] for vals in configs.values()]
    U, D, N, ev = U0[:, order], D0[:, order], N0[:, order], ev0[order]
    pos = {n: j for j, n in enumerate(configs)}
    hyps = family["hypotheses"]
    C = V.family_contrasts(family)
    rc = [ratio_contrast(U, D, N, C[j]) for j in range(len(hyps))]
    train_est = {h["id"]: float(r["est"]) for h, r in zip(hyps, rc)}
    optimism = _optimism(app, window)
    effects = {h: e - optimism for h, e in train_est.items()}

    decl = _confirm_declaration(cl, configs)
    win_ev = {cw: _window_events(app, cw, decl, configs, cfg) for cw in ledger.CONFIRM_NAMES}

    def se_window(cw):
        out = {}
        for h, r in zip(hyps, rc):
            n_w = win_ev[cw][h["a"]] + win_ev[cw][h["b"]]
            out[h["id"]] = V.window_se(r["se"], ev[pos[h["a"]]] + ev[pos[h["b"]]], n_w) if n_w else float("inf")
        return out

    corr = V.bootstrap_corr(U, D, C, B=cfg.b_boot, seed=cfg.boot_seed)
    back = V.expected_power(family, effects=effects, se_window=se_window("backward"), corr=corr, alpha=alpha,
                            method=method, seed=cfg.boot_seed)
    h1 = hyps[0]["id"]                                  # 整套改动 vs 改前
    se_f = se_window("forward")[h1]
    fwd = (V.forward_check_power(effects[h1], se_f, delta=family["delta"], alpha=alpha,
                                 train_sign=float(np.sign(train_est[h1]))) if np.isfinite(se_f) else 0.0)
    surv = _survivorship(symbols, U, D, N, pos[V.FULL], pos[V.BASE], meta["end_date"], cfg)
    gf = _gate_family(app, window, changes, extra)

    manifest = {"family": family, "train_est": train_est, "alpha": float(alpha), "method": method,
                "B": int(cfg.b_boot), "seed": int(cfg.boot_seed),
                "expected_power": {"backward": float(back["mapping_first"]), "forward": float(fwd),
                                   "backward_detail": back, "window_events": win_ev, "optimism": optimism},
                "survivorship": surv, "fingerprints": ledger.current_fingerprints(app, window),
                "round": round_id, "train_window": window, "confirm_scan": decl}
    if gf is not None:
        manifest["gate_family"] = gf
    rec = V.preregister(app, manifest, actor="tune.preregister")

    needs = min(back["mapping_first"], fwd) < 0.5
    text = (f"验证清单已冻结:{len(configs)} 个配置、{len(hyps)} 个要检验的比较。"
            f"{holdout.WINDOW_WORDS['backward']}上确认下来的预期把握约 {back['mapping_first']:.0%},"
            f"{holdout.WINDOW_WORDS['forward']}上核对通过的预期把握约 {fwd:.0%}。{surv['text']}")
    if needs:
        text += "有一段的预期把握不到一半:打开之前必须先问用户,是照样打开,还是先不验证。"
    text += "把预期把握告诉用户之后,记一条「已告知」的裁定,才能打开留作验证的数据。"
    return {"manifest_hash": rec["data"]["manifest_hash"],
            "expected_power": {"backward": float(back["mapping_first"]), "forward": float(fwd)},
            "needs_user_consent": needs, "survivorship": surv["text"], "gate_family": gf is not None,
            "configs": configs, "text": text, "record": rec}


def record_discovery(app: str, *, fc: list, axes: list, window: dict, note: str, ref: dict | None = None,
                     label_horizon: int | None = None) -> dict:
    """写一条发现记录(discover):研究结论或筛选草稿经确认登记到登记簿之后记账,它涉及的轴算「看过」;
    改闸 / 删闸定案之前必须先有(adopt 的闸 5)。返回写入的记录。

    fc = 登记簿条目编号(FC-xxx,至少一条);axes = 涉及的轴(参数写 section.field,不对应参数的特征写 feature:名);
    window = 发现时看过涨跌结果的买点区间 {start, end};label_horizon 缺省取 Settings;
    ref 缺省 = {登记簿: 当前内容的 sha256}。"""
    bad = [a for a in axes if not (isinstance(a, str) and ledger.AXIS_RE.match(a))]
    if bad:
        raise SystemExit(f"这些轴名写法不对(参数写 section.field,特征写 feature:名): {bad}")
    rec = ledger.make_record(
        "discover", app, actor="tune.record_discovery", round=None, fc=list(fc), axes=list(axes),
        window={"start": str(window["start"]), "end": str(window["end"])},
        label_horizon=label_horizon or Settings().label_horizon, head_buffer=None, git_head=None,
        base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None, n_looks=1,
        ref={REGISTRY: ledger.sha256_file(ledger.REPO / REGISTRY)} if ref is None else ref, note=note)
    return ledger.append(rec)


def _frozen(app: str, manifest_hash: str | None) -> dict:
    """账本里的调参验证清单记录:给了哈希取那一份,否则取最新一份。学习端单独冻结的闸清单不算。"""
    recs = [r for r in ledger.read(app) if r["kind"] == "preregister"]
    if manifest_hash is None:
        tuning = [r for r in recs if "confirm_scan" in r["data"]["manifest"]]
        if not tuning:
            raise SystemExit(f"「{app}」还没有冻结的验证清单,先冻结清单。")
        return tuning[-1]
    mine = [r for r in recs if r["data"]["manifest_hash"] == manifest_hash]
    if not mine:
        raise SystemExit("账本里没有这份验证清单。")
    if "confirm_scan" not in mine[-1]["data"]["manifest"]:
        raise SystemExit("这份清单是学习端单独冻结的闸清单,不是调参的验证清单,不能据此打开留作验证的数据。")
    return mine[-1]


def _window_sums(app: str, confirm_window: str, manifest_hash: str, configs: dict, cfg) -> dict:
    """validate 的 load_window_sums:确认窗每个配置格的每股计数和 {配置名: DataFrame(index=股票代码, 列 U/D/N)}。
    延迟标签扫描(续跑)→ 核对代码没变 → 过守卫现算标签 → 逐片接上标签,按买点事件口径汇总(整段合成一折)。"""
    import multivar_scan as MS
    import region_core as RC
    manifest = _frozen(app, manifest_hash)["data"]["manifest"]
    name, out = _confirm_window(app, confirm_window, manifest["confirm_scan"], cfg,
                                fingerprints=manifest["fingerprints"])
    MS.compute_deferred_labels(app, name, cfg, manifest_hash=manifest_hash, confirm_window=confirm_window)
    cl = S.load_classification(app, name)
    prep, combo, preds = _confirm_prep(out, cl, labelled=True)
    if prep is None:
        raise SystemExit(f"{holdout.WINDOW_WORDS[confirm_window]}上按清单里的配置一个买点都没有,检验不了。")
    U, D, N = RC.stock_sums(prep, _cells(cl, list(configs.values()), combo, preds), fold_mode="pooled")
    idx = pd.Index(prep.symbols, name="symbol")
    return {n: pd.DataFrame({"U": U[:, j, 0], "D": D[:, j, 0], "N": N[:, j, 0]}, index=idx)
            for j, n in enumerate(configs)}


def validate(app: str, *, confirm_window: str, cfg: Settings | None = None, manifest_hash: str | None = None) -> dict:
    """在一段留作验证的数据上按冻结清单检验一次(validate.validate);每段只能开一次。

    manifest_hash 缺省 = 最新一份验证清单。拒绝条件(清单未冻结、预期把握未告知、把握不足且用户未同意、该段已开过、
    清单不是最新)由确认窗守卫机械执行,不放行时一个标签都不读。窗口数据按清单冻结的扫描声明做延迟标签扫描、
    过守卫后现算标签(`_window_sums`);结果文件写在这段确认窗扫描的输出目录下。
    两段都开完后,返回里的 validation = {"manifest_hash", "extrapolate": {"backward": 开窗记录时间, "forward": 开窗记录时间}},
    给已落地的定案记独立验证结论时原样交给 adopt;没开完为 None。
    返回 {"confirm_window", "manifest_hash", "text", "interpretation", "validation", "result"}。"""
    import validate as V
    cfg = cfg or Settings()
    pre = _frozen(app, manifest_hash)
    h = pre["data"]["manifest_hash"]
    res = V.validate(app, confirm_window, manifest_hash=h,
                     load_window_sums=lambda configs, window: _window_sums(app, confirm_window, h, configs, cfg),
                     out_dir=out_dir_of(app, _confirm_name(confirm_window, pre["data"]["manifest"]["confirm_scan"])),
                     actor="tune.validate")
    return {"confirm_window": confirm_window, "manifest_hash": h, "text": res["text"],
            "interpretation": res["interpretation"], "validation": _validation(app, h), "result": res}


def _validation(app: str, manifest_hash: str) -> dict | None:
    """这份清单两段开窗记录的出处 {"manifest_hash", "extrapolate": {确认窗: 记录时间}};有一段没开 → None。"""
    opened = {r["data"]["confirm_window"]: r["ts"] for r in ledger.read(app)
              if r["kind"] == "extrapolate" and r["data"]["manifest_hash"] == manifest_hash}
    if set(opened) != set(ledger.CONFIRM_NAMES):
        return None
    return {"manifest_hash": manifest_hash, "extrapolate": {cw: opened[cw] for cw in ledger.CONFIRM_NAMES}}


def confirm_rows(app: str, confirm_window: str, combo: dict, gate_cols: list, *,
                 manifest_hash: str | None = None) -> pd.DataFrame:
    """学习端在确认窗上检闸子族的取数口(feature-study fs.run 的缺省 load_rows)。

    读这份验证清单那段确认窗的扫描结果、接上开窗时补算的标签,取一个检测组合(combo = {检测参数键: 值})的行。
    返回列同 extract.build_from_longtable:symbol、date、year、买点事件键列、闸字段列(扫描结果里有的)、
    M / c0_atr_pct、up / down / both / none;只丢完全重复的行。
    读之前先过确认窗守卫(purpose="gate_family",读取区间 = 这段确认窗的买点区间):这段还没按这份清单开过窗、
    清单没带闸子族、或闸子族在这段已检过 → HoldoutLocked,一行都不读。"""
    import multivar_scan as MS
    import pyarrow.parquet as pq
    from multivar_core import STATES
    pre = _frozen(app, manifest_hash)
    manifest = pre["data"]["manifest"]
    op = ledger.latest(app, "open")
    if op is None:
        raise SystemExit(f"「{app}」还没做开局核对,没有留作验证的数据。")
    seg = op["data"]["confirm"][confirm_window]
    holdout.guard_label_access(app, seg["start"], seg["end"], "gate_family",
                               manifest_hash=pre["data"]["manifest_hash"], confirm_window=confirm_window)
    name = _confirm_name(confirm_window, manifest["confirm_scan"])
    out = out_dir_of(app, name)
    cl = S.load_classification(app, name)
    grid, _ = S.derived_axes(cl)
    base = cl["ref_params"]
    lack = [k for k in grid if k not in combo]
    off = {k: v for k, v in combo.items()
           if (v not in grid[k] if k in grid else base[k.split(".", 1)[0]][k.split(".", 1)[1]] != v)}
    if lack or off:
        raise SystemExit(f"这段留作验证的数据只按验证清单里的配置扫过,取不出这个组合(缺 {lack},没扫过 {off})。")
    committed = MS.committed_shards(out) or set()
    parts = [p for p in sorted((out / "longtable").glob("part-*.parquet")) if p.name in committed]
    if not parts:
        raise SystemExit("这段留作验证的数据还没有扫描结果。")
    names = pq.read_schema(parts[0]).names
    seg = S.segment_cols(cl, names)
    gates = [c for c in gate_cols if c in names]
    extra = [c for c in ("M", "c0_atr_pct") if c in names]
    got = []
    for df in MS.read_with_labels(out / "longtable",
                                  list(dict.fromkeys(["symbol", *grid, *gates, *seg, "buy_date", *extra, *MS.FP_COLS]))):
        keep = np.ones(len(df), dtype=bool)
        for k in grid:
            keep &= (df[k] == combo[k]).to_numpy()
        got.append(df[keep])
    df = pd.concat(got, ignore_index=True)
    if df.empty:
        raise SystemExit(f"检测组合 {combo} 在这段留作验证的数据上一行都没有。")
    df["symbol"] = df["symbol"].astype(str)
    df = df.rename(columns=dict(zip(MS.FP_COLS, STATES)))
    df["date"] = pd.to_datetime(df["buy_date"])
    df["year"] = df["date"].dt.year.astype(str)
    cols = list(dict.fromkeys(["symbol", "date", "year", *seg, *gates, *extra, *STATES]))
    return df[cols].drop_duplicates(["symbol", *seg, *gates, *STATES]).reset_index(drop=True)


# ---------------------------------------------------------------- 定案

def adopt(app: str, *, window: str, changes: dict, provisional: bool, verified: bool, selects_on: list,
          depends_on: dict, reason: str, confirm: bool = False, validation: dict | None = None) -> dict:
    """用户批准后写正式参数与定案记录(adopt.adopt)。**confirm=False 只返回 diff 与检查结果,不写任何东西。**
    返回里带「这组参数一共被比较过几次」(机械闸 4);改闸要求登记簿已有待验证行、未经独立验证的双标注(闸 5);
    depends_on 记定案时的背景参数(闸 6)。validation = 已落地定案的独立验证出处(两段开完后 `validate` 返回的
    validation),给已落地定案记验证结论时用。"""
    import adopt as A
    return A.adopt(app, window=window, changes=changes, provisional=provisional, verified=verified,
                   selects_on=selects_on, depends_on=depends_on, reason=reason, confirm=confirm,
                   validation=validation)
