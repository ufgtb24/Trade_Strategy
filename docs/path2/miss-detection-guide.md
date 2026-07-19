# 漏检调查工具 · 使用说明书

## 什么是"漏检"

你在 K 线图上看到某段行情、觉得**应该出一个 pattern(比如 bottom_burst)**,但副图里 pattern marker 空空如也。这就是**漏检**——图像上"应该出的"却没出。

漏检的根因可能在三层:

1. **Detector 没检测到某个 event**(比如 BurstDetector 因 chain 断链未产出 burst)
2. **Event 检出了、但没和其他 role 配上 pair**(比如 burst 与 tb 因 gap 超阈无法组合)
3. **Pair 层每对都能过、但组合到最后 DFS 零解**(通道 ⑦ 组合级)

漏检工具帮你**精确定位是哪一层出问题**,从而决定:改 detector 参数、改 dag_spec、或确认"设计正确、不该匹配"。

---

## 5 个使用入口 · 按操作路径选

| 入口 | 用户操作 | 回答的问题 | 主要场景 |
|---|---|---|---|
| **A · 时段查询** | K 线主图**框选**一段时间 | "这段时间为啥没出 event?" | 副图完全空 · 一个 marker 都没有 |
| **C · 单点问命运** | 副图**单点**一个 marker | "这个 event 为啥没进任何 pattern?" | 副图有 marker · 不知道该跟谁配 |
| **D · pair 查询** | 主图/副图 **shift+click 两个** marker | "这两个 event 为啥没连成 edge?" | 眼看两个 marker "该配上却没配" |
| **B · 拓扑面板** | 拓扑图**点一条 role edge** | "这条 role 关系整体失败分布如何?" | 想看关系全体样本,不聚焦某一对 |
| **E · workflow** | 命令行跑 `scan-top-miss.py` | "全宇宙 top-K 漏检疑云股是哪些?" | 还不知道该看哪支股 |

---

## 入口 A · 时段查询

### 场景

你看 DGNX 在 2025-08-01 前后有一波大涨,预期应该出一个 burst,但副图 burst band 一片空白。

### 操作

1. **主图上拖拽框选**一段时间(比如 2025-07-15 → 2025-09-01)
2. 侧栏立即弹出 `FailedAttemptsCard`
3. 卡片头部有下拉,可以 filter event 类型(全部 / burst / bo / tb)

### 你看到什么

每次失败的 detector attempt 一张子卡片:

```
[burst · [90, 120] · 与你的框 [100, 150] 部分相交]
栽在 chain_break: gap=15 > gap_max=10
触发 bar=105
参照历史 (75, 89)
```

**含义**:
- **`failure_event_window` `[90, 120]`** = 该 attempt 判据评估**实际扫过**的 bar 范围(实测轨迹,不是"若成功会覆盖")
- **overlap 徽标**(三色):绿色 = 完全在你的框内、黄色 = 部分越出、蓝色 = 候选大于你的框
- **`gate_name`**(如 `chain_break`)= 触发失败的具体判据
- **`measured` vs `threshold`** = 实测值 · 阈值
- **`trigger_bar`** = gate 触发所在 bar(BurstDetector 逃逸场景下可能溢出你的框,副标会明示)
- **`evaluation_lookback`** tooltip = detector 内部参照的历史 bar(不参与判据,只显示)

### 只列框内 attempt

只列 `[start_idx, gate_idx] ⊆ 你的框` 的 attempt——**压缩搜索空间**,信息不稀释。

`start_idx` 溢出框左边界的 span attempt(如 BurstDetector 一簇跨度大、簇首在框外、断链点在框内)按定义**不属于该时段**——想看它们就把框拉宽,让整段 attempt 的实测轨迹装进来。

### 三大 detector 的 gate 全枚举

**BurstDetector**(2 gate):
- `chain_break`:相邻 bo `gap > gap_max`
- `min_bos_insufficient`:簇末 bo 数 `< min_bos`

**BODetector**(5 gate):
- `peak_no_local_max`:窗口内不是最高实体
- `peak_side_bars_insufficient`:peak 在前/后 min_side_bars 内
- `peak_relative_height_insufficient`:相对高度不够
- `peak_already_active`:peak 索引已 active
- `no_active_peak_broken`:active_peaks 无一被突破

**ThrowbackDetector**(4 gate):
- `phase1_break`:找止跌途中破位
- `phase1_pullback_shortage`:止跌确认但回落深度不足
- `phase1_no_trough_timeout`:扫满未找到止跌
- `phase2_break`:事件本体扫描破位

### 决策建议

| 看到什么 | 决策方向 |
|---|---|
| `chain_break: gap=15 > 10` | 改 `gap_max` 参数(从 10 → 15?)|
| `min_bos_insufficient: 4 < 5` | 改 `min_bos` 或者接受"这只股 bo 天生少" |
| `phase1_break: 破位差=-0.3` | 改 `anchor_measure` / `support_measure` 或看是否设计正确 |
| `peak_relative_height_insufficient: 0.008 < 0.01` | 改 `min_relative_height` |

---

## 入口 D · pair 查询(shift+click 两个 marker)

### 场景

K 线上你**眼看有一个 bo**(主图三角)**和一个 burst**(副图 band),你直觉认为它俩"就该配上",但 pattern 没成。

### 操作

1. **按住 Shift** · 点主图 bo 三角(第 1 击 = src)
2. **仍按 Shift** · 点副图 burst band(第 2 击 = dst)
3. 侧栏立即弹出 `PairDetailCard`

**跨图允许**:主图 bo marker + 副图 span band 混选都可以。

**第 3 击**:清空重来(第 3 击自动成为新的 src)。

### 你看到什么

```
burst_1 → tb_3 · TemporalEdge · burst_to_tb

feasible_window  ✓
satisfies        ✗ gap 越界 · gap=15 vs 阈 10
```

**含义**:
- **4 subcheck 短路**:`feasible_window` → `satisfies` → `anchor` → `strict` · 遇第一 fail 停(不再评估后续)
- 与 detector 内部短路语义一致

### auto swap · 顺序反了怎么办

如果你的顺序反了(dst → src),后端自动检测反向 edge · 自动切换:

```
⚠ 你点的顺序是 tb_3 → burst_1 · 该方向无 edge · 已改按 burst_1 → tb_3 查询    [撤回]
```

想强制查另一方向 · 点撤回按钮。

### 5 类 invalid_reason

| invalid_reason | UI 提示 |
|---|---|
| `same_role` | "两个 event 属于同一 role · role 内无 edge · 无法查 pair" |
| `no_edge_between_roles` | "两 role 在 dag_spec 中无直连 edge · pair 无从查起" |
| `only_negation_edge` | "两 role 间只有 negation 关系 · 请用入口 C(候选级)看违禁信号" |
| `direction_mismatch_with_hint` | 自动 auto swap,顶部黄条 + 撤回按钮 |
| `event_not_found` | "找不到该 event · 请检查 event_id" |

### 通道覆盖

入口 D 覆盖通道 ③(satisfies)+ ④(anchor)+ ⑤(strict) · **不含** ⑥ negation(negation 归入口 C · UI 上也点不到 negation dst)。

### 决策建议

| 栽在哪 | 决策方向 |
|---|---|
| `satisfies fail: gap 越界` | 改 `min_gap` / `max_gap` |
| `anchor fail: anchor 破位` | 改 `anchor_measure` 或核查语义 |
| `strict fail: 有更早候选` | 检查 `strict=True/False` 或 next 语义是否成立 |
| `feasible_window fail` | 时序窗过窄 · 改 gap range |

---

## 入口 C · 单点问命运

### 场景

副图有一个孤立的 burst band(marker 存在),但 pattern 没成。你**不知道该跟哪个 tb 配**,想让系统告诉你这个 burst 到底怎么了。

### 操作

副图**单点**(**不带 Shift**)那个 burst band。

### 你看到什么

`RejectionChainCard`,按 6 种 stage 分组:

```
burst_1 · burst

[① node.where 剔除]      passed

[③ satisfies fail]      与 tb_3 · gap=15 vs 阈 10
[④ anchor 破位]           与 tb_7 · anchor 不匹
[⑤ strict 不清空]         与 tb_9 · 有更早候选

[⑦ 组合零解 (combine tail)]
尝试 4 次分支全 fail · 组合零解
```

**含义**:
- **按 stage 分组渲染** · 6 stage 分色(qualify / satisfies / anchor / strict / negation / combine)
- **combine tail** 灰色卡片 · 在链尾 · 显示"尝试 N 次分支全 fail · 组合零解"

### combine tail 是什么(通道 ⑦ 唯一暴露入口)

即使**每一对 pair 单独都能过**(比如 burst→tb_3 满足、burst→tb_7 也满足),但 DFS 组合到最后仍然凑不出一组合法解(可能上下游 anchor 冲突、或 kleene 数量不够)。这种"pair 层都过但组合零解"的信号,**只有入口 C 能看到**——入口 A/D 都不涉及。

### 决策建议

| 主要 stage 集中在 | 决策方向 |
|---|---|
| 全在 ① qualify | 参数太严 · 改 `node.where` 的 clause 阈值 |
| 全在 ③ satisfies | gap 参数问题 |
| 全在 ④ anchor | anchor 语义问题 |
| 只有 ⑦ combine | 上游都通过 · 组合冲突 · 深查 spec 结构 · 可能设计问题 |
| 无 rejection_chain | 该 event 直接进了 match 或根本没进 solver · 应该看入口 B 分布 |

---

## 入口 B · 拓扑面板

### 场景

你**不知道具体是哪一对失败**,想看整个 role 关系的**失败分布**。

### 操作

拓扑面板上**点一条 role edge**(比如 burst → tb)。

### 你看到什么

`PairListCard`:

```
burst_to_tb   12/15 通过 · 3 失败

gap 越界: 2   anchor 破位: 1   strict fail: 0

burst_1  tb_3   gap_out           [点行深钻 → 入口 D]
burst_5  tb_7   anchor_mismatch
burst_5  tb_11  gap_out
```

**含义**:
- **miss_reasons 分布**:整条 edge 全体失败 pair 的分类计数
- **example_failed_pairs**(3-5 条抽样):点某一行 → 自动跳转入口 D 深钻这对

### 拓扑面板为什么不染色

染色回答"全宇宙哪条边最红"——需要全宇宙参照系。**单股 UI 锁定后**,你只有这一只股的数据,染色信号无处发力(1-2 样本极化就 0% / 100%)。染色的价值锚在批量层(入口 E),但入口 E 用 markdown 榜替代,所以拓扑面板整段撤染色。

---

## 入口 E · workflow scan-top-miss

### 场景

你**还不知道该看哪只股** · 想从全宇宙 6000 只股里找 top-K 疑云。

### 操作

命令行:

```bash
python scripts/scan-top-miss.py \
    --start=2025-07-15 --end=2025-09-01 \
    --min-pct=30 --top-k=20 \
    --out=top_miss.md
```

### 你看到什么

`top_miss.md`:

```markdown
# scan-top-miss · 2025-07-15 → 2025-09-01

筛选:涨幅 > 30% · matches 为空 · 按涨幅降序

## Top-5

1. **DGNX** · 2025-07-15 → 2025-09-01 · +48.5%
   - chain_break(实测 gap=15 vs 阈 gap_max=10,共 3 次)

2. **NVDA** · 2025-07-15 → 2025-09-01 · +32.1%
   - min_bos_insufficient(实测 4 vs 阈 5,共 1 次)
```

**含义**:每支股一行 · 涨幅 + 主导 gate 摘要。顺着榜挨个用入口 A/C/D 挖细节。

**建议**:每周跑一次 · 系统性发现漏检 · 不靠偶然想起某只股。

---

## 硬伤修补 · UI 现在诚实了什么

之前 UI 有信息缺口,现在都补齐:

| 硬伤 | 现象 | 修补后你能看到 |
|---|---|---|
| **A · role rel 徽标** | 后端有数据、前端零渲染 | 候选表 role 一列右侧 `8/10 ✓` 徽标 · 3 档色(全过绿 / 部分过黄 / 零过红) |
| **B · anchor 复核** | diagnose 不调 `_anchor_ok` · 虚报通过 | anchor 值真实反映 · 破位的 pair 不再显示通过 |
| **C · 跨节点 clause 降级** | 静默 fallback 到错值 | 显示 `⚠ pending` 图标 + hover title · 明示未复核 |
| **D · multi-value 展示** | 数组扁平化成一个数字 | `distinct_pk_min = [3, 5, 2]` 完整数组显示 |
| **E · kind-aware measured** | 所有 measured 硬编码 "gap=" 前缀 | 按 kind 分色 · `gap=15` / `Δanchor=0.234` / `strict候选=2` |

---

## 快速决策树 · 该走哪个入口

**从"你看到什么"出发**:

- 副图**完全空**(marker 一个都没有) → **入口 A** 时段查询(问 detector 内部 gate)
- 副图**有 marker**,主图**有 bo**,你**知道**该跟哪个配 → **入口 D** shift+click 两个
- 副图**有 marker**,你**不知道**该跟谁配 → **入口 C** 单点 marker(追它全命运)
- 想看**整条关系的分布**(不聚焦某对) → **入口 B** 拓扑点 edge
- 想**批量发现候选股** → **入口 E** workflow

---

## 兜底 · V1 D0 driver(超细节调查)

若 4 入口都不够精细(比如你要在 BurstDetector 内某个具体 bar 打断点、看 `relative_height` 的具体值、看参数敏感度):

1. 主图右键 → 弹菜单 → **"复制 driver 脚本"**
2. 粘贴到 PyCharm · 加 `breakpoint()`
3. 脚本已含 `set_current_symbol` + `scan_one_symbol` · 可条件断点某只股

Driver 是**边角深挖工具** · 不是日常主用。上面 4 入口覆盖 95% 场景,Driver 每月用 1-2 次即可。

---

## FAQ

**Q1:入口 A 的 `failure_event_window` 究竟是什么?**

A:**该次 attempt 判据评估从 `start_idx` 起、扫到 `gate_idx` 失败停** 的**实测**扫过的 bar 范围。**不是**"若成功会覆盖的窗口"(那是估算,attempt 失败时不存在)。

- BO 点事件 → window = `(i, i)` 单点
- Burst / Tb span 事件 → window = `(start_idx, gate_idx)` span
- Detector 内部为判据参照的历史 bar(如 BODetector 的回望窗)进 `evaluation_lookback` tooltip,**不进 window**、不参与 ⊆ 判据

**Q2:为什么只列"完全落在框内"的 attempt,而不是所有和框相交的?**

A:**压缩搜索空间**——只列"完全落在你的框内"的失败 attempt。避免 `start_idx` 远小于框 start 的 attempt 稀释信息量。若你怀疑边缘漏了,扩大框重查。

**Q3:入口 D shift+click 我按顺序反了怎么办?**

A:后端自动检测反向 edge · 自动切换 · 卡片顶部黄条明示"顺序已自动切换" + 撤回按钮。你不用记 dag_spec 里 role 方向。

**Q4:入口 C 的 combine tail 是什么?**

A:该 candidate 尝试与所有 counterpart 组合,**每对 pair 单独都能过**,但组合到最后 DFS 零解(可能上下游 anchor 冲突、kleene 数量不够、或 spec 结构矛盾)。这个信号**只有入口 C 能看到**——入口 A/D 都不涉及。

**Q5:拓扑面板为啥不染色?**

A:染色回答"全宇宙哪条边最红"——需要跨股参照系。单股 UI 锁定后只有这一只样本,染色 1-2 样本极化误导多于帮助。染色的价值锚在批量层(入口 E)· 但入口 E 用 markdown 榜替代 · 所以拓扑面板整段撤染色。

**Q6:入口 D 里 negation 通道呢?**

A:negation 语义是"src 上的**全称约束**,禁止某类 dst 在窗内出现"——不是"两 event 的 pair 关系"。UI 上 negation dst 根本不渲染成 marker(它不属于任何 role_index)· 你 shift+click 也点不到。所以入口 D **不含** negation。想看违禁信号 · 用入口 C(rejection_chain 里 `stage='negation'`)。

**Q7:为什么入口 B 保留"点边过滤"、只撤"染色"?**

A:两者产品定位不同:
- **染色** = 类层聚合信号(全宇宙统计)· 单股无用
- **点边过滤** = 类作过滤器打开对象列表(单股场景仍有价值:"我关心 burst-tb 类关系,想看这类下所有具体 pair")

只撤染色 · 保留点边。

**Q8:入口 A 里 tb 的 attempt 是"整个 evaluate_throwback 调用"还是"分阶段一/二"?**

A:采**松对齐**——**一次 `evaluate_throwback(bo, df)` = 一次 attempt** · 不分阶段。阶段一失败(phase1_break / phase1_pullback_shortage / phase1_no_trough_timeout)和阶段二失败(phase2_break)都归到同一 attempt 上,`failure_event_window = (bo.end_idx + 1, gate_idx)` · gate_name 明确到具体判据。理由:调查漏检要看**完整扫描过程**,阶段一失败本身就是"tb 没出的原因",不能只让阶段二可见。

**Q9:5 硬伤全修完了吗?**

A:是。Sprint 1 修 A/B/C/D 首批 · Sprint 2 修 E + refs_other_role · 硬伤全清。

---

## 术语速查

| 术语 | 含义 |
|---|---|
| **event** | detector 产出的一个具体实例(如某个 bo、某个 burst) |
| **role** | dag_spec 中的一个占位类(如 burst、tb) |
| **pair** | 两个具体 event 之间的关系候选(如 burst_1 + tb_3) |
| **candidate** | 已 qualified 但还没进 match 的 event |
| **match** | 完整满足 dag_spec 全部 role 的组合 |
| **attempt** | detector 一次尝试产出 event 的过程(短路遇第一 gate fail 停) |
| **gate** | detector 内部某条判据(如 chain_break / peak_relative_height) |
| **subcheck** | pair 层的判据(feasible_window / satisfies / anchor / strict) |
| **通道** | 漏检根因的独立源头(共 7 个,见下表) |

**7 通道全枚举**(与入口的映射):

| 通道 | 语义 | 唯一暴露入口 |
|---|---|---|
| ① detect gate | detector 内部 gate 失败 | 入口 A |
| ② node.where | 单节点属性判据剔除 | 入口 C |
| ③ satisfies | edge kind 基础判据 | 入口 D / C(单)、B(分布) |
| ④ anchor | anchor_field 二次校验 | 入口 D / C(单)、B(分布) |
| ⑤ strict_clear | next 语义严格清空 | 入口 D / C(单) |
| ⑥ negation_clear | 全称禁止违禁 | 入口 C 唯一(D 不含) |
| ⑦ DFS combine | 组合零解 | 入口 C 唯一(combine tail) |

7 通道均被至少一个入口覆盖 · 通道 ① / ⑥ / ⑦ 各有唯一入口。
