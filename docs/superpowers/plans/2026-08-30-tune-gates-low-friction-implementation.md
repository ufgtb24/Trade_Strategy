# tune-gates 低心智负担重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 tune-gates 的入口层从「用户编辑源码文件里的常量」改造成「Claude 直接调库函数」，让用户只说「帮我调 X 的参数」就能工作，内部机制词一律不外泄。

**Architecture:** 新增 `tune.py` 作为唯一调用面（7 个函数 + 一个带默认值的 `Settings`）。六个脚本的 `main()` 改成模块级 `run(...)` 函数——**头部十余行常量装配换成参数，逻辑体一行不动**。`tune.py` 保持薄：只做参数默认值、状态探测、转发、危险动作守卫。`current.py` / `apps/*/run.py` / `MODE` 全部删除。

**Tech Stack:** Python 3.12 · uv · pytest · dataclasses · numpy/pandas · **本 skill 内允许命令行/函数传参（破例，见 Global Constraints）**

**Spec:** `docs/superpowers/specs/2026-08-30-tune-gates-low-friction-redesign.md`

## Global Constraints

- **本 plan 中所有项目内路径均相对 repo root**（如 `.claude/skills/tune-gates/tune.py`）。例外：`~/.claude/...`、`/tmp/...` 等与 worktree 无关的系统路径保持绝对。
- **工作目录 = 当前 worktree 根**，不要 `cd` 到主仓库或其他 worktree。
- **规范破例（本 skill 内）**：全局 CLAUDE.md 的「所有入口程序不要使用 parser，参数声明在 `main()` 起始位置」在 `.claude/skills/tune-gates/` 内**不再适用**。理由：该规范自带初衷（「不喜欢每次运行需要手动输入参数」），本重构后参数由 Claude 代填、不由人手填，初衷由代理满足。Task 10 须把这条例外写进项目 `CLAUDE.md`。
- **`study.py` 的生成必须确定性**：它的整份文件 sha256 是扫描结果的准入校验（`study_io.check_study_matches` / `check_run_matches_classification`）。同一份 grid 生成两次字节必须逐字相同——**不得含时间戳、不得依赖 dict 迭代顺序、不得含随机排序**。否则重跑 `setup()` 会让已有扫描结果作废、必须重扫数小时。
- **逻辑体一行不动**：本次是签名替换 + 头部改写，不是逻辑重写。任何对 `main()` 逻辑体的实质改动都要在报告里单独说明理由。
- **测试基线**：改造前 `uv run pytest .claude/skills/tune-gates/ -q` 是 **94 passed / 0 failed / 0 errors**。`test_bench_workers.py` 会在 Task 2 被删除，故总数会下降；**验收口径是 0 failed / 0 errors，不锁死总数**。
- **不得 `git push`，不得开 PR。** 每个 task 结束时本地 commit。
- 中文注释与文档（项目规范）。依赖用 `uv run`。
- **禁止真的删除任何研究目录或已有扫描结果**。涉及删除的验证一律在 `tmp_path` 假树上做。

---

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `.claude/skills/tune-gates/tune.py` | 唯一调用面：`Settings` + 7 个函数 | **新建**（Task 1/3/4/5/6/7/9） |
| `.claude/skills/tune-gates/test_tune.py` | `tune.py` 的测试 | **新建**（Task 1） |
| `.claude/skills/tune-gates/bench_workers.py` | WORKERS 定标 | 改造（Task 2 拆机制 / Task 9 接线） |
| `.claude/skills/tune-gates/test_bench_workers.py` | 改写表测试 | **删除**（Task 2） |
| `.claude/skills/tune-gates/app_setup.py` | 接入端 + 退役清理 | 改造（Task 3） |
| `.claude/skills/tune-gates/multivar_scan.py` | 扫描出长表 | 改造（Task 4） |
| `.claude/skills/tune-gates/compare_longtable.py` | 一致性验证 | 改造（Task 5） |
| `.claude/skills/tune-gates/region_find.py` | 识别稳健区 | 改造（Task 6） |
| `.claude/skills/tune-gates/plateau.py` | 单参数平台图 | 改造（Task 7） |
| `.claude/skills/tune-gates/grid_propose.py` | 网格提案生成 + study.py 确定性渲染 | **新建**（Task 8） |
| `.claude/skills/tune-gates/test_grid_propose.py` | 提案与确定性测试 | **新建**（Task 8） |
| `.claude/skills/tune-gates/current.py` | app 身份单源 | **删除**（Task 9） |
| `.claude/skills/tune-gates/apps/_template/run.py` | run 级常量模板 | **删除**（Task 9） |
| `.claude/skills/tune-gates/apps/bb_v1/run.py` | bb_v1 run 级常量 | **删除**（Task 9） |
| `.claude/skills/tune-gates/study_io.py` | 声明加载 / 指纹 / run_meta | 小改（Task 9 删 `load_run` / `RUN_REQUIRED`） |
| `.claude/skills/tune-gates/SKILL.md` | 执行协议（给 Claude） | 重写（Task 10） |
| `.claude/skills/tune-gates/reference.md` | 实证坑清单（给 Claude） | 瘦身（Task 10） |
| `docs/explain/tune-gates_调参判据卡.md` | 判据卡（给用户） | **新建**（Task 10） |
| `CLAUDE.md` | 项目规范 | 加规范例外一段（Task 10） |

**任务顺序的依据**：Task 2 先拆掉 `bench_workers` 对目标脚本源码形态的正则依赖——否则 Task 4/5 每改一个脚本都要同步维护一张即将作废的改写表，且 `test_bench_workers.py` 会红。Task 9 的删除动作必须排在所有转换之后（`current.py` / `run.py` 在 Task 3-7 期间仍被旧路径引用）。

---

## Task 1: `tune.py` 骨架 —— `Settings` 与 `status()`

**背景**：`status()` 是「用户说一句话，Claude 就知道该干什么」的技术基础。该信息目前散在文件系统各处、无人汇总。**一律现场探测，不引入第二份进度记录**（两份真相迟早对不上）。

本 task 是**纯新增**，不改任何既有文件，不破坏任何东西。

**Files:**
- Create: `.claude/skills/tune-gates/tune.py`
- Create: `.claude/skills/tune-gates/test_tune.py`

**Interfaces:**
- Consumes: `study_io`（`APPS_DIR` / `REPO` / `file_sha256` / `load_classification` / `check_regenerable` / `load_run_meta`）
- Produces:
  - `tune.Settings`（frozen dataclass，字段见 Step 3）
  - `tune.status(app: str, window: str = "main") -> dict`，键：`app` / `window` / `installed`（bool）/ `classification_stale`（bool | None）/ `scanned_shards`（int）/ `scanned_symbols`（int）/ `compared`（bool）/ `compare_mismatch`（int | None）/ `found`（bool）/ `exposure_rounds`（int）/ `regenerable`（bool | None）/ `regenerable_reasons`（list[str]）/ `out_dir`（str）

- [ ] **Step 1: 写失败测试**

新建 `.claude/skills/tune-gates/test_tune.py`：

```python
# -*- coding: utf-8 -*-
"""tune.py 的测试。全部在 tmp_path 假树上跑,不碰真实 apps/ 与 outputs/。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune  # noqa: E402


def _mk_installed_app(apps: Path, name: str = "demo") -> Path:
    """造一个已接入的 app:study.py + 与之匹配的 classification.json。"""
    import study_io as S
    d = apps / name
    d.mkdir(parents=True)
    study = d / "study.py"
    study.write_text(
        'APP_MODULE = "x.y"\nBASE_YAML = "params.yaml"\nWIDE_OVERRIDES = {}\n'
        'SCAN_GRID = {}\nWHERE_LEVELS = {}\nREF_POINT = {}\n'
        'TIGHT_WHERES = {}\nFLAG_RULES = []\n', encoding="utf-8")
    (d / "classification.json").write_text(json.dumps({
        "app": name, "app_module": "x.y", "base_yaml": "params.yaml",
        "fingerprints": {"study": S.file_sha256(study), "base": "b", "source": {"hash": "s", "files": []}},
    }), encoding="utf-8")
    return d


def test_status_reports_not_installed(tmp_path):
    """没有 study.py → installed=False,其余字段不炸。"""
    st = tune.status("nope", apps_dir=tmp_path / "apps", repo=tmp_path)
    assert st["installed"] is False
    assert st["scanned_shards"] == 0
    assert st["classification_stale"] is None


def test_status_detects_stale_classification(tmp_path):
    """study.py 改过而 classification.json 没重生成 → classification_stale=True。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    (d / "study.py").write_text("APP_MODULE = 'changed'\n", encoding="utf-8")
    st = tune.status("demo", apps_dir=apps, repo=tmp_path)
    assert st["installed"] is True
    assert st["classification_stale"] is True


def test_status_counts_scan_progress_and_exposure(tmp_path):
    """分片数与 exposure 轮次都从文件系统现场数出来。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    (d / "exposure.jsonl").write_text('{"ts":"t1"}\n{"ts":"t2"}\n', encoding="utf-8")
    lt = tmp_path / "outputs" / "tune_gates" / "demo" / "main" / "longtable"
    lt.mkdir(parents=True)
    (lt / "part-000.parquet").write_bytes(b"")
    (lt / "part-001.parquet").write_bytes(b"")
    st = tune.status("demo", apps_dir=apps, repo=tmp_path)
    assert st["scanned_shards"] == 2
    assert st["exposure_rounds"] == 2
    assert st["found"] is False


def test_settings_defaults_match_migrated_values():
    """迁移正确性:Settings 的默认值必须与改造前 apps/bb_v1/run.py 的取值逐项相同。"""
    s = tune.Settings()
    assert s.head_buffer == 250
    assert (s.start_date, s.end_date) == ("2024-01-01", "2026-01-01")
    assert (s.label_horizon, s.first_passage_k) == (40, 5.0)
    assert (s.price_min, s.price_max, s.volume_min) == (0.5, 30.0, 10000.0)
    assert s.ticker_regex is None
    assert s.shard_stocks == 200
    assert s.cmp_ticker_regex == r"^[A-Z][A-C]"
    assert (s.cmp_seed, s.cmp_n_random_cells, s.cmp_n_tight_cells) == (11, 64, 12)
    assert s.min_win_bars == 1
    assert (s.fold_col, list(s.folds)) == ("fold_Y", ["2024", "2025"])
    assert s.min_count_per_fold == 100
    assert s.neighbor_axes == "all"
    assert (s.b_boot, s.boot_seed, s.top_n) == (300, 0, 20)
    assert list(s.split_half_seeds) == list(range(20))
    assert s.workers == 16


def test_settings_is_frozen():
    """Settings 不可变:防止某次调用改了它影响后续调用。"""
    s = tune.Settings()
    with pytest.raises(Exception):
        s.head_buffer = 100
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_tune.py -q
```
期望：collection error 或 6 个 FAIL，报 `ModuleNotFoundError: No module named 'tune'`。

- [ ] **Step 3: 实现 `tune.py` 的 `Settings` 与 `status()`**

新建 `.claude/skills/tune-gates/tune.py`：

```python
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
    workers: int = 16                       # 机器级,不随 app 变;定标见 reference.md §3.1
    # ---- 一致性验证 ----
    cmp_ticker_regex: str = r"^[A-Z][A-C]"  # 红线要求参与比较的股数 >= 500
    cmp_seed: int = 11
    cmp_n_random_cells: int = 64
    cmp_n_tight_cells: int = 12
    min_win_bars: int = 1
    # ---- 识别 ----
    fold_col: str = "fold_Y"
    folds: tuple = ("2024", "2025")
    min_count_per_fold: int = 100           # 仅在一个 app 上校准过,见 reference.md §8 坑 8
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

    apps_dir / repo 显式可注入,是为了让测试在 tmp_path 假树上跑而不依赖真实仓库状态。
    """
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    repo = Path(repo) if repo else REPO
    app_dir = apps_dir / app
    study_p = app_dir / "study.py"
    out = out_dir_of(app, window, repo)
    lt = out / "longtable"

    st = {"app": app, "window": window, "out_dir": str(out), "installed": study_p.exists(),
          "classification_stale": None, "scanned_shards": 0, "scanned_symbols": 0,
          "compared": False, "compare_mismatch": None, "found": (out / "region_report.md").exists(),
          "exposure_rounds": 0, "regenerable": None, "regenerable_reasons": []}

    exposure = app_dir / "exposure.jsonl"
    if exposure.exists():
        st["exposure_rounds"] = sum(1 for ln in exposure.read_text(encoding="utf-8").splitlines() if ln.strip())

    cl_p = app_dir / "classification.json"
    if st["installed"] and cl_p.exists():
        cl = json.loads(cl_p.read_text(encoding="utf-8"))
        st["classification_stale"] = S.file_sha256(study_p) != cl.get("fingerprints", {}).get("study")
    elif st["installed"]:
        st["classification_stale"] = True      # 有声明没分类表 = 待生成,同样归入"要重建"

    if lt.is_dir():
        shards = sorted(lt.glob("part-*.parquet"))
        st["scanned_shards"] = len(shards)
        if (lt / "run_meta.json").exists():
            ok, why = S.check_regenerable(lt, apps_dir=apps_dir)
            st["regenerable"], st["regenerable_reasons"] = ok, why

    log = out / "compare_longtable.log"
    if log.exists():
        st["compared"] = True
        for ln in reversed(log.read_text(encoding="utf-8").splitlines()):
            if "mismatch=" in ln:
                st["compare_mismatch"] = int(ln.split("mismatch=")[1].split(",")[0])
                break
    return st
```

**注意**：`scanned_symbols` 本 task 先固定为 0——数它需要读 parquet（慢），Task 4 接上 `scan()` 之后再由调用方按需补。不要为它引入额外依赖。

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest .claude/skills/tune-gates/test_tune.py -q
```
期望：6 passed。

- [ ] **Step 5: 跑全套自测**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```
期望：**100 passed**（94 + 6 新增），0 failed 0 errors。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/tune-gates/tune.py .claude/skills/tune-gates/test_tune.py
git commit -m "feat(tune-gates): 新增 tune.py 调用面骨架(Settings + status)

用户只想说「帮我调 X 的参数」,不想知道 study.py / classification.json /
run_meta.json / 指纹这些内部机制。tune.py 是所有机制操作的唯一发起点。

status() 一律现场探测文件系统(接入没/分类表是否过期/扫到哪/验证过没/识别过没/
看过几轮/能否再生),不维护第二份进度记录——两份真相迟早对不上。

Settings 的默认值逐项迁自 apps/bb_v1/run.py,并用测试钉住迁移等价;★ 标记的字段
进 RUN_CALIBER(改了必须换 window),其余随便改不影响已有扫描结果复用。"
```

---

## Task 2: 拆掉 `bench_workers` 对目标脚本源码形态的正则依赖

**背景**：`bench_workers` 把目标脚本复制一份、用 `re.subn` 改写 9 条常量字面行（含失配断言），再起子进程跑。**这套机制的唯一存在理由就是「参数只能写死在 `main()` 里」**——本重构一开始就该拆掉它，否则 Task 4/5 每改一个脚本都要同步维护一张即将作废的改写表，且 `test_bench_workers.py` 会红。

本 task 把 `bench_workers` 降级为一个明确报错的 stub，Task 9 重新接线到 `tune.scan` / `tune.compare`。**这是计划内的临时状态**：`bench_workers` 是一次性定标工具（迄今只真跑过一次），没有其他消费者，不影响任何流水线。

**Files:**
- Modify: `.claude/skills/tune-gates/bench_workers.py`
- Delete: `.claude/skills/tune-gates/test_bench_workers.py`

**Interfaces:**
- Produces: 无（本 task 只做删除）

- [ ] **Step 1: 确认 `test_bench_workers.py` 是唯一受影响的测试**

```bash
grep -rn "bench_workers\|_tool_specs\|WORKERS_PATTERN" .claude/skills/tune-gates/test_*.py
```

期望：只有 `test_bench_workers.py` 命中。若还有别的文件命中，**停下来报告**，不要自行处理。

- [ ] **Step 2: 删除测试文件**

```bash
git rm .claude/skills/tune-gates/test_bench_workers.py
```

- [ ] **Step 3: 把 `bench_workers.py` 的改写机制换成 stub**

删除 `_tool_specs()` 整个函数、模块级的 `WORKERS_PATTERN` 常量，并把 `main()` 整个替换为：

```python
def main():
    raise SystemExit(
        "bench_workers 正在随入口层重构改造中(见 docs/superpowers/plans/"
        "2026-08-30-tune-gates-low-friction-implementation.md 的 Task 9)。\n"
        "原来的「复制脚本 + 正则改写常量行」机制已删除——它的唯一存在理由是"
        "「参数只能写死在 main() 里」,该前提已不成立。\n"
        "改造后将直接起子进程调 tune.scan(app, workers=W, ...)。")
```

同时把文件头 docstring 里描述「复制一份、只改写 WORKERS 一行、改写一律 `re.subn` + 失配断言」的**跑法**那段改成一句：

```
**跑法**:改造中(见 plan Task 9)。改造后每个 WORKERS 值起一个子进程调 tune.scan/tune.compare,
不再复制脚本、不再改写源码——那套正则改写的唯一存在理由是「参数只能写死在 main() 里」。
```

保留 `PeakSampler` / `_proc_kb` / `_run_one` 这些内存采样工具（Task 9 还要用）。若 `re` / `shutil` 在删除后不再被引用，一并从 import 里去掉。

- [ ] **Step 4: 跑全套自测**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```
期望：**0 failed / 0 errors**；总数比 Task 1 结束时少（`test_bench_workers.py` 的用例数），把实际数字记进报告。

- [ ] **Step 5: 确认 stub 真的会响亮失败**

```bash
uv run python -c "
import sys; sys.path.insert(0, '.claude/skills/tune-gates')
import bench_workers
try:
    bench_workers.main()
except SystemExit as e:
    print('OK 响亮失败:', str(e).splitlines()[0])
"
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/tune-gates/bench_workers.py
git commit -m "refactor(tune-gates): 拆掉 bench_workers 对目标脚本源码形态的正则依赖

那套「复制脚本 + re.subn 改写 9 条常量行 + 失配断言」机制的唯一存在理由就是
「参数只能写死在 main() 里」。本重构第一步就拆掉它,否则后面每改一个入口脚本
都要同步维护一张即将作废的改写表。

test_bench_workers.py 一并删除(它断言改写表与真实源码逐条命中,而那些字面行
即将消失)。bench_workers 暂降级为响亮报错的 stub,Task 9 重新接线到
tune.scan/tune.compare——它是一次性定标工具、无其他消费者,不影响流水线。"
```

---

## Task 3: `app_setup` 函数化 —— `tune.setup()` / `tune.retire()`

**背景**：`app_setup.main()` 的三个 `MODE` 分支各自被吸收——`build` → `tune.setup()`；`check` → `tune.status()`（Task 1 已覆盖）；`delete` → `tune.retire()`。

**关键**：`plan_delete` / `_worktree_dirty` / `_execute_delete` **已经是模块级函数**，`test_app_delete.py` 测的就是它们，**本 task 不动它们、那 11 个测试不受影响**。要搬的只是 `main()` 里的打印与编排。

**Files:**
- Modify: `.claude/skills/tune-gates/app_setup.py:174-220`（删除 `main()` 与 `if __name__` 块）
- Modify: `.claude/skills/tune-gates/tune.py`（追加 `setup` / `retire`）
- Modify: `.claude/skills/tune-gates/test_tune.py`（追加）

**Interfaces:**
- Consumes: `app_setup.plan_delete(app, apps_dir, repo, delete_notes, delete_exposure) -> dict`、`app_setup._execute_delete(plan, app_dir, confirm) -> None`、`study_io.build_classification` / `write_classification` / `load_study` / `import_app`
- Produces:
  - `tune.setup(app: str, *, apps_dir=None) -> dict` —— 读已存在的 `apps/<app>/study.py`，生成 `classification.json`，返回 `{"app","kinds","filter_fields","where_fields","end_node","bound_nodes","detection_combos","source_files"}`。**幂等。**

  > **对 spec §4 的一处细化**：spec 写的是 `setup(app, grid)` 一个函数。实施时拆成两个——`setup(app)` 只从**已存在的** `study.py` 生成分类表，写 `study.py` 的动作归 Task 8 的 `install(app, ...)`。理由：写 `study.py` 会让该 app 已有的扫描结果作废（它的哈希是准入校验），而只重生成分类表不会；两者危险等级不同，合成一个函数会让调用方无法只做安全的那一半。
  - `tune.retire(app: str, *, confirm: bool = False, delete_notes: bool = False, delete_exposure: bool = False) -> dict` —— 返回 `plan_delete` 的清单；`confirm=False` 时**不删任何东西**。

- [ ] **Step 1: 写失败测试**

在 `.claude/skills/tune-gates/test_tune.py` 末尾追加：

```python
def test_retire_dry_run_returns_plan_without_deleting(tmp_path):
    """confirm=False 只返回清单,一个文件都不能少。"""
    apps = tmp_path / "apps"
    d = _mk_installed_app(apps)
    (d / "notes.md").write_text("# notes\n", encoding="utf-8")
    before = sorted(p.name for p in d.iterdir())
    plan = tune.retire("demo", confirm=False, apps_dir=apps, repo=tmp_path)
    assert {Path(x["path"]).name for x in plan["must"]} >= {"study.py", "classification.json"}
    assert "notes.md" in {Path(x["path"]).name for x in plan["keep"]}
    assert sorted(p.name for p in d.iterdir()) == before      # 一个都没删


def test_retire_refuses_unknown_app(tmp_path):
    with pytest.raises(SystemExit):
        tune.retire("nope", confirm=False, apps_dir=tmp_path / "apps", repo=tmp_path)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_tune.py -k retire -q
```
期望：2 FAIL，报 `AttributeError: module 'tune' has no attribute 'retire'`。

- [ ] **Step 3: 在 `tune.py` 追加 `setup` 与 `retire`**

在 `tune.py` 的 `status()` 之后插入：

```python
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
```

- [ ] **Step 4: 删除 `app_setup.py` 的 `main()` 与 `if __name__` 块**

删除 `app_setup.py` 第 174 行起的 `def main() -> None:` 整个函数体，以及文件末尾的：

```python
if __name__ == "__main__":
    main()
```

**保留** `plan_delete` / `_regenerable` / `_worktree_dirty` / `_execute_delete` 四个模块级函数**逐字不动**。

把文件头 docstring 里描述 `MODE` 三个取值的那几段，替换为：

```
本模块只提供 app 接入端的**模块级函数**,不再有 main()/MODE——调用面统一在 tune.py:
  tune.setup(app)   生成 classification.json(原 MODE="build")
  tune.status(app)  报告分类表是否过期(原 MODE="check")
  tune.retire(app)  退役清理(原 MODE="delete")
```

- [ ] **Step 5: 跑测试确认通过 + 全套自测**

```bash
uv run pytest .claude/skills/tune-gates/test_tune.py -k retire -q      # 2 passed
uv run pytest .claude/skills/tune-gates/test_app_delete.py -q          # 11 passed,不受影响
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3             # 0 failed 0 errors
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/tune-gates/app_setup.py .claude/skills/tune-gates/tune.py \
        .claude/skills/tune-gates/test_tune.py
git commit -m "refactor(tune-gates): app_setup 函数化,MODE 概念消失

三个 MODE 取值各自被吸收:build → tune.setup();check → tune.status()(已覆盖);
delete → tune.retire()。用户再不用知道 MODE 这个词,Claude 也不用 sed 源码字面量
(Task 9 的实施里每一轮都要 sed 去、sed 回、再验残留)。

plan_delete / _worktree_dirty / _execute_delete 三个安全关键函数逐字未动,
test_app_delete.py 的 11 个测试不受影响——它们测的本来就是模块级函数。"
```

---

## Task 4: `multivar_scan` 函数化 —— `tune.scan()`

**背景**：本 task 是六个转换里最大的一个（`main()` 211 行）。**只改头部十余行常量装配，逻辑体一行不动。**

**Files:**
- Modify: `.claude/skills/tune-gates/multivar_scan.py:65-79`（`main()` 头部）
- Modify: `.claude/skills/tune-gates/tune.py`（追加 `scan`）

**Interfaces:**
- Consumes: `tune.Settings`
- Produces:
  - `multivar_scan.run(app: str, cfg, out_dir: str) -> None` —— `cfg` 是 `tune.Settings`
  - `tune.scan(app: str, *, window: str = "main", cfg: Settings | None = None, **overrides) -> dict`

- [ ] **Step 1: 改 `multivar_scan.py` 的 `main()` 签名与头部**

把第 65 行的 `def main() -> None:` 到第 79 行 `OUT_DIR = f"outputs/tune_gates/{APP}/{RUN}"` 这一整段（即从 `def main` 到 `OUT_DIR = ...` 那行，**不含**其后的空行与 `from path2_web.scan import ...`）替换为：

```python
def run(app: str, cfg, out_dir: str) -> None:
    """扫描出候选长表。断点续跑:已完成的股票从既有分片与 baseline csv 里认出来。

    cfg 是 tune.Settings;out_dir 相对 repo root。本函数不读 current.py / run.py——
    参数全部由调用方(tune.scan)给,run 级口径写进 run_meta.json 供 compare/region 读。
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
```

然后把紧随其后的那行横幅 print：

```python
    print(f"[multivar_scan] APP={APP} RUN={RUN} → {OUT_DIR} (窗 {START_DATE}..{END_DATE}, HEAD_BUFFER={HEAD_BUFFER}, WORKERS={WORKERS})")
```

改为（去掉已不存在的 `RUN`）：

```python
    print(f"[multivar_scan] app={APP} → {OUT_DIR} (窗 {START_DATE}..{END_DATE}, HEAD_BUFFER={HEAD_BUFFER}, WORKERS={WORKERS})")
```

**其余一行不动**——`S.require(APP, "APP")` 保留（`app` 为空字符串时仍应响亮失败）。删除文件末尾的 `if __name__ == "__main__": main()` 块（若有）。

- [ ] **Step 2: 确认没有遗漏的 `RUN` 引用**

```bash
grep -n '\bRUN\b\|current\|load_run' .claude/skills/tune-gates/multivar_scan.py
```
期望：无输出（或只命中注释/字符串里的无关词）。有命中就逐个处理。

- [ ] **Step 3: 在 `tune.py` 追加 `scan`**

```python
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
```

- [ ] **Step 4: 冒烟验证签名装配正确（不真跑扫描）**

```bash
uv run python -c "
import sys, inspect
sys.path.insert(0, '.claude/skills/tune-gates')
import multivar_scan, tune
print('run 签名:', inspect.signature(multivar_scan.run))
print('scan 签名:', inspect.signature(tune.scan))
assert not hasattr(multivar_scan, 'main'), 'main() 应已删除'
s = tune.Settings()
print('覆盖生效:', __import__('dataclasses').replace(s, ticker_regex='^A[A-C]').ticker_regex)
"
```

- [ ] **Step 5: 跑全套自测 + Commit**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3   # 0 failed 0 errors

git add .claude/skills/tune-gates/multivar_scan.py .claude/skills/tune-gates/tune.py
git commit -m "refactor(tune-gates): multivar_scan 函数化(main → run(app, cfg, out_dir))

头部十余行常量装配换成参数,211 行逻辑体一行未动。不再读 current.py / run.py,
run 级口径由调用方给、写进 run_meta.json 供 compare/region 读(单一来源)。

横幅去掉已不存在的 RUN,改打 app 与推导出的输出路径——横幅的铁律是显示实际会用的值。"
```

---

## Task 5: `compare_longtable` 函数化 —— `tune.compare()`

**背景**：`main()` 88 行。本 task 另修一处既有缺陷：`APP = meta["app"]` 是**静默覆盖**而非校验——若传入的 app 与长表记录的 app 不符，会读 A 的长表按 B 的分类去切且毫无报错。函数化之后 `app` 是显式入参，这个静默覆盖必须改成响亮校验。

**Files:**
- Modify: `.claude/skills/tune-gates/compare_longtable.py:109-122`（`main()` 头部）与 `:124`（`APP = meta["app"]`）
- Modify: `.claude/skills/tune-gates/tune.py`（追加 `compare`）

**Interfaces:**
- Produces:
  - `compare_longtable.run(app: str, cfg, longtable_dir: str) -> None`
  - `tune.compare(app: str, *, window: str = "main", cfg: Settings | None = None, **overrides) -> dict`

- [ ] **Step 1: 改 `compare_longtable.py` 的 `main()` 签名与头部**

把 `def main():` 到 `OUT_LOG = None ...` 那一整段替换为：

```python
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
    OUT_LOG = None        # None → <LONGTABLE_DIR 父目录>/compare_longtable.log
```

横幅那行改为：

```python
    print(f"[compare_longtable] app={APP} → {LONGTABLE_DIR} (抽样 {TICKER_REGEX}, WORKERS={WORKERS})")
```

- [ ] **Step 2: 把静默覆盖改成响亮校验**

找到：

```python
    meta = S.load_run_meta(lt); APP = meta["app"]
```

替换为：

```python
    meta = S.load_run_meta(lt)
    if meta["app"] != APP:
        raise SystemExit(f"扫描结果属于 app {meta['app']!r},但本次传入的是 {APP!r}——"
                         "读 A 的长表按 B 的分类去切会静默出错,拒绝执行")
```

**这不是逻辑体改动的例外，是本 task 明确要求的修复**，请在报告里单独记一句。

- [ ] **Step 3: 在 `tune.py` 追加 `compare`**

```python
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
```

- [ ] **Step 4: 冒烟验证 + 全套自测**

```bash
uv run python -c "
import sys, inspect
sys.path.insert(0, '.claude/skills/tune-gates')
import compare_longtable, tune
print(inspect.signature(compare_longtable.run)); print(inspect.signature(tune.compare))
assert not hasattr(compare_longtable, 'main'), 'main() 应已删除'
print('import 无副作用')
"
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```

**注意**：`compare_longtable.py` 底部原有 `if __name__ == "__main__": main()` 保护块，删除 `main()` 时一并删掉。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/compare_longtable.py .claude/skills/tune-gates/tune.py
git commit -m "refactor(tune-gates): compare_longtable 函数化 + app 静默覆盖改响亮校验

main → run(app, cfg, longtable_dir),88 行逻辑体未动。

同批修一处既有缺陷:原来 APP = meta['app'] 是静默覆盖不是校验——传入 A 却读到
B 的长表时,会按 B 的分类切 A 的数据且毫无报错。函数化后 app 是显式入参,
不一致直接 SystemExit。"
```

---

## Task 6: `region_find` 函数化 —— `tune.find()`

**背景**：`main()` 188 行，第二大。与 Task 5 同款的 `APP = meta["app"]` 静默覆盖也在这里，同样改成校验。

**Files:**
- Modify: `.claude/skills/tune-gates/region_find.py:33-48`（`main()` 头部）与 `:50`（`APP = meta["app"]`）
- Modify: `.claude/skills/tune-gates/tune.py`（追加 `find`）

**Interfaces:**
- Produces:
  - `region_find.run(app: str, cfg, longtable_dir: str, out_dir: str | None = None) -> None`
  - `tune.find(app: str, *, window: str = "main", cfg: Settings | None = None, **overrides) -> dict`

- [ ] **Step 1: 改 `region_find.py` 的 `main()` 签名与头部**

把 `def main() -> None:` 到 `OUT_DIR = None ...` 那一整段替换为：

```python
def run(app: str, cfg, longtable_dir: str, out_dir: str | None = None) -> None:
    """在联合空间(真扫维 × where 维)上识别稳健区,出 cells.csv / 切片图 / region_report.md。

    三口径并报不折中:naive 只作参考,optimism 校正当上界,split-half 按均值 ± SE 报
    (它对随机对半分的种子高度敏感,不是稳定的界)。
    """
    APP = app
    LONGTABLE_DIR = longtable_dir
    FOLD_COL, FOLDS = cfg.fold_col, list(cfg.folds)
    MIN_COUNT_PER_FOLD = cfg.min_count_per_fold
    NEIGHBOR_AXES = cfg.neighbor_axes
    B_BOOT, TOP_N = cfg.b_boot, cfg.top_n
    SPLIT_HALF_SEEDS = list(cfg.split_half_seeds)
    BOOT_SEED = cfg.boot_seed      # bootstrap 重采样的 RNG 种子;与 split-half 种子无关
    OUT_DIR = out_dir              # None → LONGTABLE_DIR 的父目录
```

**注意 `list(...)` 转换**：`Settings` 用 tuple 存 `folds` / `split_half_seeds`（frozen dataclass 需要可哈希默认值），而下游 `prepare()` 与报告行按 list 语义使用，这里显式转回。

横幅那行改为：

```python
    print(f"[region_find] app={APP} → {LONGTABLE_DIR} (功效线 {MIN_COUNT_PER_FOLD}/fold, B={B_BOOT}, split-half 种子 {len(SPLIT_HALF_SEEDS)} 个)")
```

- [ ] **Step 2: 把静默覆盖改成响亮校验**

找到：

```python
    meta = S.load_run_meta(lt); APP = meta["app"]; HEAD_BUFFER = meta["head_buffer"]
```

替换为：

```python
    meta = S.load_run_meta(lt)
    if meta["app"] != APP:
        raise SystemExit(f"扫描结果属于 app {meta['app']!r},但本次传入的是 {APP!r}——"
                         "读 A 的长表按 B 的分类去切会静默出错,拒绝执行")
    HEAD_BUFFER = meta["head_buffer"]      # ★ 口径从长表自己的记录读,不从 cfg 取(单一来源)
```

- [ ] **Step 3: 在 `tune.py` 追加 `find`**

```python
def find(app: str, *, window: str = "main", cfg: Settings | None = None, **overrides) -> dict:
    """在扫描结果上识别稳健区。**前置红线:必须先 compare 且 mismatch=0。**

    调用方(Claude)有责任在 compare 未通过时不调本函数——见 SKILL.md 的红线一节。
    """
    from dataclasses import replace
    import region_find
    cfg = replace(cfg or Settings(), **overrides) if overrides else (cfg or Settings())
    lt = out_dir_of(app, window) / "longtable"
    region_find.run(app, cfg, str(lt.relative_to(REPO)))
    return status(app, window)
```

- [ ] **Step 4: 冒烟验证 + 全套自测**

```bash
uv run python -c "
import sys, inspect
sys.path.insert(0, '.claude/skills/tune-gates')
import region_find, tune
print(inspect.signature(region_find.run)); print(inspect.signature(tune.find))
assert not hasattr(region_find, 'main'), 'main() 应已删除'
"
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/region_find.py .claude/skills/tune-gates/tune.py
git commit -m "refactor(tune-gates): region_find 函数化 + app 静默覆盖改响亮校验

main → run(app, cfg, longtable_dir, out_dir),188 行逻辑体未动。
HEAD_BUFFER 仍从 run_meta.json 读(口径单一来源),folds/split_half_seeds 从
Settings 的 tuple 显式转回 list(frozen dataclass 需要可哈希默认值)。"
```

---

## Task 7: `plateau` 函数化

**背景**：`main()` 只有 30 行，是六个里最轻的。它服务单参数路径（至今零实战），本 task 只做形态统一，不碰其判定逻辑。

**Files:**
- Modify: `.claude/skills/tune-gates/plateau.py:177-207`
- Modify: `.claude/skills/tune-gates/tune.py`（追加 `plateau_report`）

**Interfaces:**
- Produces:
  - `plateau.run(csv: str, out_dir: str, *, rel_tol: float = 0.05, min_match: int = 100) -> dict`
  - `tune.plateau_report(csv: str, out_dir: str, *, rel_tol: float = 0.05, min_match: int = 100) -> dict`

- [ ] **Step 1: 改 `plateau.py` 的 `main()`**

把 `def main():` 到 `MIN_MATCH = 100 ...` 加那行 `# ──────────────────` 的整段替换为：

```python
def run(csv: str, out_dir: str, *, rel_tol: float = 0.05, min_match: int = 100) -> dict:
    """逐闸平台判定:出 verdicts.json / verdicts.md / 每闸一张 png。

    rel_tol 与 min_match 至今未走过实战校准(见 SKILL.md「首轮使用注意」),不要当已验证默认。
    """
    CSV = csv
    OUT_DIR = out_dir
    REL_TOL = rel_tol
    MIN_MATCH = min_match
```

并在函数末尾（原 `print(f"判定 {len(verdicts)} 闸 → {out}/verdicts.md (+json +png)")` 之后）追加：

```python
    return verdicts
```

删除文件末尾的 `if __name__ == "__main__": main()` 块。

- [ ] **Step 2: 在 `tune.py` 追加转发**

```python
def plateau_report(csv: str, out_dir: str, *, rel_tol: float = 0.05, min_match: int = 100) -> dict:
    """单参数路径:事后切档位的宽表 → 逐闸平台图与判定。"""
    import plateau
    return plateau.run(csv, out_dir, rel_tol=rel_tol, min_match=min_match)
```

- [ ] **Step 3: 跑 plateau 自己的测试 + 全套自测**

```bash
uv run pytest .claude/skills/tune-gates/test_plateau.py -q
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/tune-gates/plateau.py .claude/skills/tune-gates/tune.py
git commit -m "refactor(tune-gates): plateau 函数化,形态与其余入口统一

main → run(csv, out_dir, *, rel_tol, min_match) 并返回 verdicts。判定逻辑未动。"
```

---

## Task 8: 网格提案 —— `propose_grid()` 与确定性渲染 `study.py`

**背景**：这是「Claude 先提一套网格、用户增删改」这个协作方式的技术基础，也是本计划唯一的新能力。

**⚠ 本 task 的红线**：`study.py` 的整份文件 sha256 是扫描结果的准入校验。**同一份 grid 渲染两次，字节必须逐字相同**——不得含时间戳、不得依赖 dict 迭代顺序。否则重跑一次接入就让已有扫描结果作废、必须重扫数小时。

**Files:**
- Create: `.claude/skills/tune-gates/grid_propose.py`
- Create: `.claude/skills/tune-gates/test_grid_propose.py`
- Modify: `.claude/skills/tune-gates/tune.py`（追加 `propose_grid` / `install`）

**Interfaces:**
- Produces:
  - `grid_propose.levels_for(default) -> list | None`
  - `grid_propose.propose(mod, base: dict, *, scan_grid: dict, where_levels: dict) -> dict` —— 返回 `{"params": [{"section","field","default","levels","kind"}...]}`，`kind` 由 `classify()` 探针实测得出
  - `grid_propose.ref_point_from_base(base: dict, scan_grid: dict, kinds: dict) -> dict` —— **自动推导参照格**
  - `grid_propose.render_study(*, app_module, base_yaml, wide_overrides, scan_grid, where_levels, ref_point, tight_wheres) -> str` —— **确定性**渲染 study.py 源码文本
  - `tune.propose_grid(app_module: str, base_yaml: str = "params.yaml") -> dict`
  - `tune.install(app: str, *, app_module, base_yaml="params.yaml", wide_overrides, scan_grid, where_levels, tight_wheres, apps_dir=None) -> dict` —— 推导 REF_POINT → 写 study.py → 调 `setup()`。**注意签名里没有 `ref_point`**，见下。

> **REF_POINT 不再是入参，改为自动推导。** 它的定义就是「生产参数落在网格的哪一格」，有唯一正确答案，手写它等于给一个确定的问题引入手滑机会——**2026-08-30 真发生过一次**：`path2_apps/bb_v1/params.yaml` 的生产值已是 `stop_confirm_bars: 1`，而手写的 `REF_POINT` 还停在旧生产值 `2`，被误当成「需要用户拍板的语义决定」挂了一轮。自动推导后这类问题不会再出现。`levels_for()` 保证默认值必在档位中，所以推导出的落点必然精确命中网格。

- [ ] **Step 1: 写失败测试**

新建 `.claude/skills/tune-gates/test_grid_propose.py`：

```python
# -*- coding: utf-8 -*-
"""网格提案与 study.py 确定性渲染的测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grid_propose  # noqa: E402
import study_io as S  # noqa: E402

GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
        ("burst", "gap_max"): [4, 8, 12, 20]}
WHERE = {("burst", "first_drought_min"): [0, 20, 40]}
REF = {"bo.min_relative_height": 0.2, "burst.gap_max": 8}


def _render():
    return grid_propose.render_study(
        app_module="path2_apps.demo.dag_spec", base_yaml="params.yaml",
        wide_overrides={"burst": {"first_drought_min": 0}},
        scan_grid=GRID, where_levels=WHERE, ref_point=REF,
        tight_wheres={"FINAL": {("burst", "first_drought_min"): 40}})


def test_render_is_byte_identical_across_calls():
    """★ 红线:同一份 grid 渲染两次必须逐字相同——study.py 的哈希是长表准入校验,
    渲染不稳定会让已有扫描结果无声作废、必须重扫数小时。"""
    assert _render() == _render()


def test_rendered_study_loads_with_all_eight_declarations(tmp_path):
    """渲染出来的必须是 load_study 能吃的合法声明(8 项齐全)。"""
    p = tmp_path / "study.py"
    p.write_text(_render(), encoding="utf-8")
    st = S.load_study(p)
    for name in S.STUDY_NAMES:
        assert hasattr(st, name), f"缺少声明 {name}"
    assert st.SCAN_GRID == GRID
    assert st.WHERE_LEVELS == WHERE
    assert st.REF_POINT == REF


def test_render_does_not_embed_timestamp():
    """不得含时间戳——它会让每次渲染的哈希都不同。"""
    import re
    text = _render()
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text)


def test_propose_levels_always_include_current_default():
    """推荐档位必须含参数当前默认值:参照格才落得进网格,build_classification 的
    REF_POINT 守卫才过得去。"""
    for default in (0.2, 8, 1.5, 40):
        levels = grid_propose.levels_for(default)
        assert default in levels
        assert len(levels) >= 3
        assert levels == sorted(set(levels))


def test_propose_levels_rejects_non_numeric():
    """非数值型不猜档位,返回 None 让人来定。"""
    assert grid_propose.levels_for("close") is None
    assert grid_propose.levels_for(None) is None


def test_ref_point_is_derived_from_production_values():
    """★ 参照格自动推导:取生产参数在网格上的落点,只含 D 维。

    手写 REF_POINT 曾导致真实事故——生产值已从 2 改成 1,手写的还停在 2,
    被误当成「需要用户拍板的语义决定」。自动推导后这类问题不会再出现。
    """
    base = {"bo": {"min_relative_height": 0.2}, "burst": {"gap_max": 8, "min_bos": 1}}
    kinds = {("bo", "min_relative_height"): "D", ("burst", "gap_max"): "D",
             ("burst", "min_bos"): "F"}
    grid = {("bo", "min_relative_height"): [0.1, 0.2, 0.3],
            ("burst", "gap_max"): [4, 8, 12],
            ("burst", "min_bos"): [1, 2, 3]}
    ref = grid_propose.ref_point_from_base(base, grid, kinds)
    assert ref == {"bo.min_relative_height": 0.2, "burst.gap_max": 8}   # F 维不进
    for dotted, v in ref.items():
        sec, field = dotted.split(".")
        assert v in grid[(sec, field)], "参照格必须精确落在网格档位上"


def test_ref_point_rejects_production_value_off_grid():
    """生产值不在档位里 → 响亮失败,不静默取最近档(那会让参照格偷偷变成别的格)。"""
    import pytest
    base = {"bo": {"x": 0.25}}
    with pytest.raises(SystemExit):
        grid_propose.ref_point_from_base(base, {("bo", "x"): [0.1, 0.2, 0.3]}, {("bo", "x"): "D"})
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest .claude/skills/tune-gates/test_grid_propose.py -q
```
期望：collection error，`ModuleNotFoundError: No module named 'grid_propose'`。

- [ ] **Step 3: 实现 `grid_propose.py`**

新建 `.claude/skills/tune-gates/grid_propose.py`：

```python
# -*- coding: utf-8 -*-
"""网格提案 + study.py 的确定性渲染。

**为什么要确定性**:study.py 的整份文件 sha256 是扫描结果的准入校验
(study_io.check_study_matches / check_run_matches_classification)。同一份 grid
渲染两次若字节不同,重跑一次接入就让已有扫描结果作废、必须重扫数小时。
所以:不写时间戳、所有 dict 按 sorted 键序输出、浮点用 repr 保证往返一致。
"""
from __future__ import annotations


def levels_for(default):
    """按默认值机械地铺一组候选档位。**默认值必在其中**——参照格要落进网格,
    否则 build_classification 的「REF_POINT 必须恰好覆盖全部 D 维」守卫会拒。

    这是**机械建议不是判断**:哪个参数值得扫、档位该多宽,需要对这个走势的先验知识,
    由人复核(见 SKILL.md「网格提案」一节)。非数值型返回 None,交人指定。
    """
    if isinstance(default, bool) or not isinstance(default, (int, float)):
        return None
    if default == 0:
        return None                                   # 0 无法按乘子铺档,交人指定
    vals = [default * m for m in (0.5, 1.0, 1.5, 2.5)]
    if isinstance(default, int):
        out = sorted({int(round(v)) for v in vals} | {default})
    else:
        out = sorted({float(f"{v:.4g}") for v in vals} | {float(default)})
    return out if len(out) >= 3 else None


def propose(mod, base: dict, *, scan_grid: dict | None = None,
            where_levels: dict | None = None) -> dict:
    """列出这个 app 的可调参数、推荐档位与**实测**的维度分类,供 Claude 翻译成人话。

    base 是底座快照(study_io.base_snapshot 的输出):{section: {field: value}}。
    kind 由 classify() 探针实测得出(W=where 阈值 / F=过滤型 / D=构造参数需真扫 / E=边参数),
    **不凭参数名猜**——用人话说就是「改了必须重扫」(D/E)还是「可以事后切档位」(W/F)。
    """
    from multivar_core import classify
    params, trial = [], {}
    for section in sorted(base):
        for field in sorted(base[section]):
            lv = levels_for(base[section][field])
            if lv:
                trial[(section, field)] = lv
    kinds = classify(mod, base, scan_grid or trial, where_levels or {}).kinds
    for section in sorted(base):
        for field in sorted(base[section]):
            default = base[section][field]
            params.append({"section": section, "field": field, "default": default,
                           "levels": levels_for(default),
                           "kind": kinds.get((section, field))})
    return {"params": params}


def ref_point_from_base(base: dict, scan_grid: dict, kinds: dict) -> dict:
    """参照格 = 生产参数在网格上的落点,自动推出来,**不接受手写**。

    为什么自动:REF_POINT 的定义就是「生产参数落在网格的哪一格」,有唯一正确答案。
    手写它等于给一个确定的问题引入手滑机会——2026-08-30 真出过一次:生产值已从 2
    改成 1,而手写的 REF_POINT 还停在 2,被误当成「需要用户拍板的语义决定」挂了一轮。

    只取 D 维:build_classification 校验「REF_POINT 必须恰好覆盖全部 D 维」。
    生产值不在档位里就响亮失败——静默取最近档会让参照格偷偷变成另一个格,
    而参照格是所有增量的基准。
    """
    ref = {}
    for (section, field), levels in scan_grid.items():
        if kinds.get((section, field)) != "D":
            continue
        v = base.get(section, {}).get(field)
        if v not in levels:
            raise SystemExit(
                f"生产值 {section}.{field}={v!r} 不在档位 {levels} 里——参照格必须精确落在"
                "网格上(它是所有增量的基准)。请把该生产值加进档位,或改用含它的档位。")
        ref[f"{section}.{field}"] = v
    return ref


def _fmt(v) -> str:
    """确定性地把一个值渲染成 Python 字面量。dict 按 sorted 键序,保证字节稳定。"""
    if isinstance(v, dict):
        items = sorted(v.items(), key=lambda kv: repr(kv[0]))
        return "{" + ", ".join(f"{_fmt(k)}: {_fmt(x)}" for k, x in items) + "}"
    if isinstance(v, (list, tuple)):
        body = ", ".join(_fmt(x) for x in v)
        return f"[{body}]" if isinstance(v, list) else f"({body},)" if len(v) == 1 else f"({body})"
    return repr(v)


def render_study(*, app_module: str, base_yaml: str, wide_overrides: dict, scan_grid: dict,
                 where_levels: dict, ref_point: dict, tight_wheres: dict) -> str:
    """渲染 apps/<app>/study.py 的源码文本。**确定性:同输入同字节。**"""
    return f'''# -*- coding: utf-8 -*-
"""tune-gates · study 声明(由 tune.install 生成,不要手改)。

改这个文件会让已有扫描结果作废——它的整份文件哈希是长表准入校验。
要换网格请重新走一次接入流程,那会开一份新的扫描结果。
"""

APP_MODULE = {app_module!r}
BASE_YAML = {base_yaml!r}

WIDE_OVERRIDES = {_fmt(wide_overrides)}

SCAN_GRID = {_fmt(scan_grid)}

WHERE_LEVELS = {_fmt(where_levels)}

REF_POINT = {_fmt(ref_point)}

TIGHT_WHERES = {_fmt(tight_wheres)}

FLAG_RULES = []
'''
```

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest .claude/skills/tune-gates/test_grid_propose.py -q
```
期望：5 passed。

- [ ] **Step 5: 在 `tune.py` 追加 `propose_grid` 与 `install`**

```python
def propose_grid(app_module: str, base_yaml: str = "params.yaml") -> dict:
    """读 pattern 的参数,提一套带推荐档位与实测维度分类的网格方案供用户增删改。

    **返回的是机械建议不是判断**:哪个参数值得扫、档位该多宽,需要对这个走势的先验知识。
    Claude 须把它翻译成人话列给用户(参数名说人话、按「改了必须重扫」/「可以事后切档位」
    分组、标出推荐档位),由用户增删改。
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
    """
    import importlib
    import grid_propose
    from multivar_core import classify
    apps_dir = Path(apps_dir) if apps_dir else S.APPS_DIR
    mod = importlib.import_module(app_module)
    base_yaml_dict = mod.Params.from_yaml(S.app_dir(mod) / base_yaml).to_dict()
    from multivar_core import apply_overrides
    base = apply_overrides(base_yaml_dict, wide_overrides, {})
    kinds = classify(mod, base, scan_grid, where_levels).kinds
    ref_point = grid_propose.ref_point_from_base(base, scan_grid, kinds)
    d = apps_dir / app
    d.mkdir(parents=True, exist_ok=True)
    (d / "study.py").write_text(grid_propose.render_study(
        app_module=app_module, base_yaml=base_yaml, wide_overrides=wide_overrides,
        scan_grid=scan_grid, where_levels=where_levels, ref_point=ref_point,
        tight_wheres=tight_wheres), encoding="utf-8")
    return setup(app, apps_dir=apps_dir)
```

- [ ] **Step 6: 跑全套自测 + Commit**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3

git add .claude/skills/tune-gates/grid_propose.py .claude/skills/tune-gates/test_grid_propose.py \
        .claude/skills/tune-gates/tune.py
git commit -m "feat(tune-gates): 网格提案 + study.py 确定性渲染

「Claude 先提一套网格、用户增删改」这个协作方式的技术基础。levels_for() 保证
默认值必在档位中——参照格要落进网格,否则 build_classification 的守卫会拒。

★ 渲染必须确定性:study.py 的整份 sha256 是扫描结果的准入校验,同一份 grid 渲染两次
字节不同就会让已有长表无声作废、必须重扫数小时。故不写时间戳、dict 按 sorted 键序、
浮点走 repr。有测试逐条钉住。"
```

---

## Task 9: 删除 `current.py` / `run.py`，`bench_workers` 接线

**背景**：所有转换完成，旧的传参载体可以删了。同时把 Task 2 降级成 stub 的 `bench_workers` 接到新调用面上——它现在只需起子进程调 `tune.scan`，不再复制脚本、不再改写源码。

**Files:**
- Delete: `.claude/skills/tune-gates/current.py`、`apps/_template/run.py`、`apps/bb_v1/run.py`
- Modify: `.claude/skills/tune-gates/study_io.py`（删 `load_run` 与 `RUN_REQUIRED`）
- Modify: `.claude/skills/tune-gates/test_study_io.py`（删 `load_run` 的 3 个测试）
- Modify: `.claude/skills/tune-gates/bench_workers.py`

**Interfaces:**
- Consumes: `tune.scan` / `tune.compare` / `tune.Settings`

- [ ] **Step 1: 确认没有残留引用**

```bash
grep -rn "import current\|load_run\|RUN_REQUIRED\|run\.py" .claude/skills/tune-gates/*.py
```

期望：只有 `study_io.py` 自身的定义、`test_study_io.py` 的 3 个测试、以及注释里的无关词。**若某个入口脚本仍在引用，说明前面的 task 漏改，回去补。**

- [ ] **Step 2: 删除文件与 `load_run`**

```bash
git rm .claude/skills/tune-gates/current.py \
       .claude/skills/tune-gates/apps/_template/run.py \
       .claude/skills/tune-gates/apps/bb_v1/run.py
```

在 `study_io.py` 中删除 `RUN_REQUIRED` 常量与 `load_run()` 函数整体。

在 `test_study_io.py` 中删除这三个测试：`test_load_run_reads_all_required_fields`、`test_load_run_missing_file_gives_actionable_error`、`test_load_run_missing_field_lists_which`。

- [ ] **Step 3: `bench_workers` 接线**

把 Task 2 留下的 stub `main()` 替换为：

```python
def main():
    # ---- 实验参数 ----
    APP = "bb_v1"                      # 定标用哪个 app 的真实数据
    WORKER_GRID = [4, 8, 12, 16, 20, 24, 26]
    SAMPLE_SEC = 0.4
    TICKER_REGEX = r"^A[A-C]"          # 108 只：W=26 时每 worker 仍有 ~4 个任务，避免尾部效应主导
    SCRATCH = Path(os.environ.get("CLAUDE_SCRATCH", "/tmp")) / "bench_workers"
    # ──────────────────
    SCRATCH.mkdir(parents=True, exist_ok=True)
    scratch_rel = os.path.relpath(SCRATCH, REPO)
    print(f"scratch={SCRATCH}\n股票正则={TICKER_REGEX} · WORKERS 网格={WORKER_GRID} · 采样间隔={SAMPLE_SEC}s\n", flush=True)

    # 不再复制脚本、不再改写源码:直接起子进程调 tune 的函数,参数走命令行传给 -c。
    # 那套正则改写的唯一存在理由是「参数只能写死在 main() 里」,该前提已不成立。
    def _cmd(call: str) -> str:
        return (f"import sys; sys.path.insert(0, {str(REPO / '.claude/skills/tune-gates')!r}); "
                f"import tune; {call}")

    for name in ("scan", "compare"):
        print(f"===== {name} =====", flush=True)
        rows = []
        for w in WORKER_GRID:
            if name == "scan":
                # 每轮重来：扫描是断点续跑的，残留分片会让后续轮次「已完成」而秒退。
                # compare 轮不删——它读的是 scan 轮最后一次留下的扫描结果(含 run_meta.json)
                shutil.rmtree(SCRATCH / "scan_out", ignore_errors=True)
                call = (f"tune.scan({APP!r}, window='bench', workers={w}, "
                        f"ticker_regex={TICKER_REGEX!r})")
            else:
                call = (f"tune.compare({APP!r}, window='bench', workers={w}, "
                        f"cmp_ticker_regex={TICKER_REGEX!r})")
            r = _run_one_code(_cmd(call), w, SAMPLE_SEC)
            rows.append(r)
            flag = "" if r["rc"] == 0 else f"  ⚠ rc={r['rc']}"
            print(f"  W={w:>2}  wall {r['wall']:7.1f}s  峰值 {r['peak_mb']:7.0f} MB"
                  f"({'PSS' if r['pss'] else 'RSS,高估'}, {r['n_proc']} 进程){flag}", flush=True)
            if r["rc"] != 0:
                print("    " + "\n    ".join(r["out"].strip().splitlines()[-6:]), flush=True)

        ok = [r for r in rows if r["rc"] == 0]
        if not ok:
            print("  (全部失败,跳过汇总)\n", flush=True)
            continue
        base = min(ok, key=lambda r: r["workers"])
        print(f"\n  相对 W={base['workers']} 的加速比与内存:")
        for r in ok:
            dw = r["workers"] - base["workers"]
            per_w = (r["peak_mb"] - base["peak_mb"]) / dw if dw else float("nan")
            print(f"    W={r['workers']:>2}  {base['wall'] / r['wall']:5.2f}×  "
                  f"峰值 {r['peak_mb']:6.0f} MB  每多一 worker 约 {per_w:6.1f} MB", flush=True)


if __name__ == "__main__":
    main()
```

并把 `_run_one` 改名为 `_run_one_code` 且改成跑 `-c` 代码串（原来是跑脚本文件）：

```python
def _run_one_code(code: str, workers: int, interval: float) -> dict:
    """跑一次并采样。返回 wall / 峰值内存 / 脚本自报的末行。"""
    t0 = time.time()
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=REPO,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sampler = PeakSampler(proc.pid, interval)
    sampler.start()
    out, _ = proc.communicate()
    sampler.stop()
    wall = time.time() - t0
    tail = [ln for ln in out.strip().splitlines() if ln.strip()]
    return dict(workers=workers, wall=wall, peak_mb=sampler.peak_kb / 1024, pss=sampler.pss_ok,
                n_proc=sampler.n_peak_proc, rc=proc.returncode, last=tail[-1] if tail else "(无输出)",
                out=out)
```

**注意**：`SCRATCH` 目前只用于内存采样输出与 scan_out 清理；`tune.scan(window='bench')` 会写进 `outputs/tune_gates/<app>/bench/`。若要严格保持「输出一律写 scratchpad」，在报告里说明实际落点，**不要为此改 `tune.scan` 的目录推导**（那是全局约定）。

- [ ] **Step 4: 冒烟 + 全套自测**

```bash
uv run python -c "
import sys; sys.path.insert(0, '.claude/skills/tune-gates')
import bench_workers, inspect
print(inspect.signature(bench_workers._run_one_code))
print('import 无副作用')
"
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```

**不要真跑 benchmark**（拉进程池扫股票，耗时极长）。

- [ ] **Step 5: Commit**

```bash
git add -A .claude/skills/tune-gates/
git commit -m "refactor(tune-gates): 删除 current.py / run.py,bench_workers 接入 tune

所有入口转换完成,旧的传参载体可以删了:current.py(app 身份单源)、
apps/*/run.py(run 级常量)、study_io.load_run/RUN_REQUIRED 一并移除,
它们的职责由 tune.Settings 与函数入参承担。

bench_workers 从 Task 2 的 stub 接回来:直接起子进程调 tune.scan/tune.compare,
参数走 -c 代码串。不再复制脚本、不再正则改写源码——9 条改写与失配断言彻底消失。"
```

---

## Task 10: 文档三拆 + 禁止词检查 + CLAUDE.md 规范例外

**背景**：`SKILL.md` 一份文档混着两个读者是心智负担的另一个根因；且旧协议自相矛盾（一边写「Claude 不许跳」，一边要求「把三行指纹报告原样给用户看」），泄漏正是从这类条款来的。

**Files:**
- Rewrite: `.claude/skills/tune-gates/SKILL.md`
- Modify: `.claude/skills/tune-gates/reference.md`
- Create: `docs/explain/tune-gates_调参判据卡.md`
- Modify: `CLAUDE.md`
- Modify: `.claude/skills/tune-gates/test_tune.py`（追加禁止词检查）

**Interfaces:** 无代码接口。

- [ ] **Step 1: 备份现有 SKILL.md 供逐条核对**

```bash
cp .claude/skills/tune-gates/SKILL.md /tmp/skill_before_lowfriction.md
grep -c "" /tmp/skill_before_lowfriction.md
```

- [ ] **Step 2: 重写 `SKILL.md` 为执行协议**

目标结构（**判据文字、数字、案例指针逐条保留**，只重新组织并把操作说明换成新调用面）：

```
# 逐闸平台调参（tune-gates）
  开头两句（选阈值的原则 / 本 skill 管「选」）

## 一、调用面（Claude 用）
  七个函数各一行说明 + 典型序列：
    tune.status(app) → 据此决定下一步
    tune.propose_grid(app_module) → 翻译成人话给用户增删改 → tune.install(...)
    tune.scan(app) → tune.compare(app) → tune.find(app)
    tune.retire(app, confirm=...) 退役
  Settings 的 ★ 字段说明（改了必须换 window）

## 二、什么时候停下来问用户（四类，其余自己定）
  不可逆动作 / 超过半小时 / 真研究决定 / 红线触发
  每类给一句人话模板

## 三、禁止词与人话译法
  ← spec §7.2 的整张表，原样落地

## 四、判据与纪律（执行时要守的）
  ← 原「一、判据与纪律」全文（红线 14 条、与既有资产的关系）

## 五、分流器：这次该走哪条路
  ← 原「二、分流器」全文

## 六、路径 A：事后切档 → 平台图
  ← 原「三、路径 A」全文，操作命令换成 tune.plateau_report(...)

## 七、路径 B：多维稳健区
  ← 原「四、路径 B」全文（B1..B5），操作命令换成 tune 的函数调用
  ← 原「入口协议」重写为基于 tune.status() 的判定，不再让用户看指纹报告

## 首轮使用注意
  ← 原节，按本计划落地情况更新
```

**入口协议的关键改写**（原来要求「把三行报告原样给用户看」，那是泄漏源）：

```
调 tune.status(app) 后按 installed / classification_stale 分流：
├─ installed=False → 新接入：propose_grid → 翻译成人话让用户增删改 → install
└─ installed=True
   ├─ classification_stale=False → 直接用
   └─ classification_stale=True → 用人话问用户：
       「上次调完这个 pattern 之后，检测逻辑或参数默认值改过吗？改过的话我重新
         过一遍参数分类；没改的话我就按上次的接着做。」
       用户说改过 → tune.setup(app)；说没改 → 继续，并把这个裁定记进
       tune 的 exposure note（跨轮持久，不会被下一次运行抹掉）
```

- [ ] **Step 3: 逐条核对判据没丢**

```bash
for k in "字典序" "win_rate 废弃" "功效线" "分年方向一致性" "算术效应归因" \
         "先对拍后读数" "作用域" "holdout" "FLAG_RULES" "OAT" "1SE" "REL_TOL" \
         "exposure.jsonl" "均值" "五链"; do
  n=$(grep -c "$k" .claude/skills/tune-gates/SKILL.md)
  o=$(grep -c "$k" /tmp/skill_before_lowfriction.md)
  [ "$n" -ge "$o" ] && echo "OK  $k ($o→$n)" || echo "!! 丢失 $k ($o→$n)"
done
```

任何一行出现 `!! 丢失` 都要回去补，**不允许在重组中删减判据**。

- [ ] **Step 4: 确认旧调用面已无残留**

```bash
grep -n "current\.py\|run\.py\|MODE=\|MODE =\|复制到研究目录\|app_setup\.py\|multivar_scan\.py\|region_find\.py" \
  .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md \
  || echo "OK 无旧调用面残留"
```

命中的都要改成 `tune.xxx()` 的说法。

- [ ] **Step 5: 新建判据卡（给用户）**

新建 `docs/explain/tune-gates_调参判据卡.md`。**只写用户需要判断的事，不含任何操作步骤、不含任何内部机制词**：

```markdown
# 调参判据卡

这份文档只回答一件事：**Claude 给你的调参结果，什么时候能信、什么时候不能信。**
怎么跑、跑什么，都不用你管。

## 一、三个分数怎么读

识别结果会同时给三个数字，它们**并列呈报、不折中**：

- **朴素分数**：直接在数据上挑出来的最好成绩。它一定偏乐观——因为「挑」这个动作本身就会挑中运气好的那个。只作参考。
- **扣掉挑选偏差后的分数**：把「反复挑最好的」带来的虚高扣掉之后的估计。按标准口径它可以当**上界**看。
- **对半分验证**：把数据一分为二，在一半上挑、去另一半上验。它对怎么分高度敏感（实测换个分法能从 −0.03 变到 −0.31），所以按**均值 ± 波动范围**报——**不要拿单次数值当下界读**。

**判据**：朴素分数为正但扣掉偏差后翻负 → 不构成推荐。

## 二、什么时候不该信结果

1. **一致性验证没通过** —— 这是硬红线。验证不过说明「扫完再切档位」和「每档真扫一遍」结果不一致，那么所有读数都没有意义。
2. **样本量不够** —— 每个时间段的命中数低于功效线时，那个格子不可评估。注意这条功效线**只在一个走势上校准过**，口径偏松、方向不保守，换个走势不要当已验证默认。
3. **只有一个时间段成立** —— 分年方向不一致的，多半是那一年的特有现象。
4. **扫描结果再生不出来** —— 如果当前代码已经产不出那份数据，基于它的结论没法复现，我会主动告诉你。

## 三、哪些数字至今没被校准过

- 功效线（每段最少命中数）：只在一个走势上校准过一次，结论是偏松。
- 单参数路径的两个阈值：**零实战**，从未被真实数据检验过，不要当已验证默认。

## 四、什么时候该推翻我的结论

- 我说「找到稳健区」但三个分数互相矛盾 —— 以最保守的那个为准。
- 我给的参数值落在网格边缘 —— 说明真正的好区域可能在网格外面，该重扫更宽的范围。
- 我报的提升幅度没有基线对照 —— 孤立数字不能下结论，问我基线是多少。
- **同一批数据你已经让我挑过很多轮** —— 挑得越多，最终数字越乐观。我会告诉你这是第几轮。
```

- [ ] **Step 6: `reference.md` 瘦身**

删除「多维稳健区 v2 工具用法」等操作卡段落（已被 `SKILL.md` 的调用面取代），**保留实证坑清单与校准状态**（对拍开销、WORKERS 拐点、功效线偏松等，都是实测换来的资产）。在文件头 docstring 注明：

```
本文件是**实证坑清单与校准状态**，给 Claude 读。操作说明见 SKILL.md 的调用面。
```

- [ ] **Step 7: 项目 CLAUDE.md 增加规范例外**

在 `CLAUDE.md` 的「编码规范」节，把「入口脚本：不使用 argparse，参数声明在 `main()` 起始位置」那条改为：

```markdown
- 入口脚本：不使用 argparse，参数声明在 `main()` 起始位置
  - **例外：`.claude/skills/tune-gates/`**。该 skill 的参数由 Claude 代填、不由人手填，
    规范的初衷（「不喜欢每次运行需要手动输入参数」）由代理满足；调用面是
    `tune.py` 的函数入参，不是命令行。详见
    `docs/superpowers/specs/2026-08-30-tune-gates-low-friction-redesign.md` §3。
```

- [ ] **Step 8: 追加禁止词检查测试**

在 `.claude/skills/tune-gates/test_tune.py` 末尾追加：

```python
BANNED = ["MODE=", "current.py", "run.py", "classification.json", "run_meta.json",
          "exposure.jsonl", "detection_combos", "HEAD_BUFFER", "指纹", "对拍", "长表"]


def test_skill_md_human_templates_contain_no_banned_words():
    """给用户说的话里不得出现内部机制词。

    SKILL.md 的「禁止词与人话译法」一节列出了译法;本测试检查「什么时候停下来问用户」
    一节的人话模板本身干净——那些句子是要原样说给用户听的。
    """
    skill = Path(__file__).resolve().parent / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    start = text.index("## 二、什么时候停下来问用户")
    end = text.index("## 三、禁止词与人话译法")
    section = text[start:end]
    hits = [w for w in BANNED if w in section]
    assert not hits, f"人话模板里混进了内部机制词: {hits}"
```

- [ ] **Step 9: 跑全套自测 + Commit**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3

git add .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md \
        .claude/skills/tune-gates/test_tune.py CLAUDE.md docs/explain/tune-gates_调参判据卡.md
git commit -m "docs(tune-gates): 文档三拆 —— 执行协议 / 判据卡 / 实证坑清单

一份文档混着两个读者是心智负担的另一个根因,且旧协议自相矛盾:一边写「Claude
不许跳」,一边要求「把三行指纹报告原样给用户看」——泄漏正是从这类条款来的。

SKILL.md = 给 Claude 的执行协议(调用面 + 四类决策点 + 禁止词与人话译法 + 判据)。
docs/explain/tune-gates_调参判据卡.md = 给用户的,只写「什么时候能信结果」,
零操作步骤、零机制词。reference.md 瘦身为实证坑清单与校准状态。

入口协议不再让用户看指纹报告,改为基于 tune.status() 分流 + 一句人话询问。
禁止词有测试兜底,不只是规矩。

CLAUDE.md 记入规范例外:本 skill 内参数由 Claude 代填,「不使用 argparse」的
初衷由代理满足。"
```

---

## Task 11: 端到端等价验证

**背景**：这是「只换了头部、没改逻辑」的直接证据，也是本计划最关键的验收。

**Files:**
- Create: `.claude/skills/tune-gates/test_entrypoint_equivalence.py`

**Interfaces:**
- Consumes: `tune.Settings`、各模块的 `run()`

- [ ] **Step 1: 写等价性测试**

新建 `.claude/skills/tune-gates/test_entrypoint_equivalence.py`：

```python
# -*- coding: utf-8 -*-
"""入口层重构的等价性证据:新调用面装配出来的参数,与改造前的常量取值逐项相同。

不真跑扫描(要几十分钟),而是断言「装配结果」——改造的实质就是把常量装配换成参数,
所以装配结果相同即等价。改造前的取值来自 apps/bb_v1/run.py(已随 Task 9 删除),
下面的期望值是从该文件的最后一版逐字抄来的。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune  # noqa: E402

# 改造前 apps/bb_v1/run.py 的逐字取值（该文件已删除，这里是它的冻结副本）
BEFORE = {
    "DATA_DIR": "datasets/pkls", "START_DATE": "2024-01-01", "END_DATE": "2026-01-01",
    "HEAD_BUFFER": 250, "LABEL_HORIZON": 40, "FIRST_PASSAGE_K": 5.0,
    "PRICE_MIN": 0.5, "PRICE_MAX": 30.0, "VOLUME_MIN": 10000.0,
    "TICKER_REGEX": None, "SHARD_STOCKS": 200,
    "CMP_TICKER_REGEX": r"^[A-Z][A-C]", "CMP_SEED": 11,
    "CMP_N_RANDOM_CELLS": 64, "CMP_N_TIGHT_CELLS": 12, "MIN_WIN_BARS": 1,
    "FOLD_COL": "fold_Y", "FOLDS": ["2024", "2025"], "MIN_COUNT_PER_FOLD": 100,
    "NEIGHBOR_AXES": "all", "B_BOOT": 300, "SPLIT_HALF_SEEDS": list(range(20)), "TOP_N": 20,
}


def test_settings_defaults_equal_pre_refactor_values():
    """23 项逐字相同——这是迁移等价的直接证据。"""
    s = tune.Settings()
    got = {
        "DATA_DIR": s.data_dir, "START_DATE": s.start_date, "END_DATE": s.end_date,
        "HEAD_BUFFER": s.head_buffer, "LABEL_HORIZON": s.label_horizon,
        "FIRST_PASSAGE_K": s.first_passage_k, "PRICE_MIN": s.price_min,
        "PRICE_MAX": s.price_max, "VOLUME_MIN": s.volume_min,
        "TICKER_REGEX": s.ticker_regex, "SHARD_STOCKS": s.shard_stocks,
        "CMP_TICKER_REGEX": s.cmp_ticker_regex, "CMP_SEED": s.cmp_seed,
        "CMP_N_RANDOM_CELLS": s.cmp_n_random_cells, "CMP_N_TIGHT_CELLS": s.cmp_n_tight_cells,
        "MIN_WIN_BARS": s.min_win_bars, "FOLD_COL": s.fold_col, "FOLDS": list(s.folds),
        "MIN_COUNT_PER_FOLD": s.min_count_per_fold, "NEIGHBOR_AXES": s.neighbor_axes,
        "B_BOOT": s.b_boot, "SPLIT_HALF_SEEDS": list(s.split_half_seeds), "TOP_N": s.top_n,
    }
    assert got == BEFORE


def test_no_entrypoint_module_has_main():
    """六个入口的 main() 必须全部消失——留一个就会有两个调用面、迟早漂移。"""
    import app_setup, compare_longtable, multivar_scan, plateau, region_find
    for mod in (app_setup, multivar_scan, compare_longtable, region_find, plateau):
        assert not hasattr(mod, "main"), f"{mod.__name__}.main() 应已删除"


def test_no_module_imports_current_or_load_run():
    """current.py 与 load_run 的引用必须绝迹。"""
    skill = Path(__file__).resolve().parent
    for p in skill.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "import current" not in text, f"{p.name} 仍引用 current.py"
        assert "load_run(" not in text, f"{p.name} 仍调用 load_run"
```

- [ ] **Step 2: 跑测试**

```bash
uv run pytest .claude/skills/tune-gates/test_entrypoint_equivalence.py -q
```
期望：3 passed。任何一条失败都指向前面某个 task 的遗漏，回去补。

- [ ] **Step 3: 跑全套自测**

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
```
期望：**0 failed / 0 errors**。把实际 passed 数记进报告，作为新基线。

- [ ] **Step 4: 真实 `status()` 冒烟（只读）**

```bash
uv run python -c "
import sys, json; sys.path.insert(0, '.claude/skills/tune-gates')
import tune
print(json.dumps(tune.status('bb_v1'), ensure_ascii=False, indent=1, default=str))
"
```

**期望**：`installed=True`；`classification_stale=True`（`apps/bb_v1/classification.json` 是 2026-08-25 实战存档，与当前 `study.py` 不匹配，这是**已知且有意保留**的状态）；`scanned_shards=0`（`outputs/tune_gates/` 目录当前不存在）。把完整输出贴进报告。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/test_entrypoint_equivalence.py
git commit -m "test(tune-gates): 入口层重构的等价性证据

三条钉子:Settings 的 23 项默认值与改造前 apps/bb_v1/run.py 逐字相同(迁移等价);
六个入口的 main() 全部消失(留一个就会有两个调用面、迟早漂移);
current.py 与 load_run 的引用绝迹。"
```

---

## Task 12: 真实小规模端到端跑通

**背景**：前 11 个 task 只做到签名冒烟——**没有任何一步证明新调用面真能跑出长表**。而用户接下来要拿这套流程从零重跑全部调参，所以必须先在小样本上把 `install → scan → compare → find` 整条链真跑一遍。

`datasets/pkls/` 现有 **8325 个 pkl**，数据齐备。取 `^A[A-C]`（约 108 只，与历史 benchmark 同一子集）跑完整链路，预计几分钟。

**⚠ 这是烟测不是生产级验证**：红线要求参与一致性验证的股数 ≥ 500，108 只达不到统计意义。但 `mismatch=0` 作为**机械正确性**检查（「扫完再切档位」是否等于「每档真扫一遍」）仍然成立且有意义。报告里必须写明这个区别。

**Files:** 无（只跑不改）；产物落 `outputs/tune_gates/bb_v1/smoke/`（已 gitignore）

- [ ] **Step 1: 提网格并落地**

```bash
uv run python -c "
import sys, json; sys.path.insert(0, '.claude/skills/tune-gates')
import tune
p = tune.propose_grid('path2_apps.bb_v1.dag_spec')
d = [x for x in p['params'] if x['kind'] == 'D' and x['levels']]
print('D 维参数数:', len(d))
for x in d[:8]:
    print(f\"  {x['section']}.{x['field']:24s} 默认 {x['default']!r:>8}  档位 {x['levels']}\")
"
```

记下输出。然后取其中 **2 个 D 维**（保持网格小、跑得快）落地：

```bash
uv run python -c "
import sys, json; sys.path.insert(0, '.claude/skills/tune-gates')
import tune
r = tune.install('bb_v1',
    app_module='path2_apps.bb_v1.dag_spec',
    wide_overrides={'burst': {'first_drought_min': 0, 'distinct_pk_min': 1,
                              'vol_spike_min': 0, 'peak_age_min': 0},
                    'tb': {'max_day_drop_pct': None}},
    scan_grid={('bo', 'min_relative_height'): [0.1, 0.2, 0.3],
               ('burst', 'gap_max'): [4, 8, 12]},
    where_levels={('burst', 'first_drought_min'): [0, 20, 40],
                  ('tb', 'max_day_drop_pct'): [None, 0.2]},
    tight_wheres={'FINAL': {('burst', 'first_drought_min'): 20,
                            ('tb', 'max_day_drop_pct'): 0.2}})
print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
"
```

**期望**：打印分类表，`detection_combos` 为个位数或几十；**不报「REF_POINT 覆盖不全」**（自动推导应当正好覆盖 D 维）。若报错，说明 `ref_point_from_base` 与 `build_classification` 的 D 维口径不一致——**这正是本 task 要抓的问题**，回 Task 8 修。

- [ ] **Step 2: 扫描（小样本）**

```bash
uv run python -c "
import sys, json; sys.path.insert(0, '.claude/skills/tune-gates')
import tune
st = tune.scan('bb_v1', window='smoke', ticker_regex=r'^A[A-C]', shard_stocks=50)
print(json.dumps(st, ensure_ascii=False, indent=1, default=str))
"
```

**期望**：跑完，`scanned_shards >= 1`，`outputs/tune_gates/bb_v1/smoke/longtable/` 下有 parquet 分片与 `run_meta.json`。把耗时与分片数记进报告。

- [ ] **Step 3: 一致性验证**

```bash
uv run python -c "
import sys, json; sys.path.insert(0, '.claude/skills/tune-gates')
import tune
st = tune.compare('bb_v1', window='smoke', cmp_ticker_regex=r'^A[A-C]',
                  cmp_n_random_cells=8, cmp_n_tight_cells=2)
print(json.dumps(st, ensure_ascii=False, indent=1, default=str))
"
```

**期望**：`compare_mismatch == 0`。**非 0 就停下来报告，不要继续 Step 4**——那说明重构改变了行为，是本计划最严重的失败模式。

- [ ] **Step 4: 识别**

```bash
uv run python -c "
import sys, json; sys.path.insert(0, '.claude/skills/tune-gates')
import tune
st = tune.find('bb_v1', window='smoke', min_count_per_fold=5, b_boot=30,
               split_half_seeds=tuple(range(5)))
print(json.dumps(st, ensure_ascii=False, indent=1, default=str))
"
```

**注意**：功效线降到 5、`b_boot` 降到 30 是为了让 108 只的小样本能跑完出报告——**这些数字只用于烟测，不是推荐值**，报告里要写明。

**期望**：`found == True`，`outputs/tune_gates/bb_v1/smoke/region_report.md` 生成。**不解读它的结论**（样本量根本不够），只确认链路通。

- [ ] **Step 5: 确认审计日志与状态**

```bash
uv run python -c "
import sys, json; sys.path.insert(0, '.claude/skills/tune-gates')
import tune
print(json.dumps(tune.status('bb_v1', 'smoke'), ensure_ascii=False, indent=1, default=str))
"
tail -1 .claude/skills/tune-gates/apps/bb_v1/exposure.jsonl
```

**期望**：`exposure_rounds >= 1`（`find` 应当追加了一行）；那一行含 `note` 字段与三口径的分子分母。

- [ ] **Step 6: 清理烟测产物并 Commit**

```bash
rm -rf outputs/tune_gates/bb_v1/smoke
git status --porcelain          # apps/bb_v1/{study.py,classification.json} 应显示已修改
git add .claude/skills/tune-gates/apps/bb_v1/
git commit -m "chore(tune-gates): 真实小规模端到端跑通,bb_v1 声明由新流程重新生成

^A[A-C] 约 108 只跑完 install → scan → compare → find 整条链,mismatch=0。
这是前 11 个 task 里唯一证明「新调用面真能跑出长表」的一步——此前只有签名冒烟。

apps/bb_v1/study.py 与 classification.json 随之由 tune.install 重新生成:
REF_POINT 现在自动取生产参数在网格上的落点(params.yaml 的 stop_confirm_bars=1),
不再手写。旧的 2026-08-25 分类存档不需要保留——真正的存档是
docs/research/2026-08-25_multivar-bb_v1/ref_params.json 与 notes.md 的正文记录,
两者都独立于 app 目录、均未触碰。

烟测用的功效线 5 / b_boot 30 只为让小样本跑完出报告,不是推荐值;
108 只也达不到一致性验证要求的 500 只,mismatch=0 在这里是机械正确性检查
(切档位 == 真扫)而非统计验证。"
```

---

## 完成校验（全部 task 之后）

```bash
uv run pytest .claude/skills/tune-gates/ -q 2>&1 | tail -3
# 期望: 0 failed, 0 errors

uv run python -c "
import sys; sys.path.insert(0, '.claude/skills/tune-gates')
import tune, inspect
for f in ('status','propose_grid','install','setup','scan','compare','find','retire','plateau_report'):
    print(f, inspect.signature(getattr(tune, f)))
"

git log --oneline -12        # 12 个 commit,每个 task 一个
git status --porcelain       # 除既有未跟踪研究目录外应干净
```

**未实施项（用户已拍板不做）**：
- 新增分析能力（「功能完善」= 现有能力一个不少）
- `study.py` 的形态改造（只推翻入口层）
- 补齐单参数路径（`plateau.py` 的两个阈值校准、三项模板）

## 两个原「悬而未决」项已消解（2026-08-30 裁定，不需用户拍板）

用户明确：**skill 开发完会彻底重新运行一遍调参**。据此二者都不再是决定：

**1. `REF_POINT["tb.stop_confirm_bars"]` 该是 2 还是 1 —— 问题本身作废。**
核实 `path2_apps/bb_v1/params.yaml`：生产值就是 **`stop_confirm_bars: 1`**。参照格的定义是「生产参数在网格上的落点」，所以 1 才对，2 是旧生产值的残留（`notes.md:11` 记录 2026-08-25 底座确为 `stop_confirm_bars=2`，代码此后已改）。原先「把参照格从实战设定挪走」的担忧方向反了。
**处理**：Task 8 把 REF_POINT 改为**自动推导**，`install()` 签名里不再有它——这类问题以后不会再出现。Task 12 用真实 app 验证推导结果能过 `build_classification` 的守卫。

**2. `apps/bb_v1/classification.json` 与 `study.py` 不匹配 —— 无需保留，直接由新流程重生成。**
此前判定「不重建」的理由之一是「`notes.md` 整篇围绕它写」，**该前提经核实为假**：`grep classification notes.md` **零命中**。`notes.md:5` 明写「证据目录是一次性研究产物、可能被清理；**本文件自足**」，`:9`/`:11` 引用的是 `docs/research/2026-08-25_multivar-bb_v1/ref_params.json`（已存在）并把底座要点抄进了正文。
**真正的存档是 `ref_params.json` + `notes.md` 正文，两者都独立于 app 目录、本计划均不触碰。** `apps/bb_v1/classification.json` 只是 `study.py` 的派生物，Task 12 的 `install()` 会连同 `study.py` 一起重新生成，不必询问用户。
