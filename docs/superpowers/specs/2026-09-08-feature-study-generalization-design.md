# feature-study 通用化设计

> 2026-09-08 · 把 `.claude/skills/feature-study/` 从耦合 bb 系 pattern 改成任意 path2 app 可用。
> 本文中所有项目内路径均相对 repo root。

## 1. 背景

`feature-study` 的六步流程与统计电池（`run_battery.py`）的**算法**是 pattern 无关的：`controls` 是入参，FDR / 秩回归 / 双维去簇 / 尾部富集全部只认列名。**耦合主要集中在数据构建层** `extract_skeleton.py`（189 行），另有一处在电池的列名默认值上。

实测清点，pattern-特异点共 **9 处**，而文件注释只标了 3 处：

| # | 位置 | 内容 | 注释是否标注 |
|---|---|---|---|
| 1 | 37-38 | `from path2_apps.bb_v1...` 两行 import | ✅ |
| 2 | 44-45 | `PATTERN_ID` / `END_NODE` | ✅ |
| 3 | 54 | `TB_OVERRIDES`（快照兼容） | ❌ |
| 4 | 129-130 | `m.node_index["tb"]` / `["burst"]` | ❌ |
| 5 | 131 | 去重键 `(sym, tb.instance_id, tb.anchor_bo_id)` | ❌ |
| 6 | 133-135 | `evs[tb.anchor_bo_id]`、`burst.members[0]` | ❌ |
| 7 | 143-150 | `first_bo_idx` / `burst_count` / `bo_drought` / `bo_vol_ratio` | ❌ |
| 8 | 153-161 | 控制列 `m1_burst_runup` / `m2_depth_rel` 的几何 | ❌（反被标为"标准控制列，勿删"） |
| 9 | 163 | `match_forward_returns(m, "tb", ...)` | ❌ |

37-38 行那句注释「其余骨架 pattern 无关」由此证伪。

**第 10 处在电池里**：`run_battery.py:109` 的 `time_col: str = "tb_start"` 是默认参数（算法本身可传任意列名，不硬编码），但默认值与第 26-27 行的 CSV 约定文档都写着 `tb_start` —— 一个 bb 系专有名字（tb = throwback）。`SKILL.md` 第 3 步的调用示例不传 `time_col`，因此实际依赖这个默认值。

**另有三个连带问题**：

- **第 9 处是 bug**：44-46 行定义了 `END_NODE = "tb"`，105 行 `_resolve_end_events(m, END_NODE)` 用了常量，163 行却写字面量 `"tb"`。改 `END_NODE` 不生效，end_node 非 tb 的 pattern 会静默用错买点锚。
- **控制集冷启动**：`SKILL.md` 规定控制列只能来自登记簿「已关闭」段判定"有信号"的条目。新 pattern 首轮研究时该段必为空 → `controls=[]` → 关 2 整体跳过 → 全部判定降级。而首轮恰是建立认知的时候。
- **两个工具用法不一致**：`run_battery.py` 是 `sys.path.insert` 后 import 的，`extract_skeleton.py` 是复制到研究目录改的。

## 2. 目标与非目标

**目标**：换 pattern 时只写一个 per-app 文件，通用骨架不出现任何 `path2_apps.*` 字面 import、不出现任何 node 名。

**非目标（YAGNI）**：
- 不支持 path2 之外的东西——两道自检门依赖 scan 文件与 `path2.eval.match_forward_returns`，跨出 path2 无意义。
- 不做 tune-gates 那样的 `install` 自动生成。那边 `study.py` 是纯常量所以可渲染；这边核心是 `observe()` 里的几何计算，属走势语义，生成不出来，硬做只得到一个要人重写的空壳。只提供 `_template`。

## 3. 设计

### 3.1 文件布局

```
.claude/skills/feature-study/
  extract.py            # 通用骨架(原 extract_skeleton.py,改名 + 从"复制模板"改为"可 import 的库")
  run_battery.py        # 统计电池,不动
  apps/
    _template/adapter.py
    bb_v1/adapter.py    # 从现骨架搬出来的 bb 系耦合
```

布局与 `.claude/skills/tune-gates/apps/<app>/` 对齐，同仓两个 skill 用同一套心智模型。

### 3.2 adapter 接口

per-app 唯一要写的文件，导出三常量一函数：

```python
APP_MODULE = "path2_apps.bb_v1"          # 骨架据此动态 import build_pattern / Params / eval_meta
PARAM_OVERRIDES = {"tb": {"max_day_drop_pct": None}}   # 快照兼容,按 yaml section 分组
DEDUP_COLS = ("symbol", "tb_id", "bo_id")              # observe 返回的哪几列构成一条观测的身份
KNOWN_SIGNALS = ["m1_burst_runup", "m2_depth_rel"]     # 已知信号列名;登记簿关闭一条就加一条

def observe(m, evs, win, atr) -> dict | None:
    """一条 match → **仅 pattern 特异的列**:锚点索引、走势原始量、KNOWN_SIGNALS 各列。
    返回 None = 这条不进样本(边界不足等)。合并原骨架的 129-135 / 143-150 / 153-161 三段。
    atr 为整列 np.ndarray(骨架预算,窗口 14)。"""
```

**列的归属划清**——骨架注入通用列，`observe` 只管走势特异的：

| 列 | 由谁产出 | 说明 |
|---|---|---|
| `symbol` | 骨架 | 当前股票代码 |
| `label` | 骨架 | 官方 `match_forward_returns` 重算并过自检门 |
| `entry_idx` | 骨架 | 买点在窗内的 bar 序号 = `m.node_index[end_node].start_idx`；时间桶去簇用 |
| `entry_date` | 骨架 | `entry_idx` 对应日期，事件诊断可读用 |
| `c0_atr_pct` | 骨架 | 通用波动率控制列，见 3.4 |
| 其余一切 | `observe` | 锚点索引、走势原始量、`KNOWN_SIGNALS` 各列 |

`entry_idx` 由骨架产出而非 adapter，理由同 `END_NODE`：它能从 end_node 事件推出来，不该让人填。它同时取代原来那个 bb 专名的 `tb_start`（见 §4 第 5 条）。

设计取舍：

- **`END_NODE` 不进 adapter**，骨架从 `eval_meta()` 取。项目铁律保证每个 app 必导出它；能推导的不让人填，填错也没人拦。顺带消灭第 9 处字面量。此原则与 tune-gates `_template/study.py` 的「只放推不出来的」一致。
- **去重从函数降级为列名声明**。原为流式 `seen` 集合，改为 `observe` 正常返回、骨架事后 `drop_duplicates(DEDUP_COLS, keep="first")`，语义等价（均保留首次出现）。代价是多算若干最终丢弃的行，几何计算成本可忽略。
- **`observe` 合并三段**：输入相同、都是走势语义，拆开无收益。返回 `None` 替代原先散落的两处 `continue`。

### 3.3 骨架职责

保留且全部 pattern 无关：动态 import `APP_MODULE`、从 `eval_meta()` 取 end_node、切窗、`dag_analyze`、serialize 同口径过滤、两道自检门（match 集逐股对齐 + label 官方重算 `<1e-12`）、ATR 预算、去重、落盘。

**用法改为 import**，与 `run_battery.py` 拉齐。每轮研究脚本约二十行：

```python
import sys; sys.path.insert(0, "<repo>/.claude/skills/feature-study")
from extract import build_dataset
from apps.bb_v1 import adapter

def compute_features(win, o):
    ...   # 这一轮要验的特征口径族,唯一需要创造性的部分

build_dataset(adapter, scan=SCAN, out_csv=OUT_CSV, compute_features=compute_features)
```

骨架后续修 bug 自动惠及所有研究，不必回头改各自复制的副本。

### 3.4 通用波动率控制列

骨架自算 `c0_atr_pct`，**不进 adapter**：取买点（end_node 事件 `start_idx`）**前一根**的 `ATR / close`。前一根保证时点安全（决策时刻已知）。口径与 2026-09-07 研究中使用的「买点日 ATR% 三分层重加权基线」同源。

**ATR 窗口固定 14，不从 params 取**：控制列不需要与 detector 同源，它只是混杂控制；跟着 pattern 参数走会让不同 pattern 的控制列不可比。

于是控制集 = `["c0_atr_pct"] + adapter.KNOWN_SIGNALS`。新 pattern 冷启动时后半段为空但控制集非空，**关 2 照常跑、判定不降级**；随登记簿关闭条目，per-app 那半段逐步长起来。

依据：本轮登记的 FC-009「`forward_return` 的优势全是波动率读数」——波动率是跨 pattern 最普遍的混杂源，本就该在控制集里。

## 4. SKILL.md 改动（四处）

1. **第 2 步「数据构建」整段重写**：接新 pattern 复制 `apps/_template/adapter.py` 填四样；每轮研究只写二十行脚本。删去已证伪的「其余骨架 pattern 无关」。
2. **控制列改为两段拼接**：`c0_atr_pct`（骨架给的通用地板）+ `adapter.KNOWN_SIGNALS`。`m1_burst_runup` / `m2_depth_rel` 从「skill 的标准配置」降级为「bb 系当前的已知信号」，物理位置搬进 `apps/bb_v1/adapter.py`。
3. **第 6 步归档规矩落地**：原文「判定"有信号"的同时把它加进本 skill 的标准控制列清单（第 2 步）」无处可加——第 2 步只是文档描述。改为加进 `apps/<app>/adapter.py` 的 `KNOWN_SIGNALS` 并在 `observe()` 里实现其计算。
4. **新增「接入新 pattern」节**：复制模板、填四样、`KNOWN_SIGNALS` 起手留空。
5. **第 3 步的电池调用示例**：`run_battery.py` 的 `time_col` 默认值由 `"tb_start"` 改为 `"entry_idx"`，同步改第 26-27 行的 CSV 约定文档。算法一行不动——只是把默认列名从 bb 专名换成通用名。无存量研究依赖旧列名（见 §5），可直接改。

## 5. 验收关卡

**在 bb_v1 上真跑一轮完整六步**，产出第一个 `docs/research/<日期>_feature-study-<slug>/`。

理由：清点发现 `docs/research/` 下**没有任何 `*feature-study*` 目录**——该 skill 自 2026-08-20 建立至今，完整归档流程一次都没走过（骨架本身在 `20260818T110622` 端到端验收过，但没留下按第 6 步归档的研究目录）。不跑这一轮，等于把一个没跑过的东西重构成另一个没跑过的东西。

**验收判据是机制性的，不依赖统计结论**：

- 两道自检门通过（match 集逐股对齐、label 逐 match `<1e-12`）
- 控制集非空且关 2 未降级（`c0_atr_pct` + m1/m2 三列都在）
- 六步走完，产出 `final_report.md` + `dataset.csv` + 二十行脚本
- 登记簿 `docs/feature_candidates.md` 回写一条

**明确不作为判据**：结论要与 2026-09-07 那轮研究复现。两者**宇宙不同**——feature-study 的样本是「pattern 已成立的 match」（全部过闸），那轮用的是宽进池（含被闸拦下的样本）。拿结论对齐会误判。

## 6. 已知取舍

**研究目录脚本不再自包含**。改前每份研究里躺着完整 189 行骨架，可逐位复现；改后 import 的是 skill 当前版本。接受此代价：skill 在 git 里，重现走 checkout 到研究报告提交时的版本；每份研究存一份骨架副本反而制造「哪份是真的」的困惑，且今天这个 `"tb"` 字面量 bug 会永远躺在每份历史副本里。

清点确认**当前无存量研究依赖现有形状**，此代价基本落空。

归档语义相应变为：研究目录只存**研究特异**的东西（二十行脚本、`dataset.csv`、报告），通用工具版本由 git 管。
