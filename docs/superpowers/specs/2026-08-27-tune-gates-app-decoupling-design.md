# tune-gates skill 自包含 + app 解耦 设计

> 日期：2026-08-27 · 状态：brainstorm 已逐节确认，待用户审阅后转 writing-plans
> 本 spec 中所有项目内路径均相对 repo root。

## 0. 问题

`tune-gates` skill 的多维稳健区 v2 链路在 2026-08-25 bb_v1 实战中落地，但两件事没做对：

**不自包含**：skill 的测试（`test_multivar_core.py:19`、`test_multivar_equiv.py:38`）、工具原件（`multivar_scan.py` 的 `REF_PARAMS`）和操作卡（`reference.md` §1「参照底座」）都读 `docs/research/2026-08-25_multivar-bb_v1/ref_params.json`；可复用的 `bench_workers.py` 放在 `docs/research/.../repro/`。`docs/research/` 是一次性研究产物目录、将来可能被清理——清了 skill 测试直接红。

**与 bb_v1 耦合且耦合散落**：同一个 app 事实被手抄在三个入口脚本里——`SCAN_GRID`/`WHERE_LEVELS` 在 scan 与 compare 各一份（必须逐字一致）；`HEAD_BUFFER` 三份（`region_find` 靠正则读 ledger 交叉核对，这个核对本身是重复声明的症状）；`region_find` 的 `COMBO_LEVELS`/`FILTER_PREDS`/`WHERE_PREDS` 是人手把 `classify()` 输出抄回源码；`compare_longtable` 的 `MDD_DIM`/`MDD_FIELD` 注释原话「取自 classify() 实测 filter_fields 映射」；`END_NODE`/`KEY_NODES`/`WIDE_OVERRIDES` 全部可推导却手写。换 app = 改 3 个文件约 8 个 dict 并保持一致，每一步都是静默不一致的机会。

**一个事实订正**：`ref_params.json` 不是不可再生的快照——它 = `path2_apps/bb_v1/p2.yaml` ⊕ 四项宽进覆盖（`first_drought_min 0 / distinct_pk_min 1 / vol_spike_min 0 / max_day_drop_pct None`），后者正是 `multivar_scan` 的 `WIDE_OVERRIDES`。注意底座是 `p2.yaml` 而非 `params.yaml`（后者是 web 入口 SSoT，二者在 `tb.max_window`/`scb_mode`/`judged_measure`/`stop_confirm_bars` 上不同）。

## 1. 目标与原则

1. **skill 自包含**：skill 读取的、测试依赖的、操作卡让人重跑的，全部住在 `.claude/skills/tune-gates/` 内。`docs/research/` 只能是写入目标，绝不是读取来源。
2. **通用区零 app 专名**：`SKILL.md`、`reference.md`、四个入口脚本、库核里不出现任何具体 app 的参数名、节点名、数字；举例一律指向 `apps/<app>/notes.md`。
3. **耦合收进一个可整删的目录**：`apps/<app>/` 是换 app 时唯一要改的地方；`rm -rf apps/<app>` 后通用区（含测试）不受影响。
4. **耦合内容过期 = 指纹作证据 + 必问用户**：机器算指纹、列出变了什么与后果；重生成与否由用户裁定，指纹一致也要问。
5. **不改库核**：`multivar_core.py`、`region_core.py`、`path2/dag/` 零改动。推导所需函数（`classify`/`loosest_level`/`col_of`/`node_col`/`compile_plan`/`eval_meta`）全部已存在。

## 2. 目录结构

```
.claude/skills/tune-gates/
├── SKILL.md · reference.md           通用指令
├── multivar_core.py · region_core.py 库核（不动）
├── multivar_scan.py                  工具：main() = APP + run 级常量
├── compare_longtable.py              工具：同上
├── region_find.py                    工具：同上
├── app_setup.py                      新增（通用）：study.py → classification.json；MODE=build|check
├── study_io.py                       新增（通用）：加载 study/classification/run_meta + 推导 helper（I/O 与文件约定，故不进库核）
├── bench_workers.py                  从 docs/research/2026-08-25_multivar-bb_v1/repro/ 搬入
├── plateau.py                        不动（已通用）
├── fixtures/
│   └── bb_v1_p2_wide.json            现 ref_params.json 原样搬入；仅测试读
├── test_*.py                         只读 fixtures/，不 import apps/
└── apps/                             ★ 耦合区
    ├── _template/study.py            新 app 起手模板（五项声明带说明注释）
    └── bb_v1/
        ├── study.py                  人写声明
        ├── classification.json       app_setup 生成；人不改
        └── notes.md                  本 app 实例数字、坑的具体案例、上次对拍作用域
```

三条边界：通用区不静态 import `apps/`（工具按 `APP` 常量 `importlib` 动态加载）；测试不读 `apps/`；`apps/<app>/` 是唯一换 app 要改的地方。

## 3. `study.py` 与 `classification.json` 的分工

### 3.1 `study.py`——只放推不出来的东西

```python
APP_MODULE = "path2_apps.bb_v1.dag_spec"
BASE_YAML  = "p2.yaml"      # 相对 app 包目录；底座 = 搜索空间之外的一切
WIDE_OVERRIDES = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                  "tb": {"max_day_drop_pct": None}}
SCAN_GRID    = {("bo", "min_relative_height"): [...], ...}    # D/F 维档位
WHERE_LEVELS = {("burst", "first_drought_min"): [...], ...}   # W 维档位
REF_POINT    = {"bo.min_relative_height": 0.2, ...}           # 参照格（点号键）
TIGHT_WHERES = {"FINAL": {...}, "B": {...}}                   # 对拍用的收紧 where 套；app 的候选生产点
FLAG_RULES   = [lambda c: "first_drought 闸恒真" if c["burst.gap_max"] >= c["burst.first_drought"] > 0 else None]
```

`FLAG_RULES` 是 app 语义、推不出来，故留在 `study.py`。`TIGHT_WHERES` 现硬编码在 `compare_longtable` 里，归 `study.py`。

### 3.2 `classification.json`——`app_setup.py` 生成，人不改

| 字段 | 来源 |
|---|---|
| `kinds` / `filter_fields` / `where_fields` | `classify()` 输出，Dim 用点号键序列化 |
| `end_node` | `mod.eval_meta()["end_node"]`（铁律，所有 app 必声明） |
| `bound_nodes` | `compile_plan(spec).wcc_plans` 的 comp 并集（与 `row_columns` 同源），替代手写 `KEY_NODES` |
| `detection_combos` | `len(detection_combos(...))` 计数 |
| `ref_params` | `BASE_YAML` ⊕ `WIDE_OVERRIDES` 展开后的完整快照 |
| `fingerprints.source` | app 包目录全部 `.py` + 从 spec 推出的 detector 模块文件（`type(n.detector).__module__` → 文件），内容 sha256，按路径排序后聚合 |
| `fingerprints.base_yaml` | `yaml.safe_load` 后键排序 JSON 序列化再 sha256（注释/空白/顺序变化不误报） |
| `fingerprints.study` | `study.py` 文件内容 sha256 |
| `generated_at` / `git_head` | 生成时刻与 HEAD |

引擎（`path2/dag/`）不进指纹：不是 app 内容，其正确性由 skill 自身测试保障。

### 3.3 `app_setup.py`

`main()` 顶部常量：`APP = None`（原件；复制后填）、`MODE = "build"`（或 `"check"`）。无 argparse。

**build**：加载 `apps/<APP>/study.py` → `importlib` 进 `APP_MODULE` → 读 `BASE_YAML` 展开快照 → `Params.from_dict(strict=True)` → `classify()` → 跑现有全部静态守卫（`check_predicate_axes`、共享 detector、negation dst——在这里就响亮失败，不等到扫描）→ 推 `end_node`/`bound_nodes` → 算三个指纹 → 写 `classification.json` → 终端打印分类表。幂等，重跑覆盖。

**check**：只算指纹不写文件，输出三行报告：

```
source:    一致 / 变更文件 [path2_apps/bb_v1/dag_spec.py, path2/atoms/throwback_v1.py]
base_yaml: 一致 / 已变更(N 项)
             tb.max_window      20 → 15    [底座常量 · 全部检测组合受影响 · 长表过期]
             burst.gap_max       8 → 10    [D 维 · 网格档位覆盖 · 仅参照格坐标需核对]
             tb.new_param       (无) → 3   [新增 · 未进网格 · 将以新值作底座常量]
study:     一致 / 已变更
```

`base_yaml` 逐条 diff 靠 `classification.json` 里存的 `ref_params` 快照与当前 yaml 对比；每条按「在 `SCAN_GRID`/`WHERE_LEVELS`/`WIDE_OVERRIDES` 中」→ 标 D/F/W 维或宽进覆盖，否则标「底座常量」。条目删除不特殊处理——`Params.from_dict(strict=True)` 在 build 时自然失败。

**为什么值必须比**：底座 yaml 不是搜索空间，是搜索空间之外的一切。bb_v1 的 25 个参数里 11 个在搜（网格覆盖，底座值无所谓），14 个在全部 442,368 格里取底座值不动——这 14 个变一个，整张长表换了世界。

## 4. 三个工具的 `main()`

| 工具 | 保留的 run 级常量 | 删除的手抄内容（改从 study/classification 读或推导） |
|---|---|---|
| `multivar_scan` | `APP`、日期、`HEAD_BUFFER`、`TICKER_REGEX`、价量过滤、H/K、`WORKERS`、`SHARD_STOCKS`、`OUT_DIR` | `PATTERN_ID`、`REF_PARAMS`、`WIDE_OVERRIDES`、`SCAN_GRID`、`WHERE_LEVELS` |
| `compare_longtable` | `LONGTABLE_DIR`、`TICKER_REGEX`、`WORKERS`、`N_RANDOM_CELLS`/`N_TIGHT_CELLS`/`SEED`、`MIN_WIN_BARS`、`OUT_LOG` | `SCAN_GRID`、`WHERE_LEVELS`、`WIDE`、`WHERES`、`MDD_DIM`、`MDD_FIELD`、`END_NODE`、`KEY_NODES`、`BASE` 路径；**以及 `APP`、日期、`HEAD_BUFFER`、H/K、价量过滤——全部改读 `run_meta.json`** |
| `region_find` | `LONGTABLE_DIR`、`FOLD_COL`/`FOLDS`、`MIN_COUNT_PER_FOLD`、`NEIGHBOR_AXES`、`B_BOOT`/`SEED`/`TOP_N`、`OUT_DIR` | `COMBO_LEVELS`、`FILTER_PREDS`、`WHERE_PREDS`、`REF_POINT`、`FLAG_RULES`；**以及 `APP`、`HEAD_BUFFER`——改读 `run_meta.json`** |

**run 级口径单源**：`multivar_scan` 是唯一声明 run 级口径的地方，除写 ledger 外另写机器可读的 `longtable/run_meta.json`（`APP`、`START/END`、`HEAD_BUFFER`、`LABEL_HORIZON`、`FIRST_PASSAGE_K`、`PRICE_MIN/MAX`、`VOLUME_MIN`、`git_head`、`fingerprints.study`）。`compare_longtable` 与 `region_find` 从它读——对拍的 label 口径（日期/H/K/价量）本就必须与扫描逐字一致，以前靠人抄一遍保证，现在结构上不可能不一致。`region_find` 现有的 `_check_head_buffer` 正则核对随之删除。

推导规则（写在一个共享 helper 里，三个工具共用；helper 放在 `multivar_core.py` 之外的新小模块 `study_io.py`，因为它是 I/O 与文件约定、不是纯算法）：
- `COMBO_LEVELS` = `SCAN_GRID` 中 `kinds != "F"` 的维 → 点号键
- `FILTER_PREDS` = F 维 → `(node_col(filter_fields[d]), op, levels)`
- `WHERE_PREDS` = W 维 → `(node_col(where_fields[d]), op, levels)`
- 对拍 `WHERES["wide"]` = 每 W 维取 `loosest_level`；`KEY_NODES` = `bound_nodes`；`END_NODE` = `end_node`

**启动一致性闸**：`multivar_scan` 加载 `classification.json` 后核 `fingerprints.study` 与当前 `study.py`，不一致 `SystemExit`「study.py 已改，先重跑 app_setup」；`compare_longtable` / `region_find` 另核 `run_meta.json` 里记录的 `fingerprints.study` 与当前 `classification.json` 的一致（长表是在哪份 study 下扫的，就只能用那份分类去切它）。源码/底座指纹不在工具里挡（那是询问协议的事），只写进 ledger。

**对拍 mask 统一按 `kinds` 分派**：每个维按 `kinds[d]` 选 `filter_fields`（F，`>=`）或 `where_fields`（W，op-aware）取列与 op；`TIGHT_WHERES` 里混有 F 维（如 `tb.max_day_drop_pct`）也走同一条路，原 `MDD_DIM/MDD_FIELD` 特判随之消失。

**用法保留「复制到研究目录改常量」**，四个入口脚本（含 `app_setup.py`）一律复制后再改，复制的只是 run 级常量，app 声明留在 skill 内不复制。**原件里 `APP = None`**，未填直接 `SystemExit`「复制到研究目录后在 main() 顶部填 APP」——这既是「勿直接跑原件」的硬闸，也让通用区真正零 app 专名（验收 gate 4 据此严格成立）。`OUT_DIR` / `LONGTABLE_DIR` 默认值指 `outputs/tune_gates/<APP>/`（`outputs/` 已在 `.gitignore`），杜绝直接跑原件写进生产研究目录的事故。

## 5. 入口协议（写进 SKILL.md，Claude 不许跳）

```
用户调 skill，指明 app X
├─ apps/X/ 不存在 → 首次接入
│    cp -r apps/_template apps/X → 与用户一起填 study.py 五项声明
│    → app_setup MODE=build → 对拍必做（reference.md §4.0 表第一行）
└─ apps/X/ 存在
     app_setup MODE=check → 三行报告原样给用户看
     → 问：「上次为 X 生成耦合内容是 <generated_at>。app 自那以后改过吗？要重新生成吗？」
       ├─ 用户：没改 / 复用 → 用现有 classification.json
       └─ 用户：改了 / 重生成 → app_setup MODE=build
            → 按 §4.0 表决定对拍：source 变 → 完整重做；只 base_yaml 变 → 免对拍
```

**指纹是证据不是裁定**：三行全「一致」也要问；指纹报变更但用户裁定复用也听用户，但 Claude 把「指纹不一致、用户裁定复用」写进本次 ledger。

## 6. 文档拆分

**`SKILL.md`**：七步流程里的 bb_v1 例子（毒药组 0up/12dn、peak_age max=507 只测到 180 等）改通用表述，案例移 `apps/bb_v1/notes.md` 并留「实例见 `apps/<app>/notes.md`」；「入口粒度」后新增「入口协议」节 = §5 决策树；用法段改为：复制四个入口脚本到研究目录 → 填 `APP` → `app_setup`（首次 build / 复用前 check）→ 依次跑 scan / compare / region。

**`reference.md`**：§0-§7 骨架保留，**全部 bb_v1 数字撤出**（1024 组合、442,368 格、20.3 分钟、439,824 次比较、ĉ 等）迁 `notes.md`；§8 坑清单每条保留通用教训，案例改「例：bb_v1，见 notes.md 坑 N」；§3.1 WORKERS 定标是机器相关，留通用区、标明机器；附录 A 整体迁出；顶部加「证据目录 `docs/research/...` 是一次性产物可能被清理，本卡自足」。

**`apps/bb_v1/notes.md`**（新）：承接迁出内容 + `final_report.md` 关键读数摘要（未发现稳健区那组数字）+ **上次对拍作用域记录**（对拍过的 grid/where 集合、mismatch=0、日期、commit）——供下次「要重做对拍吗」有据可查。

**边界规则**（写进 SKILL.md）：通用区文档禁止出现具体 app 的参数名、节点名、数字；举例一律指向 `apps/<app>/notes.md`。

## 7. 测试与验收

**测试改造**：`test_multivar_core.py`/`test_multivar_equiv.py` 的 `BASE` 改读 `fixtures/bb_v1_p2_wide.json`；测试内 `SCAN_GRID` 字面量保留（测试自带数据）。它们仍 `import path2_apps.bb_v1.dag_spec`——测 `classify()` 必须有真 app，此耦合不可消，注释明说。

**新增测试**：
- `app_setup` build 对 fixture 生成 → `kinds`/`filter_fields`/`where_fields` 与迁移前手抄值逐项相等（迁移正确性直接证据）；`end_node`/`bound_nodes` 与 `eval_meta`/`compile_plan` 一致
- 指纹：改 yaml 注释 → `base_yaml` 指纹不变；改一个值 → check 报告列出该条且标签正确（底座常量 vs D 维）；改 `study.py` → 工具启动 `SystemExit`
- 每个新断言至少做一次突变测试（拿掉被测修复必须红）

**四道验收 gate，全绿才交付**：
1. `uv run pytest .claude/skills/tune-gates/` 全绿
2. `mv .claude/skills/tune-gates/apps/bb_v1 <scratch>/ && pytest` 仍全绿，然后移回——「删耦合区不伤通用区」的直接证明
3. 迁移等价：新 `compare_longtable` 在 `^AA` 子集 → **7752 次、mismatch=0**（与迁移前逐字相同）；新 `region_find` 对现有长表重跑 → `region_report.md` 关键数字（naive +0.0705 / optimism 校正 −0.0557 / split-half −0.1319 / 稳定性 0.07）逐字不变
4. `grep -rn "bb_v1\|\"burst\"\|\"tb\"\|\"bo\"\|burst\.\|tb\." SKILL.md reference.md multivar_scan.py compare_longtable.py region_find.py app_setup.py study_io.py` 命中 = 0（`apps/_template/study.py` 不在此列，但它也不得含 bb_v1 专名——模板注释用 `<node>.<param>` 占位）

**不动的东西**：`docs/research/2026-08-25_multivar-bb_v1/` 原样保留（含 `repro/` 与三份 `region_find` 副本）——那次研究的证据，不再是 skill 依赖。唯一例外：`repro/bench_workers.py` 搬进 skill 后研究目录那份删除（它从来不是研究产物）。

## 8. 明确不做

- 不改 `multivar_core.py`/`region_core.py`/`path2/dag/`
- 不把声明下沉到 `path2_apps/<app>/`（方案 B，已否决：grid/参照格是研究选择非 app 常量，且违反「耦合可手删」）
- 不做多 study 并存（每 app 一个 `study.py`；历史 grid 属研究记录，归 `docs/research/`）
- 不做 argparse；`MODE` 是 `main()` 顶部常量
- 不为旧 scan 文件 / 旧长表做兼容（`.claude/rules/scan-file-no-backcompat.md`）
- 不重新校准功效线 100 / `REL_TOL 0.05`（仍标「仅 bb_v1 校准过」，属另一任务）
