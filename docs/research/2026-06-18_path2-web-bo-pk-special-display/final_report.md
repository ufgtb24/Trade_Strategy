# path2_web bo/pk 特殊显示设计裁定

> 日期：2026-06-18
> 任务：裁定 path2_web UI 中 bo/pk 是否应像 dev_ui 那样钉到 K 线主图，并消化"类型无关渲染器"红线压力。
> 团队：viz_lead（协调 + 拍板）/ kline_advocate（方案一）/ uniform_advocate（方案二）/ semantics_judge（第一性裁定）

---

## 结论速览

**采纳综合方案，不是凑数中间方案，引入两条正交且通用的契约协议：**

- **(A) render_grid 主分流**：新契约字段 `NodeSpec.render_grid ∈ {'price', 'time'}` 由 atom 作者一次性声明，决定**事件本体 marker** 落哪个 grid。bo 声明 `render_grid='price'` 钉 K 线主图三角；其余现役 atom（burst/trend/platform/tb 默认 'time'，dist 未来若入用必须显式 'time'）留 marker 副图沿用现状。
- **(B) 卫星 marker（referenced_points）**：扩展 `BOEvent.referenced_points: tuple[(bar_idx, price, label), ...]` 由 bo 自带下发。前端规则"**任何 render_grid='price' 事件**带 `referenced_points` 字段，就在每个 (bar_idx, price) 位置画带 label 的小 marker"——pk 编号通过 label 字符串内容承载（BreakoutDetector emit 时填 `f"pk{p.id}"`），**前端代码字面上不出现 "pk" 这个词，也不对 label 内容做条件分支**。pk 不升格为 event，只作为 bo payload 里的几何引用点存在。

两条协议都是 schema-driven、O(1) 分支，与 atom 数无关，不破"类型无关渲染器"红线；render_grid 是"语义中立的空间维度枚举"，referenced_points 是"语义中立的被引用几何点列表"，都不是 atom 命名白名单。

---

## 正面回答 4 个开放追问

### Q1 — 方案一 vs 方案二哪个合适？

**方案一（升格版）**。判据三条：

1. **信息论：方案一 +1 bit 解释力**。bo 的 (time, price) 二维语义同图呈现；pk 作为带编号 label 的卫星 marker 画在各自的 bar 位置 = 直接揭示 bo↔pk 突破关系的时间-价格几何。方案二只在同一 grid 呈现 time 维，price 与 pk 数据要靠 sidebar / tooltip 切换访问，**互信息严格更少**。
2. **眼动成本：方案一 0 跨 grid，方案二 ≥1 次跨 grid + sidebar 三段切换**。axisPointer cross 改善的是"找列"，没改善"跨 y 跨度"（K 线 grid 顶到 marker 副图 grid 视觉跨度 ≈ 视窗一半）。
3. **方案一可以做到不破红线**（见 Q2 / §红线处理）。这反过来反证：方案二防止"特殊化"的初衷可以靠契约升格满足，不必牺牲信息密度。

uniform_advocate 提的"axisPointer + band separator + sidebar 双向高亮 + tooltip pk 编号"四件套（下称"四件套"）的根本局限：**它把"bo 与突破的 K 线 bar 共现"和"bo 与 pk 编号共现"拆成两次空间访问**，且 tooltip 是 O(1) 单事件载体，无法支持"多个 bo 之间的横向比较"（哪个 bo 突破 pk 多 / 少）。常驻标签 `[1,3,7]` vs `[2]` 可以一眼横扫。

### Q2 — 点事件应统一显示还是 bo/pk 特殊化？

**既不"按 class_id 特殊化"，也不"按 isPoint 一刀切"，而是按 `NodeSpec.render_grid` 字段二分**。这条规则在三个层面成立：

- **数据模型层**：render_grid 是渲染坐标维度的语义中立枚举，atom 作者一次性声明"我属于价格坐标还是时间坐标"。bo / dist 几何上都是 isPoint，但前者锚价格、后者锚时间（dist 的语义是"放量阴线"——没有"派发"的正解 y 价位）。靠 isPoint 一刀切会让 dist 几何同构地被误送上价格 grid。
- **契约层**：render_grid 是 NodeSpec 字段（不是 EventDict 字段），由 atom 一次性自报，不随 event runtime 几何抖动（避免 BurstEvent 单元素退化 / TrendSegment 末段退化等"同 detector 同语义、跨 grid 分裂"的事实退化）。默认值 'time' = 守序保守（未声明的 atom 维持现状副图）。
- **前端层**：render_grid 二分 if + `referenced_points` 字段存在 if，共 **O(1) 个分支与 atom 数无关**，不破红线。

bo 与 pk 不是被特殊化的类型，而是**第一个声明 render_grid='price' 的 NodeSpec**。未来其他 atom 想上 K 线主图，填一行 NodeSpec 即可，前端零改动。

#### render_grid 与 referenced_points 是正交的两条协议

需要分清楚：

- **render_grid 机制**给**事件本体的主 marker** 分流 grid。pk 不是事件、没有 NodeSpec、不进入 render_grid 机制——pk 在 K 线上的可见性不靠 render_grid。
- **referenced_points 机制**让任何 **render_grid='price' 的事件**携带一组 `(bar_idx, price, label)` 几何引用点，前端按字段存在性渲染卫星 marker。这是独立于 render_grid 的一层，且同样 schema-driven、不读 class_id、不读 label 内容做条件、O(1) 分支。

两条协议各自通用、互不依赖。"pk 出现在 K 线上"的本质是"bo 在自己的 payload 里携带了若干被突破点的坐标 + 编号 label，前端按通用协议把它们画成卫星 marker"——pk 没有得到 event 身份、不需要 event 身份。前端代码字面上没有 "pk" 这个词；BreakoutDetector emit 时把 pk_id 塞进 label 字符串而已。未来若有别的 atom（例如"支撑反弹"原子）也想引用历史关键点，填同一个 `referenced_points` 字段即可，前端零改动——这点和 render_grid 的"未来 atom 想上 K 线就声明 render_grid='price'"是对偶的。

#### 字段命名理由：为什么是 `render_grid` 而不是 `anchor`

`path2/dag/edges.py` 已有 `TemporalEdge.anchor_field` / `anchor_src_field`（整改四），语义是**"事件↔事件 event_id 复核键"**——dst 端 event 的某字段必须等于 src 端 event 的某字段（默认 `event_id`），是边上的引用约束。用法见 `path2_apps/bottom_breakout_burst/dag_spec.py:14` 的 `anchor_field="anchor_bo_id"`，且已经是 `path2/dag/_solve.py:101` signature_fields 推导源 + `path2/dag/spec.py:117 _validate_anchor` 校验对象。

新提议字段的语义是**"事件↔渲染坐标系"**——节点的事件 marker 应该画在哪个 grid。这与上面的"事件↔事件引用"属于**完全不同的范畴**。若沿用 `anchor` 一词，spec 作者每次写 `dag_spec.py` 都要分清两种 anchor（边上一种、节点上一种），且阅读 `_validate_anchor` 时会被误以为牵涉新字段。

选 `render_grid` 的理由：
- 字面意思 = "这个节点的事件 marker 渲染在哪个 grid"，与前端 ECharts 的 `grid` / `yAxisIndex` 概念直接对应。
- 与 `anchor_field` / `anchor_src_field` 不共用任何关键词，无歧义。
- 默认值 `'time'` 守序保守不变。

### Q3 — tb（throwback）等其他点事件怎么处理？

**tb 不是点事件，是 span**（throwback.py:32-36 明文 start=止跌点、end=大涨前一根/timeout，跨多 bar）。用户原追问把 tb 视为"点事件中的低频项"是事实错误。

**tb 留 marker 副图**，render_grid='time'。理由：tb 的语义是"可买入窗口"，本身是时间区间，价格 grid 上没有合适的常驻表达；且 tb 的"是买点"语义已通过 `end_role` 协议 + 严格窗双竖虚线 + per-match `ret_N` 行表达，已是契约式呈现、零类型耦合。

其余 span 事件（trend/burst/platform）同理默认 render_grid='time' → 副图沿用现状。

### Q4 — "高频 vs 低频"作为分类轴是否合适？

**不合适，伪命题。** 三方一致裁定：

- **非 a priori 可知**：频率是 runtime 涌现属性，同一 atom 在不同股票 / 参数 / 窗口下出 0 个到 N 个不等，前端无法在扫描前确定它"是高还是低"。
- **不可证伪**：没有"高/低"的阈值定义。
- **统计偶然事实不应做渲染分类轴**：把它当轴 = 让渲染规则随数据漂移，违反契约稳定性。

拥挤问题的应然解：`packLanes`（render/geometry.ts 已实现）几何自适应分轨，重叠多就堆 lane，不换通道。

---

## 类型无关渲染器红线处理

### 红线的精确定义（semantics_judge 拍板，三方接受）

> 红线 = **前端代码不得让"画什么/怎么画"取决于事件类型枚举（class_id），等价于：前端分支数 O(1) 与 atom 数无关。**

> 绿区（不破）：按几何派生属性（isPoint）分支；按后端下发的语义中立枚举（如 `render_grid ∈ {price, time}`、`source_tag`）分支；按字段存在性（`if e.referenced_points`）分支。**前提：枚举集合不随 atom 增加而扩张**。

> 红区（破）：前端读 class_id 字面量做 if/switch；后端下发类别级 hint（如 `render_hint ∈ {bo_triangle, pk_label}`，只是把白名单从前端搬到契约）；按 OHLC 回写 EventDict 缺失字段（契约渗透）。

### 本方案的红线审计

逐条核对：

| 改动 | 分支特征 | 是否破红线 |
|---|---|---|
| `NodeSpec.render_grid: 'price' \| 'time'` | 语义中立空间维度枚举，O(1) | 不破 |
| 前端 `renderGridOf(e) === 'price'` 二路分流 | 字段读取，O(1) | 不破 |
| `BOEvent.referenced_points` 字段存在性 if | schema-driven，任何 render_grid='price' 事件可填 | 不破 |
| 价格 grid 上 marker y 派生 = `bars[e.start_idx].h + offset` | 渲染组合（不回写 event），ECharts 已有数据双源 | 不破（见下"契约渗透 vs 渲染组合"判据） |

### 契约渗透 vs 渲染组合（重要判据，戳法 1 处置）

uniform_advocate 提出 "BOEvent 无 price 字段 ⇒ 画到价格 grid 必须查 OHLC ⇒ 契约渗透"。**裁定：不成立，是渲染组合。**

判据小表：

| 维度 | 契约渗透 | 渲染组合 |
|---|---|---|
| 数据流向 | 前端用 OHLC 回填 EventDict 缺失字段 | EventDict 与 OHLC 在同坐标系并列绘制，互不修改 |
| 失败模式 | OHLC 缺失 ⇒ event 不可渲染 | OHLC 缺失 ⇒ event 可降级到副图 |
| grep 痕迹 | `event.price = bars[i].close` 这类回写 | 仅 `api.coord([event.start_idx, ...])` |

chart.ts 当前已是渲染组合形态（bars 与 events 两数据源 → 共 xAxis 不同 yAxisIndex），bo 上价格 grid 只需把 marker 的 yAxisIndex 改 0 + y 派生公式，**EventDict 字段零扩展、bars 字段零修改**。

唯一**真扩展**：要在 K 线上画 pk 编号（不在 bo 自身 bar，而在历史 peak 所在 bar），必须下发 peak 的 bar_idx + price + 编号 label。这通过扩 `BOEvent.referenced_points: tuple[(bar_idx, price, label), ...]` 解决——**作为 bo 的 payload 下发，不升格独立 pk event；字段语义中立（"我引用的几何点"），任何 render_grid='price' 事件都可用**（见 pk 处理节）。

---

## 分类轴拍板：「NodeSpec.render_grid」

| 轴 | a priori 可知 | 可证伪 | 信息论价值 | 评价 |
|---|---|---|---|---|
| 高频 / 低频 | ✗ runtime 涌现 | ✗ 无阈值 | 低 | **伪命题** |
| K 线锚定 vs span（裸 isPoint） | △ event runtime 可知 | ✓ 是 | 高 | 接近正确但**会被退化反例打穿**（BurstEvent 单元素 / TrendSegment 末段 isPoint 退化时同 detector 跨 grid 分裂） |
| 事件间内在关系（bo↔pk） | ✓ spec 边即定 | ✓ 是 | 高 | **关联轴，不是分流轴**，承担 tooltip / sidebar 关联呈现 |
| **`NodeSpec.render_grid`（拍板）** | ✓ atom 定义时即定 | ✓ 是 | 高 | **应然**：detector 级声明，不随 event runtime 抖动，前端 O(1) 分支 |

### 现役 atom 在 `render_grid` 轴上的归位

| atom (class_id) | 几何 | 当前所属语义 | `render_grid` 落点 |
|---|---|---|---|
| `bo` | point (start==end) | "这根 bar 突破若干 pk 高点" — 价格事件 | **`price`** |
| `burst` | span（链长 ≥3 实践不退化） | 密度爆发信号 — 时间区间 | `time` |
| `trend` | span（hysteresis 保证段长） | regime 区段 — 时间区间 | `time` |
| `platform` | span | 窄幅震荡平台 — 时间区间 | `time` |
| `tb` | span（[止跌, 大涨前]） | 可买入窗口 — 时间区间 | `time` |
| `dist` | point (单 bar) | 放量阴线派发 — 语义异质，价格 grid 无正解 y | `time`（**显式声明守序保守**） |
| `match` | span | pattern 命中跨度 | `time`（漏斗 / sidebar 视图，不直接 K 线呈现） |

未声明 render_grid 的 atom 默认 `time` → 守序保守，所有现役 atom 即便不改也能跑（维持现状），bo 加一行升级到 K 线。

---

## pk 处理：扩 BO 字段，不升格 event

**最终决定：pk 不升格为 path2 event；扩 BO 字段 `referenced_points: tuple[(bar_idx, price, label), ...]` 由 bo 自带下发，字段语义中立（"被引用的几何点"），通过通用卫星 marker 协议渲染。**

三层论据（不依赖 UI 偏好）：

1. **模型论 — 范畴错误**：pk 是 BreakoutDetector 实例的**滚动状态字段**（`_peak_id_counter` 跨 bar 演化），不是 occurrence。Event 是 occurrence 的载体；把 detector 内部状态升格为 occurrence 是范畴错误。
2. **机制论 — 无下游消费者**：pk 没有独立检测语义、生命周期被 `supersede` 规则绑死、所有 pattern 通过 `bo.broken_peak_ids / distinct_pk` 间接使用。把 pk 升格成 stream 后，**无 spec 有 `consumes_stream='pk'` 的 node**，机制空转。
3. **契约论 — 升格连锁反应**：pk 出流后下游 detector 凭什么不消费？W.attr("pk_count") 该读 pk event 还是 bo.distinct_pk？这会撕裂现有 atom 契约。

**pk 在 K 线上的渲染**：前端从 `bo.referenced_points` 直读，对每个 `(bar_idx, price, label)` 在该 K 线 bar 位置画一个小 marker（圆点 / 小三角等），label 字符串（BreakoutDetector emit 时填 `f"pk{p.id}"`）作为标注显示。这是 **schema-driven**：前端只判 `if (e.referenced_points)` 是否有字段，不读 class_id，不对 label 内容做条件分支；任何未来 render_grid='price' 事件想引用历史关键点都填这个字段。bo 自身的主三角仍由 render_grid='price' 走主 marker 通道；卫星 marker 是它的几何引用展开。tooltip 可在卫星 marker 上展开成 `pk3@2024-03-15 close=$52.30 [click→定位]`，sidebar pk 行 ↔ K 线 bar 通过 `selectedEventId` 双向高亮（机制现成）。

---

## `span × render_grid='price'` 的载入期校验

当前 `render_grid='price'` 的渲染规则只为 **point 几何**（`start_idx == end_idx`）定义：主 marker = 三角，y 派生 = `bars[start_idx].h * 1.005`。**span 事件（`start_idx != end_idx`）落入未定义象限**——若 atom 作者声明 `render_grid='price'` 但 detector 输出 span event，渲染规则不存在。

**裁定：spec.py 加载入期校验，显式拒绝。**

```
# path2/dag/spec.py PatternSpec._validate_render_grid (新增校验)
对每个 NodeSpec n:
    if n.render_grid == 'price':
        # 反射 n.detector.event_cls 的几何承诺，或在 NodeSpec 上增加一个
        # is_point_geometry: bool = True 的元属性供 atom 作者声明
        if not _detector_emits_point_geometry(n.detector):
            raise SpecValidationError(
                f"NodeSpec({n.tag}).render_grid='price' 当前只允许 point 几何, "
                f"但 {n.detector.event_cls.__name__} 是 span event。"
                f"若需 span × price，需先扩 event 价格字段 (y_band / y_start_end) "
                f"并扩 chart.ts 渲染规则 (见 §未来扩展路径 E1)。"
            )
```

为什么是显式拒绝而非静默 fallback：

- **静默 fallback 到 "point at start_idx"** 会**吞掉 span 信息**——作者本来可能想要价格区间叠层 / 端点钉价格, 单点渲染是误导。
- **显式抛错**强迫作者要么改 point 几何, 要么显式实现 (span × price) 规则后放行校验, **意图必然显化**。
- 这条校验是"一行 if + 一行 raise", 实现成本 ≈ 零, 但封死了未来"声明 render_grid='price' 又是 span"的 spec 错误的悄无声息发生。

校验放行的扩展路径见 §未来扩展路径 E1。

---

## 未来扩展路径

本方案为以下扩展留下了开放路径（当前不实现，YAGNI 拒绝纳入 plan）：

### (E1) `span × render_grid='price'` 渲染规则

当前 spec 校验拒绝 span event 声明 `render_grid='price'`。未来若有 atom 需要"价格带 / 端点钉价格 + 区间淡色覆盖"的可视化（例如支撑/阻力区段、价格通道），需要：

1. 扩 event 字段提供 y 维（候选：`y_band: tuple[float, float]` 或 `y_start: float, y_end: float`）。
2. 校验放行：spec.py 的 `_validate_render_grid` 加分支——若同时声明了 y 字段，则允许 `render_grid='price'` on span。
3. 加 `chart.ts` 中 (span × price) renderer 规则：横向价格带矩形 / 端点 marker + 区间淡色覆盖。

### (E2) tb 升级 `render_grid='price'`

tb 的"可买入窗口"语义当前已通过 `end_role` 协议 + 严格窗双竖虚线 + per-match `ret_N` 行表达，留 `render_grid='time'` 是守序保守。

未来若产品判断 tb 端点应钉价格（如止跌点价位 / 大涨前价位）会更直观，按 (E1) 流程升级：先实现 span × price 规则 + tb 端点价格字段，再把 dag_spec.py 中 tb 的 NodeSpec 改 `render_grid='price'`。

---

## 落地最小变更面

### 契约改动

```
# path2/dag/nodes.py（NodeSpec）
NodeSpec 增加可选字段:
    render_grid: Literal['price', 'time'] = 'time'  # 默认守序保守

# path2/atoms/breakout.py（BOEvent dataclass）
BOEvent 增加字段:
    referenced_points: Tuple[Tuple[int, float, str], ...] = ()
    # (bar_idx, price, label) 三元组的元组
    # detect 期填: tuple((p.idx, p.high_price, f"pk{p.id}") for p in broken_peaks)
    # 原 broken_peak_ids 仍保留供 W.attr 读

# path2_web/serialize.py
serialize_pattern 在 TopoNode 投影中加 render_grid 字段;
serialize_analysis 在 event 投影中加 referenced_points 字段透传。
```

### 前端改动（path2_web_ui/src/）

```
# types.ts
TopoNode 加 render_grid?: 'price' | 'time'
EventDict 加 referenced_points?: Array<[number, number, string]>

# render/visible.ts
新增 renderGridOf(e, topology, bandKeyOf): 
    topology.nodes.find(n => n.source_tag === bandKeyOf(e))?.render_grid ?? 'time'

# render/chart.ts
在 filtered 之后按 renderGridOf 一分为二:
  - render_grid='price' 的 events → 新增 on-price layer(yAxisIndex=0,
    主 marker = 三角,y 派生 = bars[start_idx].h * 1.005)
  - render_grid='time' 的 events → 现状 grid2 副图通道(band×lane)

新增卫星 marker renderItem(通用,与 atom 类型无关):
  对任何 render_grid='price' 的 event,若 e.referenced_points 存在,
  逐 (bar_idx, price, label) 在 K 线 grid 画小 marker + label 文本。
  前端不读 label 内容做条件,只透传渲染。

应用 path2_apps/bottom_breakout_burst/dag_spec.py
  bo 节点的 NodeSpec 加 render_grid='price'
```

### 前端分支数审计

| 改动位置 | 新增分支 | 与 atom 数关系 |
|---|---|---|
| `chart.ts` render_grid 二分 | 1 个 if（'price' / 'time'）| O(1) |
| `chart.ts` referenced_points 卫星 marker | 1 个 if（字段存在）| O(1) |
| **合计** | **2 个 O(1) 分支** | **与 atom 数无关 → 不破红线** |

### YAGNI（明确不做）

- ❌ **不**升格 pk 为独立 Event / 不出 pk stream / 不引入 PkDetector
- ❌ **不**在 chart.ts 读 class_id 做 if / switch
- ❌ **不**在 EventDict 加 `render_grid_to_price: boolean`（用 NodeSpec.render_grid 即可，不污染 event 层）
- ❌ **不**改 ECharts grid 数量（仍 3-grid，bo 跨到 grid0 是 yAxisIndex 改动，不是新 grid）
- ❌ **不**为方案二的"垂直引导虚线"留 fallback 代码（与方案一并存等于双渲染策略，奥卡姆否决）
- ❌ **不**实现 axisPointer cross 增强（用户已锁定方案一方向，cross 是方案二的妥协补丁）
- ❌ **不**给 dist 此刻加 render_grid 声明（path2_apps 零使用，待 dist 真正入用时由 spec 作者填）

---

## 未解争议（老实记录）

1. **bo marker 在价格 grid 上的 y 派生公式**（`bars[start_idx].h + offset` vs `close + offset` vs ATR 缩放 offset）—— 不影响契约，但影响视觉。建议落地时实测 3 个表达式选最不重叠 K 线柱体的；非阻塞。
2. **卫星 marker 在 dataZoom 缩到全窗（>200 bar）时的密度坍缩**—— uniform_advocate 提的"K 线缩放标签密度爆炸"是真实视觉问题。建议策略：dataZoom 比例 < 阈值时自动隐藏卫星 marker 的 label 文本（仅保留小点 marker），保留 tooltip 详细信息；阈值由前端经验定。这是策略问题不是架构问题。
3. **referenced_points 字段的填充责任**：BreakoutDetector 当前已知道 `Peak.idx` 与 `Peak.high_price`（breakout.py:189-198）但没在 BOEvent 里输出 price 维。需在 emit 处一行 `tuple((p.idx, p.high_price, f"pk{p.id}") for p in broken_peaks)`——非难点，但要写测试覆盖"首 bo / 无 peak / 多 peak"三种 case。

---

## 附：三轴对比小表

| 轴 | 方案一（bo 钉 K 线 + pk 标签） | 方案二（四件套：axisPointer + sidebar + tooltip + separator） |
|---|---|---|
| **信息论** | bo 的 (time, price) 两维同图呈现，pk 作为卫星 marker 在各自 bar 位置带编号 label 直接揭示突破关系（+1 bit 解释力） | 仅 time 维同图，price 与 pk 都靠侧栏数值（需双场切换，0 bit 增益） |
| **眼动成本** | 0 跨 grid 扫视；K 线 ↔ marker y 距 ≈ bar 高度 | ≥1 次 K 线 ↔ marker ↔ sidebar 三段切换；axisPointer 列对齐但行跨度大 |
| **契约整洁度** | 加 NodeSpec.render_grid + BOEvent.referenced_points，前端 +2 个 O(1) 分支 | 零契约扩展，但保留副图非价格 grid 的视觉妥协 |

---

## 方法论沉淀

本轮裁定值得记录的方法论：

1. **"几何派生" vs "类型耦合"的真分界**：派生若导致单 event 跨 grid 分裂（同 detector 同语义被映射到两个容器）= 几何是类型代理，须升格到 detector 级承诺；派生若只决定渲染样式（颜色 / 高度 / lane 算法）= 合法 generalization。
2. **奥卡姆 vs 防滑坡的辩证**：直接特殊化 bo = 简单但留滑坡；引入 render_grid 字段 = 多一层契约但封死滑坡。判据 = 契约扩展是否带来"语义中立枚举"（前端分支与 atom 数解耦）。render_grid 通过；class_id 白名单不通过。
3. **守序保守默认值的工程红利**：render_grid 默认 'time' 让现状所有 atom 不改即可运行（向后兼容），新需求按需声明。这把"契约升级"做成增量而非破坏性。
4. **正交协议拆分破"事件 vs 非事件"的伪两难**：pk 不是 event 但用户想画在 K 线上 —— 直接结论是"要么升格 event、要么牺牲需求"。把"主 marker 分流（render_grid）"和"卫星点渲染（referenced_points）"拆成两条正交协议后，pk 可以作为 bo payload 里的"被引用几何点"被通用渲染机制画出来，既不要 event 身份也不破红线。**字段命名的中立化（broken_peaks → referenced_points）是关键**：把 bo-语义降级为"任何价格锚事件可用的几何引用"，让前端代码字面上没有 "pk" 这个词。

— viz_lead（基于 kline_advocate / uniform_advocate / semantics_judge 两轮交叉质询后拍板；本版（2026-06-18 后续追加）引入"卫星 marker 协议（referenced_points）"以承载 pk 在 K 线上的独立可视化）
