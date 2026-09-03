# -*- coding: utf-8 -*-
"""tune-gates · Claude 的唯一调用面。

**这个文件存在的理由**:用户只想说「帮我调 X 的参数」,不想知道 study.py / classification.json /
run_meta.json / 指纹 / W-F-D-E 维这些内部机制。所有机制操作从这里发起,机制词不外泄——
禁止词清单与人话译法见 SKILL.md。

设计要点:
  - status() 一律**现场探测**文件系统,不维护第二份进度记录(两份真相迟早对不上)。
  - run 级口径(Settings 里带 ★ 的字段)只在开新一跑时给一次,之后 compare/find 从
    run_meta.json 读——同一个值不会有两个来源。
  - 危险动作(retire)默认 confirm=False 只返回清单不动手。
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S  # noqa: E402


@dataclass(frozen=True)
class Settings:
    """一跑的口径与预算。默认值迁自改造前的 apps/bb_v1/run.py。

    ★ 标记的字段进 study_io.RUN_CALIBER:它们改了**必须换 window**(新开输出目录),
    write_run_meta 会拒绝把不同口径写进同一目录。未标记的(workers / top_n / b_boot /
    split_half_seeds / cmp_* 等)随便改,不影响已有扫描结果复用。
    """
    # ---- 数据与时间窗 ----
    data_dir: str = "datasets/pkls"
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
    cmp_ticker_regex: str = r"^[A-Z][A-C]"  # 红线要求参与比较的股数 >= 500
    cmp_seed: int = 11
    cmp_n_random_cells: int = 64
    cmp_n_tight_cells: int = 12
    min_win_bars: int = 1
    # ---- 识别 ----
    fold_col: str = "fold_Y"
    folds: tuple = ("2024", "2025")
    min_count_per_fold: int = 100           # 仅在一个 app 上校准过,见 reference.md §6 坑 8
    neighbor_axes: str = "all"
    b_boot: int = 300
    boot_seed: int = 0                      # bootstrap 重采样种子;与 split-half 种子无关
    split_half_seeds: tuple = tuple(range(20))
    top_n: int = 20


def out_dir_of(app: str, window: str = "main", repo: Path | None = None) -> Path:
    """一跑的输出根目录。window 区分同一 app 的多份扫描结果(主窗/外推窗口径不同,必须分开放)。"""
    return (Path(repo) if repo else REPO) / "outputs" / "tune_gates" / app / window


def status(app: str, window: str = "main", *, apps_dir: Path | None = None,
           repo: Path | None = None) -> dict:
    """现场探测这个 app 当前进行到哪一步。**不写任何文件。**

    apps_dir / repo 显式可注入,覆盖的是 app 目录与输出目录(out_dir_of)的解析路径,
    让测试能在 tmp_path 假树上跑。但这个注入不彻底:一旦长表目录下有 run_meta.json、
    走到可再生性实检(S.check_regenerable)这一步,它内部解析底座 yaml 与源码指纹用的
    仍是**真实仓库**的 REPO——`check_regenerable` 只接 `apps_dir` 参数,没有 `repo` 参数
    可穿透,这是它的签名限制,本函数不越界去改共享模块。
    """
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    repo = Path(repo) if repo else REPO
    app_dir = apps_dir / app
    study_p = app_dir / "study.py"
    out = out_dir_of(app, window, repo)
    lt = out / "longtable"

    st = {"app": app, "window": window, "out_dir": str(out), "installed": study_p.exists(),
          "classification_stale": None, "source_stale": None, "base_stale": None,
          "scanned_shards": 0, "scanned_symbols": 0,
          "compared": False, "compare_mismatch": None, "found": (out / "region_report.md").exists(),
          "exposure_rounds": 0, "regenerable": None, "regenerable_reasons": []}

    exposure = app_dir / "exposure.jsonl"
    if exposure.exists():
        st["exposure_rounds"] = sum(1 for ln in exposure.read_text(encoding="utf-8").splitlines() if ln.strip())

    cl_p = app_dir / "classification.json"
    if st["installed"] and cl_p.exists():
        try:
            cl = json.loads(cl_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            st["classification_stale"] = True   # 分类表损坏,读不出来 = 同样归入"要重建"
        else:
            st["classification_stale"] = S.file_sha256(study_p) != cl.get("fingerprints", {}).get("study")
            # 分类表存在且能解析 → 顺带核一遍 detector 源码 / 底座 yaml 是否变过——这是
            # classification_stale(只看 study.py 字节)之外的独立信号:即便没扫描、没有
            # run_meta.json 可核(check_regenerable 只在长表已存在时才有值),这两条也该
            # 有个机械信号,而不是只能靠"问用户"。
            try:
                study = S.load_study(study_p)
                mod = S.import_app(study)
                base_now = S.base_snapshot(mod, study)
                spec0 = mod.build_pattern(mod.Params.from_dict(base_now, strict=True))
                src_now = S.source_fingerprint(S.source_files(mod, spec0))
                st["source_stale"] = src_now["hash"] != cl.get("fingerprints", {}).get("source", {}).get("hash")
                st["base_stale"] = S.canonical_hash(base_now) != cl.get("fingerprints", {}).get("base")
            except Exception as e:
                # study.py 语法错 / app import 失败 / build_pattern 崩,都不能带崩 status()——
                # 与下面 regenerable 分支同款倒向保守侧:判不了时 None,原因不吞。
                st["source_stale"] = st["base_stale"] = None
                st["fingerprint_check_error"] = f"源码/底座指纹核查本身失败({type(e).__name__}: {e}),保守判无法判定"
    elif st["installed"]:
        st["classification_stale"] = True      # 有声明没分类表 = 待生成,同样归入"要重建"

    if lt.is_dir():
        shards = sorted(lt.glob("part-*.parquet"))
        st["scanned_shards"] = len(shards)
        if (lt / "run_meta.json").exists():
            try:
                ok, why = S.check_regenerable(lt, apps_dir=apps_dir)
                st["regenerable"], st["regenerable_reasons"] = ok, why
            except Exception as e:
                # check_regenerable 文档明载:run_meta/classification 损坏或 import app 期
                # 抛出的 BaseException 会穿透它直接向上抛,调用方必须自己接住——status() 正是
                # 「用户说一句话就知道该干什么」的入口,不能在这里连带炸掉,倒向保守侧。
                st["regenerable"] = False
                st["regenerable_reasons"] = [f"可再生性核查本身失败({type(e).__name__}: {e}),保守判不可再生"]

    log = out / "compare_longtable.log"
    if log.exists():
        st["compared"] = True
        for ln in reversed(log.read_text(encoding="utf-8").splitlines()):
            if "mismatch=" in ln:
                try:
                    st["compare_mismatch"] = int(ln.split("mismatch=")[1].split(",")[0])
                except ValueError as e:
                    # 与 classification_stale/regenerable 两处解析同款:格式一旦漂移不能
                    # 带崩 status()——保守侧留 None(已是初始值),原因不吞。
                    st["compare_mismatch_error"] = f"mismatch 行解析失败({type(e).__name__}: {e}): {ln!r}"
                break
    return st


def setup(app: str, *, apps_dir: Path | None = None) -> dict:
    """从 apps/<app>/study.py 生成分类表 classification.json。幂等。

    跑 classify + 全部静态守卫 + 推导 + 三指纹。守卫在这里响亮失败,不等到扫描:
    E 维不许进 SCAN_GRID / REF_POINT 恰好覆盖 D 维 / TIGHT_WHERES 键在网格内 /
    共享 detector 实例 / negation dst 谓词轴。
    """
    import app_setup  # noqa: F401 —— 仅为触发其模块级 sys.path 设置
    from path2 import config
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    study_path = apps_dir / app / "study.py"
    if not study_path.exists():
        raise SystemExit(f"{study_path} 不存在:该 app 尚未接入,先用 tune.propose_grid + 落地网格")
    study = S.load_study(study_path)
    mod = S.import_app(study)
    config.set_runtime_checks(True)
    cl = S.build_classification(app, study, mod, study_path)
    S.write_classification(app, cl, apps_dir=apps_dir)
    return {"app": app, "kinds": cl["kinds"], "filter_fields": cl["filter_fields"],
            "where_fields": cl["where_fields"], "end_node": cl["end_node"],
            "bound_nodes": cl["bound_nodes"], "detection_combos": cl["detection_combos"],
            "source_files": cl["fingerprints"]["source"]["files"]}


def retire(app: str, *, confirm: bool = False, delete_notes: bool = False,
           delete_exposure: bool = False, apps_dir: Path | None = None,
           repo: Path | None = None) -> dict:
    """app 退役清理。**confirm=False 时只返回清单,一个文件都不删。**

    分组按「误删=永久丢失 vs 误留=多几个文件」的不对称设计:notes.md 与 exposure.jsonl
    记的是「对这批数据做过什么」,意义不随 app 消失,默认保留、要删须分别开开关。
    重产物先过可再生性实检,验不过一律降到 blocked(只报不删)。
    只走精确路径,绝不按 app 名 glob。
    """
    import app_setup
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    repo = Path(repo) if repo else REPO
    plan = app_setup.plan_delete(app, apps_dir, repo, delete_notes, delete_exposure)
    app_setup._execute_delete(plan, apps_dir / app, confirm)
    return plan


def scan(app: str, *, window: str = "main", cfg: Settings | None = None, **overrides) -> dict:
    """扫描出候选长表(断点续跑)。**这是最贵的一步**,全宇宙可能几十分钟到几小时。

    overrides 直接覆盖 Settings 的字段(如 ticker_regex="^A[A-C]" 先小范围试跑)。
    ★ 口径字段改了必须换 window,否则 write_run_meta 会拒绝写进同一目录。
    """
    from dataclasses import replace
    import multivar_scan
    cfg = replace(cfg or Settings(), **overrides) if overrides else (cfg or Settings())
    out = out_dir_of(app, window)
    multivar_scan.run(app, cfg, str(out.relative_to(REPO)))
    return status(app, window)


def compare(app: str, *, window: str = "main", cfg: Settings | None = None, **overrides) -> dict:
    """一致性验证。**红线:mismatch 必须为 0,否则不得读识别结果。**

    注意:★ 口径字段不从 cfg 取——它们由扫描时写进 run_meta.json、本函数内部读之
    (单一来源)。cfg 在这里只提供 cmp_* / workers 这些非口径旋钮。
    """
    from dataclasses import replace
    import compare_longtable
    cfg = replace(cfg or Settings(), **overrides) if overrides else (cfg or Settings())
    lt = out_dir_of(app, window) / "longtable"
    compare_longtable.run(app, cfg, str(lt.relative_to(REPO)))
    return status(app, window)


def find(app: str, *, window: str = "main", cfg: Settings | None = None,
         force: bool = False, **overrides) -> dict:
    """在扫描结果上识别稳健区。**前置红线:必须先 compare 且 mismatch=0——本函数自己核这条
    红线,不再只靠调用方自觉。**

    判据是 `status()["compared"] and status()["compare_mismatch"] == 0`,不是单看
    `compared`:`compared` 只代表验证日志文件存在,半路崩溃也会留下这个文件,此时
    `compare_mismatch` 是 `None`。不满足就响亮拒绝、不做任何事——在未验证一致的扫描结果上
    识别出的区域,产出的正是用户会据此拍板的报告,这是本工具最经不起放过的一条红线。

    `force=True` 是逃生舱:仅当调用方已经用别的证据独立确认过一致性(如刚人工核对过
    compare 日志内容与此次长表确实对应)才该用,平时不传。
    """
    st = status(app, window)
    if not force and not (st["compared"] and st["compare_mismatch"] == 0):
        raise SystemExit(
            f"{app}/{window} 尚未通过一致性验证(compared={st['compared']!r}, "
            f"compare_mismatch={st['compare_mismatch']!r}):在扫描结果上识别稳健区之前必须先跑 "
            f"tune.compare({app!r}, window={window!r}) 且其 compare_mismatch 为 0——"
            "未验证一致的扫描结果上识别出的区域不可信。若已用别的证据独立确认过一致性,"
            "可传 force=True 跳过本检查,后果自负。"
        )
    from dataclasses import replace
    import region_find
    cfg = replace(cfg or Settings(), **overrides) if overrides else (cfg or Settings())
    lt = out_dir_of(app, window) / "longtable"
    region_find.run(app, cfg, str(lt.relative_to(REPO)))
    return status(app, window)


def plateau_report(csv: str, out_dir: str, *, rel_tol: float = 0.05, min_match: int = 100) -> dict:
    """单参数路径:事后切档位的宽表 → 逐闸平台图与判定。"""
    import plateau
    return plateau.run(csv, out_dir, rel_tol=rel_tol, min_match=min_match)


def propose_grid(app_module: str, base_yaml: str = "params.yaml") -> dict:
    """读 pattern 的参数,提一套带推荐档位与实测维度分类的网格方案供用户增删改。

    **返回的是机械建议不是判断**:哪个参数值得扫、档位该多宽,需要对这个走势的先验知识。
    Claude 须把它翻译成人话列给用户(参数名说人话、按「改了必须重扫」/「可以事后切档位」
    分组、标出推荐档位),由用户增删改。

    个别参数可能 kind=None(逐维探测两条路都失败,如与另一参数存在构造不变式冲突,或非
    数值型/零值);这类字段的 `reason` 非空,须原样带给用户、不要静默丢弃或强行分组。
    """
    import importlib
    import grid_propose
    mod = importlib.import_module(app_module)
    base = mod.Params.from_yaml(S.app_dir(mod) / base_yaml).to_dict()
    return grid_propose.propose(mod, base)


def install(app: str, *, app_module: str, base_yaml: str = "params.yaml",
            wide_overrides: dict, scan_grid: dict, where_levels: dict,
            tight_wheres: dict, apps_dir: Path | None = None) -> dict:
    """把敲定的网格落地成 apps/<app>/study.py,随即生成分类表。

    **写 study.py 会让该 app 已有的扫描结果作废**(它的哈希是准入校验)——
    调用方须先确认用户知道这一点。

    REF_POINT 不是入参:它由生产参数在网格上的落点自动推出(见 grid_propose
    .ref_point_from_base 的 docstring,那里记着手写它导致的一次真实事故)。

    **FLAG_RULES 不是入参**:它的取值是 lambda,渲染函数无法确定性地把它转成源码文本,
    所以本函数也不接受、不推导它——渲染出的 study.py 里 FLAG_RULES 恒为空列表,
    需要旗标规则的 app 必须在**第一次扫描之前**手改该文件补上(之后再改就要开一份新的
    扫描结果,见渲染出的 study.py 头部说明)。

    **写盘是原子的**:`setup()` 内部还有好几道 `render_study`/顶部 `classify()` 都不查的
    静态守卫(TIGHT_WHERES 键须在网格内 / E 维不许进 SCAN_GRID / 共享 detector 实例 /
    negation dst 谓词轴),任何一道在这里失败,study.py 都已经落盘、旧文件已被覆盖——
    对已接入且有扫描结果的 app,这是真损失(旧指纹对不上、新分类表又生不出来)。故本函数
    写盘前先把原文件字节读进内存(不存在则记 None),`setup()` 失败时原样写回(不存在则
    删掉刚建的文件)并重新抛出原异常;连回滚本身都失败会响亮报出、不吞。
    """
    import importlib
    import grid_propose
    from multivar_core import apply_overrides, classify
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    mod = importlib.import_module(app_module)
    base_yaml_dict = mod.Params.from_yaml(S.app_dir(mod) / base_yaml).to_dict()
    base = apply_overrides(base_yaml_dict, wide_overrides, {})
    kinds = classify(mod, base, scan_grid, where_levels).kinds
    ref_point = grid_propose.ref_point_from_base(base, scan_grid, kinds)
    d = apps_dir / app
    d.mkdir(parents=True, exist_ok=True)
    study_p = d / "study.py"
    original = study_p.read_bytes() if study_p.exists() else None
    study_p.write_text(grid_propose.render_study(
        app_module=app_module, base_yaml=base_yaml, wide_overrides=wide_overrides,
        scan_grid=scan_grid, where_levels=where_levels, ref_point=ref_point,
        tight_wheres=tight_wheres), encoding="utf-8")
    try:
        return setup(app, apps_dir=apps_dir)
    except BaseException as e_setup:
        try:
            if original is None:
                study_p.unlink()
            else:
                study_p.write_bytes(original)
        except OSError as e_restore:
            raise RuntimeError(
                f"{study_p} 写入后 setup() 失败({type(e_setup).__name__}: {e_setup}),回滚也"
                f"失败({type(e_restore).__name__}: {e_restore})——该文件现处于不可信状态,"
                "请手动核对/从 git 还原后重试"
            ) from e_setup
        raise
