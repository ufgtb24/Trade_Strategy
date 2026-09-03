# tune-gates skill 自包含 + app 解耦 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `tune-gates` skill 改成自包含（不再读 `docs/research/`）、通用区零 app 专名、全部 app 耦合收进 `apps/<app>/` 一个可整删目录，并加上「双指纹作证据 + 必问用户」的耦合内容过期协议。

**Architecture:** 新增 `study_io.py`（加载 `study.py` / 生成与读取 `classification.json` / 指纹 / 推导 helper / `run_meta.json`）和 `app_setup.py`（build/check 两模式入口）；三个既有工具的 `main()` 只保留 run 级常量，其余全部从 `study.py` + `classification.json` + `run_meta.json` 推导；库核 `multivar_core.py` / `region_core.py` 零改动。

**Tech Stack:** Python 3.12 / `uv` / pandas / pyarrow / pyyaml（已装 6.0.3）/ pytest。测试全部在 skill 目录内以显式路径跑。

**Spec:** `docs/superpowers/specs/2026-08-27-tune-gates-app-decoupling-design.md`（本 plan 从它推出，执行者两份都读）。

**本 plan 中所有项目内路径均相对 repo root。**

## Global Constraints

- **数据只读**：`datasets/pkls/` 只读；**绝不写主目录**（当前 worktree 之外的 `/home/yu/PycharmProjects/Trade_Strategy/`）。
- **不改 `path2/dag/`、不改 `multivar_core.py`、不改 `region_core.py`**。推导所需函数全部已存在：`classify` / `loosest_level` / `col_of` / `node_col` / `apply_overrides` / `detection_combos` / `check_predicate_axes` / `compile_plan` / `detector_topo_order` / `mod.eval_meta()`。
- **入口脚本无 argparse**：全部参数是 `main()` 顶部的大写常量。`app_setup.py` 的模式切换也是常量 `MODE`。
- **四个入口脚本原件 `APP = None`**（`multivar_scan.py` / `app_setup.py`）或 `LONGTABLE_DIR = None`（`compare_longtable.py` / `region_find.py`），未填直接 `SystemExit`；用法是复制到研究目录再填。
- **通用区零 app 专名**：`SKILL.md`、`reference.md`、`multivar_scan.py`、`compare_longtable.py`、`region_find.py`、`app_setup.py`、`study_io.py`、`bench_workers.py`、`apps/_template/study.py` 里不得出现 `bb_v1`、`"burst"`、`"tb"`、`"bo"`、`burst.`、`tb.`（注释里的「例如」也不行）。测试文件与 `fixtures/` 例外（测 `classify()` 必须有真 app）。
- **测试不读 `apps/`**：`rm`/`mv` 掉 `apps/bb_v1` 后全部测试仍绿。
- **不为旧 scan / 旧长表做兼容**（`.claude/rules/scan-file-no-backcompat.md`）。唯一例外：为既有长表 `docs/research/2026-08-25_multivar-bb_v1/longtable/` **本地**补写一份 `run_meta.json`（该目录已 gitignore，不入库），只为本 plan 的迁移等价 gate。
- **不重新校准判据阈值**（功效线 100 / `REL_TOL 0.05`），仍标「仅 bb_v1 校准过」。
- **不动 `docs/research/2026-08-25_multivar-bb_v1/`** 的既有文件（含 `repro/` 三份 `region_find` 副本），唯一例外是 `repro/bench_workers.py` 搬走后删除。
- **每个新断言至少做一次突变测试**（拿掉被测修复必须红），在 task 的 step 里写明。
- commit message 中文、前缀 `feat/fix/test/perf/docs/chore`；结尾附
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XiES9oyMj2Wx7KmJvTczcr
  ```
- **完成后 push 分支 `worktree-tune-tools`，不开 PR**。
- **临时文件一律放本会话 scratchpad**（系统提示给出的目录），下文 `$SP` 指其下一个子目录：先 `SP=<scratchpad>/<taskN> && mkdir -p $SP`。不用 `/tmp`。
- 跑测试统一：`uv run pytest .claude/skills/tune-gates/ -q`（skill 测试不进默认收集，必须显式路径）。基线：本 plan 开始前 50 passed。
- 调工具纪律：中途消息正文至多一句状态行（无代码 token、不预告"我去调用 X"），随后直接发调用；长篇解释只放不再调工具的收尾消息。若发现自己把调用写成了正文文字，不要停笔，在同一条消息里立即发出真正的调用。

---

## 文件结构（完成态）

```
.claude/skills/tune-gates/
├── SKILL.md                      通用指令（Task 10 重写）
├── reference.md                  通用操作卡（Task 10 重写）
├── multivar_core.py              库核，不动
├── region_core.py                库核，不动
├── study_io.py                   ★新增（Task 2/3/4）：study 加载 / classification 生成读取 / 指纹 / 推导 / run_meta
├── app_setup.py                  ★新增（Task 5）：MODE=build|check
├── multivar_scan.py              Task 6 改造
├── compare_longtable.py          Task 7 改造
├── region_find.py                Task 8 改造
├── bench_workers.py              Task 1 从研究目录搬入 + Task 9 适配
├── plateau.py                    不动
├── fixtures/
│   ├── bb_v1_p2_wide.json        Task 1：现 ref_params.json 原样搬入（测试专用）
│   └── study_bb_v1.py            Task 2：冻结的 study 声明副本（测试专用，与 apps/bb_v1/study.py 内容相同但独立存在）
├── test_multivar_core.py         Task 1 改 BASE 路径
├── test_multivar_equiv.py        Task 1 改 BASE 路径
├── test_region_core.py           不动
├── test_plateau.py               不动
├── test_study_io.py              ★新增（Task 2/3/4/6）
└── apps/
    ├── _template/study.py        Task 2
    └── bb_v1/
        ├── study.py              Task 2
        ├── classification.json   Task 5 生成并提交
        └── notes.md              Task 10
```

**责任边界**：`study_io.py` 是唯一知道文件约定（`apps/<app>/study.py`、`classification.json`、`run_meta.json` 的路径与 schema）的模块；四个入口脚本只调它，不自己拼路径、不自己算指纹。`study_io.py` 永远在 skill 目录内、不被复制（入口脚本被复制到研究目录后经 `sys.path` 找到它）。

---

## 契约（各 task 共用，先读）

### `study.py` 必须导出的 8 个名字

```python
APP_MODULE: str                  # 如 "path2_apps.<app>.dag_spec"
BASE_YAML: str                   # 相对 app 包目录的 yaml 文件名；底座 = 搜索空间之外的一切
WIDE_OVERRIDES: dict             # {section: {field: value}}，宽进覆盖
SCAN_GRID: dict                  # {(section, field): [levels]}，D/F 维档位（tuple 键，与 multivar_core.Dim 一致）
WHERE_LEVELS: dict               # {(section, field): [levels]}，W 维档位
REF_POINT: dict                  # {"section.field": value}，点号键；必须恰好覆盖全部 D 维
TIGHT_WHERES: dict               # {name: {(section, field): value}}，对拍用收紧套；键 ⊆ SCAN_GRID ∪ WHERE_LEVELS
FLAG_RULES: list                 # [callable(cell_dict_with_dotted_keys) -> str | None]
```

### `classification.json` schema（点号键；`app_setup` 生成，人不改）

```json
{
  "app": "<app>", "app_module": "...", "base_yaml": "...",
  "kinds": {"sec.field": "D"|"F"|"W"|"E", ...},
  "detector_nodes": {"sec.field": ["node_id", ...], ...},
  "filter_fields": {"sec.field": ["node_id", "field", "op"], ...},
  "where_fields":  {"sec.field": ["node_id", "field", "op"], ...},
  "scan_grid":    {"sec.field": [levels], ...},
  "where_levels": {"sec.field": [levels], ...},
  "wide_overrides": {section: {field: value}},
  "ref_point": {"sec.field": value},
  "end_node": "node_id",
  "bound_nodes": ["node_id", ...],          # 已排序
  "detection_combos": 1024,
  "ref_params": {section: {field: value}},  # BASE_YAML ⊕ WIDE_OVERRIDES 展开后的完整快照
  "fingerprints": {
    "source": {"hash": "<sha256>", "files": ["path2_apps/<app>/dag_spec.py", "..."]},
    "base": "<sha256 of canonical-json(ref_params)>",
    "study": "<sha256 of study.py bytes>"
  },
  "generated_at": "<ISO>", "git_head": "<short sha>"
}
```

`fingerprints.base` 对**展开后快照**（已套 WIDE）算——与 spec §3.2 「对 yaml 解析结构算」相比是收窄：被宽进覆盖的键改动对长表零影响，本就不该报「已变更」；快照指纹与逐条 diff 由此严格一致。

### `run_meta.json` schema（`multivar_scan` 写在 `longtable/` 内；`compare` / `region` 读）

```json
{"app": "<app>", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "head_buffer": 250,
 "label_horizon": 40, "first_passage_k": 5.0, "price_min": 0.5, "price_max": 30.0, "volume_min": 10000.0,
 "study_fingerprint": "<sha256>", "git_head": "<short sha>", "written_at": "<ISO>"}
```

### `study_io.py` 公开函数（签名固定，各 task 按此实现/调用）

```python
SKILL_DIR: Path            # Path(__file__).resolve().parent
APPS_DIR: Path             # SKILL_DIR / "apps"
REPO: Path                 # git rev-parse --show-toplevel

def require(value, name: str) -> None                       # value is None → SystemExit(f"{name} 未填:复制到研究目录后在 main() 顶部填")
def dotted(dim: tuple) -> str                               # == multivar_core.col_of
def undotted(s: str) -> tuple                               # "a.b" → ("a","b")
def load_study(path: Path)                                  # 从文件路径加载 study 模块;缺任一必需名 → ValueError
def import_app(study)                                       # importlib.import_module(study.APP_MODULE)
def app_dir(mod) -> Path                                    # Path(mod.__file__).parent
def base_snapshot(mod, study) -> dict                       # apply_overrides(mod.Params.from_yaml(app_dir/BASE_YAML).to_dict(), study.WIDE_OVERRIDES, {})
def file_sha256(path: Path) -> str
def canonical_hash(obj) -> str                              # sha256(json.dumps(obj, sort_keys=True, default=str).encode())
def source_files(mod, spec) -> list[Path]                   # app 包目录 *.py（排序）∪ spec 各 detector 所在模块文件（排序、去重）
def source_fingerprint(files: list[Path]) -> dict           # {"hash": ..., "files": [相对 REPO 路径...]}
def build_classification(app: str, study, mod, study_path: Path) -> dict   # 跑 classify + 全部静态守卫 + 推导 + 指纹;返回 schema dict
def write_classification(app: str, data: dict, apps_dir: Path = APPS_DIR) -> Path
def load_classification(app: str, apps_dir: Path = APPS_DIR) -> dict
def snapshot_diff(old: dict, new: dict, cl: dict) -> list[tuple[str, object, object, str]]  # [(dotted_key, old, new, label)]
def check_report(app: str, study, mod, cl: dict, study_path: Path) -> str  # 三行报告文本
def derived_axes(cl: dict) -> tuple[dict, list]             # (combo_levels: {dotted: levels}(D 维,SCAN_GRID 序), preds: [(col, op, levels)](F 维 SCAN_GRID 序 + W 维 WHERE_LEVELS 序))
def pred_mask(df, assignments: dict, cl: dict) -> "pd.Series[bool]"   # assignments {Dim: value};D → ==;F/W → op-aware;value None → 不加谓词
def write_run_meta(longtable_dir: Path, meta: dict) -> None  # 已存在且任一口径字段不同 → SystemExit
def load_run_meta(longtable_dir: Path) -> dict               # 不存在 → SystemExit
def check_study_matches(cl: dict, study_path: Path) -> None  # cl["fingerprints"]["study"] != file_sha256(study_path) → SystemExit
def check_run_matches_classification(meta: dict, cl: dict) -> None  # meta["study_fingerprint"] != cl["fingerprints"]["study"] → SystemExit
```

### 与既有代码的对应关系（迁移时逐项对照）

| 旧位置 | 旧内容 | 新来源 |
|---|---|---|
| `multivar_scan.py:67` `PATTERN_ID` | `"bb_v1"` | `APP` 常量 |
| `multivar_scan.py:80-82` `REF_PARAMS`/`WIDE_OVERRIDES` | 路径 + dict | `base_snapshot()` / `study.WIDE_OVERRIDES` |
| `multivar_scan.py:87-97` `SCAN_GRID`/`WHERE_LEVELS` | dict 字面量 | `study.SCAN_GRID` / `study.WHERE_LEVELS` |
| `compare_longtable.py:125-131,149-160` `APP_MODULE`…`WHERES` | 全部字面量 | `study.*` + `cl` + `run_meta` |
| `compare_longtable.py:155-156` `MDD_DIM`/`MDD_FIELD` | 特判 | 删除；`pred_mask` 按 `kinds` 分派 |
| `compare_longtable.py:143` `END_NODE`/`KEY_NODES` | `"tb"`, `("burst","tb")` | `cl["end_node"]` / `cl["bound_nodes"]` |
| `compare_longtable.py:178` `ref_bo` + `dims[2:]` | 固定前两维 | 固定「`detector_nodes[d] == (拓扑首节点,)` 的维」于 `REF_POINT` |
| `region_find.py:43-48` `COMBO_LEVELS`/`FILTER_PREDS`/`WHERE_PREDS` | 手抄 | `derived_axes(cl)` |
| `region_find.py:51-52,55` `REF_POINT`/`FLAG_RULES` | 字面量 | `study.REF_POINT` / `study.FLAG_RULES` |
| `region_find.py:33-36,59` `_check_head_buffer` | 正则读 ledger | 删除；`load_run_meta()["head_buffer"]` |

---

### Task 1: 自包含第一步——fixtures 与 bench_workers 搬家

**Files:**
- Create: `.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json`（复制自 `docs/research/2026-08-25_multivar-bb_v1/ref_params.json`，字节相同）
- Move: `docs/research/2026-08-25_multivar-bb_v1/repro/bench_workers.py` → `.claude/skills/tune-gates/bench_workers.py`
- Modify: `.claude/skills/tune-gates/test_multivar_core.py:19`、`.claude/skills/tune-gates/test_multivar_equiv.py:38`
- Modify: `.claude/skills/tune-gates/reference.md:54`（`repro/bench_workers.py` → `bench_workers.py`；本 task 只改这一处指针，全文重写在 Task 10）

**Interfaces:**
- Produces: `fixtures/bb_v1_p2_wide.json`——后续所有测试的 `BASE`。

- [ ] **Step 1: 复制夹具并核字节相同**

```bash
mkdir -p .claude/skills/tune-gates/fixtures
cp docs/research/2026-08-25_multivar-bb_v1/ref_params.json .claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json
cmp docs/research/2026-08-25_multivar-bb_v1/ref_params.json .claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json && echo SAME
```
Expected: 打印 `SAME`。

- [ ] **Step 2: 两个测试改读夹具**

`test_multivar_core.py:19` 与 `test_multivar_equiv.py:38` 的
```python
BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
```
都改为
```python
BASE = json.loads((Path(__file__).parent / "fixtures/bb_v1_p2_wide.json").read_text())
```
（两文件顶部已 `from pathlib import Path`。）

- [ ] **Step 3: 跑测试确认仍绿**

Run: `uv run pytest .claude/skills/tune-gates/test_multivar_core.py .claude/skills/tune-gates/test_region_core.py -q`
Expected: 全部 passed（与改前相同数目）。

- [ ] **Step 4: 搬 bench_workers.py**

```bash
git mv docs/research/2026-08-25_multivar-bb_v1/repro/bench_workers.py .claude/skills/tune-gates/bench_workers.py
```
把 `reference.md:54` 里的 `` `repro/bench_workers.py` `` 改成 `` `bench_workers.py`（skill 目录） ``。

- [ ] **Step 5: 确认 skill 目录不再读 docs/research（除三个工具的 OUT_DIR/LONGTABLE_DIR 默认值，那是 Task 6-8 的事）**

Run: `grep -n "docs/research" .claude/skills/tune-gates/test_*.py`
Expected: 只剩 `test_region_core.py:316` 一处注释（不是读取）。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json .claude/skills/tune-gates/test_multivar_core.py .claude/skills/tune-gates/test_multivar_equiv.py .claude/skills/tune-gates/bench_workers.py .claude/skills/tune-gates/reference.md docs/research/2026-08-25_multivar-bb_v1/repro/bench_workers.py
git commit -m "chore(tune-gates): 测试夹具与 bench_workers 搬进 skill 目录,不再读 docs/research"
```

---

### Task 2: `study.py` 声明文件（模板 + bb_v1 + 测试夹具）与 `study_io.load_study`

**Files:**
- Create: `.claude/skills/tune-gates/apps/_template/study.py`
- Create: `.claude/skills/tune-gates/apps/bb_v1/study.py`
- Create: `.claude/skills/tune-gates/fixtures/study_bb_v1.py`（与 `apps/bb_v1/study.py` 内容逐字相同；测试只读这份）
- Create: `.claude/skills/tune-gates/study_io.py`（本 task 只写 `REPO`/`SKILL_DIR`/`APPS_DIR`/`require`/`dotted`/`undotted`/`load_study`/`import_app`/`app_dir`/`base_snapshot`）
- Test: `.claude/skills/tune-gates/test_study_io.py`

**Interfaces:**
- Produces: 上面「契约」节的 `study.py` 8 名字；`study_io.load_study(path)` 等 9 个函数。

- [ ] **Step 1: 写模板 `apps/_template/study.py`**

```python
# -*- coding: utf-8 -*-
"""tune-gates · study 声明模板。复制为 apps/<app>/study.py 后填全部 8 项。

本文件是换 app 时**唯一**要写的东西;分类(W/F/D/E)、长表列名、谓词轴、end_node、bound 节点
等一切能从 spec 推出来的内容都不在这里——由 app_setup.py 生成 classification.json。
只放「推不出来」的:底座在哪、搜什么档、参照点在哪、哪些格子机制上恒真。

键写法:SCAN_GRID / WHERE_LEVELS / TIGHT_WHERES 用 (section, field) 元组键(与 Params 的
yaml section 对齐);REF_POINT 与 FLAG_RULES 里的 cell 用 "section.field" 点号键。
"""

APP_MODULE = "path2_apps.<app>.dag_spec"       # 提供 Params / build_pattern / eval_meta 的模块
BASE_YAML = "params.yaml"                      # 相对 app 包目录;底座 = 搜索空间之外的一切参数取值

# 宽进覆盖:把 where 类参数放到机制下限、把过滤型闸关掉,让完整取值空间进池
WIDE_OVERRIDES = {
    # "<section>": {"<where_field>": <机制下限>, "<gate_field>": None},
}

# D/F 维档位(真扫维与过滤型维;F 维由探针判定、不进检测笛卡尔积)。4 档左右;先查列分布再定档
SCAN_GRID = {
    # ("<section>", "<param>"): [v1, v2, v3, v4],
}

# W 维档位(纯 where 阈值)。放 F 维会被 classify() 拒绝——分类以探针为准,不凭参数名猜
WHERE_LEVELS = {
    # ("<section>", "<where_param>"): [v_loose, v_mid, v_tight],
}

# 参照格:必须恰好覆盖全部 D 维(app_setup 校验);通常取生产参数在网格上的落点
REF_POINT = {
    # "<section>.<param>": <生产值>,
}

# 对拍用的收紧 where 套:app 的候选生产点;键 ⊆ SCAN_GRID ∪ WHERE_LEVELS,可含 F 维
TIGHT_WHERES = {
    # "<name>": {("<section>", "<where_param>"): <收紧值>, ...},
}

# 格级机制标记:cell(点号键 dict)→ 标记文本或 None。用于 cells.csv 的 flags 列
FLAG_RULES = [
    # lambda c: "<说明>" if c["<a>"] >= c["<b>"] > 0 else None,
]
```

- [ ] **Step 2: 写 `apps/bb_v1/study.py`（值全部来自现 `multivar_scan.py:81-97`、`region_find.py:51-55`、`compare_longtable.py:159-160`）**

```python
# -*- coding: utf-8 -*-
"""bb_v1 · tune-gates study 声明(2026-08-25 多维稳健区实战的网格;底座 = p2.yaml)。"""

APP_MODULE = "path2_apps.bb_v1.dag_spec"
BASE_YAML = "p2.yaml"          # 不是 params.yaml(web SSoT):实战选的是 tune 分支版本,二者在 tb.max_window/scb_mode/judged_measure/stop_confirm_bars 上不同

WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                  "tb": {"max_day_drop_pct": None}}

SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3],
             ("bo", "exceed_threshold"):    [0.001, 0.003, 0.01, 0.03],
             ("burst", "gap_max"):          [4, 8, 12, 20],
             ("burst", "min_bos"):          [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"):   [0, 1, 2, 3],
             ("tb", "big_rise_k"):          [3.0, 5.0, 8.0, 12.0],
             ("tb", "max_day_drop_pct"):    [None, 0.2]}

WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40],
                ("burst", "distinct_pk_min"):   [1, 3, 4],
                ("burst", "vol_spike_min"):     [0, 10, 15],
                ("burst", "peak_age_min"):      [0, 125]}

REF_POINT = {"bo.min_relative_height": 0.2, "bo.exceed_threshold": 0.003, "burst.gap_max": 8,
             "tb.stop_confirm_bars": 2, "tb.big_rise_k": 5.0}

TIGHT_WHERES = {"FINAL": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 4, ("burst", "vol_spike_min"): 15,
                          ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2},
                "B":     {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3, ("burst", "vol_spike_min"): 10,
                          ("burst", "peak_age_min"): 0, ("tb", "max_day_drop_pct"): 0.2}}

FLAG_RULES = [lambda c: "first_drought 闸恒真" if c["burst.gap_max"] >= c["burst.first_drought"] > 0 else None]
```

```bash
cp .claude/skills/tune-gates/apps/bb_v1/study.py .claude/skills/tune-gates/fixtures/study_bb_v1.py
```

- [ ] **Step 3: 写失败测试**

`test_study_io.py`：
```python
# -*- coding: utf-8 -*-
"""study_io 单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_study_io.py -q
测试只读 fixtures/,不读 apps/——删掉 apps/<app> 后本文件必须仍绿。
"""
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
import sys; sys.path.insert(0, str(HERE))  # noqa: E702
import subprocess  # noqa: E402
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

import study_io as S  # noqa: E402

FIX = HERE / "fixtures"
STUDY = FIX / "study_bb_v1.py"
BASE = json.loads((FIX / "bb_v1_p2_wide.json").read_text())


def test_load_study_exports_all_eight():
    st = S.load_study(STUDY)
    for name in ("APP_MODULE", "BASE_YAML", "WIDE_OVERRIDES", "SCAN_GRID", "WHERE_LEVELS", "REF_POINT", "TIGHT_WHERES", "FLAG_RULES"):
        assert hasattr(st, name), name


def test_load_study_missing_name_raises(tmp_path):
    p = tmp_path / "study.py"
    p.write_text(STUDY.read_text().replace("FLAG_RULES = [", "FLAG_RULES_X = ["))
    with pytest.raises(ValueError, match="FLAG_RULES"):
        S.load_study(p)


def test_dotted_roundtrip():
    assert S.dotted(("a", "b")) == "a.b" and S.undotted("a.b") == ("a", "b")


def test_require_none_exits():
    with pytest.raises(SystemExit, match="APP 未填"):
        S.require(None, "APP")
    S.require("x", "APP")


def test_base_snapshot_equals_frozen_fixture():
    """迁移正确性的直接证据:p2.yaml ⊕ WIDE_OVERRIDES 必须与实战用的 ref_params 快照逐字相等。"""
    st = S.load_study(STUDY); mod = S.import_app(st)
    assert S.base_snapshot(mod, st) == BASE
```

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'study_io'`。

- [ ] **Step 4: 写 `study_io.py` 第一部分**

```python
# -*- coding: utf-8 -*-
"""tune-gates · study / classification / run_meta 的文件约定与推导 helper。

本模块是唯一知道下列路径与 schema 的地方,四个入口脚本只调它:
  apps/<app>/study.py             人写的 8 项声明(换 app 唯一要改的地方)
  apps/<app>/classification.json  app_setup 生成:分类 + 推导字段 + 双指纹(人不改)
  <longtable_dir>/run_meta.json   multivar_scan 写:run 级口径单源(compare/region 读)
本文件永远在 skill 目录内、不被复制;入口脚本复制到研究目录后经 sys.path 找到它。
不含算法——classify/推导用的全是 multivar_core 的既有函数。
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
SKILL_DIR = Path(__file__).resolve().parent
APPS_DIR = SKILL_DIR / "apps"
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(SKILL_DIR))

from multivar_core import apply_overrides, col_of  # noqa: E402

STUDY_NAMES = ("APP_MODULE", "BASE_YAML", "WIDE_OVERRIDES", "SCAN_GRID", "WHERE_LEVELS",
               "REF_POINT", "TIGHT_WHERES", "FLAG_RULES")


def require(value, name: str) -> None:
    """入口脚本原件的硬闸:常量未填直接退出,既防误跑原件也让通用区零 app 专名。"""
    if value is None:
        raise SystemExit(f"{name} 未填:复制到研究目录后在 main() 顶部填")


def dotted(dim: tuple) -> str:
    return col_of(dim)


def undotted(s: str) -> tuple:
    sec, field = s.split(".", 1)
    return (sec, field)


def load_study(path: Path):
    """从文件路径加载 study 模块(不经 sys.path,避免多个 app 的 study.py 同名互相遮蔽)。"""
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"tune_gates_study_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    missing = [n for n in STUDY_NAMES if not hasattr(mod, n)]
    if missing:
        raise ValueError(f"{path} 缺少声明: {missing}")
    return mod


def import_app(study):
    return importlib.import_module(study.APP_MODULE)


def app_dir(mod) -> Path:
    return Path(mod.__file__).resolve().parent


def base_snapshot(mod, study) -> dict:
    """底座快照 = BASE_YAML 全量参数 ⊕ WIDE_OVERRIDES。这就是「搜索空间之外的一切」。"""
    base = mod.Params.from_yaml(app_dir(mod) / study.BASE_YAML).to_dict()
    return apply_overrides(base, study.WIDE_OVERRIDES, {})
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q`
Expected: 5 passed。

- [ ] **Step 6: 突变测试**

把 `base_snapshot` 里的 `study.WIDE_OVERRIDES` 临时改成 `{}` → 跑 → `test_base_snapshot_equals_frozen_fixture` 必须 FAIL；改回 → 5 passed。

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/tune-gates/apps/_template/study.py .claude/skills/tune-gates/apps/bb_v1/study.py .claude/skills/tune-gates/fixtures/study_bb_v1.py .claude/skills/tune-gates/study_io.py .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): study.py 声明文件(模板+bb_v1+测试夹具)与 study_io 加载/底座快照"
```

---

### Task 3: 分类生成与推导（`build_classification` / `derived_axes` / `pred_mask`）

**Files:**
- Modify: `.claude/skills/tune-gates/study_io.py`（追加）
- Test: `.claude/skills/tune-gates/test_study_io.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `load_study` / `import_app` / `base_snapshot`。
- Produces: `build_classification(app, study, mod, study_path) -> dict`（schema 见契约；本 task 先不填 `fingerprints`——留 `{}`，Task 4 补）、`write_classification` / `load_classification`、`derived_axes(cl)`、`pred_mask(df, assignments, cl)`。

- [ ] **Step 1: 写失败测试（追加到 `test_study_io.py`）**

```python
import pandas as pd  # noqa: E402  (文件顶部已有 import 区,放到那里)


@pytest.fixture(scope="module")
def cl():
    st = S.load_study(STUDY); mod = S.import_app(st)
    return S.build_classification("bb_v1_fixture", st, mod, STUDY)


def test_classification_matches_hand_transcribed_values(cl):
    """迁移正确性:与迁移前三个脚本里手抄的分类/字段逐项相等(旧 region_find.py:43-48、compare_longtable.py:155-156)。"""
    assert cl["kinds"] == {"bo.min_relative_height": "D", "bo.exceed_threshold": "D", "burst.gap_max": "D",
                           "burst.min_bos": "F", "tb.stop_confirm_bars": "D", "tb.big_rise_k": "D",
                           "tb.max_day_drop_pct": "F", "burst.first_drought_min": "W", "burst.distinct_pk_min": "W",
                           "burst.vol_spike_min": "W", "burst.peak_age_min": "W"}
    assert cl["filter_fields"] == {"burst.min_bos": ["burst", "count", ">="], "tb.max_day_drop_pct": ["tb", "day_drop", "<"]}
    assert cl["where_fields"] == {"burst.first_drought_min": ["burst", "first_drought", ">="],
                                  "burst.distinct_pk_min": ["burst", "distinct_pk", ">="],
                                  "burst.vol_spike_min": ["burst", "max_bar_vol_ratio", ">="],
                                  "burst.peak_age_min": ["burst", "peak_age_max", ">="]}
    assert cl["end_node"] == "tb" and cl["bound_nodes"] == ["burst", "tb"]
    assert cl["detection_combos"] == 1024
    assert cl["ref_params"] == BASE
    assert cl["detector_nodes"]["bo.min_relative_height"] == ["bo"]


def test_derived_axes_order_and_content(cl):
    combo, preds = S.derived_axes(cl)
    assert list(combo) == ["bo.min_relative_height", "bo.exceed_threshold", "burst.gap_max", "tb.stop_confirm_bars", "tb.big_rise_k"]
    assert preds == [("burst.count", ">=", [1, 2, 3, 4]), ("tb.day_drop", "<", [None, 0.2]),
                     ("burst.first_drought", ">=", [0, 20, 40]), ("burst.distinct_pk", ">=", [1, 3, 4]),
                     ("burst.max_bar_vol_ratio", ">=", [0, 10, 15]), ("burst.peak_age_max", ">=", [0, 125])]


def test_pred_mask_is_op_aware(cl):
    df = pd.DataFrame({"burst.gap_max": [8, 8, 12], "burst.count": [1, 3, 3], "tb.day_drop": [0.1, 0.3, 0.1],
                       "burst.first_drought": [0, 25, 25]})
    m = S.pred_mask(df, {("burst", "gap_max"): 8, ("burst", "min_bos"): 2, ("tb", "max_day_drop_pct"): 0.2,
                         ("burst", "first_drought_min"): 20}, cl)
    assert m.tolist() == [False, False, False]      # 行1 count<2;行2 day_drop>=0.2;行3 gap_max!=8
    m2 = S.pred_mask(df, {("burst", "gap_max"): 8, ("tb", "max_day_drop_pct"): None}, cl)
    assert m2.tolist() == [True, True, False]       # None → 不加谓词


def test_ref_point_must_cover_exactly_D_dims(tmp_path):
    st = S.load_study(STUDY); mod = S.import_app(st)
    bad = tmp_path / "study.py"
    bad.write_text(STUDY.read_text().replace('"tb.big_rise_k": 5.0', '"tb.big_rise_k_x": 5.0'))
    with pytest.raises(ValueError, match="REF_POINT"):
        S.build_classification("x", S.load_study(bad), mod, bad)


def test_write_and_load_classification(cl, tmp_path):
    p = S.write_classification("appx", cl, apps_dir=tmp_path)
    assert p == tmp_path / "appx" / "classification.json"
    assert S.load_classification("appx", apps_dir=tmp_path) == cl
```

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q`
Expected: 新增 5 个 FAIL（`AttributeError: build_classification`）。

- [ ] **Step 2: 实现（追加到 `study_io.py`）**

```python
from multivar_core import (check_predicate_axes, classify, detection_combos, loosest_level, node_col)  # noqa: E402
from path2.dag._solve import compile_plan  # noqa: E402


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, cwd=REPO).strip()


def build_classification(app: str, study, mod, study_path: Path) -> dict:
    """跑 classify + 全部静态守卫 + 推导,返回 classification.json 的 dict(fingerprints 由 Task 4 填)。

    守卫在这里响亮失败,不等到扫描:REF_POINT 恰好覆盖 D 维 / TIGHT_WHERES 键在网格内 /
    共享 detector 实例 / negation dst 谓词轴。"""
    base = base_snapshot(mod, study)
    cls = classify(mod, base, study.SCAN_GRID, study.WHERE_LEVELS)
    d_dims = {dotted(d) for d in study.SCAN_GRID if cls.kinds[d] == "D"}
    if set(study.REF_POINT) != d_dims:
        raise ValueError(f"REF_POINT 必须恰好覆盖全部 D 维: 期望 {sorted(d_dims)},实际 {sorted(study.REF_POINT)}")
    grid_dims = set(study.SCAN_GRID) | set(study.WHERE_LEVELS)
    for name, w in study.TIGHT_WHERES.items():
        extra = set(w) - grid_dims
        if extra:
            raise ValueError(f"TIGHT_WHERES[{name!r}] 含网格外的维 {sorted(extra)}")
    # 与 scan_one_stock 同一套 override 造 spec0(F 维最松档),守卫与列集才与生产同源
    filter_min = {d: loosest_level(study.SCAN_GRID[d], cls.filter_fields[d][2])
                  for d in study.SCAN_GRID if cls.kinds[d] == "F"}
    spec0 = mod.build_pattern(mod.Params.from_dict(apply_overrides(base, {}, filter_min), strict=True))
    det_nodes = [n for n in spec0.nodes if n.detector is not None]
    if len({id(n.detector) for n in det_nodes}) != len(det_nodes):
        raise ValueError("多 node 共享 detector 实例:反转循环不支持,请拆成独立实例")
    check_predicate_axes(spec0, {**cls.where_fields, **cls.filter_fields})
    p0 = mod.Params.from_dict(base, strict=True)
    end_node = mod.eval_meta(params=p0)["end_node"]
    bound = sorted({nid for w in compile_plan(spec0).wcc_plans for nid in w.comp})
    return {
        "app": app, "app_module": study.APP_MODULE, "base_yaml": study.BASE_YAML,
        "kinds": {dotted(d): k for d, k in cls.kinds.items()},
        "detector_nodes": {dotted(d): list(v) for d, v in cls.detector_nodes.items()},
        "filter_fields": {dotted(d): list(v) for d, v in cls.filter_fields.items()},
        "where_fields": {dotted(d): list(v) for d, v in cls.where_fields.items()},
        "scan_grid": {dotted(d): list(v) for d, v in study.SCAN_GRID.items()},
        "where_levels": {dotted(d): list(v) for d, v in study.WHERE_LEVELS.items()},
        "wide_overrides": study.WIDE_OVERRIDES, "ref_point": dict(study.REF_POINT),
        "end_node": end_node, "bound_nodes": bound,
        "detection_combos": len(detection_combos(study.SCAN_GRID, cls)),
        "ref_params": base, "fingerprints": {},
        "generated_at": datetime.now().isoformat(timespec="seconds"), "git_head": _git_head(),
    }


def write_classification(app: str, data: dict, apps_dir: Path = APPS_DIR) -> Path:
    p = Path(apps_dir) / app / "classification.json"; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n")
    return p


def load_classification(app: str, apps_dir: Path = APPS_DIR) -> dict:
    p = Path(apps_dir) / app / "classification.json"
    if not p.exists():
        raise SystemExit(f"{p} 不存在:先跑 app_setup(MODE='build')")
    return json.loads(p.read_text())


def derived_axes(cl: dict) -> tuple:
    """region 侧的轴:combo_levels = D 维(SCAN_GRID 序);preds = F 维(SCAN_GRID 序)+ W 维(WHERE_LEVELS 序)。"""
    combo = {d: lv for d, lv in cl["scan_grid"].items() if cl["kinds"][d] == "D"}
    preds = [(node_col(*cl["filter_fields"][d][:2]), cl["filter_fields"][d][2], lv)
             for d, lv in cl["scan_grid"].items() if cl["kinds"][d] == "F"]
    preds += [(node_col(*cl["where_fields"][d][:2]), cl["where_fields"][d][2], lv)
              for d, lv in cl["where_levels"].items()]
    return combo, preds


def _cmp(x, v, op: str):
    return (x >= v) if op == ">=" else (x < v) if op == "<" else (x > v) if op == ">" else (x <= v)


def pred_mask(df: pd.DataFrame, assignments: dict, cl: dict) -> pd.Series:
    """长表行掩码:D 维按列等值;F/W 维按 classification 的字段与 op;value None = 不加谓词。
    与 test_multivar_equiv._pred / _rows_keys 同语义(向量化)。"""
    m = pd.Series(True, index=df.index)
    for dim, v in assignments.items():
        key = dotted(dim); kind = cl["kinds"][key]
        if kind == "D":
            m &= df[key] == v
        else:
            if v is None:
                continue
            n, f, op = (cl["filter_fields"] if kind == "F" else cl["where_fields"])[key]
            m &= _cmp(df[node_col(n, f)], v, op)
    return m
```

- [ ] **Step 3: 跑测试**

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q`
Expected: 10 passed。

- [ ] **Step 4: 突变测试**

（a）`derived_axes` 里把 W 维那段的 `cl["where_levels"]` 改成 `cl["scan_grid"]` → `test_derived_axes_order_and_content` FAIL；改回。（b）`pred_mask` 里 `_cmp` 的 `"<"` 分支改成 `<=` → `test_pred_mask_is_op_aware` 第一断言仍 `[False,False,False]`？——`day_drop 0.3 <= 0.2` 仍 False，不敏感；改用把 `if v is None: continue` 删掉 → 第二断言 FAIL（`None` 参与比较抛 TypeError）；改回。两次都记进 commit message。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/study_io.py .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): study_io 分类生成(含全部静态守卫)+ 轴推导 + op-aware 谓词掩码"
```

---

### Task 4: 双指纹与 check 报告

**Files:**
- Modify: `.claude/skills/tune-gates/study_io.py`（追加 + 让 `build_classification` 填 `fingerprints`）
- Test: `.claude/skills/tune-gates/test_study_io.py`（追加）

**Interfaces:**
- Produces: `file_sha256` / `canonical_hash` / `source_files(mod, spec)` / `source_fingerprint(files)` / `snapshot_diff(old, new, cl)` / `check_report(app, study, mod, cl, study_path)` / `check_study_matches(cl, study_path)`。
- `build_classification` 返回值的 `fingerprints` 从此非空。

- [ ] **Step 1: 写失败测试（追加）**

```python
def test_fingerprints_present_and_source_lists_app_and_detector_files(cl):
    fp = cl["fingerprints"]
    assert set(fp) == {"source", "base", "study"} and len(fp["source"]["hash"]) == 64
    files = fp["source"]["files"]
    assert any(f.endswith("path2_apps/bb_v1/dag_spec.py") for f in files)
    assert any(f.endswith("path2/atoms/throwback_v1.py") for f in files)
    assert files == sorted(files)


def test_base_fingerprint_ignores_yaml_comments(tmp_path):
    """指纹算的是展开后快照,不是文件字节:改注释/空白/顺序不报变更。"""
    st = S.load_study(STUDY); mod = S.import_app(st)
    y = S.app_dir(mod) / st.BASE_YAML
    alt = tmp_path / st.BASE_YAML; alt.write_text("# 只加一行注释\n" + y.read_text())
    class St2:  # 同 study 但 BASE_YAML 指向 tmp 副本
        pass
    for n in S.STUDY_NAMES: setattr(St2, n, getattr(st, n))
    orig_app_dir = S.app_dir
    S.app_dir = lambda m: tmp_path            # 只为本测试临时改向
    try:
        snap2 = S.base_snapshot(mod, St2)
    finally:
        S.app_dir = orig_app_dir
    assert S.canonical_hash(snap2) == S.canonical_hash(S.base_snapshot(mod, st))


def test_snapshot_diff_labels(cl):
    old = cl["ref_params"]
    import copy; new = copy.deepcopy(old)
    new["tb"]["max_window"] = 15              # 底座常量
    new["burst"]["gap_max"] = 10              # D 维
    new["tb"]["brand_new"] = 3                # 新增
    del new["bo"]["total_window"]             # 删除
    d = {k: (o, n, lab) for k, o, n, lab in S.snapshot_diff(old, new, cl)}
    assert d["tb.max_window"] == (20, 15, "底座常量 · 全部检测组合受影响 · 长表过期")
    assert d["burst.gap_max"] == (8, 10, "D 维 · 网格档位覆盖 · 仅参照格坐标需核对")
    assert d["tb.brand_new"] == (None, 3, "新增 · 未进网格 · 将以新值作底座常量")
    assert d["bo.total_window"] == (20, None, "删除 · build 时 Params.from_dict(strict) 会失败")
    assert set(d) == {"tb.max_window", "burst.gap_max", "tb.brand_new", "bo.total_window"}


def test_check_report_all_consistent_and_study_changed(cl, tmp_path):
    st = S.load_study(STUDY); mod = S.import_app(st)
    rep = S.check_report("bb_v1_fixture", st, mod, cl, STUDY)
    assert rep.splitlines()[0].startswith("source:    一致") and "base:      一致" in rep and "study:     一致" in rep
    alt = tmp_path / "study.py"; alt.write_text(STUDY.read_text() + "\n# touched\n")
    rep2 = S.check_report("bb_v1_fixture", S.load_study(alt), mod, cl, alt)
    assert "study:     已变更" in rep2
    with pytest.raises(SystemExit, match="study.py 已改"):
        S.check_study_matches(cl, alt)
    S.check_study_matches(cl, STUDY)
```

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q`
Expected: 4 个新 FAIL。

- [ ] **Step 2: 实现（追加；并在 `build_classification` 的 return 前计算指纹）**

```python
def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def source_files(mod, spec) -> list:
    """源码指纹范围:app 包目录全部 .py ∪ spec 各 detector 所在模块文件。引擎(path2/dag)不进指纹。"""
    files = set(app_dir(mod).glob("*.py"))
    for n in spec.nodes:
        if n.detector is not None:
            files.add(Path(sys.modules[type(n.detector).__module__].__file__).resolve())
    return sorted(files)


def source_fingerprint(files: list) -> dict:
    h = hashlib.sha256()
    rel = []
    for f in sorted(files, key=lambda p: str(Path(p).resolve().relative_to(REPO))):
        r = str(Path(f).resolve().relative_to(REPO)); rel.append(r)
        h.update(r.encode() + b"\0" + Path(f).read_bytes() + b"\0")
    return {"hash": h.hexdigest(), "files": rel}
```

在 `build_classification` 里,`return {` 之前加:
```python
    fps = {"source": source_fingerprint(source_files(mod, spec0)),
           "base": canonical_hash(base), "study": file_sha256(study_path)}
```
并把 return dict 里的 `"fingerprints": {}` 改为 `"fingerprints": fps`。

```python
def _flat(d: dict) -> dict:
    return {f"{sec}.{k}": v for sec, kv in d.items() for k, v in kv.items()}


def snapshot_diff(old: dict, new: dict, cl: dict) -> list:
    """逐条 diff 两份底座快照,每条打「后果标签」:在网格内的只影响参照格坐标;不在网格内的是
    全部检测组合共用的底座常量,变了整张长表过期。"""
    fo, fn = _flat(old), _flat(new)
    grid = {**cl["scan_grid"], **cl["where_levels"]}
    out = []
    for k in sorted(set(fo) | set(fn)):
        o, n = fo.get(k), fn.get(k)
        if k in fo and k in fn and o == n:
            continue
        if k not in fo:
            lab = "新增 · 未进网格 · 将以新值作底座常量"
        elif k not in fn:
            lab = "删除 · build 时 Params.from_dict(strict) 会失败"
        elif k in grid:
            lab = f"{cl['kinds'][k]} 维 · 网格档位覆盖 · 仅参照格坐标需核对"
        else:
            lab = "底座常量 · 全部检测组合受影响 · 长表过期"
        out.append((k, o, n, lab))
    return out


def check_report(app: str, study, mod, cl: dict, study_path: Path) -> str:
    """MODE=check 的三行报告(指纹只是证据,重生成与否由用户裁定——协议见 SKILL.md「入口协议」)。"""
    base_now = base_snapshot(mod, study)
    spec0 = mod.build_pattern(mod.Params.from_dict(base_now, strict=True))
    src_now = source_fingerprint(source_files(mod, spec0))
    old_src = cl["fingerprints"]["source"]
    if src_now["hash"] == old_src["hash"]:
        l1 = "source:    一致"
    else:
        # classification 只存聚合哈希(不为逐文件 diff 再存一份 per-file 哈希),故列「范围内全部文件」供人配合 git diff 看
        l1 = "source:    已变更 · 范围内文件: [" + ", ".join(src_now["files"]) + "]"
    diffs = snapshot_diff(cl["ref_params"], base_now, cl)
    if not diffs:
        l2 = "base:      一致"
    else:
        l2 = f"base:      已变更({len(diffs)} 项)\n" + "\n".join(
            f"             {k:24s} {o!s:>8} → {n!s:<8} [{lab}]" for k, o, n, lab in diffs)
    l3 = "study:     一致" if file_sha256(study_path) == cl["fingerprints"]["study"] else "study:     已变更"
    l4 = f"上次生成:  {cl['generated_at']} @ {cl['git_head']}"
    return "\n".join([l1, l2, l3, l4])


def check_study_matches(cl: dict, study_path: Path) -> None:
    if file_sha256(study_path) != cl["fingerprints"]["study"]:
        raise SystemExit("study.py 已改,与 classification.json 不一致:先重跑 app_setup(MODE='build')")
```

注:源码指纹只存聚合哈希,故 `source` 不一致时报告列「范围内全部文件」而非精确变更文件——spec §3.3 示例的「变更文件 [...]」在此实现为「范围内文件」,理由是不为逐文件 diff 再存一份 per-file 哈希(YAGNI;用户看范围列表 + `git diff` 即可)。

- [ ] **Step 3: 跑测试**

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q`
Expected: 14 passed。

- [ ] **Step 4: 突变测试**

`snapshot_diff` 里把 `elif k in grid:` 改成 `elif False:` → `test_snapshot_diff_labels` FAIL（`burst.gap_max` 被打成底座常量）；改回。

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/study_io.py .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): 源码/底座/study 三指纹 + 逐条带后果标签的 check 报告"
```

---

### Task 5: `app_setup.py` 入口 + 生成并提交 `apps/bb_v1/classification.json`

**Files:**
- Create: `.claude/skills/tune-gates/app_setup.py`
- Create（生成）: `.claude/skills/tune-gates/apps/bb_v1/classification.json`

**Interfaces:**
- Consumes: Task 3/4 的 `build_classification` / `write_classification` / `load_classification` / `check_report`。

- [ ] **Step 1: 写 `app_setup.py`**

```python
# -*- coding: utf-8 -*-
"""多维稳健区 v2 · app 接入端:apps/<APP>/study.py → apps/<APP>/classification.json。
用法:复制到研究目录、填 APP、选 MODE 后 `uv run python <路径>/app_setup.py`(无 argparse)。

MODE="build":跑 classify + 全部静态守卫 + 推导 + 三指纹 → 写 classification.json,打印分类表。幂等。
MODE="check":只算指纹不写文件,打印三行报告(source / base / study 各一行)+ 上次生成时间。
             报告是给用户看的证据;要不要重生成由用户裁定(协议见 SKILL.md「入口协议」),本脚本不替用户决定。
"""
from __future__ import annotations

import subprocess, sys
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
import study_io as S  # noqa: E402


def main() -> None:
    APP = None            # 复制到研究目录后填,如 "<app>"
    MODE = "build"        # "build" | "check"

    S.require(APP, "APP")
    study_path = S.APPS_DIR / APP / "study.py"
    if not study_path.exists():
        raise SystemExit(f"{study_path} 不存在:cp -r {S.APPS_DIR / '_template'} {S.APPS_DIR / APP} 后填 8 项声明")
    study = S.load_study(study_path); mod = S.import_app(study)
    from path2 import config
    config.set_runtime_checks(True)
    if MODE == "build":
        cl = S.build_classification(APP, study, mod, study_path)
        p = S.write_classification(APP, cl)
        print(f"写入 {p}")
        print("参数分类:"); [print(f"  {d:32s} {k}") for d, k in cl["kinds"].items()]
        print("过滤型字段:", cl["filter_fields"]); print("where 字段:", cl["where_fields"])
        print(f"end_node={cl['end_node']} bound_nodes={cl['bound_nodes']} 检测组合数={cl['detection_combos']}")
        print("源码指纹范围:", cl["fingerprints"]["source"]["files"])
    elif MODE == "check":
        print(S.check_report(APP, study, mod, S.load_classification(APP), study_path))
    else:
        raise SystemExit(f"MODE 只能是 build/check,得到 {MODE!r}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 用它生成 bb_v1 的 classification.json（复制到 scratchpad 改 APP 再跑，遵守「勿跑原件」）**

```bash
cp .claude/skills/tune-gates/app_setup.py $SP/app_setup.py
sed -i 's|^    APP = None.*|    APP = "bb_v1"|' $SP/app_setup.py
uv run python $SP/app_setup.py
```
Expected: 打印「写入 …/apps/bb_v1/classification.json」+ 分类表（D×5 / F×2 / W×4）+ `检测组合数=1024`。

- [ ] **Step 3: 验证原件硬闸与 check 模式**

```bash
uv run python .claude/skills/tune-gates/app_setup.py; echo "rc=$?"
sed -i 's|^    MODE = "build"|    MODE = "check"|' $SP/app_setup.py
uv run python $SP/app_setup.py
```
Expected: 第一条输出 `APP 未填:…` 且 `rc=1`；第二条打印三行 `一致` + 上次生成时间。

- [ ] **Step 4: Commit（classification.json 一并提交）**

```bash
git add .claude/skills/tune-gates/app_setup.py .claude/skills/tune-gates/apps/bb_v1/classification.json
git commit -m "feat(tune-gates): app_setup 入口(build/check)+ 生成并入库 bb_v1 的 classification.json"
```

---

### Task 6: `multivar_scan.py` 改造 + `run_meta.json`

**Files:**
- Modify: `.claude/skills/tune-gates/multivar_scan.py:66-125`（`main()` 头部到 `columns`）、`:269-283`（ledger 行）
- Modify: `.claude/skills/tune-gates/study_io.py`（追加 `write_run_meta` / `load_run_meta` / `check_run_matches_classification`）
- Test: `.claude/skills/tune-gates/test_study_io.py`（追加 run_meta 测试）
- Create（本地、不入库）: `docs/research/2026-08-25_multivar-bb_v1/longtable/run_meta.json`

**Interfaces:**
- Consumes: `load_study` / `import_app` / `load_classification` / `check_study_matches` / `base_snapshot`。
- Produces: `longtable/run_meta.json`（schema 见契约）；`ScanConfig` 的构造方式（`module_path=study.APP_MODULE, base_dict=cl["ref_params"]` 去掉 WIDE 后？——**不**：`ScanConfig.base_dict` 传 `base_snapshot` 之前的原始 yaml dict、`wide_overrides` 传 `study.WIDE_OVERRIDES`，与旧行为逐字一致；见 Step 3）。

- [ ] **Step 1: 写失败测试（追加到 `test_study_io.py`）**

```python
def test_run_meta_roundtrip_and_caliber_guard(tmp_path):
    meta = {"app": "x", "start_date": "2024-01-01", "end_date": "2026-01-01", "head_buffer": 250,
            "label_horizon": 40, "first_passage_k": 5.0, "price_min": 0.5, "price_max": 30.0, "volume_min": 10000.0,
            "study_fingerprint": "abc", "git_head": "0000000", "written_at": "t"}
    S.write_run_meta(tmp_path, meta)
    assert S.load_run_meta(tmp_path)["head_buffer"] == 250
    S.write_run_meta(tmp_path, {**meta, "written_at": "t2", "git_head": "1111111"})   # 非口径字段可变
    with pytest.raises(SystemExit, match="head_buffer"):
        S.write_run_meta(tmp_path, {**meta, "head_buffer": 63})                       # 口径字段变 → 拒绝续跑
    with pytest.raises(SystemExit, match="run_meta.json 不存在"):
        S.load_run_meta(tmp_path / "nope")


def test_check_run_matches_classification(cl):
    S.check_run_matches_classification({"study_fingerprint": cl["fingerprints"]["study"]}, cl)
    with pytest.raises(SystemExit, match="study"):
        S.check_run_matches_classification({"study_fingerprint": "zzz"}, cl)
```

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q` → 2 个新 FAIL。

- [ ] **Step 2: 实现（追加到 `study_io.py`）**

```python
RUN_CALIBER = ("app", "start_date", "end_date", "head_buffer", "label_horizon", "first_passage_k",
               "price_min", "price_max", "volume_min", "study_fingerprint")


def write_run_meta(longtable_dir: Path, meta: dict) -> None:
    """run 级口径单源。已存在且任一口径字段不同 → 拒绝(续跑必须同口径,否则长表混窗)。"""
    p = Path(longtable_dir) / "run_meta.json"; p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        old = json.loads(p.read_text())
        bad = [k for k in RUN_CALIBER if old.get(k) != meta.get(k)]
        if bad:
            raise SystemExit(f"{p} 已存在且口径不同: {bad}(旧 {[old.get(k) for k in bad]} / 新 {[meta.get(k) for k in bad]});"
                             "换口径请换 OUT_DIR,不要在同一长表上混窗续跑")
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")


def load_run_meta(longtable_dir: Path) -> dict:
    p = Path(longtable_dir) / "run_meta.json"
    if not p.exists():
        raise SystemExit(f"{p}: run_meta.json 不存在——该长表不是 multivar_scan 新版产出,或路径填错")
    return json.loads(p.read_text())


def check_run_matches_classification(meta: dict, cl: dict) -> None:
    if meta.get("study_fingerprint") != cl["fingerprints"]["study"]:
        raise SystemExit("长表的 study 指纹与当前 classification.json 不一致:长表是在另一份 study 下扫的,"
                         "只能用那份分类去切它(重扫或换回那份 study)")
```

Run 测试 → 16 passed。

- [ ] **Step 3: 改 `multivar_scan.py` 的 `main()`**

把 `:66-125` 整段替换为：
```python
def main() -> None:
    APP = None                                       # 复制到研究目录后填,如 "<app>"
    DATA_DIR = "datasets/pkls"
    START_DATE, END_DATE = "2024-01-01", "2026-01-01"
    HEAD_BUFFER = 250                                # ★ run 级口径单源:写进 run_meta.json,compare/region 读之
    LABEL_HORIZON, FIRST_PASSAGE_K = 40, 5.0
    PRICE_MIN, PRICE_MAX, VOLUME_MIN = 0.5, 30.0, 10000.0
    # WORKERS 实测定标见 reference.md §3.1(拐点 16~20;瓶颈是 CPU 拓扑不是内存)
    WORKERS = 16
    TICKER_REGEX = None
    OUT_DIR = None                                   # None → outputs/tune_gates/<APP>/(outputs/ 已 gitignore)
    SHARD_STOCKS = 200

    import study_io as S
    from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls
    S.require(APP, "APP")
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
    cfg = ScanConfig(module_path=study.APP_MODULE, base_dict=base_yaml, wide_overrides=study.WIDE_OVERRIDES,
                     scan_grid=study.SCAN_GRID, where_levels=study.WHERE_LEVELS, end_node=end_node,
                     label_horizon=LABEL_HORIZON, fp_k=FIRST_PASSAGE_K, price_min=PRICE_MIN, price_max=PRICE_MAX)
    filter_min = {d: loosest_level(study.SCAN_GRID[d], cls.filter_fields[d][2])
                  for d in study.SCAN_GRID if cls.kinds[d] == "F"}
    spec0 = mod.build_pattern(mod.Params.from_dict(apply_overrides(base_yaml, study.WIDE_OVERRIDES, filter_min), strict=True))
    columns = row_columns(cfg, cls, spec0) + ["fold_Y", "fold_6M"]

    out = REPO / (OUT_DIR or f"outputs/tune_gates/{APP}/"); lt = out / "longtable"; lt.mkdir(parents=True, exist_ok=True)
    S.write_run_meta(lt, {"app": APP, "start_date": START_DATE, "end_date": END_DATE, "head_buffer": HEAD_BUFFER,
                          "label_horizon": LABEL_HORIZON, "first_passage_k": FIRST_PASSAGE_K,
                          "price_min": PRICE_MIN, "price_max": PRICE_MAX, "volume_min": VOLUME_MIN,
                          "study_fingerprint": cl["fingerprints"]["study"], "git_head": cl["git_head"],
                          "written_at": pd.Timestamp.now().isoformat(timespec="seconds")})
```
注意：`ScanConfig.base_dict` 传的是**未套 WIDE 的原始 yaml dict**（`base_yaml`），`wide_overrides` 单独传——这与旧代码 `base=json(ref_params)`（已含 WIDE）+ `wide_overrides=WIDE` 的效果逐字相同（`apply_overrides` 幂等：WIDE 套两遍 = 套一遍），只是来源从快照文件变成 yaml；`classify()` 用的 `base`（已套 WIDE）与旧代码相同。

然后删除 `:101-104` 的 `PatternRegistry` 段（已被上面替换覆盖）。`:127` 原 `out = REPO / OUT_DIR; lt = ...` 那行已被替换段末尾覆盖，删除重复。

ledger 行（原 `:269-272`）改为：
```python
    lines = [f"# multivar_scan 台账 · {APP}", "",
             f"- 窗:{START_DATE}..{END_DATE};HEAD_BUFFER={HEAD_BUFFER};LABEL_HORIZON={LABEL_HORIZON};FIRST_PASSAGE_K={FIRST_PASSAGE_K}",
             f"- 过滤:price [{PRICE_MIN},{PRICE_MAX}],volume_min {VOLUME_MIN};底座 {study.BASE_YAML}(base 指纹 {cl['fingerprints']['base'][:12]});宽进 {study.WIDE_OVERRIDES}",
             f"- study 指纹 {cl['fingerprints']['study'][:12]};源码指纹 {cl['fingerprints']['source']['hash'][:12]};classification 生成于 {cl['generated_at']} @ {cl['git_head']}",
             f"- SCAN_GRID:{cl['scan_grid']}", f"- WHERE_LEVELS:{cl['where_levels']}",
```
其余 ledger 行不动。**另有一处**：原 `:266` `combo_cols = [col_of(d) for d in SCAN_GRID if cls.kinds[d] != "F"]` 的 `SCAN_GRID` 改 `study.SCAN_GRID`。改完 `grep -n "SCAN_GRID\|WHERE_LEVELS\|PATTERN_ID\|REF_PARAMS\|WIDE_OVERRIDES" multivar_scan.py` 里每一处都必须带 `study.`/`cl[` 前缀或在字符串里，不得有裸名。模块 docstring 第 7 行「产出与 region_find.py 共用 HEAD_BUFFER(写进 ledger.md,region_find 读出核对)」改为「run 级口径写进 longtable/run_meta.json,compare_longtable / region_find 读之(单源)」。`from multivar_core import` 保持不变。

- [ ] **Step 4: 原件硬闸 + 冒烟到 scratchpad**

```bash
uv run python .claude/skills/tune-gates/multivar_scan.py; echo "rc=$?"          # 期望 "APP 未填" rc=1
cp .claude/skills/tune-gates/multivar_scan.py $SP/
sed -i 's|^    APP = None.*|    APP = "bb_v1"|; s|^    TICKER_REGEX = None|    TICKER_REGEX = r"^AA"|' $SP/multivar_scan.py
sed -i "s|^    OUT_DIR = None.*|    OUT_DIR = \"$SP/scan_out/\"|" $SP/multivar_scan.py   # 绝对路径亦可:REPO / 绝对路径 = 该绝对路径
uv run python $SP/multivar_scan.py | tail -5
ls $SP/scan_out/longtable/ ; cat $SP/scan_out/longtable/run_meta.json
```
Expected: 跑通；`longtable/` 内有 `part-0000.parquet` + `run_meta.json`；`run_meta.json` 的 `head_buffer=250`、`study_fingerprint` 与 `apps/bb_v1/classification.json` 的 `fingerprints.study` 相同。

- [ ] **Step 5: 列集与旧长表逐字相同（迁移等价）**

```bash
uv run python - <<'PY'
import pandas as pd, glob
new = pd.read_parquet(glob.glob("<SP>/scan_out/longtable/part-0000.parquet")[0]).columns.tolist()
old = pd.read_parquet("docs/research/2026-08-25_multivar-bb_v1/longtable/part-0000.parquet").columns.tolist()
assert new == old, (new, old); print("列集一致", len(new))
PY
```
（把 `<SP>` 换成实际路径。）Expected: `列集一致 N`。

- [ ] **Step 6: 为既有长表本地补写 run_meta.json（Task 7/8 的等价 gate 需要；目录已 gitignore）**

```bash
uv run python - <<'PY'
import sys; sys.path.insert(0, ".claude/skills/tune-gates")
import study_io as S, pandas as pd
cl = S.load_classification("bb_v1")
S.write_run_meta("docs/research/2026-08-25_multivar-bb_v1/longtable", {
  "app": "bb_v1", "start_date": "2024-01-01", "end_date": "2026-01-01", "head_buffer": 250,
  "label_horizon": 40, "first_passage_k": 5.0, "price_min": 0.5, "price_max": 30.0, "volume_min": 10000.0,
  "study_fingerprint": cl["fingerprints"]["study"], "git_head": "88ec1c3",
  "written_at": pd.Timestamp.now().isoformat(timespec="seconds") + " (迁移补写,值取自该目录 ledger.md)"})
print("ok")
PY
git status --short docs/research/2026-08-25_multivar-bb_v1/   # 期望无输出(longtable/ 被忽略)
```

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/tune-gates/multivar_scan.py .claude/skills/tune-gates/study_io.py .claude/skills/tune-gates/test_study_io.py
git commit -m "feat(tune-gates): multivar_scan 改读 study/classification,写 run_meta.json 作 run 级口径单源;原件 APP=None 硬闸"
```

---

### Task 7: `compare_longtable.py` 改造

**Files:**
- Modify: `.claude/skills/tune-gates/compare_longtable.py`（全文件：docstring、`_init`、`_cell_where_mask` 删除、`_worker`、`main()`）

**Interfaces:**
- Consumes: `load_run_meta` / `check_run_matches_classification` / `load_study` / `load_classification` / `check_study_matches` / `pred_mask` / `base_snapshot` / `undotted`。
- Produces: 与旧版同语义的对拍日志；plan 项数由 7 维 grid 推出（见 Step 3 说明）。

- [ ] **Step 1: 改 `_init`**

```python
def _init(cfg: dict) -> None:
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
```
（`_init` 不再调 `classify`——分类来自 `cfg["cl"]`；文件顶部 `import importlib` 加进 import 区。）

- [ ] **Step 2: 删 `_cell_where_mask`，改 `_worker` 的掩码与键节点**

`_worker` 里
```python
        g = g_all[_cell_where_mask(g_all, cell, where, C["cls"], C["MDD_DIM"], C["MDD_FIELD"])]
```
改为
```python
        g = g_all[S.pred_mask(g_all, {**cell, **where}, C["cl"])]
```
（`_worker` 顶部加 `import study_io as S`。）`C["KEY_NODES"]` 两处改为 `C["key_nodes"]`、`C["END_NODE"]` 改 `C["end_node"]`、`C["H"]`/`C["K"]`/`C["PRICE_MIN"]`/`C["PRICE_MAX"]`/`C["bs"]`/`C["be"]`/`C["s"]`/`C["e"]`/`C["MIN_WIN_BARS"]` 保持键名但由新 `main()` 提供。

- [ ] **Step 3: 改 `main()`（整段替换）**

```python
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
```
其后进程池与汇总段保持原样（`n_cmp = n_mism = ...` 到 `log_f.close()`）。文件顶部 `from multivar_core import ...` 改为 `apply_overrides, loosest_level, node_col`（`node_col` 在 `_worker` 的 got 键里仍在用；`classify`/`col_of` 不再用），加 `import importlib`。

- [ ] **Step 4: 改 docstring**

把文件头 docstring 的「本文件相对它只有两处变化」段落之后追加第 3 条：
```
  3. **零 app 字面量**:网格/where/收紧套/底座/end_node/bound 节点全部来自 apps/<app>/study.py +
     classification.json,label 口径来自长表旁的 run_meta.json(与扫描逐字同源,结构上不可能不一致);
     切面 (a) 的「固定维」推导为「只影响拓扑首 detector 节点的 D 维」并取参照格值,不再写死前两维。
```

- [ ] **Step 5: 迁移等价 gate（对既有长表、`^AA` 子集）**

```bash
uv run python .claude/skills/tune-gates/compare_longtable.py; echo "rc=$?"   # 期望 "LONGTABLE_DIR 未填" rc=1
cp .claude/skills/tune-gates/compare_longtable.py $SP/
sed -i 's|^    LONGTABLE_DIR = None.*|    LONGTABLE_DIR = "docs/research/2026-08-25_multivar-bb_v1/longtable/"|; s|^    TICKER_REGEX = r"\^\[A-Z\]\[A-C\]"|    TICKER_REGEX = r"^AA"|' $SP/compare_longtable.py
sed -i "s|^    OUT_LOG = None.*|    OUT_LOG = \"$SP/cmp.log\"|" $SP/compare_longtable.py
uv run python $SP/compare_longtable.py | tail -3
```
Expected 输出末行形如 `对拍 <N> 股×格(19 只有效股 × <P> 项),mismatch=0`。**红线 mismatch=0**。`P` 由 7 维 grid 推出：`cells_a` = 4·4·4·4·2 = 512，`cells_b` = 64 + 2⁷ = 192，`c` = 12×2 = 24 → **P = 728**，N = 19 × 728 = **13,832**（旧版 408 项是 6 维 grid 的数字，本版把 F 维 `max_day_drop_pct` 也纳入切面与角点，覆盖更宽）。若 mismatch ≠ 0：**不得**放宽键/容差/缩股票集；按 `.claude/rules` 的 systematic-debugging 排查 `pred_mask` 与旧 `_cell_where_mask` 的语义差异（最可能是 F 维 `None` 档或 `<` 口径）。

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/tune-gates/compare_longtable.py
git commit -m "feat(tune-gates): compare_longtable 改读 study/classification/run_meta,删 MDD 特判与 app 字面量"
```

---

### Task 8: `region_find.py` 改造

**Files:**
- Modify: `.claude/skills/tune-gates/region_find.py:29-64,173`（`_check_head_buffer` 删除、`main()` 头部、报告首行）

**Interfaces:**
- Consumes: `load_run_meta` / `check_run_matches_classification` / `load_study` / `load_classification` / `check_study_matches` / `derived_axes`。

- [ ] **Step 1: 删 `_check_head_buffer`（`:33-36`）与 `import re`，改 `main()` 头部（`:39-64` 替换为）**

```python
def main() -> None:
    LONGTABLE_DIR = None          # 复制到研究目录后填:multivar_scan 产出的 longtable/(含 run_meta.json)
    FOLD_COL, FOLDS = "fold_Y", ["2024", "2025"]
    MIN_COUNT_PER_FOLD = 100      # 仅在一个 app 上校准过(口径偏松、方向不保守,见 reference.md §8);换 app 不要当已验证默认
    NEIGHBOR_AXES = "all"
    B_BOOT, SEED, TOP_N = 300, 0, 20
    OUT_DIR = None                # None → LONGTABLE_DIR 的父目录

    import study_io as S
    S.require(LONGTABLE_DIR, "LONGTABLE_DIR")
    lt = REPO / LONGTABLE_DIR
    meta = S.load_run_meta(lt); APP = meta["app"]; HEAD_BUFFER = meta["head_buffer"]
    study_path = S.APPS_DIR / APP / "study.py"
    study = S.load_study(study_path)
    cl = S.load_classification(APP); S.check_study_matches(cl, study_path); S.check_run_matches_classification(meta, cl)
    COMBO_LEVELS, preds = S.derived_axes(cl)
    REF_POINT, FLAG_RULES = study.REF_POINT, study.FLAG_RULES
    out = REPO / OUT_DIR if OUT_DIR else lt.parent
    df = _load(lt)
    prep = prepare(df, COMBO_LEVELS, preds, FOLD_COL, FOLDS)
```
其后从 `axes = list(range(...))` 起原样保留（它们只用 `COMBO_LEVELS` / `preds` / `REF_POINT` / `FLAG_RULES` / `HEAD_BUFFER` / `FOLDS` 这些名字，均已在上面定义）。报告首行 `:173` 的 `f"- 长表 {LONGTABLE_DIR};HEAD_BUFFER={HEAD_BUFFER};..."` 前面加 `f"- app {APP};study 指纹 {cl['fingerprints']['study'][:12]}"`。

- [ ] **Step 2: 迁移等价 gate（对既有长表重跑到 scratchpad）**

```bash
uv run python .claude/skills/tune-gates/region_find.py; echo "rc=$?"   # 期望 "LONGTABLE_DIR 未填" rc=1
cp .claude/skills/tune-gates/region_find.py $SP/
sed -i 's|^    LONGTABLE_DIR = None.*|    LONGTABLE_DIR = "docs/research/2026-08-25_multivar-bb_v1/longtable/"|' $SP/region_find.py
sed -i "s|^    OUT_DIR = None.*|    OUT_DIR = \"$SP/region_out/\"|" $SP/region_find.py
mkdir -p $SP/region_out && uv run python $SP/region_find.py > $SP/region.log 2>&1; tail -3 $SP/region.log
grep -E "联合空间|naive s_nb|optimism =|稳定性" $SP/region_out/region_report.md
grep -E "联合空间|naive s_nb|optimism =|稳定性" docs/research/2026-08-25_multivar-bb_v1/region_report.md
```
Expected（新旧两组 grep 必须给出相同数字）：`联合空间 … = 442368 格;可评估 361629;不可评估 80739;邻域分为负 361412`、`naive s_nb = 0.0705;split-half = -0.1319`、`optimism = 0.1263 ± 0.0062`、`稳定性 … = 0.07(基于 22/300 …)`。**轴顺序允许不同**（新版 preds 序 = F 维在前，`tb.day_drop` 从末位移到第 2 位），`shape` 元组的排列、`flat` 编号、`slice_*.png` 文件名顺序都可以变，**四个标量与三个计数必须逐字相等**。若任一不等：在 `$SP/region_find.py` 里临时把 `preds` 手工重排成旧序 `[burst.count, burst.first_drought, burst.distinct_pk, burst.max_bar_vol_ratio, burst.peak_age_max, tb.day_drop]` 再跑一次——若此时相等，说明差异纯由轴序引起（`rank_cells` 的 `lexsort` 在精确平局时按 flat 序破平局），记进 commit message 并接受；若仍不等，是真回归，回到 Step 1 排查。

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/tune-gates/region_find.py
git commit -m "feat(tune-gates): region_find 改读 run_meta/classification/study,删手抄谓词轴与 HEAD_BUFFER 正则核对"
```

---

### Task 9: `bench_workers.py` 适配新常量

**Files:**
- Modify: `.claude/skills/tune-gates/bench_workers.py:111-128`（`main()` 顶部与 `TOOLS`）

**Interfaces:**
- Consumes: Task 6/7 改后的三个工具的常量名（`APP` / `OUT_DIR` / `LONGTABLE_DIR` / `OUT_LOG` / `TICKER_REGEX` / `WORKERS`）。

- [ ] **Step 1: 改常量与 sed 表**

`main()` 顶部加 `APP = None` 并 `require`；`TOOLS` 改为：
```python
    import sys as _sys; _sys.path.insert(0, str(SKILL))
    import study_io as S
    S.require(APP, "APP")
    TOOLS = [
        ("multivar_scan", SKILL / "multivar_scan.py", [
            (r'^(\s*)APP = None.*', rf'\1APP = "{APP}"'),
            (r'^(\s*)OUT_DIR = None.*', r'\1OUT_DIR = "{SCRATCH_REL}/scan_out/"'),
            (r'^(\s*)TICKER_REGEX = .*', rf'\1TICKER_REGEX = r"{TICKER_REGEX}"'),
        ]),
        ("compare_longtable", SKILL / "compare_longtable.py", [
            (r'^(\s*)LONGTABLE_DIR = None.*', r'\1LONGTABLE_DIR = "{SCRATCH_REL}/scan_out/longtable/"'),
            (r'^(\s*)OUT_LOG = None.*', r'\1OUT_LOG = "{SCRATCH_ABS}/cmp.log"'),
            (r'^(\s*)TICKER_REGEX = .*', rf'\1TICKER_REGEX = r"{TICKER_REGEX}"'),
        ]),
    ]
```
注意 `compare_longtable` 现在依赖 `scan_out/longtable/` 里有 `run_meta.json` 与分片——bench 循环里 `shutil.rmtree(SCRATCH / "scan_out")` 在**每个 W 的 scan 轮之前**执行（现有行为），而 compare 轮读的是最后一次 scan 留下的目录：把 `rmtree` 改为只在 `name == "multivar_scan"` 时执行，让 compare 轮复用 scan 最后一轮的产出。docstring 里「输出一律写 scratchpad」保留。

- [ ] **Step 2: 冒烟（W 网格缩到 [4]，正则 `^AA`）**

```bash
cp .claude/skills/tune-gates/bench_workers.py $SP/
sed -i 's|^    APP = None.*|    APP = "bb_v1"|; s|WORKER_GRID = \[4, 8, 12, 16, 20, 24, 26\]|WORKER_GRID = [4]|; s|TICKER_REGEX = r"\^A\[A-C\]"|TICKER_REGEX = r"^AA"|' $SP/bench_workers.py
CLAUDE_SCRATCH=$SP uv run python $SP/bench_workers.py 2>&1 | tail -8
```
Expected: 两个工具各打印一行 `W= 4  wall …  峰值 … MB(PSS, 5 进程)`，无 `⚠ rc=`。

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/tune-gates/bench_workers.py
git commit -m "chore(tune-gates): bench_workers 适配 APP/OUT_DIR/LONGTABLE_DIR 新常量,compare 轮复用 scan 产出"
```

---

### Task 10: 文档拆分——SKILL.md / reference.md 通用化 + `apps/bb_v1/notes.md`

**Files:**
- Modify: `.claude/skills/tune-gates/SKILL.md`
- Modify: `.claude/skills/tune-gates/reference.md`
- Create: `.claude/skills/tune-gates/apps/bb_v1/notes.md`

**Interfaces:**
- Produces: 通用区零 app 专名（Task 11 gate 4 据此 grep）。

- [ ] **Step 1: 写 `apps/bb_v1/notes.md`（承接从 `reference.md` 迁出的全部 bb_v1 内容；以下按 `reference.md` 当前行号指明来源，**逐字搬**，不改数字）**

```markdown
# bb_v1 · tune-gates 实例记录

> 本文件是 app 耦合区的一部分(`apps/bb_v1/`),记录 bb_v1 在多维稳健区 v2 上的真实运行数字与案例。
> 通用流程见 `../../reference.md`;本文件可随 `apps/bb_v1/` 整体删除。
> 证据目录 `docs/research/2026-08-25_multivar-bb_v1/` 是一次性研究产物,可能被清理;本文件自足。

## 1. 底座与网格
（搬 reference.md:11 的「bb_v1 实例:…都不是默认值」句、:12 的 WIDE 五项、附录 A :170-173 四条）

## 2. 分类实测
（搬 reference.md:24-32 的表与 1024 说明）

## 3. 扫描实测
（搬 reference.md:36-46 的数字块与预算研究对照段,:14 的 7,831,477 行/3985 股句）

## 4. 对拍实测与作用域记录
（搬 reference.md:110 「本例实测:1078 只…439,824 次比较,mismatch=0」、:112 Step B 的 73/92、164/172、:116 「本轮真实破过红线」段）
**上次对拍作用域**:2026-08-26;网格 = 本文件 §1 的 SCAN_GRID(6 维,不含 max_day_drop_pct)× where 集合 {wide, FINAL, B};1078 股 × 408 项;mismatch=0;对应 commit 见研究目录 final_report.md §④。
**2026-08-27 迁移后**:新版 compare_longtable 以 7 维 grid(含 max_day_drop_pct)在 ^AA 子集 19 股 × 728 项 mismatch=0(Task 7 gate)。

## 5. 识别实测
（搬 reference.md:124-137 的读数块、三口径读法、产出文件清单）

## 6. 复核记录
（搬 reference.md:141-147 四条）

## 7. 外推
（搬 reference.md:151 的「本例截至本轮尚未执行」句）

## 8. 坑的具体案例
（搬 reference.md:157-166 每条里的 bb_v1 具体数字与字段名;通用教训留在 reference.md §8,此处按编号 1-10 对应）

## 9. 结果一行摘要
（搬附录 A :174-175）
```
实施者把括号里指向的原文**逐字**复制到对应节（括号说明本身不保留）。

- [ ] **Step 2: 重写 `reference.md`**

保留结构 §0-§8，按下面规则改：
- 顶部引言 `:3` 改为：「本卡是 pattern 无关的操作卡；每一步的真实数字与案例在 `apps/<app>/notes.md`（如 `apps/bb_v1/notes.md`）。证据目录 `docs/research/...` 是一次性研究产物、可能被清理，本卡自足。方法论全文见 `SKILL.md` 第 4 步。」——**这是全文唯一允许出现 `bb_v1` 的地方**（作为 notes 文件名指路），Task 11 的 grep 对 `reference.md` 单独排除 `apps/bb_v1/notes.md` 这个字面量。
- §1 准备：三个 bullet 改为通用——「参照底座 = `study.py` 的 `BASE_YAML`（app 目录下的生产参数 yaml，不是 `Params()` 默认值）⊕ `WIDE_OVERRIDES`；`app_setup` 展开成 `classification.json` 的 `ref_params`」/「where 维放机制下限（`WIDE_OVERRIDES`）」/「HEAD_BUFFER 在 `multivar_scan` 一处声明、写进 `run_meta.json`，`compare`/`region` 读之，不再各声明一份」/「输出目录默认 `outputs/tune_gates/<app>/`（gitignore），长表 parquet 分片需要 `pyarrow`」。删 :11 的 bb_v1 句、:14 的行数。
- §2 分类与选维：保留 :18-22；删 :24-32 的表与 1024 句，改为「分类由 `app_setup` 生成到 `classification.json`；`detection_combos` = D 维档位笛卡尔积（F/W 维不进）；格数 ≠ 检测组合数。实例见 `apps/<app>/notes.md` §2」。
- 新增 **§2.1 换 app / 复用：入口协议**（内容 = 下面 SKILL.md 新节的决策树，两处同文）。
- §3 扫描：删 :36-46 数字块，改为「复制四个入口脚本到研究目录→填 `APP`→`app_setup`→`multivar_scan`」+ 保留 :47-48 两条（断点续跑、台账）。§3.1 保留全部（机器相关，非 app），`repro/bench_workers.py`→`bench_workers.py`（Task 1 已改）。
- §4 对拍：§4.0 全部保留；§4.1 Step A 删「本例实测：1078 只…」句，改「实例见 notes §4」；Step B 删 73/92、164/172 数字；删 :116 「本轮真实破过红线」段（搬 notes），保留其教训句「正确做法是先起对拍这个长跑任务、再跑 region_find」。耗时提醒段保留但把 9304s/1217s 等数字改为「见 notes §3/§4」。
- §5 识别：:120 改「复制 `region_find.py`，只需填 `LONGTABLE_DIR`（`COMBO_LEVELS`/`PREDS`/`REF_POINT`/`FLAG_RULES` 全部从 `classification.json` + `study.py` 推导）」；删 :122 段；删 :124-137 读数块，改「实例见 notes §5」；保留三口径读法那句的通用部分（去掉数字）。
- §6 复核：四条保留通用教训，删具体数字与字段名（`burst.peak_age_max`、`tb.day_drop`、0.07、217/504 等），案例指 notes §6。
- §7 外推：删「本例（bb_v1）截至本轮尚未执行」。
- §8 坑：每条保留**通用教训**，删 bb_v1 字段名/数字，末尾加「案例：notes §8 坑 N」。坑 2 改写为：「**参数名不能告诉你它属于哪类**：一个读起来像 where 阈值的百分比参数实为 detector 内部 emit 门（探针分类 = F），塞进 `WHERE_LEVELS` 会被 `classify()` 硬拒。换 app 时一律以 `app_setup` 的分类输出为准，不凭名字预判。」
- 删附录 A。

- [ ] **Step 3: 重写 `SKILL.md`**

按行改：
- `:15` 括号里 `如 gap_max / big_rise_k / min_relative_height / stop_confirm_bars` 改 `如切串间距、确认根数、突破幅度阈值`；末尾加「；**换 app 或复用已有 app 前先走「入口协议」节**」。
- 在 `## 流程（七步）` 之前插入新节：

```markdown
## 入口协议（多维稳健区 v2 · 换 app / 复用必走，Claude 不许跳）

app 耦合内容全部在 `.claude/skills/tune-gates/apps/<app>/`（`study.py` 人写 8 项声明 / `classification.json` 机器生成 / `notes.md` 实例记录），整夹可删。用户指明 app X 后：

```
apps/X/ 存在？
├─ 否 → 首次接入:cp -r apps/_template apps/X → 与用户一起填 study.py 8 项
│        → app_setup MODE=build → 对拍必做(reference.md §4.0 表第一行)
└─ 是 → app_setup MODE=check → 把三行报告(source / base / study)原样给用户看
         → 问:「上次为 X 生成耦合内容是 <generated_at>。app 自那以后改过吗?要重新生成吗?」
           ├─ 用户:没改 / 复用 → 用现有 classification.json
           └─ 用户:改了 / 重生成 → app_setup MODE=build
                → 按 §4.0 表定对拍:source 变 → 完整重做;只 base 变 → 免对拍
```

**指纹是证据不是裁定**：三行全「一致」也要问；指纹报变更但用户裁定复用也听用户，但把「指纹不一致、用户裁定复用」写进本次 ledger。`base` 指纹比的是**值**不只是条目名——底座 yaml 是「搜索空间之外的一切」，不在网格里的参数在全部检测组合中取底座值，变一个整张长表换世界。

**通用区/耦合区边界**：`SKILL.md`、`reference.md`、四个入口脚本里不出现任何具体 app 的参数名、节点名、数字；举例一律指向 `apps/<app>/notes.md`。
```
- `:21` 括号里 `如 bb_v1 的 first_drought_min / … / max_day_drop_pct` 改 `如纯 where 字段与 filter_params 声明的闸`；`:22` `如 gap_max / min_bos / stop_confirm_bars / tb·bo 几何参数` 改 `如切串间距、最小串长、确认根数、几何阈值`。
- `:25` 里 `（bb_v1 案例：peak_age max=507 只测到 180，补测 250/350 后…）`、`（first_drought 漏 x=0，499 个首簇样本）` 改 `（案例见 apps/<app>/notes.md）`；`6 维 4 档=4096 格 × where 档全宇宙分钟级（格数 ≠ 检测组合数：…故实需检测 1024 次）` 改 `格数 ≠ 检测组合数：F 维不进检测笛卡尔积、事后按字段谓词切`；`first_drought_min ≤ gap_max 的格闸恒真（报告 flags）` 改 `机制上恒真的格由 study.py 的 FLAG_RULES 标记（报告 flags）`；`test_multivar_equiv.py 思路扩到 ≥500 股` 改 `compare_longtable.py`。
- `:26` `peak_age 案例整体交集 [125,250]…（vol_spike 两年峰值同在 x=15）`、`毒药闸「白过滤」实为 day_drop p50=0.006/p90=0.08…` 改 `（案例见 apps/<app>/notes.md）`。
- `:28` `（如毒药组 0up/12dn 对照 0.72 池基率）` 改 `（如某闸删除组的四态计数对照池基率）`。
- `:38-39` 两条红线的括号案例改 `（案例见 apps/<app>/notes.md）`。
- `:43-44` 的 `2026-08 bb_v1 实证：…`、`同实证：head_buffer 63→250…`、`2026-08 教训：head_buffer=63 恰好…` 三处改 `（实证见 apps/<app>/notes.md）`，保留结论句。
- `:49` `region_find 读 ledger 核对` 改 `HEAD_BUFFER 由 multivar_scan 写进 run_meta.json、compare/region 读之（单源）`。
- `:74-86` 用法节整段改为：

```markdown
## 多维稳健区 v2 工具用法

**先复制到研究目录再填常量，勿直接跑 skill 目录里的原件**（原件 `APP=None` / `LONGTABLE_DIR=None`，直接跑会 `SystemExit`）。app 声明不复制——它在 `apps/<app>/`。

```
cp .claude/skills/tune-gates/{app_setup,multivar_scan,compare_longtable,region_find}.py docs/research/<日期>_<任务>/
# 各文件 main() 顶部填 APP / LONGTABLE_DIR 等 run 级常量(无 argparse)
uv run python docs/research/<日期>_<任务>/app_setup.py          # 首次 MODE=build;复用前 MODE=check(见「入口协议」)
uv run python docs/research/<日期>_<任务>/multivar_scan.py      # 出 longtable/(分片 + run_meta.json)+ ledger.md
uv run python docs/research/<日期>_<任务>/compare_longtable.py  # 对拍(按股并行);红线 mismatch=0,读 region 之前必须先绿
uv run python docs/research/<日期>_<任务>/region_find.py        # 读 longtable/ + run_meta.json,出 cells.csv/region_report.md
uv run pytest .claude/skills/tune-gates/ -q                     # skill 自测(fixtures/ 自带,不依赖 apps/ 与 docs/research/)
```
```
- `:95` 首轮使用注意里 `bb_v1 端到端全宇宙实战` 改 `一个 app 的端到端全宇宙实战（记录在 apps/<app>/notes.md）`。

- [ ] **Step 4: 零 app 专名 grep**

```bash
cd .claude/skills/tune-gates
grep -n "bb_v1\|\"burst\"\|\"tb\"\|\"bo\"\|burst\.\|tb\.\|peak_age\|first_drought\|max_day_drop\|min_bos\|gap_max\|big_rise_k\|stop_confirm" SKILL.md multivar_scan.py compare_longtable.py region_find.py app_setup.py study_io.py bench_workers.py apps/_template/study.py
grep -n "bb_v1\|\"burst\"\|\"tb\"\|\"bo\"\|burst\.\|tb\.\|peak_age\|first_drought\|max_day_drop\|min_bos\|gap_max\|big_rise_k\|stop_confirm" reference.md | grep -v "apps/bb_v1/notes.md"
```
Expected: 两条都无输出。（`SKILL.md:3` 的 description 里 `gap_max / big_rise_k / min_relative_height / stop_confirm_bars` 是触发词——**也要改**：换成「那些一改就得重新检测的构造参数，如切串间距、确认根数、突破幅度阈值」，触发词仍是用户会说的话。）

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/reference.md .claude/skills/tune-gates/apps/bb_v1/notes.md
git commit -m "docs(tune-gates): 通用区去 app 专名,实例数字迁 apps/bb_v1/notes.md,新增入口协议"
```

---

### Task 11: 四道验收 gate + push

**Files:** 无新改动（若 gate 失败回到对应 task 修）。

- [ ] **Step 1: gate 1 — 全部测试绿**

Run: `uv run pytest .claude/skills/tune-gates/ -q`
Expected: `66 passed`（50 基线 + 16 新增）或更多，0 failed。

- [ ] **Step 2: gate 2 — 删耦合区不伤通用区**

```bash
mv .claude/skills/tune-gates/apps/bb_v1 $SP/
uv run pytest .claude/skills/tune-gates/ -q; echo "rc=$?"
mv $SP/bb_v1 .claude/skills/tune-gates/apps/bb_v1
git status --short .claude/skills/tune-gates/apps/   # 期望无输出
```
Expected: `rc=0`、同样的 passed 数。

- [ ] **Step 3: gate 3 — 迁移等价（Task 7 Step 5 与 Task 8 Step 2 已各自跑过；此处只核对两处日志仍在且结论为 mismatch=0 / 数字相等，不重跑）**

把两处的关键输出行（compare 的末行、region 的四个标量）抄进最终 commit message。

- [ ] **Step 4: gate 4 — 零 app 专名（Task 10 Step 4 的两条 grep 再跑一次）**

Expected: 无输出。

- [ ] **Step 5: 清理与 push**

```bash
git status --short          # 期望干净
git log --oneline ec6ed28..HEAD | head -20
git push origin worktree-tune-tools
git rev-parse --short HEAD origin/worktree-tune-tools
```
Expected: 本地与远端 HEAD 相同。**不开 PR。**

---

## 自审记录（写 plan 时完成）

- **Spec 覆盖**：§1 原则 1（自包含）→ Task 1/2/5；原则 2（零专名）→ Task 10/11；原则 3（可整删）→ Task 2/11 gate 2；原则 4（指纹 + 必问）→ Task 4/5/10 入口协议；原则 5（不改库核）→ Global Constraints。§2 目录树 → 文件结构节。§3.1/3.2/3.3 → Task 2/3/4/5。§4 表与单源 → Task 6/7/8；对拍 mask 分派 → Task 3 `pred_mask`；启动闸 → `check_study_matches` / `check_run_matches_classification`。§5 → Task 10 新节。§6 → Task 10。§7 → Task 11 + 各 task 内 gate；测试改造 → Task 1；新增测试 → Task 2/3/4/6；突变测试 → 各 task Step。§8 不做 → 无对应 task（正确）。
- **两处对 spec 的收窄**：`fingerprints.base` 对展开后快照算而非 yaml 解析结构（Task 4 契约节说明理由）；`source` 不一致时报「范围内文件」而非精确变更文件（Task 4 Step 2 说明理由）。
- **类型一致性**：`cl["filter_fields"][k]` 是 `list[str]`（JSON）而 `Classification.filter_fields[d]` 是 `tuple`——`pred_mask` / `derived_axes` 用 `cl`（list）、`multivar_scan` 用 `cls`（tuple），两者不混用；`bound_nodes` 在 JSON 为 list、`compare` 里 `tuple(cl["bound_nodes"])` 后当 `key_nodes`；`REF_POINT` 点号键、`SCAN_GRID` 元组键，`dotted()`/`undotted()` 转换。
- **对拍 plan 项数变化**（408 → 728）已在 Task 7 Step 5 说明并写进 notes §4。
