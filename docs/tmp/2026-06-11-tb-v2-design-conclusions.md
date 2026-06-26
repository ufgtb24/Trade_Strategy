# tb v2 迭代设计结论（临时设计状态）

> 状态：**部分敲定、部分待裁**。burst 重叠机制（all_ends / 密度聚类）已派 agent team 深挖，
> 其结论会反过来影响「tb 扫描终止规则」与「burst→tb 边锚点」两项。
> 本文先冻结已敲定的部分，避免结论散失在对话里。

## 背景

tb v1（可买入区间事件）已实现并合入 path2web2（commits `d93a9d7..e8a8bb0`，
spec=`docs/superpowers/specs/2026-06-11-path2-tb-buy-window-redesign.md`）。
v1 语义：`[start_idx, end_idx]` = 回踩成功后的可买入窗；start=止跌点（回落段最低点）、
end=大涨前一根/timeout；破位 anchor ⟹ 不产事件；纯走势（无成交量门）。

用户随后提出 6 条 v2 需求，经逐条评估 + 两轮 AskUserQuestion 收敛，结论如下。

## 已敲定的设计结论

### 1. 扫描起点严格 `bo_idx + 1`（需求 1）
v1 已如此，保持。tb 的每次评估针对单一 bo。

### 2. 预算参数拆分（需求 3）
删 `throwback_N`（单一预算同时当止跌搜索窗+买点窗，语义混）。新参数：

| 参数 | 默认 | 约束 |
|---|---|---|
| `throwback_max_start_gap` | 5 | `tb.start_idx − bo.end_idx ≤ 5`（买点不离 bo 过远） |
| `throwback_max_window` | 5 | `tb.end_idx − tb.start_idx ≤ 5`（买点窗不持续过长） |

第一性原理依据（用户）：买点不应离突破过远，买点窗也不应过长。

### 3. anchor / 破位判断参数化（需求 4，多关卡机制已取消）
- **多关卡 AND 机制取消**。数学论证：用户举的嵌套窗（`[bo-N:bo].max()` 与
  `[bo-N:bo-1].max()`）做 AND，「全部跌破」= `low < min(各关卡)`，嵌套窗下 min 恒等于
  小窗那道 ⟹ K 道坍缩成单道，毫无增量。
- 取而代之两个 measure 参数（复用 breakout.py 的 `_measure`，扩展支持 `"low"`）：
  - `throwback_anchor_measure: str = "high"` —— anchor = `_measure(df, bo_idx-1, anchor_measure)`
  - `throwback_support_measure: str = "low"` —— 破位 = `_measure(df, i, support_measure) < anchor`
- 默认值即 v1 现行为（`low[i] < high[bo-1]`），纯参数化、零行为变更。

### 4. ATR 取 `bo_idx − 1`（需求 6）
回落门与大涨退出共用的 ATR 从 `bo_idx` 改为 `bo_idx − 1`：bo 当根有异常波动
（大阳线 TR 膨胀），会污染 Wilder ATR 当根值。
「超跌」语义 = 破位 anchor（⟹ 不产事件），**无**独立的 ATR 跌幅退出条件。

### 5. bo detector measure 配置与改名（需求 5）
- `BODetector` 参数 `breakout_mode` → `breakout_measure`（与 `peak_measure` 命名统一）。
- `Params.bo_breakout_mode` → `bo_breakout_measure`。
- 两者默认值 `body_top` → `high`（peak 与 breakout 都按 high 度量）。
- ⚠️ 这是**全局 bo 行为变更**（high ≥ body_top ⟹ 更多突破点），须重跑全宇宙扫描对照。

### 6. 超跌语义（需求 6 附属，AskUserQuestion 已拍）
超跌 = 破位 anchor（不产事件）。不新增独立的「base_min 之上 drop≥k×ATR」退出。

## 已裁项（agent team 已收口，全文见 `docs/research/2026-06-11_burst-all-ends-density/final_report.md`）

### A. burst 重叠机制：all_ends（买家视角）+ 密度聚类 —— ✅ 已裁定
用户的核心诉求 = **不错过买点**，思考框架 = 买入视角（只根据过去判断）：

- 买家在**每个 break point 上回望**：「当前及过去一段时间是否形成连续突破？」
  ⟹ burst 检测应是 **all_ends**（每个 bo 作为潜在 last_bo 回望成串），
  而非 all_heads（变起点）。例：bos `[0,1,2,3,4]`，站在 bo2 回望得 `[0,1,2]`，
  站在 bo4 回望得 `[0..4]` —— 起点固定（0），终点各异 ⟹ 嵌套同 start 异 end。
- **固定回看窗有缺陷**：bos `[70,80,85,90,95]`、窗 20：从 90 回望含 70，
  从 95 回望 95−70=25>20 ⟹ 70 被踢出 —— 但 70 明明紧贴这一串。
  ⟹ 不应采用「从判断点往前看固定窗口」；真正目标是**把以异常密度聚在一起的
  一串 bo 找出来**（密度聚类，方法待团队设计——候选方向：相邻 gap 链式聚类等）。
- 现状（代码事实）：`BurstDetector` 是贪心非放回（`i=j` 不回头，自称 ==kleene），
  全 codebase 无任何 detector 支持重叠（trend=regime 真分区、platform=贪心、
  bo/dist=单 bar 点事件）。当前参数下贪心≡all-heads（drought≥60>max_span=20，
  全集 DIFF=0），漏检是休眠的，bo 变密才激活。
- 用户立场：kleene/贪心不合理、会漏检；grouping 类事件应支持重叠。

**裁决（team 三方交叉一致）**：all_ends 因果维度严格成立（end=当前 bo 即时物化，
完整 last_bo 覆盖）；但「固定起始」是 **chain 链式聚类（相邻 gap≤g 链接）下前缀族**
的属性、非 all_ends 枚举族本身——用户批判的固定回看窗正是 span 规则，真正的设计
动作在聚类规则层（span→chain）。参数 `g=5`（实证双峰：簇内 92% gap≤5、背景 p90=17、
6~16 空档；自适应/截断/DBSCAN 均否决）。无界链=feature 不截断。重叠原则收窄为
「识别类（burst/tb）许重叠、划分类（trend regime）禁止」。
⚠ 参数考古：`THR_DROUGHT` 双源分裂（dataclass=20 生效 / yaml=60 不走全集入口），
旧「all-heads≡greedy、DIFF=0 休眠」定理前提已破，旧等价性结论不可再引用。

### B. 受 A 影响的两个下游决策 —— ✅ 已据 A 定稿
- **tb 扫描终止规则**（原需求 2「遇下一个 bo 即终止」）：**正式撤销**。
  保持 per-bo 独立扫 + 按 span 去重（即现实现 commit `9a2f252` 行为）。
  skeptic 证实 tb 流与 burst 切串正交，「每个 last_bo 都被判」已结构性成立、tb 无需改。
- **burst→tb 边锚点**：**定稿**改 `Child(burst,"last_bo")` + `max_gap =
  throwback_max_start_gap`（=5），两项必须同步（只改锚不收 gap ⟹ 中段 last_bo 的
  tb 窗跨过同簇后续 bo、语义错位）。semantics §6.5 证明锚 first_bo 时同簇前缀在
  match 层塌缩、「每个 last_bo 独立买点」不兑现——改锚 last_bo 是买家诉求的传导路径。
- **（新增）burst 切串**：`BurstDetector` 从 span-greedy 改 chain(g=5)-all_ends
  前缀物化；`burst_max_span` 退役 → `burst_gap_max=5`；`MIN_BOS` 保留；
  隐含约束 `THR_DROUGHT > g`。

## 下一步

1. ~~agent team 裁定 A~~ ✅ 已完成（final_report.md）。
2. 据本文（已定稿的 v2 全部结论 + A/B 裁决）更新 v2 spec，走 writing-plans →
   subagent-driven 实施。
3. **实施 gate**：2×2 析因 `{span,chain}×{greedy,all_ends}` 全宇宙 `res.matches`
   DIFF（hit/LOST/new + 短/长链分桶，每格开 RUNTIME_CHECKS）+ 前端体积评估
   （res.events ≈54/ticker 渲染承载，不够则物化层折叠、非截断链长）。
