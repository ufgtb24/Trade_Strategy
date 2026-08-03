# 共享简报 · path2_app 优化工作流设计研究

> lead 主会话已现场核实的事实底座。**所有数字/路径都是 2026-07-25 现场读的**，但你仍需对与你结论相关的关键点自行复核（红线：不得引用本简报里的参数快照当依据，要用就现场读代码）。

## 0. 用户诉求（原文要点）

> 让 claude code 自动帮我开发或优化一个 path2_apps —— 用 path2 构造筛选 pattern 来筛选会上涨的股票，设计一个适用于该任务的工作流。

三块：
1. **业务背景**：需求是「构建新 pattern」或「优化已有 pattern」，例如"横盘后出现代表启动的连续突破时买入"。当前 `bottom_breakout_burst` 就是干这个的，但不是最优的，要继续优化。
2. **机制研究**：claude code 有没有特定机制擅长「代码在批量数据中的优化」。已知工具：skill / agent team / workflow / ralph-loop / subagent / background agent / hook / cron；也可结合 optuna（参考 `BreakoutStrategy/mining/pipeline.py`）或自写实验脚本。
3. **人机结合**：人类擅长看 K 线图。用户的漏检诊断入口就是为此设计的——他看 K 线然后判断"这个地方应该被 detector 识别"。

**终极目标**：系统化地从顶层 dag 到底层 detector 代码的优化工作流，充分利用三种资源（claude code 能力 / 人类对 K 线的感性判断 / 大数据优化与测试）。用户可能只输入一句"我想要一个匹配 XX 走势的 pattern"或"优化这个 pattern"，工作流就自动运行。

**首要原则（用户明示）**：**最优化 > 最自动化**。不强求一键执行，可多步完成、多流程交替。可以一轮也可以多轮，迭代可在工作流内部（循环）或外部（用户多次调用）。中间可引导人类执行人类擅长的任务（如看 K 线找特定样本）。最终输出最优的 path2_apps 代码 + 参数。

**用户自陈的当前劣势**（关于他的人肉 detector 代码诊断）：
1. 无法批量处理，需要一个一个排查。
2. 不知如何让 claude code 介入。

---

## 1. 优化对象的三层自由度

一个 path2_app = `path2_apps/<id>/{dag_spec.py, params.py, params.yaml, __init__.py}`：

| 层 | 内容 | 现有覆盖 |
|---|---|---|
| ① dag 拓扑 | 节点集 / 类型化边（TemporalEdge / ContainmentEdge / NegationEdge / Child 端点选择器）/ detector 选型 | `authoring-path2-app` skill 层① |
| ② detector 代码 | `path2/atoms/*.py` 的判据函数（如 throwback 的 `_find_start_idx`/`_find_end_idx`、trend 的切段） + node 的 `where` 判据 | `authoring-path2-app` skill 层②（**但只是"设计+移交实现"，没有搜索/优化循环**） |
| ③ 参数 | `params.yaml`（SSoT，4 section: bo/burst/tb/edges） | `tune-pattern-strength` skill（**只能优化参数数值**） |

**用户明确指出的 gap**：`tune-pattern-strength` 只能优化参数，不能优化 detector 代码和顶层 dag 结构。

---

## 2. 现有资产清单（路径 + 能力边界）

### 2.1 评分标准（固定，不重新发明）
`docs/research/pattern_config_scoring_standard.md` — 必读全文。要点：
- `score = w·lift`，`lift = median_配置 − median_基线`，`w = n/(n+200)`，n = 买点窗数（按 end_node event_id 去重）
- 硬门：`n ≥ 200`、`q25 ≥ 0`、label 自检一致
- **排序一律用 `median_confirm`**（只取买点窗第一天，与窗宽无关），`median`（窗内逐日均值）只作对照——防"缩窗刷分"
- 禁前瞻偏差（如 tb 的 `outcome`）
- 基线 = `bo_only`（同 bo 参数、去掉 burst/tb 过滤）；2024 全年 n=23968 median=0.1159，2025 全年 n=29502 median=0.1234
- 跨期：两个整年窗按「最差 score」排序（可选，非硬门）

### 2.2 skills
- `.claude/skills/authoring-path2-app/`（SKILL.md 195 行 + design-heuristics.md 224 行）
  - 自顶向下三层 gate（拓扑→detector→参数），**每层用 `AskUserQuestion` 与用户确认**，故**必须在主会话 inline 运行**（AskUserQuestion 在 subagent/workflow 内不可用）
  - Step 0 入口分诊三路：创建 / 结构修改 / 纯调参（短路到 tune-pattern-strength）
  - Step 3 移交 `superpowers:writing-plans` → subagent-driven 实现。**本 skill 不自己实现**
  - Step 4 两段判据：判据1 形态（用户在环看 K 线）、判据2 统计（run_eval / run_regress）
- `.claude/skills/tune-pattern-strength/`（SKILL.md 140 行 + `eval_skeleton.py` 205 行 + `sweep.py` 63 行）
  - 流程：建对照 → 定判据 → 单因子消融 → 坐标扫描确认平台 → 诚实性三检查（极限测试/前瞻偏差/算术效应）→ 多窗口复核 → 误伤审查（run_regress）→ 定案
  - **明确声明「逻辑改造不在本 skill 内」**：逻辑改动只作为诊断出现（关掉某判据看 score 动不动），不作为候选实施
  - 自带 `eval_skeleton.py` / `sweep.py`，**要求复用不要重写**

### 2.3 workflow
`.claude/workflows/tune-dagspec-to-match.js`（170 行）—— 4 phase：Diagnose（目标票逐 gate 漏斗）→ Tune（迭代收敛到最小变更集）→ Verify（健全性 + 全宇宙影响 + 最小性对抗）→ Synthesize。
**关键局限：单样本**（一个 ticker + 一个窗口），且 CTX 里硬编码了大量"主会话已内联确诊"的结论——即真正的诊断智能在主会话，workflow 只是执行放大器。

### 2.4 评估器 `path2_web/eval_runner.py`（14397 字节）
三 mode 共享骨架，全宇宙 7532 只 pkl 多进程扫描：
- `run_eval(module_path, start, end, horizons=(5,10,20), out_path, param_overrides=...)` → 命中 + 多 horizon forward_return 分布，落盘 JSON
- `run_regress(baseline_path, param_overrides=...)` → 按 `(symbol, buy_date)` 对拍，返回 `added` / `removed`（带改前收益）/ `unchanged_count`
- `run_healthcheck(module_path, start, end, target_ticker=...)` → 新建/改动 detector 后全宇宙体检（数量级 + 目标命中 + errors）
- 切窗：双端缓冲（首部 `eval_meta.head_buffer_trading_days` warm-up，尾部 `label_horizon`）
- `param_overrides` 是 **nested dict**：`{"bo": {...}, "burst": {...}}`，worker 内 `dataclasses.replace` 局部 patch，不破坏 yaml SSoT

### 2.5 漏检诊断（人机接口，`path2_web/diagnose.py` + Vue 前端）
4 个入口（`.claude/docs/glossary.md` §5.1、`.claude/docs/modules/path2_web.md`「漏检 4 入口」节）：
- **入口 A**（`scope=time`）：K 线 brush 框选时段 → 列出 `failure_event_window` 完全落入框内的失败 attempt（跨界的只报 `outside_frame_attempts_count`）。**这是用户说的"漏检入口 A"**
- **入口 B**（`scope=nodes`）：拓扑点边查 miss_reasons 分布
- **入口 D**（`scope=pair`）：shift+click 两个 event 查为啥没连（4 个 subcheck 短路）
- **入口 E**：CLI workflow `scripts/scan-top-miss.py`（177 行）批量 markdown 排序 —— **已存在的批量入口，务必现场读它到底做了什么、够不够**

### 2.6 event 级断点调试
`path2/debug_ctx.py`（`_DEBUG_MODE` + `DEBUG_BAR_RANGE` env + `debug_break(i)` 双闸）+ `path2_web/api.py::/diagnose` 写 env + detector 内埋 `debug_break`。
用户在 K 线 marker 上**右键** → "Debug tb at bar X" → 后端写 env → detector 在 attempt 入口断点 → 用户在 PyCharm F10 单步看中间量。
研究报告：`docs/research/2026-07-15_event-level-debug-breakpoint/final_report.md`、`2026-07-15_event-debug-dual-emit-multi-anchor/final_report.md`
**这是纯人肉、单样本、需要 IDE 的通道——用户说的两个劣势就出在这里。**

### 2.7 其他
- `path2_apps/` 现有：`bottom_breakout_burst`（主）、`bo_only`（基线对照）、`high_close_streak`（空壳）、`try_conplex_where`
- `BreakoutStrategy/mining/pipeline.py`：optuna study（`OPTUNA_PKL`），前身流水线的调参方式，可参考
- 铁律：所有 pattern 必须声明 `eval_meta()`（返回 `end_role` + `head_buffer_trading_days`），discovery 闸过滤，无 fallback
- 数据：`datasets/pkls/` 7532 只
- 相关既往研究：`docs/research/2026-07-25_tb-recall-quality-tuning/`（评分标准的出处）、`2026-07-20_label-study-tb-pullback-vol-shrink/`、`.claude/skills/label-study/`（特征×label 三关判定工作流）

---

## 3. lead 给出的初步问题结构（可被推翻）

优化 = 在异质搜索空间上最大化 `score`：
- **层③参数**：数值空间，可被 optuna / 坐标扫描机械搜索，反馈信号是 score。已有 skill 覆盖。
- **层②detector 代码 + 层①拓扑**：离散、语义化的空间，**只有 LLM 和人类能生成候选**。目前完全没有搜索循环——`authoring-path2-app` 是"设计一次 + 移交实现"，不是"生成-评估-选择"的迭代。

两个候选杠杆（需要你们证伪或强化）：
1. **成本常数决定一切**：跑一次全宇宙 eval 的 wall-clock 是多少？这决定了能负担多少次候选评估，进而决定工作流是"少量高质量候选"还是"大规模搜索"。**必须实测，不要估**。
2. **人类 K 线判断的产出应该是一次性的标注样本集，而不是逐个诊断**：如果人类标注 N 个「这里应该被识别」的 `(ticker, date)`，就得到了一个可批量计算的 recall 目标；机器可以在这个目标 + score 双目标下搜索。`tune-dagspec-to-match.js` 是这个思路的 N=1 版本。这是否成立？代价多大？

---

## 4. 纪律

- **不写正式代码**。只做思考、分析、讨论。需要实验验证 → 临时代码放 `temp_code/`，用完删。
- 读文件省上下文：先 grep/glob 定位，再 Read 用 `offset`/`limit`。
- 工具调用纪律：中途消息正文至多一句状态行（无代码 token、不预告"我去调用 X"），随后直接发调用；长篇解释只放不再调工具的收尾消息。若发现自己把调用写成了正文文字，不要停笔，在同一条消息里立即发出真正的调用。
- 归档目录：`docs/research/2026-07-25_path2-app-optimization-workflow/`
