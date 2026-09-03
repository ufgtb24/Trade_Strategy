# tune-gates 机制改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 `docs/research/2026-08-29_tune-gates-mechanism-design/final_report.md` 的 14 项拍板（按报告推荐值）+ 修红基线 + split-half 多种子；外推窗计数（§1.4）**不做**（用户已拍板）。

**Architecture:** 三条主线。① **参数落点重排**——run 级常量从四个入口脚本的 `main()` 迁到 `apps/<app>/run.py`（**不能进 `study.py`**，见 Global Constraints），APP 身份由新增的单源 `current.py` 提供、各脚本 `main()` 顶部显式读取一行。② **识别端补审计与稳健性**——`region_find` 追加只写不覆盖的 `exposure.jsonl`，`split_half` 从单种子改为多种子报均值±SE。③ **app 退役清理**——`app_setup` 新增 `delete` MODE，走精确路径匹配 + 可再生性实检，绝不 glob。

**Tech Stack:** Python 3.12 · uv · pytest · numpy/pandas · 无 argparse（项目规范：参数声明在 `main()` 起始或专用常量文件）

**Spec:** `docs/research/2026-08-29_tune-gates-mechanism-design/final_report.md`（§1–§6 与 §4 拍板表）

## Global Constraints

- **本 plan 中所有项目内路径均相对 repo root**（如 `.claude/skills/tune-gates/study_io.py`）。例外：`/tmp/...`、`~/.claude/...` 等与 worktree 无关的系统路径保持绝对。
- **工作目录 = 当前 worktree 根**，不要 `cd` 到主仓库或其他 worktree。
- **run 级常量绝不能写进 `apps/<app>/study.py`。** `study_io.py:127` 的 study 指纹是 `file_sha256(study_path)`（整份文件哈希），`check_run_matches_classification` 拿它当长表准入校验——改 `study.py` 任何一个字，已有长表当场读不了、必须重扫。落点只能是 `apps/<app>/run.py`。
- **无 argparse**（项目规范）。参数声明在 `main()` 起始处，或本 plan 新增的 `current.py` / `apps/<app>/run.py`。
- **测试基线**：改造前 `uv run pytest .claude/skills/tune-gates/ -q` 是 **13 failed / 47 passed / 8 errors**。Task 1 把它修绿；**Task 1 之后每个 task 的验收标准都是「全绿且不新增失败」**。
- **不得 `git push`，不得开 PR。** 每个 task 结束时本地 commit。
- 中文注释与文档（项目规范）。
- **禁止在实施中真的删除任何研究目录或长表**。Task 9 只实现 dry-run + 显式开关，验收用临时假目录树，绝不对真实 `docs/research/**` 执行删除。

---

## File Structure

| 文件 | 职责 | 本计划中的动作 |
|---|---|---|
| `.claude/skills/tune-gates/current.py` | 单源 app 身份（`APP` / `RUN`） | **新建**（Task 2） |
| `.claude/skills/tune-gates/apps/_template/run.py` | run 级常量模板 | **新建**（Task 2） |
| `.claude/skills/tune-gates/apps/bb_v1/run.py` | bb_v1 的 run 级常量 | **新建**（Task 2） |
| `.claude/skills/tune-gates/study_io.py` | 声明加载 / 指纹 / run_meta / 新增 run 加载与可再生性检测 | 修改（Task 2/5/8） |
| `.claude/skills/tune-gates/app_setup.py` | app 接入端 + 新增 delete MODE | 修改（Task 3/9） |
| `.claude/skills/tune-gates/multivar_scan.py` | 扫描出长表 | 修改（Task 3） |
| `.claude/skills/tune-gates/compare_longtable.py` | 对拍 | 修改（Task 3） |
| `.claude/skills/tune-gates/region_find.py` | 识别稳健区 + 新增 exposure 写入 | 修改（Task 3/6/7） |
| `.claude/skills/tune-gates/region_core.py` | 张量分析 / bootstrap / split_half | 修改（Task 6） |
| `.claude/skills/tune-gates/bench_workers.py` | WORKERS 定标（靠正则改写目标脚本） | 修改（Task 4） |
| `.claude/skills/tune-gates/fixtures/study_bb_v1.py` | 自测用的 study 声明 | 修改（Task 1） |
| `.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json` | 冻结的 base 快照期望值 | 重新生成（Task 1） |
| `.claude/skills/tune-gates/apps/bb_v1/study.py` | bb_v1 实战声明 | 修改（Task 1） |
| `.claude/skills/tune-gates/SKILL.md` | 主文档 | 修改（Task 10/11） |
| `.claude/skills/tune-gates/reference.md` | 操作卡 | 修改（Task 10） |

---

## Task 1: 修红基线（三处「红」的同一根因）

**背景（实施者必读）**：commit `41fd193` 删除了 `path2_apps/bb_v1/p2.yaml`（内容并入 `params.yaml`）并重写了 `path2/atoms/throwback_v1.py`（tb 方案 C），删掉了 8 个 tb 字段。而两份 study 声明的 `BASE_YAML` 至今指着 `p2.yaml`。这**一处**造成全部 21 个失败：

- `fixtures/study_bb_v1.py:5` 的 `BASE_YAML="p2.yaml"` → `FileNotFoundError` → `test_study_io.py` 的 8 errors + 3 failed
- `fixtures/bb_v1_p2_wide.json` 冻结了已删的 8 个 tb 字段 → `Params.from_dict(strict=True)` 抛 `ValueError: params dict section 'tb' 含未知字段: ['anchor_mode','atr_window','big_rise_k','judged_measure','max_start_gap','max_window','reference_measure','scb_mode']` → `test_multivar_core.py` 8 failed + `test_multivar_equiv.py` 2 failed

**Files:**
- Modify: `.claude/skills/tune-gates/fixtures/study_bb_v1.py`
- Modify: `.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json`（重新生成）
- Modify: `.claude/skills/tune-gates/apps/bb_v1/study.py`
- Test: `.claude/skills/tune-gates/test_study_io.py`、`test_multivar_core.py`、`test_multivar_equiv.py`（既有，不新增）

**Interfaces:**
- Consumes: 无
- Produces: 绿色测试基线。后续所有 task 的验收都以「不新增失败」为准。

- [ ] **Step 1: 确认失败基线与 tb 新字段清单**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
# 期望: 13 failed, 47 passed, 8 errors

# tb 当前真实字段（新实现）
uv run python -c "
from dataclasses import fields
from path2_apps.bb_v1.params import Params
import inspect
tb = [f for f in fields(Params) if f.name=='tb'][0]
print([f.name for f in fields(tb.type)])
"
```

记下输出的 tb 字段名清单，Step 3 要用。

- [ ] **Step 2: 修 `fixtures/study_bb_v1.py`**

把第 2 行 docstring 与第 5 行 `BASE_YAML` 改掉，并重写三处含已删字段的声明：

```python
# -*- coding: utf-8 -*-
"""bb_v1 · tune-gates study 声明(自测夹具;底座 = params.yaml)。

2026-08-30: 原底座 p2.yaml 于 41fd193 被删(内容并入 params.yaml),tb 同批换代为方案 C、
删除 8 个旧字段。本夹具据此改底座并重写 tb 三维——它是**通用区测试资产**,只需保证
classify/build_classification/pred_mask 有一份真实可用的 spec 输入,不必与 apps/bb_v1/ 一致。
"""

APP_MODULE = "path2_apps.bb_v1.dag_spec"
BASE_YAML = "params.yaml"

WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                  "tb": {"max_day_drop_pct": None}}

SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
             ("bo", "exceed_threshold"):    [0.001, 0.003, 0.01, 0.03],
             ("burst", "gap_max"):          [4, 8, 12, 20],
             ("burst", "min_bos"):          [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"):   [1, 2, 3, 4],
             ("tb", "max_rise_k"):          [1.0, 1.5, 2.5, 4.0]}

WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40],
                ("burst", "distinct_pk_min"):   [1, 3, 4],
                ("burst", "vol_spike_min"):     [0, 10, 15],
                ("burst", "peak_age_min"):      [0, 125],
                ("tb", "max_day_drop_pct"):     [None, 0.2]}

REF_POINT = {"bo.min_relative_height": 0.2, "bo.exceed_threshold": 0.003, "burst.gap_max": 8,
             "burst.min_bos": 1, "tb.stop_confirm_bars": 1, "tb.max_rise_k": 1.5}

TIGHT_WHERES = {"FINAL": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 4, ("burst", "vol_spike_min"): 15,
                          ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2},
                "B":     {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3, ("burst", "vol_spike_min"): 10,
                          ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2}}

FLAG_RULES = [lambda c: "first_drought 闸恒真" if c["burst.gap_max"] >= c["burst.first_drought"] > 0 else None]
```

**三处关键改动的理由（写进 commit message）**：
1. `stop_confirm_bars` 档位去掉 `0`——新实现 `throwback_v1.py` 的 `__init__` 对 `< 1` 直接 `raise ValueError`（「cnt 在第一根不刷新根即变 1，K=0 与 K=1 行为完全等价」）。
2. `big_rise_k` → `max_rise_k`：字段已删；替代维单位与语义都变了（Wilder ATR 倍数 → median TR 倍数；旧的是 Phase 2「大涨收窗」出口，新的由 DOWN→UP 反弹臂与 STABLE rise 出口共用），默认 1.5，故档位取 `[1.0, 1.5, 2.5, 4.0]` 而非旧的 `[3,5,8,12]`。
3. `max_day_drop_pct` 从 `SCAN_GRID` 挪到 `WHERE_LEVELS`——毒药闸在 tb 方案 C 里从 F 维（detector 构造参数）改为 W 维（事件出 `max_day_drop` 字段、阈值由 app 的 where 表达，见 `path2_apps/bb_v1/dag_spec.py:59-60`）。
4. `REF_POINT` 必须恰好覆盖全部 D 维（`app_setup` 会校验），所以补上 `burst.min_bos`（若 Step 4 报「REF_POINT 覆盖不全」按报错补齐）。

- [ ] **Step 3: 重新生成 `fixtures/bb_v1_p2_wide.json`**

该文件是 `base_snapshot()` 的冻结期望值。用当前实现重新生成：

```bash
uv run python -c "
import subprocess, sys, json
from pathlib import Path
REPO = Path(subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO/'.claude/skills/tune-gates'))
import study_io as S
study = S.load_study(REPO/'.claude/skills/tune-gates/fixtures/study_bb_v1.py')
mod = S.import_app(study)
snap = S.base_snapshot(mod, study)
out = REPO/'.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json'
out.write_text(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
print(json.dumps(snap['tb'], ensure_ascii=False, indent=1))
"
```

**人工核对（不要跳过）**：打印出的 `tb` 段必须只含新实现的字段（`max_rise_k` / `stop_confirm_bars` / `vol_window` / `max_span` / `measure` / `max_day_drop_pct`），且 `max_day_drop_pct` 因 `WIDE_OVERRIDES` 为 `None`。**重新生成冻结值等于用当前实现的输出当期望值——若当前实现有 bug 就会把 bug 冻结进去，所以这一步必须人眼确认字段与取值合理，再进 Step 4。**

- [ ] **Step 4: 同步 `apps/bb_v1/study.py`**

`apps/bb_v1/study.py` 是实战声明，同样 stale。做与 Step 2 完全相同的四处修改（`BASE_YAML` / `stop_confirm_bars` 档位 / `big_rise_k`→`max_rise_k` / `max_day_drop_pct` 移到 `WHERE_LEVELS`），并在文件头 docstring 注明「2026-08-30 随 tb 方案 C 换代更新；上一版网格见 git history」。

改完后跑：

```bash
uv run python -c "
import subprocess, sys
from pathlib import Path
REPO = Path(subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO/'.claude/skills/tune-gates'))
import study_io as S
study = S.load_study(S.APPS_DIR/'bb_v1'/'study.py')
mod = S.import_app(study)
print('load ok; BASE_YAML =', study.BASE_YAML)
"
```

期望：打印 `load ok; BASE_YAML = params.yaml`，无异常。

- [ ] **Step 5: 跑全套自测**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```

期望：**68 passed**（47 + 原 13 failed + 原 8 errors），0 failed 0 errors。若仍有失败，逐个看报错——只允许「fixture 声明与新 tb 字段不匹配」这一类，按报错继续修 Step 2/3；**不允许**为了让测试通过而修改 `region_core.py` / `multivar_core.py` / `study_io.py` 的实现。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/tune-gates/fixtures/ .claude/skills/tune-gates/apps/bb_v1/study.py
git commit -m "fix(tune-gates): 修红基线——底座改 params.yaml 并重写 tb 三维

41fd193 删除 p2.yaml 并把 tb 换代为方案 C(删 8 个旧字段),而两份 study 声明的
BASE_YAML 至今指着已删文件。这一处造成全部 21 个测试失败:
- FileNotFoundError → test_study_io 8 errors + 3 failed
- strict=True 拒收已删的 8 个 tb 字段 → test_multivar_core 8 + test_multivar_equiv 2

同批修正三处 stale 网格:stop_confirm_bars 去掉 0 档(新实现 <1 直接 raise);
big_rise_k → max_rise_k(字段已删,单位与语义均变,档位重定);max_day_drop_pct
从 SCAN_GRID 挪到 WHERE_LEVELS(毒药闸 F → W)。

冻结快照 bb_v1_p2_wide.json 按当前实现重新生成并人工核对字段。"
```

---

## Task 2: run 级常量落点 `apps/<app>/run.py` + 单源身份 `current.py`

**Files:**
- Create: `.claude/skills/tune-gates/current.py`
- Create: `.claude/skills/tune-gates/apps/_template/run.py`
- Create: `.claude/skills/tune-gates/apps/bb_v1/run.py`
- Modify: `.claude/skills/tune-gates/study_io.py`（新增 `load_run`）
- Test: `.claude/skills/tune-gates/test_study_io.py`（追加）

**Interfaces:**
- Produces:
  - `current.APP: str`、`current.RUN: str`
  - `study_io.load_run(app: str, apps_dir: Path = APPS_DIR) -> ModuleType` —— 加载 `apps/<app>/run.py`，缺文件时 `SystemExit` 并提示从 `_template` 复制；缺必填字段时 `SystemExit` 并列出缺哪些
  - `study_io.RUN_REQUIRED: tuple[str, ...]` —— run.py 必填字段名

- [ ] **Step 1: 写失败测试**

在 `.claude/skills/tune-gates/test_study_io.py` 末尾追加：

```python
def test_load_run_reads_all_required_fields(tmp_path):
    """run.py 的必填字段能被读出，且类型正确。"""
    import study_io as S
    app_dir = tmp_path / "demo"; app_dir.mkdir()
    (app_dir / "run.py").write_text(
        "DATA_DIR='datasets/pkls'\n"
        "START_DATE='2024-01-01'\nEND_DATE='2026-01-01'\n"
        "HEAD_BUFFER=250\nLABEL_HORIZON=40\nFIRST_PASSAGE_K=5.0\n"
        "PRICE_MIN=0.5\nPRICE_MAX=30.0\nVOLUME_MIN=10000.0\n"
        "TICKER_REGEX=None\nSHARD_STOCKS=200\n"
        "CMP_TICKER_REGEX=r'^[A-Z][A-C]'\nCMP_SEED=11\n"
        "CMP_N_RANDOM_CELLS=64\nCMP_N_TIGHT_CELLS=12\nMIN_WIN_BARS=1\n"
        "FOLD_COL='fold_Y'\nFOLDS=['2024','2025']\n"
        "MIN_COUNT_PER_FOLD=100\nNEIGHBOR_AXES='all'\n"
        "B_BOOT=300\nSPLIT_HALF_SEEDS=list(range(20))\nTOP_N=20\n", encoding="utf-8")
    run = S.load_run("demo", apps_dir=tmp_path)
    assert run.HEAD_BUFFER == 250
    assert run.FOLDS == ["2024", "2025"]
    assert run.SPLIT_HALF_SEEDS == list(range(20))


def test_load_run_missing_file_gives_actionable_error(tmp_path):
    import study_io as S
    (tmp_path / "demo").mkdir()
    with pytest.raises(SystemExit) as e:
        S.load_run("demo", apps_dir=tmp_path)
    assert "_template" in str(e.value)


def test_load_run_missing_field_lists_which(tmp_path):
    import study_io as S
    app_dir = tmp_path / "demo"; app_dir.mkdir()
    (app_dir / "run.py").write_text("HEAD_BUFFER=250\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        S.load_run("demo", apps_dir=tmp_path)
    assert "FOLDS" in str(e.value)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k load_run -q
```
期望：3 个 FAIL，报 `AttributeError: module 'study_io' has no attribute 'load_run'`。

- [ ] **Step 3: 实现 `study_io.load_run`**

在 `.claude/skills/tune-gates/study_io.py` 中 `load_study` 定义之后插入：

```python
RUN_REQUIRED = ("DATA_DIR", "START_DATE", "END_DATE", "HEAD_BUFFER", "LABEL_HORIZON",
                "FIRST_PASSAGE_K", "PRICE_MIN", "PRICE_MAX", "VOLUME_MIN", "TICKER_REGEX",
                "SHARD_STOCKS", "CMP_TICKER_REGEX", "CMP_SEED", "CMP_N_RANDOM_CELLS",
                "CMP_N_TIGHT_CELLS", "MIN_WIN_BARS", "FOLD_COL", "FOLDS",
                "MIN_COUNT_PER_FOLD", "NEIGHBOR_AXES", "B_BOOT", "SPLIT_HALF_SEEDS", "TOP_N")


def load_run(app: str, apps_dir: Path = APPS_DIR):
    """加载 apps/<app>/run.py 的 run 级常量。

    为什么不放 study.py:study 指纹是整份文件哈希、且被 check_run_matches_classification
    当长表准入校验——把 TOP_N 这类识别端常量放进去,改一个数就让已有长表读不了、必须重扫。
    run.py 不进任何指纹,改它不影响长表复用。
    """
    p = Path(apps_dir) / app / "run.py"
    if not p.exists():
        raise SystemExit(f"{p} 不存在:cp {APPS_DIR / '_template' / 'run.py'} {p} 后按注释填写")
    spec = importlib.util.spec_from_file_location(f"tune_gates_run_{app}", p)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    missing = [k for k in RUN_REQUIRED if not hasattr(mod, k)]
    if missing:
        raise SystemExit(f"{p} 缺少必填字段: {missing}(模板见 {APPS_DIR / '_template' / 'run.py'})")
    return mod
```

若文件顶部尚未 `import importlib.util`，一并补上（与 `load_study` 用同一套导入机制）。

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k load_run -q
```
期望：3 passed。

- [ ] **Step 5: 建 `apps/_template/run.py`**

```python
# -*- coding: utf-8 -*-
"""tune-gates · run 级常量模板。复制为 apps/<app>/run.py 后按需改。

与 study.py 的分工(**不要搞混,搞混会让已有长表作废**):
  - study.py = 搜索空间的声明(底座/网格/参照格)。它的**整份文件哈希**是 study 指纹,
    被 check_run_matches_classification 当长表准入校验——改它就得重扫。
  - run.py   = 这一跑的口径与预算(时间窗/功效线/bootstrap 次数/输出条数)。不进任何指纹,
    随便改,已有长表照常可读。

判据:这个常量改了以后,已有的长表还能不能用?能 → run.py;不能 → study.py。
"""

# ---- 数据与时间窗(改了要重扫) ----
DATA_DIR = "datasets/pkls"
START_DATE, END_DATE = "2024-01-01", "2026-01-01"
HEAD_BUFFER = 250                 # ★ run 级口径单源:写进 run_meta.json,compare/region 读之
LABEL_HORIZON, FIRST_PASSAGE_K = 40, 5.0
PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
TICKER_REGEX = None               # None = 全宇宙;调试用 r"^A[A-C]" 之类缩小
SHARD_STOCKS = 200                # 每个 parquet 分片攒多少只股

# ---- 对拍(compare_longtable) ----
CMP_TICKER_REGEX = r"^[A-Z][A-C]"  # 跨字母抽样;红线要求参与比较的股数 >= 500
CMP_SEED = 11
CMP_N_RANDOM_CELLS, CMP_N_TIGHT_CELLS = 64, 12
MIN_WIN_BARS = 1                  # 对齐生产 _worker 的"只跳空窗口"

# ---- 识别(region_find) ----
FOLD_COL, FOLDS = "fold_Y", ["2024", "2025"]
MIN_COUNT_PER_FOLD = 100          # 仅在一个 app 上校准过(口径偏松、方向不保守,见 reference.md §8)
NEIGHBOR_AXES = "all"
B_BOOT = 300
SPLIT_HALF_SEEDS = list(range(20))  # 多种子:单种子的 split-half 抖动 sd≈0.076,远大于 optimism 的 MC SE
TOP_N = 20
```

- [ ] **Step 6: 建 `apps/bb_v1/run.py` 与 `current.py`**

`apps/bb_v1/run.py` = 复制模板，值取自四个脚本 `main()` 当前的实际取值（与模板默认值一致，无需改动），文件头 docstring 改成 `"""bb_v1 · tune-gates run 级常量。"""` 加一行 `# 2026-08-30 自四个入口脚本 main() 迁入`。

`.claude/skills/tune-gates/current.py`：

```python
# -*- coding: utf-8 -*-
"""tune-gates · 当前作用的 app 身份(单源)。

四个入口脚本(app_setup / multivar_scan / compare_longtable / region_find)都在 main()
顶部读这里,所以切 app 只改这一个文件;而每个脚本 main() 里仍有一行显式的 `APP = C.APP`,
按回车前看得见这一跑读的是什么。

RUN 用于区分同一个 app 的多份长表(主窗 vs 外推窗)——它们口径不同,
write_run_meta 会拒绝写进同一个目录,必须分开放。
"""

APP = "bb_v1"
RUN = "main"        # 主窗;跑外推窗时改成 "oos2026" 之类,输出目录随之分开
```

- [ ] **Step 7: 跑全套自测 + Commit**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
# 期望: 71 passed（68 + 3 新增）

git add .claude/skills/tune-gates/current.py .claude/skills/tune-gates/apps/_template/run.py \
        .claude/skills/tune-gates/apps/bb_v1/run.py .claude/skills/tune-gates/study_io.py \
        .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): 新增 run.py 落点与 current.py 单源身份

run 级常量不能进 study.py:study 指纹是整份文件哈希且被长表准入校验消费,
改一个 TOP_N 就让已有长表作废。新增 apps/<app>/run.py 承载这些常量,不进任何指纹。

current.py 提供 APP/RUN 单源:切 app 只改一处,而各脚本 main() 仍显式读一行、
按回车前看得见作用对象。RUN 区分同 app 的多份长表(主窗/外推窗口径不同)。"
```

---

## Task 3: 四个入口脚本接入 `current.py` + `run.py` + 身份横幅 + MODE 默认值

**为什么四个脚本合并成一个 task**：它们是同一类改动，且 Task 4 的 `bench_workers` 正则改写表必须与四个脚本的常量行**同批**保持一致——分成四个 task 会出现中间态，那时 `bench_workers` 已经静默失配。

**Files:**
- Modify: `.claude/skills/tune-gates/app_setup.py:19-21`
- Modify: `.claude/skills/tune-gates/multivar_scan.py`（`main()` 常量段）
- Modify: `.claude/skills/tune-gates/compare_longtable.py`（`main()` 常量段）
- Modify: `.claude/skills/tune-gates/region_find.py`（`main()` 常量段）

**Interfaces:**
- Consumes: `current.APP` / `current.RUN`、`study_io.load_run`
- Produces: 四个脚本不再需要手填 `APP` / `LONGTABLE_DIR`；输出目录统一为 `outputs/tune_gates/<APP>/<RUN>/`

- [ ] **Step 1: 改 `app_setup.py`**

把 `main()` 开头（原 19-21 行）替换为：

```python
def main() -> None:
    import current as C
    APP, RUN = C.APP, C.RUN          # 单源见 current.py;此处显式一行,按回车前看得见
    MODE = "check"                   # "build" | "check" | "delete"

    S.require(APP, "APP")
    print(f"[app_setup] APP={APP} RUN={RUN} MODE={MODE}")
```

**注意**：`MODE` 默认值从 `"build"` 改为 `"check"`（拍板项 5）——`build` 会覆盖 git 跟踪的 `classification.json`，不该是默认动作。同时把文件顶部 docstring 里 `用法:复制到研究目录、填 APP、选 MODE` 一句改为 `用法:改 current.py 选 app、改 main() 里的 MODE 后 uv run python .claude/skills/tune-gates/app_setup.py`。

`sys.path` 那两行（`app_setup.py:15`）已经把 skill 目录加进去了，`import current` 可直接工作。

- [ ] **Step 2: 改 `multivar_scan.py`**

`main()` 常量段整段替换为：

```python
def main() -> None:
    import current as C
    import study_io as S
    APP, RUN = C.APP, C.RUN
    run = S.load_run(APP)
    DATA_DIR = run.DATA_DIR
    START_DATE, END_DATE = run.START_DATE, run.END_DATE
    HEAD_BUFFER = run.HEAD_BUFFER
    LABEL_HORIZON, FIRST_PASSAGE_K = run.LABEL_HORIZON, run.FIRST_PASSAGE_K
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = run.PRICE_MIN, run.PRICE_MAX, run.VOLUME_MIN
    TICKER_REGEX = run.TICKER_REGEX
    SHARD_STOCKS = run.SHARD_STOCKS
    WORKERS = 16          # 机器级,不随 app 变;实测定标见 reference.md §3.1
    OUT_DIR = f"outputs/tune_gates/{APP}/{RUN}"

    from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls
    S.require(APP, "APP")
    print(f"[multivar_scan] APP={APP} RUN={RUN} → {OUT_DIR} (窗 {START_DATE}..{END_DATE}, HEAD_BUFFER={HEAD_BUFFER}, WORKERS={WORKERS})")
```

原先 `OUT_DIR = None` 分支（`None → outputs/tune_gates/<APP>/`）现在恒为具体值——检查 `main()` 后续对 `OUT_DIR is None` 的判断，若有则删掉该分支（保留 `out = REPO / OUT_DIR`）。

- [ ] **Step 3: 改 `compare_longtable.py`**

```python
def main():
    import current as C
    import study_io as S
    APP, RUN = C.APP, C.RUN
    run = S.load_run(APP)
    LONGTABLE_DIR = f"outputs/tune_gates/{APP}/{RUN}/longtable"
    TICKER_REGEX = run.CMP_TICKER_REGEX
    SEED, N_RANDOM_CELLS, N_TIGHT_CELLS = run.CMP_SEED, run.CMP_N_RANDOM_CELLS, run.CMP_N_TIGHT_CELLS
    MIN_WIN_BARS = run.MIN_WIN_BARS
    WORKERS = 16          # 机器级;定标见 reference.md §3.1
    OUT_LOG = None        # None → <LONGTABLE_DIR 父目录>/compare_longtable.log

    print(f"[compare_longtable] APP={APP} RUN={RUN} → {LONGTABLE_DIR} (抽样 {TICKER_REGEX}, WORKERS={WORKERS})")
    S.require(LONGTABLE_DIR, "LONGTABLE_DIR")
    lt = REPO / LONGTABLE_DIR
```

- [ ] **Step 4: 改 `region_find.py`**

```python
def main() -> None:
    import current as C
    import study_io as S
    APP, RUN = C.APP, C.RUN
    run = S.load_run(APP)
    LONGTABLE_DIR = f"outputs/tune_gates/{APP}/{RUN}/longtable"
    FOLD_COL, FOLDS = run.FOLD_COL, run.FOLDS
    MIN_COUNT_PER_FOLD = run.MIN_COUNT_PER_FOLD
    NEIGHBOR_AXES = run.NEIGHBOR_AXES
    B_BOOT, TOP_N = run.B_BOOT, run.TOP_N
    SPLIT_HALF_SEEDS = run.SPLIT_HALF_SEEDS
    OUT_DIR = None        # None → LONGTABLE_DIR 的父目录

    print(f"[region_find] APP={APP} RUN={RUN} → {LONGTABLE_DIR} (功效线 {MIN_COUNT_PER_FOLD}/fold, B={B_BOOT}, split-half 种子 {len(SPLIT_HALF_SEEDS)} 个)")
    S.require(LONGTABLE_DIR, "LONGTABLE_DIR")
    lt = REPO / LONGTABLE_DIR
```

**注意**：原 `B_BOOT, SEED, TOP_N = 300, 0, 20` 里的 `SEED` 在 Task 6 会被 `SPLIT_HALF_SEEDS` 取代。本 task 先引入 `SPLIT_HALF_SEEDS` 变量但暂不使用（Task 6 接上）；若 `main()` 后续有 `split_half(..., seed=SEED)` 调用，本 task 暂改为 `seed=SPLIT_HALF_SEEDS[0]` 保持行为不变，Task 6 再改成多种子。

- [ ] **Step 5: 冒烟验证四个脚本能起来**

```bash
# app_setup 的 check 分支应能打出横幅与三行报告
uv run python .claude/skills/tune-gates/app_setup.py 2>&1 | head -8
```

期望：先打印 `[app_setup] APP=bb_v1 RUN=main MODE=check`，随后是 source/base/study 三行报告。**若报 `classification.json` 与 study 不一致属正常**（Task 1 改过 study.py），记下但不在本 task 处理。

其余三个脚本需要真实长表才能跑完，本 task 只验证 import 与常量装配：

```bash
for f in multivar_scan compare_longtable region_find; do
  uv run python -c "
import subprocess,sys
from pathlib import Path
REPO=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],text=True).strip())
sys.path.insert(0,str(REPO)); sys.path.insert(0,str(REPO/'.claude/skills/tune-gates'))
import importlib; m=importlib.import_module('$f'); print('$f import ok')
"
done
```

- [ ] **Step 6: 跑全套自测 + Commit**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3   # 期望 71 passed

git add .claude/skills/tune-gates/app_setup.py .claude/skills/tune-gates/multivar_scan.py \
        .claude/skills/tune-gates/compare_longtable.py .claude/skills/tune-gates/region_find.py
git commit -m "refactor(tune-gates): 四脚本接入 current.py/run.py + 身份横幅

run 级常量改从 apps/<app>/run.py 读;APP/RUN 从 current.py 单源读、各脚本 main()
仍显式一行。输出目录统一推导为 outputs/tune_gates/<APP>/<RUN>/,LONGTABLE_DIR
不再手填。

新增运行时身份横幅:动手前打印 APP/RUN/输出路径。它比源码字面量更强——显示的是
实际会用的值与推导出的路径,而不是你以为的值。app_setup 尤其需要:它此前是写完
才 print,覆盖 git 跟踪的 classification.json 之前一声不吭。

app_setup 的 MODE 默认值 build → check(build 会覆盖 git 跟踪文件,不该是默认动作)。"
```

---

## Task 4: `bench_workers.py` 改写表同批更新

**背景**：`bench_workers.py` 用 `re.sub(..., count=1)` 改写目标脚本源码里的常量行，**不匹配时静默 no-op**。Task 3 把 `APP = None` / `OUT_DIR = None` / `LONGTABLE_DIR = None` / `TICKER_REGEX = ...` 这些行全改了，改写表必须同批更新，否则 benchmark 会拿全宇宙 8000+ 只股票跑 7 档 WORKER 网格且完全静默。

**Files:**
- Modify: `.claude/skills/tune-gates/bench_workers.py:113-135`（常量与改写表）、`:151-154`（`re.sub` → `re.subn` + 断言）

**Interfaces:**
- Consumes: Task 3 改造后的四脚本常量行形态

- [ ] **Step 1: 把 `re.sub` 换成 `re.subn` 并对失配断言**

`bench_workers.py:151` 与 `:154` 附近，把两处替换改为：

```python
            text, n = re.subn(r'^(\s*)WORKERS = \d+', rf'\g<1>WORKERS = {w}', text, count=1, flags=re.M)
            if n != 1:
                raise SystemExit(f"{script}: WORKERS 常量行改写失配(命中 {n} 次)——"
                                 "目标脚本的常量行形态变了,请同步更新 bench_workers 的改写表")
```

```python
            for pat, rep in subs:
                text, n = re.subn(pat, rep, text, count=1, flags=re.M)
                if n != 1:
                    raise SystemExit(f"{script}: 改写表条目 {pat!r} 失配(命中 {n} 次)——"
                                     "目标脚本的常量行形态变了,请同步更新 bench_workers 的改写表")
```

**这一步是本 task 的核心价值**：静默失配变成响亮失败。即使下面的改写表将来又过期，也会当场报错而不是跑错。

- [ ] **Step 2: 更新改写表以匹配 Task 3 的新形态**

Task 3 之后，`APP` / `OUT_DIR` / `LONGTABLE_DIR` / `TICKER_REGEX` 都不再是脚本里的可改写字面行。改写策略换成：**临时改写 `current.py` 与目标 app 的 `run.py`**，脚本本身只改 `WORKERS`。

把 `main()` 里 `subs` 的构造（原 126-133 行）改为：

```python
    # Task 3 之后:APP/RUN 来自 current.py、run 级常量来自 apps/<app>/run.py,
    # 目标脚本里不再有可改写的字面行。这里改为在 scratch 里放一份临时 current.py + run.py,
    # 让复制出去的脚本通过 sys.path 优先读到它们;脚本本身只改 WORKERS 一行。
    bench_current = SCRATCH / "current.py"
    bench_current.write_text(f'APP = "{APP}"\nRUN = "bench"\n', encoding="utf-8")
    bench_apps = SCRATCH / "apps" / APP
    bench_apps.mkdir(parents=True, exist_ok=True)
    src_run = (REPO / ".claude/skills/tune-gates/apps" / APP / "run.py").read_text(encoding="utf-8")
    src_run = re.sub(r'^TICKER_REGEX = .*', f'TICKER_REGEX = r"{TICKER_REGEX}"', src_run, count=1, flags=re.M)
    src_run = re.sub(r'^CMP_TICKER_REGEX = .*', f'CMP_TICKER_REGEX = r"{TICKER_REGEX}"', src_run, count=1, flags=re.M)
    (bench_apps / "run.py").write_text(src_run, encoding="utf-8")
    subs = []   # 目标脚本只剩 WORKERS 需要改写
```

同时在复制出的脚本运行前，把 `SCRATCH` 插到 `PYTHONPATH` 最前（`env` 里设 `PYTHONPATH=f"{SCRATCH}:{...}"`），使其 `import current` 命中临时副本。

- [ ] **Step 3: 更新文件头 docstring**

把 `bench_workers.py:11` 那句「每个 WORKERS 值把目标脚本复制一份、只 sed 改常量（与「复制到研究目录改常量」…）」改为：

```
**跑法**：每个 WORKERS 值把目标脚本复制一份、只改写 WORKERS 一行；APP/RUN 与 run 级常量
通过在 scratch 里放临时 current.py + apps/<app>/run.py 并前置 PYTHONPATH 提供。
改写一律用 re.subn + 失配断言——静默 no-op 曾是这里最危险的失败模式
（TICKER_REGEX 失配会让 benchmark 拿全宇宙 8000+ 只跑 7 档网格且毫无提示）。
```

- [ ] **Step 4: 干跑验证失配断言真的会响**

```bash
uv run python -c "
import re
text = 'def main():\n    WORKERS = 16\n'
t, n = re.subn(r'^(\s*)WORKERS = \d+', r'\g<1>WORKERS = 8', text, count=1, flags=re.M)
assert n == 1, 'sanity'
t2, n2 = re.subn(r'^(\s*)NOT_THERE = \d+', r'\1x', text, count=1, flags=re.M)
assert n2 == 0
print('subn 语义确认:命中计数可用于断言')
"
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/bench_workers.py
git commit -m "fix(tune-gates): bench_workers 改写表随 Task 3 同批更新 + 失配即报错

re.sub → re.subn + 断言:改写失配从静默 no-op 变成响亮失败。这是本文件最危险的
失败模式——TICKER_REGEX 失配会让 benchmark 拿全宇宙 8000+ 只股票跑 7 档 WORKER
网格,耗时极长且毫无提示。

Task 3 后目标脚本里不再有 APP/OUT_DIR/LONGTABLE_DIR/TICKER_REGEX 的字面行,
改为在 scratch 放临时 current.py + apps/<app>/run.py 并前置 PYTHONPATH,
脚本本身只改写 WORKERS 一行。"
```

---

## Task 5: `write_run_meta` 补存 source/base 指纹副本（消除「假绿」）

**背景**：长表准入校验 `check_run_matches_classification` 只比 `study_fingerprint`。而 2026-08-25 那份长表的 study 指纹与当前 `study.py` **逐字相同**（`31cf49ee…`），却因为 `BASE_YAML` 指向的 `p2.yaml` 被删、`throwback_v1.py` 被重写而**根本无法再生**——检查放行了一份回不去的数据。`classification.json` 其实存了 source 指纹（`fingerprints.source.files` 正好列着 `path2/atoms/throwback_v1.py`），缺的是长表侧没留副本。

**Files:**
- Modify: `.claude/skills/tune-gates/study_io.py`（`write_run_meta` 附近、`RUN_CALIBER` 定义）
- Modify: `.claude/skills/tune-gates/multivar_scan.py`（写 `run_meta` 处，约 107-110 行）
- Test: `.claude/skills/tune-gates/test_study_io.py`（追加）

**Interfaces:**
- Produces: `run_meta.json` 新增两个键 `source_fingerprint: str`、`base_fingerprint: str`（**不进 `RUN_CALIBER`**——它们变了不代表口径变了，只代表不可再生；准入仍由 `study_fingerprint` 把关，可再生性由 Task 8 单独判定）

- [ ] **Step 1: 写失败测试**

```python
def test_run_meta_carries_source_and_base_fingerprints(tmp_path):
    """run_meta 要留 source/base 指纹副本,好让从长表侧出发的核对拿得到它们。"""
    import study_io as S
    meta = {"app": "demo", "start_date": "2024-01-01", "end_date": "2026-01-01",
            "head_buffer": 250, "label_horizon": 40, "first_passage_k": 5.0,
            "price_min": 0.5, "price_max": 30.0, "volume_min": 10000.0,
            "study_fingerprint": "aaa", "source_fingerprint": "bbb",
            "base_fingerprint": "ccc", "git_head": "0000000", "written_at": "t"}
    S.write_run_meta(tmp_path, meta)
    got = S.load_run_meta(tmp_path)
    assert got["source_fingerprint"] == "bbb"
    assert got["base_fingerprint"] == "ccc"


def test_source_fingerprint_not_in_run_caliber():
    """source/base 指纹不参与口径校验:它们变了是'不可再生',不是'混窗'。"""
    import study_io as S
    assert "source_fingerprint" not in S.RUN_CALIBER
    assert "base_fingerprint" not in S.RUN_CALIBER
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k "run_meta_carries or not_in_run_caliber" -q
```
期望：第一个 FAIL（`KeyError`/断言失败），第二个可能已 PASS（因为字段本来就不在），这正常。

- [ ] **Step 3: 在 `multivar_scan.py` 写 run_meta 处补两个字段**

找到写 `run_meta` 的字典（约 `multivar_scan.py:107-110`，含 `"study_fingerprint": cl["fingerprints"]["study"], "git_head": cl["git_head"],`），在同一个字典里补：

```python
                          "source_fingerprint": cl["fingerprints"]["source"]["hash"],
                          "base_fingerprint": cl["fingerprints"]["base"],
```

`write_run_meta` 本身无需改动（它写整个 dict）；`RUN_CALIBER` 保持不变。

- [ ] **Step 4: 跑测试确认通过 + 全套自测**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k "run_meta_carries or not_in_run_caliber" -q   # 2 passed
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3                                                # 73 passed
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/multivar_scan.py .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): run_meta 补存 source/base 指纹副本

消除'假绿':长表准入只比 study_fingerprint,而 study.py 可以逐字未变、
BASE_YAML 指向的底座却已被删、detector 源码已被重写——检查放行一份回不去的数据。
classification.json 本来就存了 source 指纹,缺的是长表侧没有副本,
所以从长表出发的核对拿不到它。

两个新字段不进 RUN_CALIBER:它们变了是'不可再生',不是'混窗',
不该阻止续跑;可再生性由独立的 check_regenerable 判定。"
```

---

## Task 6: `split_half` 多种子（消除四位小数无不确定度的假精确）

**背景**：`region_find.py:38` 原先 `SEED=0` 硬编码、只做一次对半分，报告里写成 `split-half = -0.1319（下界）`，四位小数无误差范围。实测 18 个有效种子的 **sd = 0.0762、极差 0.274**（−0.3083 ~ −0.0346），另有 2 个种子返回 NaN。同一行的 optimism 却带 ±SE。这个抖动比跨轮暴露偏差大 36 倍。

**Files:**
- Modify: `.claude/skills/tune-gates/region_core.py`（`split_half` 之后新增 `split_half_multi`）
- Modify: `.claude/skills/tune-gates/region_find.py`（调用处 + 报告行）
- Test: `.claude/skills/tune-gates/test_region_core.py`（追加）

**Interfaces:**
- Produces: `region_core.split_half_multi(prep, ref_index, min_count, axes, seeds) -> dict`
  返回 `{"mean": float, "sd": float, "se": float, "n_valid": int, "n_nan": int, "values": list[float]}`；
  全部种子都 NaN 时 `mean`/`sd`/`se` 为 `nan`、`n_valid=0`。**保留原 `split_half` 不动**（单种子仍是它的语义，测试与其他调用方依赖它）。

- [ ] **Step 1: 写失败测试**

在 `.claude/skills/tune-gates/test_region_core.py` 末尾追加：

```python
def test_split_half_multi_aggregates_seeds():
    """多种子聚合:n_valid 计数正确、mean 等于有效值的均值、se = sd/sqrt(n)。"""
    from region_core import split_half, split_half_multi
    df = _synth(seed=3, n_sym=400)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    ref, axes, mc = (1, 1, 0, 0), list(range(4)), 50
    seeds = list(range(6))
    r = split_half_multi(prep, ref, mc, axes, seeds)
    singles = [split_half(prep, ref, mc, axes, s) for s in seeds]
    finite = [v for v in singles if np.isfinite(v)]
    assert r["n_valid"] == len(finite)
    assert r["n_nan"] == len(seeds) - len(finite)
    if finite:
        assert r["mean"] == pytest.approx(float(np.mean(finite)), abs=1e-12)
        if len(finite) > 1:
            assert r["se"] == pytest.approx(float(np.std(finite, ddof=1) / np.sqrt(len(finite))), abs=1e-12)


def test_split_half_multi_all_nan_is_safe():
    """全 NaN 时不炸,n_valid=0 且 mean 为 nan。"""
    from region_core import split_half_multi
    df = _synth(seed=4, n_sym=60)
    prep = prepare(df, COMBO, PREDS, "fold", FOLDS)
    r = split_half_multi(prep, (1, 1, 0, 0), 10_000_000, list(range(4)), [0, 1, 2])  # 功效线高到全不可评估
    assert r["n_valid"] == 0
    assert np.isnan(r["mean"])
```

**符号说明（已核实，照抄即可）**：`COMBO = {"g": [4, 8, 12], "K": [0, 1, 2]}`、`PREDS = [("count", ">=", [1, 2, 3]), ("fd", ">=", [0, 20])]`、`FOLDS = ["2024", "2025"]`、`_synth(seed, n_sym, plateau=None, ...)` 都是 `test_region_core.py` 文件级已有的，**不要新造**。注意 fold 列名是 `"fold"` 不是 `"fold_Y"`，`ref_index` 是 4 元组、`axes` 是 `list(range(4))`——这是该文件里 `test_bootstrap_plateau_center_stable` 的既有调用形态。若 `split_half` / `split_half_multi` 不在文件顶部的 `from region_core import (...)` 列表里，在该列表补上。

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_region_core.py -k split_half_multi -q
```
期望：FAIL，`ImportError: cannot import name 'split_half_multi'`。

- [ ] **Step 3: 实现 `split_half_multi`**

在 `.claude/skills/tune-gates/region_core.py` 的 `split_half` 定义之后插入：

```python
def split_half_multi(prep: Prepared, ref_index: tuple, min_count: int, axes, seeds) -> dict:
    """多种子跑 split_half,报均值与标准误。

    为什么必须多种子:单次对半分的结果对种子极敏感——真实长表实测 18 个有效种子
    sd=0.0762、极差 0.274(-0.3083 ~ -0.0346),而同一份报告里 optimism 自身的
    MC SE 只有 0.0062。用单种子的四位小数当"下界"是假精确:换个种子,同一份数据的
    下界能从 -0.03 变成 -0.31。

    参数:
        prep / ref_index / min_count / axes: 同 `split_half`。
        seeds: 种子序列(如 range(20))。

    返回:
        {"mean","sd","se","n_valid","n_nan","values"};全部种子失效时
        mean/sd/se 为 nan、n_valid=0。sd 用 ddof=1;n_valid==1 时 sd/se 为 nan。
    """
    vals = [split_half(prep, ref_index, min_count, axes, int(s)) for s in seeds]
    finite = [v for v in vals if np.isfinite(v)]
    n = len(finite)
    if n == 0:
        return {"mean": float("nan"), "sd": float("nan"), "se": float("nan"),
                "n_valid": 0, "n_nan": len(vals), "values": vals}
    mean = float(np.mean(finite))
    sd = float(np.std(finite, ddof=1)) if n > 1 else float("nan")
    se = float(sd / np.sqrt(n)) if n > 1 else float("nan")
    return {"mean": mean, "sd": sd, "se": se, "n_valid": n, "n_nan": len(vals) - n, "values": vals}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest .claude/skills/tune-gates/test_region_core.py -k split_half_multi -q
```
期望：2 passed。

- [ ] **Step 5: `region_find.py` 改用多种子并改报告行**

把原来算 `sh` 的那行（形如 `sh = split_half(prep, ref_index, MIN_COUNT_PER_FOLD, axes, SEED)`）改为：

```python
    shm = split_half_multi(prep, ref_index, MIN_COUNT_PER_FOLD, axes, SPLIT_HALF_SEEDS)
    sh = shm["mean"]
```

并把报告里那一行（`f"- naive s_nb = {naive:.4f};split-half = {sh:.4f}(下界)"`）改为：

```python
             "", verdict_title, verdict_lead,
             (f"- naive s_nb = {naive:.4f};split-half = {shm['mean']:.4f} ± {shm['se']:.4f}"
              f"(sd {shm['sd']:.4f},{shm['n_valid']}/{len(SPLIT_HALF_SEEDS)} 个种子有效"
              + (f",{shm['n_nan']} 个返回 NaN" if shm["n_nan"] else "") + ")"),
             "- **split-half 不是稳定的界**:它对随机对半分的种子高度敏感(实测 sd≈0.076、"
             "极差≈0.27,比 optimism 自身的 MC SE 大一个数量级),故按均值±SE 报,"
             "不要拿单次数值当下界读。",
```

同时把 `import` 行补上 `split_half_multi`（`region_find.py` 顶部从 `region_core` 导入的那一处）。

- [ ] **Step 6: 跑全套自测 + Commit**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3   # 期望 75 passed

git add .claude/skills/tune-gates/region_core.py .claude/skills/tune-gates/region_find.py \
        .claude/skills/tune-gates/test_region_core.py
git commit -m "feat(tune-gates): split-half 改多种子,报均值±SE

原先 SEED=0 硬编码、只做一次对半分,报告里写成四位小数的'下界'且无不确定度,
而同一行的 optimism 带 ±SE。实测 18 个有效种子 sd=0.0762、极差 0.274
(-0.3083 ~ -0.0346),另有 2 个种子返回 NaN——换个种子,同一份数据的'下界'
能从 -0.03 变成 -0.31。

这个抖动比本轮讨论的跨轮暴露偏差(0.0021)大 36 倍,是三口径里最不该假精确的一个。
新增 split_half_multi 聚合多种子;原 split_half 单种子语义保留不动。"
```

---

## Task 7: `exposure.jsonl` 识别端运行审计日志

**背景**：`region_find` 每次运行都无条件覆盖 `region_report.md`（`region_find.py:183` 的 `write_text`），而 `out` 默认落在 gitignore 的目录下。同一份数据上"又看了一遍"这件事不留痕迹。扫描端早已为同一个覆盖病加过 `run_stats.jsonl`，识别端没加——**而识别端才是选择真正发生的地方**。

**它不是 resume 状态**：丢了它，算出来的数字一个都不变，变的只是人解读时手上有没有背景。称呼统一用「运行审计日志」。

**Files:**
- Modify: `.claude/skills/tune-gates/study_io.py`（新增 `append_exposure`）
- Modify: `.claude/skills/tune-gates/region_find.py`（末尾写报告之后追加）
- Test: `.claude/skills/tune-gates/test_study_io.py`（追加）

**Interfaces:**
- Produces: `study_io.append_exposure(app: str, record: dict, apps_dir: Path = APPS_DIR) -> Path`
  以 UTF-8 追加一行 JSON 到 `apps/<app>/exposure.jsonl`，返回该路径。目录不存在时报错（app 必须已接入）。

**为什么放 `apps/<app>/` 而不是 `outputs/`**：`outputs` 在 gitignore 里跨轮不持久；更关键的是 `RUN_CALIBER` 含 `study_fingerprint`，改 `study.py`（换档位/加维/删维）就强制换 `OUT_DIR`，历史会碎在多个目录里——**而改网格恰恰是最该被记住的那次跨轮动作**。

- [ ] **Step 1: 写失败测试**

```python
def test_append_exposure_is_append_only(tmp_path):
    """两次写入产生两行,先写的不被覆盖。"""
    import json
    import study_io as S
    (tmp_path / "demo").mkdir()
    S.append_exposure("demo", {"ts": "t1", "c_hat": {"a": 1}}, apps_dir=tmp_path)
    p = S.append_exposure("demo", {"ts": "t2", "c_hat": {"a": 2}}, apps_dir=tmp_path)
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["ts"] == "t1"
    assert json.loads(lines[1])["ts"] == "t2"


def test_append_exposure_requires_existing_app_dir(tmp_path):
    import study_io as S
    with pytest.raises(SystemExit):
        S.append_exposure("nope", {"ts": "t"}, apps_dir=tmp_path)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k append_exposure -q
```
期望：FAIL，`AttributeError: ... has no attribute 'append_exposure'`。

- [ ] **Step 3: 实现 `append_exposure`**

在 `.claude/skills/tune-gates/study_io.py` 的 `load_run` 之后插入：

```python
def append_exposure(app: str, record: dict, apps_dir: Path = APPS_DIR) -> Path:
    """把一次识别运行追加进 apps/<app>/exposure.jsonl(只追加,不覆盖)。

    这是**识别端的运行审计日志**,不是 resume 状态:丢了它算出来的数字一个都不变,
    变的只是人解读三口径时手上有没有"这批数据已经看过几次"的背景。

    为什么落 apps/<app>/ 而不是 outputs/:outputs 在 gitignore 里跨轮不持久;
    且 RUN_CALIBER 含 study_fingerprint,改 study.py 就强制换 OUT_DIR、历史会碎成多份,
    而改网格恰恰是最该被记住的那次跨轮动作。
    """
    d = Path(apps_dir) / app
    if not d.is_dir():
        raise SystemExit(f"{d} 不存在:app 未接入,无处记录运行历史")
    p = d / "exposure.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return p
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k append_exposure -q
```
期望：2 passed。

- [ ] **Step 5: `region_find.py` 末尾接上**

在 `(out / "region_report.md").write_text("\n".join(lines))` 之后、`print(...)` 之前插入：

```python
    S.append_exposure(APP, {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "tool": "region_find", "run": RUN,
        "git_head": cl["git_head"], "study_fingerprint": cl["fingerprints"]["study"],
        "longtable": LONGTABLE_DIR, "head_buffer": HEAD_BUFFER,
        "folds": FOLDS, "min_count_per_fold": MIN_COUNT_PER_FOLD,
        "neighbor_axes": NEIGHBOR_AXES, "grid_shape": list(shape), "n_cells": int(n_cells),
        "n_evaluable": int(n_eval), "ref_point": ref_c, "c_hat": cell_coords(prep, c_hat),
        "has_region": bool(has_region),
        "naive": float(naive), "optimism": float(bs["optimism"]), "optimism_se": float(bs["optimism_se"]),
        "split_half_mean": float(shm["mean"]), "split_half_se": float(shm["se"]),
        "split_half_n_valid": int(shm["n_valid"]),
        "stability": float(bs["stability"]), "ci": [float(bs["ci"][0]), float(bs["ci"][1])],
    })
```

若 `region_find.py` 顶部尚未 `from datetime import datetime`，补上。`bs` 的键名已核实：`bs["optimism"]` / `bs["optimism_se"]` / `bs["n_opt"]` / `bs["stability"]` / `bs["ci"]`（见 `region_find.py:63`），照抄即可。

- [ ] **Step 6: 跑全套自测 + Commit**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3   # 期望 77 passed

git add .claude/skills/tune-gates/study_io.py .claude/skills/tune-gates/region_find.py \
        .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): region_find 追加 exposure.jsonl 运行审计日志

region_find 每轮无条件覆盖 region_report.md,而 out 默认落在 gitignore 目录下,
于是'这批数据又看了一遍'不留痕迹。扫描端早就为同一个覆盖病加过 run_stats.jsonl,
识别端没加——而识别端才是选择真正发生的地方。

刻意不叫它 resume 状态:丢了它算出来的数字一个都不变,变的只是人解读三口径时
手上有没有背景。落 apps/<app>/ 而非 outputs/,因为改 study.py 会强制换 OUT_DIR,
历史会碎成多份,而改网格恰恰是最该被记住的跨轮动作。"
```

---

## Task 8: 可再生性检测（删除功能的安全地基）

**背景**：分级轴必须从「进不进 git」换成「**能不能用当前代码再生**」。2026-08-25 那份长表 study 指纹与当前 `study.py` 逐字相同、准入会放行，但 `BASE_YAML` 指向的 `p2.yaml` 已被删、`throwback_v1.py` 已重写——**当前代码根本再生不出它**，而它是一份已提交研究报告唯一的底层数据。

**设计原则（写进 docstring）**：**单向可靠**——报「不可再生」一定对，报「可再生」只是没发现问题。误差全推到「多留垃圾」一侧，这正是安全检查该有的形状。于是剩下的已知边界（spec 拓扑变了会让记录的文件清单本身过期）是被设计吸收的，而不是弱点：漏报只让东西留下来，永远不会造成删除。

**Files:**
- Modify: `.claude/skills/tune-gates/study_io.py`（新增 `check_regenerable`）
- Test: `.claude/skills/tune-gates/test_study_io.py`（追加）

**Interfaces:**
- Produces: `study_io.check_regenerable(longtable_dir: Path, apps_dir: Path = APPS_DIR) -> tuple[bool, list[str]]`
  返回 `(regenerable, reasons)`；`regenerable=False` 时 `reasons` 列出全部不可再生原因（可多条）。四条链依次检查，**任一条失败都返回 False 并继续收集其余原因**（一次报全，不短路）。

- [ ] **Step 1: 写失败测试**

```python
def test_check_regenerable_reports_missing_base_yaml(tmp_path, monkeypatch):
    """底座 yaml 不存在 → 不可再生,原因里点名该文件。"""
    import json
    import study_io as S
    lt = tmp_path / "longtable"; lt.mkdir()
    (lt / "run_meta.json").write_text(json.dumps({
        "app": "demo", "study_fingerprint": "aaa",
        "source_fingerprint": "bbb", "base_fingerprint": "ccc"}), encoding="utf-8")
    ok, reasons = S.check_regenerable(lt, apps_dir=tmp_path / "apps")
    assert ok is False
    assert reasons


def test_check_regenerable_missing_run_meta_is_unknown_not_deletable(tmp_path):
    """没有 run_meta 的长表 → 归属不明,必须报不可再生(只报不删)。"""
    import study_io as S
    lt = tmp_path / "longtable"; lt.mkdir()
    ok, reasons = S.check_regenerable(lt, apps_dir=tmp_path / "apps")
    assert ok is False
    assert any("run_meta" in r for r in reasons)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k check_regenerable -q
```
期望：FAIL，`AttributeError`。

- [ ] **Step 3: 实现 `check_regenerable`**

在 `.claude/skills/tune-gates/study_io.py` 的 `check_run_matches_classification` 之后插入：

```python
def check_regenerable(longtable_dir: Path, apps_dir: Path = APPS_DIR) -> tuple:
    """判断一份长表能否用**当前代码**重新生成。四条链依次核,不短路,一次报全部原因。

    **单向可靠**(设计原则,不是弱点):报"不可再生"一定对;报"可再生"只是没发现问题。
    误差全推到"多留垃圾"一侧——漏报只让东西留下来,永远不会造成删除。
    已知边界:spec 拓扑变了会让 classification 记录的文件清单本身过期,该情形归入漏报侧。

    四条链:
      1. run_meta.json 存在吗(不存在 = 归属不明,只报不删)
      2. 该 app 的 classification.json 还在吗
      3. study 指纹是否仍与当前 study.py 一致
      4. BASE_YAML 指向的底座文件是否存在;source 指纹按 classification 记录的**文件清单**
         重算是否仍一致(不需要 import app——source_fingerprint 只是按序读那些文件的字节)

    返回:
        (regenerable: bool, reasons: list[str])
    """
    reasons = []
    lt = Path(longtable_dir)
    meta_p = lt / "run_meta.json"
    if not meta_p.exists():
        return False, [f"{meta_p} 不存在:该长表归属不明(不是 multivar_scan 新版产出),只报不删"]
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    app = meta.get("app")
    if not app:
        return False, [f"{meta_p} 里没有 app 字段:归属不明,只报不删"]

    cl_p = Path(apps_dir) / app / "classification.json"
    if not cl_p.exists():
        reasons.append(f"{cl_p} 不存在:app 已退役或未接入,无法核对再生条件")
        return False, reasons
    cl = json.loads(cl_p.read_text(encoding="utf-8"))

    study_p = Path(apps_dir) / app / "study.py"
    if not study_p.exists():
        reasons.append(f"{study_p} 不存在:声明已删,无法再生")
    elif file_sha256(study_p) != meta.get("study_fingerprint"):
        reasons.append("study.py 已改(指纹与长表记录不符):当前声明产不出这份长表")

    base_yaml = cl.get("base_yaml")
    app_module = cl.get("app_module", "")
    if base_yaml and app_module:
        pkg_rel = Path(*app_module.split(".")[:-1])
        base_p = REPO / pkg_rel / base_yaml
        if not base_p.exists():
            reasons.append(f"底座 {base_p.relative_to(REPO)} 不存在(被删或改名):当前代码跑不出这份长表")

    recorded = cl.get("fingerprints", {}).get("source", {})
    files = recorded.get("files") or []
    if files:
        paths = [REPO / f for f in files]
        if all(p.exists() for p in paths):
            now = source_fingerprint(paths)["hash"]
            if now != recorded.get("hash"):
                reasons.append(f"源码指纹不符(记录 {recorded.get('hash', '')[:16]}… / 现在 {now[:16]}…):"
                               "detector 或 app 代码已被改写,当前代码产不出这份长表")
        else:
            miss = [str(p.relative_to(REPO)) for p in paths if not p.exists()]
            reasons.append(f"源码文件已不存在: {miss}")

    return (not reasons), reasons
```

**注意**：`source_fingerprint(files)` 的入参形态以 `study_io.py:195-210` 现有实现为准——实施者先读那两个函数，确认 `source_files()` 返回的元素是 `Path` 还是 `str`、`source_fingerprint()` 期望什么，据此调整上面 `paths` 的构造，**不要改 `source_fingerprint` 本身**。

- [ ] **Step 4: 跑测试确认通过 + 对真实长表干跑**

```bash
uv run pytest .claude/skills/tune-gates/test_study_io.py -k check_regenerable -q   # 2 passed

# 对真实的 2026-08-25 长表干跑(只读,不删)
uv run python -c "
import subprocess, sys
from pathlib import Path
REPO = Path(subprocess.check_output(['git','rev-parse','--show-toplevel'], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO/'.claude/skills/tune-gates'))
import study_io as S
ok, why = S.check_regenerable(REPO/'docs/research/2026-08-25_multivar-bb_v1/longtable')
print('可再生:', ok)
for r in why: print(' -', r)
"
```

**期望**：`可再生: False`，且原因里**至少**出现底座 `p2.yaml` 不存在这一条。（Task 1 改过 `study.py`，所以 study 指纹不符那条也会出现——这正确反映了「当前声明产不出这份长表」。）

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/study_io.py .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): 新增 check_regenerable 四链可再生性检测

删除功能的分级轴必须是'能不能用当前代码再生',不是'进不进 git'。
2026-08-25 那份长表 study 指纹与当前 study.py 逐字相同、准入会放行,
但底座 p2.yaml 已删、throwback_v1.py 已重写,当前代码根本再生不出来——
而它是一份已提交研究报告唯一的底层数据。

四条链:run_meta 在否 / classification 在否 / study 指纹一致否 /
底座文件在否且 source 指纹按记录的文件清单重算一致否(不需 import app)。

设计原则=单向可靠:报'不可再生'一定对,报'可再生'只是没发现问题。
误差全推到'多留垃圾'一侧,漏报只让东西留下来、永远不会造成删除。"
```

---

## Task 9: `app_setup` 新增 `delete` MODE（app 退役清理）

**背景与红线**：
- **只走精确匹配，绝不按 app 名 glob。** 实测 glob 会误伤 6 项、同时漏 3 项——真实存在的 `2026-08-20_tune-bb-v1` 用连字符命名会被漏掉，而误伤最重的一项是把整个 `2026-08-25_multivar-bb_v1` 研究目录连报告一起删。全 repo `grep -rIl bb_v1` 命中 161 个文件，这本身就是不能 grep-and-delete 的证据。
- **分级**（`notes.md` / `exposure.jsonl` 默认**保留**，因为误删=跨轮记录永久丢失、误留=目录里多两个文件，代价不对称）。
- **delete 分支必须在 `load_study` / `import_app` 之前短路**——`app_setup.py:23-27` 无条件先跑那两行，而删除场景里 app 很可能已经坏了。**这条有现成实证**：`apps/bb_v1` 在 Task 1 之前就是坏的，`MODE=check` 连三行报告都打不出来。

**Files:**
- Modify: `.claude/skills/tune-gates/app_setup.py`
- Test: `.claude/skills/tune-gates/test_app_delete.py`（**新建**）

**Interfaces:**
- Consumes: `study_io.check_regenerable`、`study_io.APPS_DIR`
- Produces: `app_setup.plan_delete(app, apps_dir, repo, delete_notes, delete_exposure) -> dict`
  纯函数，返回 `{"must": [...], "confirm": [...], "keep": [...], "blocked": [...]}`，每项是 `{"path": str, "why": str}`。**它不删任何东西**——删除动作由 `main()` 在 `CONFIRM=True` 时执行。

- [ ] **Step 1: 写失败测试（用假目录树，绝不碰真实文件）**

新建 `.claude/skills/tune-gates/test_app_delete.py`：

```python
# -*- coding: utf-8 -*-
"""app 退役清理的分级与子串安全。全部在 tmp_path 假树上跑,不碰真实文件。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app_setup  # noqa: E402


def _mk_app(apps: Path, name: str, with_notes=True, with_exposure=True):
    d = apps / name; d.mkdir(parents=True)
    (d / "study.py").write_text("APP_MODULE='x'\n", encoding="utf-8")
    (d / "classification.json").write_text("{}", encoding="utf-8")
    if with_notes:
        (d / "notes.md").write_text("# notes\n", encoding="utf-8")
    if with_exposure:
        (d / "exposure.jsonl").write_text('{"ts":"t"}\n', encoding="utf-8")
    return d


def test_notes_and_exposure_default_to_keep(tmp_path):
    """默认保留:它们记的是'对这批数据做过什么',意义不随 app 消失。"""
    apps = tmp_path / "apps"; _mk_app(apps, "demo")
    plan = app_setup.plan_delete("demo", apps, tmp_path, delete_notes=False, delete_exposure=False)
    must = {Path(x["path"]).name for x in plan["must"]}
    keep = {Path(x["path"]).name for x in plan["keep"]}
    assert must == {"study.py", "classification.json"}
    assert {"notes.md", "exposure.jsonl"} <= keep


def test_opt_in_moves_notes_to_confirm(tmp_path):
    apps = tmp_path / "apps"; _mk_app(apps, "demo")
    plan = app_setup.plan_delete("demo", apps, tmp_path, delete_notes=True, delete_exposure=True)
    confirm = {Path(x["path"]).name for x in plan["confirm"]}
    assert {"notes.md", "exposure.jsonl"} <= confirm


def test_substring_neighbour_app_is_never_touched(tmp_path):
    """bb_v1 与 bb_v10 / bb_v1_test 必须互不干扰——只走精确路径,绝不 glob。"""
    apps = tmp_path / "apps"
    _mk_app(apps, "bb_v1"); _mk_app(apps, "bb_v10"); _mk_app(apps, "bb_v1_test")
    plan = app_setup.plan_delete("bb_v1", apps, tmp_path, delete_notes=True, delete_exposure=True)
    touched = [x["path"] for grp in plan.values() for x in grp]
    assert not any("bb_v10" in p or "bb_v1_test" in p for p in touched)


def test_unregenerable_longtable_is_blocked_not_deletable(tmp_path):
    """不可再生的重产物进 blocked 组,不进可删组。"""
    apps = tmp_path / "apps"; _mk_app(apps, "demo")
    lt = tmp_path / "outputs" / "tune_gates" / "demo" / "main" / "longtable"
    lt.mkdir(parents=True)
    (lt / "run_meta.json").write_text(json.dumps({"app": "demo", "study_fingerprint": "zzz"}), encoding="utf-8")
    plan = app_setup.plan_delete("demo", apps, tmp_path, delete_notes=False, delete_exposure=False)
    blocked = " ".join(x["path"] for x in plan["blocked"])
    assert "longtable" in blocked
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_app_delete.py -q
```
期望：4 FAIL，`AttributeError: module 'app_setup' has no attribute 'plan_delete'`。

- [ ] **Step 3: 实现 `plan_delete`**

在 `.claude/skills/tune-gates/app_setup.py` 的 `main()` **之前**插入（模块级函数，便于测试）：

```python
def plan_delete(app: str, apps_dir, repo, delete_notes: bool = False,
                delete_exposure: bool = False) -> dict:
    """构造删除清单。**只走精确路径,绝不按 app 名 glob。**

    为什么不 glob:实测按名字模糊匹配会误伤 6 项、同时漏 3 项——真实存在的
    2026-08-20_tune-bb-v1 用连字符命名会被漏掉,而误伤最重的一项是把整个
    2026-08-25_multivar-bb_v1 研究目录连报告一起删。全 repo grep -rIl bb_v1
    命中 161 个文件,绝大多数是包名与历史文档。

    分组(误删=数据永久丢失、误留=多几个文件,代价不对称,所以默认偏保留):
      must    —— study.py / classification.json / __pycache__:纯配置与派生物,进 git 可找回
      confirm —— notes.md / exposure.jsonl(仅在显式开关打开时进这里):跨轮沉淀,默认保留
      keep    —— 默认保留的那些,列出来让人看见放弃了什么
      blocked —— 不可再生的重产物:只报不删

    本函数**不删任何东西**,只返回清单。
    """
    apps_dir, repo = Path(apps_dir), Path(repo)
    app_dir = apps_dir / app
    must, confirm, keep, blocked = [], [], [], []

    if not app_dir.is_dir():
        raise SystemExit(f"{app_dir} 不存在:没有这个 app 可退役")

    for name, why in (("study.py", "app 的搜索空间声明,app 退役即无意义;进 git 可 git checkout 找回"),
                      ("classification.json", "study.py 的派生物;进 git 可找回"),
                      ("__pycache__", "字节码缓存")):
        p = app_dir / name
        if p.exists():
            must.append({"path": str(p), "why": why})

    for name, flag, why in (
            ("notes.md", delete_notes,
             "跨轮实测沉淀(踩过的坑/校准记录),意义不随 app 消失;通用区仍有多处'案例见'指向它"),
            ("exposure.jsonl", delete_exposure,
             "识别端运行审计日志,记的是对这批数据看过几次;同名 app 重建后底层数据仍是同一批")):
        p = app_dir / name
        if not p.exists():
            continue
        entry = {"path": str(p), "why": why}
        if name == "exposure.jsonl" and p.exists():
            entry["why"] += f"(当前 {sum(1 for _ in p.open(encoding='utf-8'))} 条记录,删除后不可恢复)"
        (confirm if flag else keep).append(entry)

    out_root = repo / "outputs" / "tune_gates" / app
    if out_root.is_dir():
        for sub in sorted(p for p in out_root.iterdir() if p.is_dir()):
            lt = sub / "longtable"
            target = lt if lt.is_dir() else sub
            ok, why = _regenerable(target, apps_dir)
            if ok:
                confirm.append({"path": str(target), "why": "重产物,当前代码可再生;删了要重跑"})
            else:
                blocked.append({"path": str(target), "why": "不可再生,只报不删:" + "; ".join(why)})

    return {"must": must, "confirm": confirm, "keep": keep, "blocked": blocked}


def _regenerable(target, apps_dir):
    """薄封装:目录里没有 run_meta.json 时一律判不可再生(归属不明,只报不删)。

    apps_dir 必须显式透传——测试在 tmp_path 假树上跑,用默认 APPS_DIR 会去核对真实的
    apps/ 目录,让测试结果依赖真实仓库状态。
    """
    try:
        return S.check_regenerable(target, apps_dir=apps_dir)
    except Exception as e:                      # noqa: BLE001 —— 检测本身失败也归入"不可再生"侧
        return False, [f"可再生性检测异常({e.__class__.__name__}: {e}),按不可再生处理"]
```

- [ ] **Step 4: 在 `main()` 里接上 delete 分支（必须在 `load_study` 之前短路）**

把 `main()` 改成（承 Task 3 的形态）：

```python
def main() -> None:
    import current as C
    APP, RUN = C.APP, C.RUN
    MODE = "check"                   # "build" | "check" | "delete"
    CONFIRM = False                  # delete 专用:False = 只打印清单不动手
    DELETE_NOTES = False             # 点名确认:apps/<app>/notes.md(跨轮实测沉淀)
    DELETE_EXPOSURE = False          # 点名确认:apps/<app>/exposure.jsonl(运行审计日志)

    S.require(APP, "APP")
    print(f"[app_setup] APP={APP} RUN={RUN} MODE={MODE}")

    if MODE == "delete":
        # ★ 必须在 load_study / import_app 之前短路:删除场景里 app 很可能已经坏了
        #   (实证:apps/bb_v1 在底座 yaml 被删后,MODE=check 连三行报告都打不出来),
        #   若不短路就会在最需要清理的时候 ImportError。
        import subprocess as sp
        plan = plan_delete(APP, S.APPS_DIR, S.REPO, DELETE_NOTES, DELETE_EXPOSURE)
        for grp, title in (("must", "必删"), ("confirm", "点名确认"),
                           ("keep", "保留(未开开关)"), ("blocked", "绝不自动删")):
            print(f"\n== {title} ==")
            for x in plan[grp] or [{"path": "(无)", "why": ""}]:
                print(f"  {x['path']}\n      {x['why']}")
        dirty = sp.run(["git", "status", "--porcelain", str(S.APPS_DIR / APP)],
                       capture_output=True, text=True).stdout.strip()
        if dirty:
            print(f"\n⚠ {S.APPS_DIR / APP} 有未提交改动——这是整个操作里唯一真不可逆的部分:\n{dirty}")
        if not CONFIRM:
            print("\nCONFIRM=False:以上为 dry-run,未删除任何文件。确认无误后把 CONFIRM 改成 True 再跑。")
            return
        if dirty:
            raise SystemExit("拒绝删除:工作树有未提交改动,先提交或还原后再删")
        import shutil
        for x in plan["must"] + plan["confirm"]:
            p = Path(x["path"])
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            print(f"已删除 {p}")
        left = list((S.APPS_DIR / APP).iterdir()) if (S.APPS_DIR / APP).is_dir() else []
        if not left:
            (S.APPS_DIR / APP).rmdir(); print(f"已删除空目录 {S.APPS_DIR / APP}")
        return

    study_path = S.APPS_DIR / APP / "study.py"
    ...  # 以下保持原样(build / check 两个分支)
```

并把文件顶部 docstring 补一段：

```
MODE="delete":列出该 app 的耦合物分级清单(必删/点名确认/保留/绝不自动删)。默认 CONFIRM=False
             只打印不动手。**只走精确路径,绝不按 app 名 glob**(实测 glob 误伤 6 项、漏 3 项)。
             重产物先过可再生性实检,验不过一律降到"绝不自动删"。
             notes.md 与 exposure.jsonl 默认保留,要删得分别打开 DELETE_NOTES / DELETE_EXPOSURE。
```

- [ ] **Step 5: 跑测试 + 对真实 bb_v1 做 dry-run（CONFIRM 必须为 False）**

```bash
uv run pytest .claude/skills/tune-gates/test_app_delete.py -q     # 4 passed
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3        # 期望 81 passed

# 真实 dry-run:确认不会删掉不该删的
sed -i 's/^    MODE = "check"/    MODE = "delete"/' .claude/skills/tune-gates/app_setup.py
uv run python .claude/skills/tune-gates/app_setup.py
sed -i 's/^    MODE = "delete"/    MODE = "check"/' .claude/skills/tune-gates/app_setup.py
```

**期望**：`必删` 只有 `study.py` / `classification.json` / `__pycache__`；`保留` 含 `notes.md`（与 `exposure.jsonl`，若已产生）；末尾明确打印 `CONFIRM=False：以上为 dry-run，未删除任何文件`。**确认 `MODE` 已被 sed 改回 `check` 再进下一步。**

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/tune-gates/app_setup.py .claude/skills/tune-gates/test_app_delete.py
git commit -m "feat(tune-gates): app_setup 新增 delete MODE(精确匹配 + 可再生性实检)

只走精确路径,绝不按 app 名 glob:实测 glob 会误伤 6 项、同时漏 3 项——
2026-08-20_tune-bb-v1 用连字符命名会被漏掉,而误伤最重的是把整个
2026-08-25_multivar-bb_v1 研究目录连报告一起删。

分级按'误删=永久丢失 vs 误留=多几个文件'的不对称设计:notes.md 与 exposure.jsonl
记的是'对这批数据做过什么',意义不随 app 消失,默认保留、要删须分别开开关。
重产物先过 check_regenerable,验不过一律降到'绝不自动删'。

delete 分支在 load_study/import_app 之前短路——删除场景里 app 很可能已经坏了
(实证:底座 yaml 被删后 MODE=check 连报告都打不出来),不短路就会在最需要清理时 ImportError。

不做自动备份(复制上百 MB 只是造新垃圾),改成删 git 内容前查工作树是否干净:
未提交的改动是整个操作里唯一真不可逆的部分。"
```

---

## Task 10: 文档修复（入口协议判据一词 + ledger 空转指示）

**Files:**
- Modify: `.claude/skills/tune-gates/SKILL.md:22`、`:32`
- Modify: `.claude/skills/tune-gates/reference.md:31`、`:41`

**Interfaces:** 无代码接口。

- [ ] **Step 1: 一词修复——入口协议判据**

`notes.md` 默认保留会造出「目录还在、`study.py` 没了」这个新状态，而入口协议的判据写的是「`apps/X/` 存在？」——会走错分支并给出指错方向的报错。

```bash
grep -n 'apps/<app>/ 存在\|apps/X/ 存在\|apps/.*存在?' .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md
```

把命中的判据从「`apps/<app>/` 存在？」改为「**`apps/<app>/study.py` 存在？**」，并在该行后补一句：

```
（判据用 `study.py` 而非目录本身：退役清理默认保留 `notes.md` / `exposure.jsonl`，
目录可能还在但声明已删——此时该走「新接入」而不是「复用」。）
```

- [ ] **Step 2: 修 ledger 空转指示**

`SKILL.md:32` 与 `reference.md:41` 要求「把指纹不一致、用户裁定复用写进本次 ledger」，但 `ledger.md` 是 `multivar_scan.py:268` 每次运行**无条件全量覆写**的机器产物——人写进去的内容下一次运行就被无声抹掉。

```bash
grep -n 'ledger' .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md
```

把「写进本次 ledger」一律改为：

```
写进 `apps/<app>/exposure.jsonl` 的 `note` 字段（`ledger.md` 每轮被 multivar_scan
全量覆写，人写进去会被下一次运行无声抹掉，不能承载跨轮记录）
```

同时在 `region_find.py` 的 exposure 记录里补一个 `"note": ""` 键（Task 7 的记录 dict 里加一行），给人留下手写位置。

- [ ] **Step 3: 验证没有残留**

```bash
grep -n '写进本次 ledger\|记进 ledger' .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md || echo "无残留"
grep -rn 'apps/<app>/ 存在' .claude/skills/tune-gates/*.md || echo "判据已全部更新"
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md \
        .claude/skills/tune-gates/region_find.py
git commit -m "docs(tune-gates): 入口协议判据一词修复 + ledger 空转指示改指

判据 apps/<app>/ 存在? → apps/<app>/study.py 存在?:退役清理默认保留 notes.md,
会出现'目录在、声明没了'的新状态,旧判据会走错分支并给出指错方向的报错。

'写进本次 ledger' 是空转指示:ledger.md 由 multivar_scan 每轮无条件全量覆写,
人写进去下次就被抹掉。改指 exposure.jsonl 的 note 字段(只追加、跨轮持久)。"
```

---

## Task 11: `SKILL.md` 重组为「共享判据 + 分流器 + 两条并列路径」

**背景**：`SKILL.md:44` 是**一个步骤的正文**，却用加粗引出「必须真扫参数的调参（多维稳健区 v2）」再展开五个子步骤，中间还夹着对拍作用域、格数≠检测组合数、OAT 降级等大段内容。七步骨架是为单参数路径设计的，多参数路径被硬塞进第 4 步——这才是「看起来像两个 skill」的真实来源。

**决定不拆 skill**（理由见 spec §6.2）：判据共享且刚从 `eval-discipline` 合并过一次、分流器本身是共享步骤、`plateau.py` 至今零实战、触发上无收益。只重组结构。

**Files:**
- Modify: `.claude/skills/tune-gates/SKILL.md`

**Interfaces:** 无代码接口。**不改 `description`**（它已明确写了两条入口，两批用户口径词都在）。

- [ ] **Step 1: 备份当前内容以便逐条核对**

```bash
cp .claude/skills/tune-gates/SKILL.md /tmp/skill_md_before.md
wc -l /tmp/skill_md_before.md
```

- [ ] **Step 2: 重排为四段结构**

目标结构（**只搬运与拆分，不改判据文字本身**——每条判据、每个数字、每处「案例见 apps/<app>/notes.md」都要原样保留）：

```
# 逐闸平台调参（tune-gates）
  开头两句（选阈值的原则 / 本 skill 管「选」）

## 一、判据与纪律（两条路都适用）
  ← 原第 1 步「声明」全文
  ← 原第 6 步「人复核拍板」全文
  ← 原第 7 步「回放校验 + 台账」全文
  ← 原「红线（硬约束）」整节
  ← 原「与既有资产的关系」整节

## 二、分流器：这次该走哪条路
  ← 原「入口粒度：全流程 vs 单闸微调」整节
  ← 原第 2 步「分层宽进」全文（按可否事后切档分两类 = 分流判据本身）
  ← 原第 3 步「单特征质检」全文
  末尾加一句指路：
    「能事后切档 → 路径 A；必须真扫（改了就得重新检测）→ 路径 B；
      两类都有 → 先按 B 把真扫维定下来，再用 A 对可事后切的闸补切档位。」

## 三、路径 A：事后切档 → 平台图（单参数 / 单闸定阈值）
  ← 原第 4 步的**前半段**（事后可切参数在宽表上切档位、切档先查列分布）
  ← 原第 5 步「逐闸判定」全文
  ← 原「plateau.py 用法」整节
  保留原文那句实战状态提示：plateau.py 的 1SE/tol 与 REL_TOL 0.05 尚未实战校准

## 四、路径 B：多维稳健区（多参数联合）
  ← 原第 4 步的**后半段**，把 ①②③④⑤ 提为平级小节：
     B1 探针分类（W/F/D/E）
     B2 扫描出候选长表（每股反转循环；格数 ≠ 检测组合数）
     B3 对拍（先对拍后读数；作用域 = app × spec 拓扑 × 维度分类）
     B4 region_find 在联合空间上识别
     B5 人复核 + 同 HEAD_BUFFER 外推窗
  ← 原「入口协议」整节（它只服务这条路）
  ← 原「多维稳健区 v2 工具用法」整节
  保留原文的「不是所有真扫参数都值得扫」「OAT 降级为选维线索」两段

## 首轮使用注意
  ← 原节保留（内容按 Task 1..10 的落地情况更新：pytest 已绿、run.py/current.py 已落地）
```

- [ ] **Step 3: 逐条核对没有丢内容**

```bash
# 关键判据的锚点词在重组后必须仍然命中
for k in "字典序" "win_rate 废弃" "功效线" "分年方向一致性" "算术效应归因" \
         "先对拍后读数" "作用域" "holdout" "FLAG_RULES" "OAT" "1SE" "REL_TOL"; do
  n=$(grep -c "$k" .claude/skills/tune-gates/SKILL.md)
  o=$(grep -c "$k" /tmp/skill_md_before.md)
  [ "$n" -ge "$o" ] && echo "OK  $k ($o→$n)" || echo "!! 丢失 $k ($o→$n)"
done
```

任何一行出现 `!! 丢失` 都要回去补，**不允许在重组中删减判据**。

- [ ] **Step 4: 确认 description 未被改动**

```bash
sed -n '1,5p' .claude/skills/tune-gates/SKILL.md
```
期望：`name:` 与 `description:` 两行与重组前逐字相同（两条入口的触发词都在，无需改）。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/SKILL.md
git commit -m "docs(tune-gates): SKILL.md 重组为共享判据 + 分流器 + 两条并列路径

原七步骨架是为单参数路径设计的,多维稳健区被硬塞进第 4 步的正文里——
一个步骤内嵌着五个子步骤加对拍作用域、格数口径、OAT 降级等大段内容。
这是'看起来像两个 skill'的真实来源。

决定不拆 skill:判据共享且刚从 eval-discipline 合并过一次(拆开等于撤销一半);
分流器本身是共享步骤(第 2 步的分类结果才决定走哪条,放哪边都不对);
plateau.py 至今零实战;description 已覆盖两批触发词,拆开无收益。
方法论上两条路也是同一件事——region 的 r=1 邻域最小分在一维上就是平台判定。

本次只搬运与拆分,判据文字、数字、案例指针逐条保留(有锚点词核对)。
description 未改动。"
```

---

## 完成校验（全部 task 之后）

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
# 期望: 81 passed, 0 failed, 0 errors

uv run python .claude/skills/tune-gates/app_setup.py          # MODE=check,应打横幅 + 三行报告
git log --oneline -11                                          # 11 个 commit,每个 task 一个
git status --porcelain                                         # 除研究目录外应干净
```

**未实施项（用户已拍板不做）**：外推窗使用计数（spec §1.4）。理由：tune-gates 不执行外推，没有脚本能自动写它，只能人手填；半途而废的计数比没有更糟，会造成「已经在管」的错觉。**不要**在实施中顺手加上它。

**本计划不含**：`compare_longtable` 断点续跑（spec §1.5，优先级低，独立工单）。
