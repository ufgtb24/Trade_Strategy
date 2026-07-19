> **⚠️ DEPRECATED 2026-07-12** · 本 spec 已被 [`2026-07-12-failed-attempts-triple-strategy-design.md`](./2026-07-12-failed-attempts-triple-strategy-design.md) **取代**。
>
> 本版仅做"一手"（`op` + `threshold_param`），实测暴露 `phase1_break` 等 sentinel-numeric 卡片不可读、且开发者无法一站式理解 gate 语义。新版扩为**三手抓**：卡片表面自解释 + 源码位置动态获取（`code_location`）+ 逐 emission 通俗注释；契约不变式从"双向等价"放松为"单向蕴含"（`threshold_param is not None ⟹ op is not None`）；sentinel-numeric 补 op 但 `threshold_param=None`。
>
> **保留本文件仅供 commit 59cd893 / 6f43d74 / e9a5de0 / 2e0fcf0 溯源。** 新工作一律读新 spec。

---

# Failed-Attempts 卡片：Clause 结构化 · 参数名可追溯

**Spec 日期**：2026-07-13
**范围**：`path2/atoms/*.py`（Detector emission）+ `path2/dag/gate_failure.py`（契约）+ `path2_web_ui/src/components/FailedAttemptsCard.vue`（渲染）

## Context

漏检入口 A 卡片（`FailedAttemptsCard.vue:46`）当前用「`栽在 gate_name · measured vs 阈 threshold`」的一刀切句式渲染所有 gate 失败原因，对开发者不友好：

1. **参数名不可追溯**：卡片显示 `phase1_no_trough_timeout · 5 vs 阈 5`，看不出「阈 5」对应 `params.yaml` 的哪个参数——tb 段 `max_start_gap=5, max_window=5` 均为 5、无从区分该调哪个。真阈值型 gate 也一样，用户得靠 `gate_name` 猜「`chain_break` 的阈到底是 `gap_max` 还是 `min_bos`」。
2. **模板对 sentinel/timeout 型 gate 失真**：
   - **sentinel 型**（阈=`None`/`0`/`0.0` 硬常数，非可调参数）：`no_active_peak_broken`、`peak_already_active`、`peak_no_local_max` 两处、`phase1_break`、`phase2_break` 共 6 处，硬套模板后显示成 `X vs 阈 null` / `X vs 阈 0`——「阈」字面无意义、用户误以为是参数。
   - **timeout 自比型**：`phase1_no_trough_timeout`，`measured` 与 `threshold` 同变量必然相等，显示 `5 vs 阈 5` 完全无法读出参数。
3. **`MeasuredKindAware.label` 字段被丢弃**：后端产生的语义标签（如 `'峰-窗首侧翼'`）前端从未渲染，白扔一份可读性资源。

参考基准：marker tooltip 的 Clauses 段（`chart.ts:1462-1466`）已用结构化格式 `${cid}: ${measured} ${op} ${threshold} ${✓/✗}` 展示 clause 判定，例如 `distinct_pk: 3 >= 4 ✗`——**变量名 · 实测 · 通过条件比较符 · 阈 · 判定图标**四要素齐全，一眼可读。本设计把同一「结构化 clause」范式引入到 failed-attempts 卡片。

**目标**：卡片失败行结构化，让 op 与 threshold 参数名从 gate emission 源头一路传到 UI，用户看卡片一眼定位到 `params.yaml` 里该调哪个键。

## 设计原则

- **单一事实源（SSoT）**：op 与参数名在 detector emission 处填写（detector 作者最清楚判据语义），前端只做拼接、不维护映射表。
- **契约包容非阈值型**：新字段一律 `Optional`。sentinel/timeout 型 gate 把新字段留空，前端按 `op is None` 分支降级——不引入 `gate_type` 枚举、契约保持扁平。
- **减少中文**：卡片渲染沿用变量名与参数短名（英文），不消费 `measured.label`（后端字段保留、前端不再渲染）。
- **视觉复用**：句式与 marker tooltip Clauses 对齐（`${measured} ${op} ${threshold} (${param}) ${✗}`），行为一致降低认知负担。

## 契约变更

### `path2/dag/gate_failure.py`

`GateFailure` 增加两个 `Optional` 字段：

```python
@dataclass(frozen=True)
class GateFailure:
    failure_event_window: tuple[int, int]
    start_idx: int
    gate_idx: int
    anchor_bar: int
    class_id: str
    gate_name: str
    measured: MeasuredKindAware
    threshold: Any
    op: Optional[str]                 # 通过条件比较符 '>=' / '<=' / '=='；None = 非阈值型
    threshold_param: Optional[str]    # params.yaml 短名，如 'min_side_bars'；None = 无对应参数
    evaluation_lookback: Optional[tuple[int, int]]
    symbol: str
```

**语义定义**：
- `op` 表达「通过条件」的比较方向。例如 `peak_side_bars_insufficient` 的通过条件是 `max_local_idx >= min_side_bars`，则 `op='>='`；卡片读作「实测 3 需 >= 6 才通过、实际未通过」。**不是**实测比较符（那种会写成 `<`）。
- `threshold_param` 是 `params.yaml` 里的短名（不带 namespace），如 `min_side_bars` / `gap_max` / `pullback_min_atr`。因卡片顶部已显示 `class_id`（`bo` / `burst` / `tb`），与 yaml section 名一一对应，不加 namespace 前缀。
- 二者要么同时非 `None`（真阈值型 gate），要么同时 `None`（sentinel/timeout 型 gate）。序列化层（`path2_web/serialize.py` 或对应 gate serializer）需照透这两个字段。

### Detector emission 补齐清单

| 位置 | gate_name | op | threshold_param |
|---|---|---|---|
| `atoms/breakout.py:138` | `chain_break` | `<=` | `gap_max` |
| `atoms/breakout.py:162` | `min_bos_insufficient` | `>=` | `min_bos` |
| `atoms/breakout.py:312` | `no_active_peak_broken` | `None` | `None` |
| `atoms/breakout.py:363` | `peak_no_local_max`（window_start） | `None` | `None` |
| `atoms/breakout.py:385` | `peak_side_bars_insufficient`（首侧） | `>=` | `min_side_bars` |
| `atoms/breakout.py:398` | `peak_side_bars_insufficient`（尾侧） | `>=` | `min_side_bars` |
| `atoms/breakout.py:419` | `peak_already_active` | `None` | `None` |
| `atoms/breakout.py:434` | `peak_no_local_max`（window_min_low） | `None` | `None` |
| `atoms/breakout.py:448` | `peak_relative_height_insufficient` | `>=` | `min_relative_height` |
| `atoms/throwback.py:132` | `phase1_break` | `None` | `None` |
| `atoms/throwback.py:150` | `phase1_pullback_shortage` | `>=` | `pullback_min_atr` |
| `atoms/throwback.py:156` | `phase1_no_trough_timeout` | `None` | `None` |
| `atoms/throwback.py:183` | `phase2_break` | `None` | `None` |

`throwback.py` 侧 `_emit_tb_gate()` 辅助函数签名扩两个可选参数、四个调用点分别传入；`breakout.py` 侧无辅助函数、9 个 `GateFailure(...)` 构造直接补 kw。

## 前端渲染

### `FailedAttemptsCard.vue`

替换 L46 单行模板为 op 感知的两分支：

```vue
<div class="gate">栽在 {{ a.gate_name }}</div>
<div class="clause">
  <template v-if="a.op">
    {{ fmt(a.measured.value, a.measured.kind) }} {{ a.op }} {{ a.threshold }}<template v-if="a.threshold_param"> ({{ a.threshold_param }})</template> ✗
  </template>
  <template v-else>
    {{ fmt(a.measured.value, a.measured.kind) }} ✗
  </template>
</div>
```

（其余卡片元素——`class-id` 标题行、`window` 区间、`trigger bar`、`evaluation_lookback`——一律不动。）

### 渲染样例（三分支）

```
tb [155, 159]
栽在 peak_side_bars_insufficient
3 >= 6 (min_side_bars) ✗
触发 bar 159
```

```
tb [155, 159]
栽在 phase1_no_trough_timeout
5 ✗
触发 bar 159
参照历史 (140 .. 154)
```

```
bo [88, 88]
栽在 no_active_peak_broken
5155 ✗
触发 bar 88
```

sentinel/timeout 型时，卡片依靠 `gate_name` 自身表达失败语义（`no_active_peak_broken` = 没找到 active peak 可破；`phase1_no_trough_timeout` = 扫满 max_start_gap 没找到 trough）——`measured.value` 只作现场数据展示、无阈值对比。

### TypeScript 类型

`path2_web_ui/src/types.ts` 里 `GateFailure` interface 同步加：

```ts
op: string | null
threshold_param: string | null
```

保持 `null` 而非 `undefined`（与后端序列化保持一致）。

## 测试

### 后端

- `tests/path2/atoms/test_bo_on_gate.py` 与 `test_tb_on_gate.py` 现有 gate 用例补断言：
  - 真阈值型 gate emit 出的 `GateFailure` 满足 `op is not None and threshold_param is not None`；
  - sentinel/timeout 型 gate 满足 `op is None and threshold_param is None`；
  - 具体值按上表逐 gate 断言（例如 `chain_break` 断言 `op == '<=' and threshold_param == 'gap_max'`）。
- 序列化路径（若有 `GateFailure → dict` 层）补对应 key 透传测试。

### 前端

- `FailedAttemptsCard.vue` 组件测试新增两个用例（按契约「op 与 threshold_param 同生同灭」，只有两分支合法）：
  1. `op != null and threshold_param != null` → 渲染 `${value} ${op} ${threshold} (${param}) ✗`
  2. `op == null and threshold_param == null` → 渲染 `${value} ✗`
- 后端契约层增负向不变式断言：所有 emission 出的 `GateFailure` 满足 `(op is None) == (threshold_param is None)`——防止未来新增 gate 只填一半。
- 快照两张样例（`peak_side_bars_insufficient` / `phase1_no_trough_timeout`），锁定视觉输出。

### 端到端

启动 web，在真实数据上触发一个已知失败样例（`bottom_burst` 拓扑 tb 侧 `phase1_no_trough_timeout` + bo 侧 `peak_side_bars_insufficient`），肉眼确认卡片文本与 spec 样例一致。

## 非改动（明确排除）

- **不改** `MeasuredKindAware`（`kind` / `value` / `label` 三字段全保留）。
- **不改** marker tooltip Clauses 渲染（本次只对 failed-attempts 卡片改动）。
- **不改** 卡片其它元素（`class_id` 标题、`window` 区间、`trigger bar`、`evaluation_lookback`、下拉过滤、overlap 徽标）。
- **不引入** `gate_type` 枚举——三类型（threshold / sentinel / timeout）通过 `op` 是否 `None` 隐式区分即可。
- **不消费** `measured.label`——后端字段保留供未来复用，前端本次维持不渲染以贯彻「减少中文」倾向。

## 兼容性

- 后端 `GateFailure` 加字段为破坏性契约变更（frozen dataclass），所有 `GateFailure(...)` 构造点必须同步补齐——detector 侧上表已穷举；`_reify.py` 的 `EdgeWitness` 走另一路径不涉及。
- 前后端同 commit 一并落地（不引入异步版本）。
- `params.yaml` 无变更。
