# 联合信号系统 UI 集成 -- 用户工作流与交互体验分析

> 创建日期：2026-02-06
> 分析维度：用户工作流、交互体验、信息架构
> 前序文档：[数据管道技术分析](composite_signal_ui_integration_analysis.md)

---

## 一、Executive Summary

当前 UI 是一个"浏览型"工具：扫描 -> 按信号数量排序 -> 逐个看图。联合信号系统已在后端计算了 `weighted_sum`、`sequence_label`、`amplitude`、`turbulent` 四个字段，但 UI 层完全未消费这些数据。

本分析从用户实际工作流出发，识别出三个核心问题：

1. **列表阶段**：用户缺乏快速筛选和排序的能力，需要在大量股票中人工翻页寻找值得关注的标的
2. **图表阶段**：用户看图时缺乏信号之间关联性的上下文，每个信号标记是孤立的点
3. **决策阶段**：UI 没有任何机制帮助用户从"看到信号"走向"做出买入判断"

核心建议：以**最小改动量**分三步走 -- 先让列表"能说话"（展示联合信号数据），再让图表"讲故事"（信号序列可视化），最后让工作流"有闭环"（快捷标记/收藏）。

---

## 二、用户工作流深度分析

### 2.1 典型使用会话还原

基于系统功能和数据流分析，还原一次完整的用户使用会话：

```
T=0  打开 UI，点击 Load 加载最新的 JSON 结果
T=1  左侧出现排行榜（按 signal_count 降序）
T=2  从第一名开始，按 Down 键逐个浏览
T=3  每只股票：看图 3-5 秒 -> 判断是否有买入价值 -> 按 Down 到下一只
T=4  遇到感兴趣的股票 -> 在脑中或外部记事本记录 symbol
T=5  浏览完前 20-30 只后疲劳，停止
T=6  回到外部记事本，对记录的 5-8 只做进一步研究
```

### 2.2 工作流中的摩擦点

| 阶段 | 摩擦点 | 根因 |
|------|--------|------|
| T=2 | 排行榜仅按 signal_count 排序，但 3 个 B(1) 的价值不如 1 个 B(3) | 列表未消费 weighted_sum |
| T=3 | 看图时不知道信号之间的时间关系和权重关系 | 图表缺乏信号序列上下文 |
| T=3 | 异常走势（turbulent）股票混在正常股票中，浪费注意力 | 列表未标记/隔离 turbulent |
| T=3 | 看图 3-5 秒的判断负担过重，需要同时处理多个维度 | 缺乏摘要信息汇总关键指标 |
| T=4 | 感兴趣的股票需要靠记忆或外部工具记录 | UI 缺乏标记/收藏功能 |
| T=5 | 前 30 只中可能有大量 turbulent，真正值得看的被淹没 | 无过滤/分组机制 |

### 2.3 用户的真实决策模型

用户在 scan_date（扫描截止日期）做买入判断时，实际的思维过程是：

```
1. 排除：是不是异常走势？ (turbulent -> B/V/Y 信号价值大打折扣)
2. 初筛：信号强度够不够？ (weighted_sum 是否显著高于平均)
3. 故事线：信号的时间顺序是否合理？ (D -> B 是底部确认后突破，比 B -> D 好)
4. 确认：看图表验证信号标记是否与走势吻合
5. 收藏：标记感兴趣的，后续决策
```

当前 UI 只支持步骤 4（看图），步骤 1-3 和步骤 5 完全缺失。

---

## 三、列表阶段优化方案

### 3.1 列表列设计方案

在现有列中增加 composite 字段。推荐的列排列顺序：

```
+----------+------+-----+---+---+---+---+------+-----------+
| Symbol   | Wt   | All | B | V | Y | D | Amp  | Seq       |
+----------+------+-----+---+---+---+---+------+-----------+
| AAPL     | 7.0  |  5  | 2 | 1 | 1 | 1 |  34% | D2-B3-V-Y |
| TSLA   * | 2.0  |  7  | 3 | 2 | 1 | 1 |  92% | B-V-Y-B-D2|
| GOOGL    | 5.0  |  3  | 1 | 1 | 0 | 1 |  25% | D-B3-V    |
+----------+------+-----+---+---+---+---+------+-----------+
```

各列设计决策：

| 列名 | 数据源 | 列宽策略 | 排序行为 | 设计理由 |
|------|--------|---------|---------|---------|
| **Wt** | `weighted_sum` | 窄列，显示 1 位小数 | 默认降序排序列（替代 All） | 核心排序指标，用户最需要第一眼看到 |
| **Amp** | `amplitude` | 窄列，百分比格式 | 可排序 | 快速识别异常走势程度 |
| **Seq** | `sequence_label` | 自适应宽列，纯文本 | 不排序 | 提供信号故事线上下文，但不适合作为排序键 |

### 3.2 Sequence 列的显示格式

`sequence_label` 原始格式可能很长（例如 `D(2) -> B(3) -> V -> Y -> B(2) -> V`），在 Treeview 中显示存在宽度挑战。

**建议方案**：列表中显示**紧凑格式**，完整版通过 tooltip 展示。

```
原始格式:    D(2) -> B(3) -> V -> Y      (26 字符)
紧凑格式:    D2-B3-V-Y                    (10 字符)
```

紧凑格式的生成规则：
- 类型字母直接保留 (B/V/Y/D)
- 有内在属性 >1 时直接拼接数字 (B3, D2)
- 用 `-` 替代 ` -> ` 作为分隔符

紧凑格式可读性略低但节省大量空间，且类型字母本身已足够直观。在 tooltip 中可以展示完整的 `D(2) -> B(3) -> V -> Y` 格式。

**实现位置**：这个紧凑格式可以在 `composite.py` 中新增一个 `generate_compact_label()` 函数，或者在 `StockListPanel._update_tree()` 中做格式转换。建议前者，保持格式生成逻辑集中在一处。

### 3.3 turbulent 股票的处理策略

这是一个关键的 UX 决策。分析三种方案：

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **A: 标记但不隔离** - Symbol 后加 `*` 号 + 整行灰色背景 | 实现简单，信息不丢失 | 仍然分散注意力 | 中 |
| **B: 置底** - turbulent 股票排在所有正常股票之后 | 清晰的视觉分隔 | 用户可能完全忽略 turbulent 中有价值的 D 信号 | 低 |
| **C: 视觉降权 + 自然排序**（推荐） | 平衡信息完整性和注意力管理 | 实现稍复杂 | 高 |

**推荐方案 C 的具体设计**：

1. turbulent 行使用**浅灰色前景色**（Treeview tag 的 foreground 属性）
2. Symbol 列追加 `*` 标记（复用 `scan_signals.py` 的终端输出惯例）
3. Wt 列显示**有效值**（turbulent 时仅 D 信号计入的 weighted_sum）
4. Amp 列的值本身已经 >= 80%，足够醒目
5. **不改变排序位置** -- weighted_sum 自然排序已经将 turbulent 的 B/V/Y 归零了，它们自然会下沉

为什么不推荐"置底"：turbulent 股票如果有高价值的 D 信号（如 D(3)），其 weighted_sum=3.0 仍然可能高于一些正常股票。置底会隐藏这个有效信息。让 weighted_sum 驱动排序是最自然的方案，因为 `calc_effective_weighted_sum()` 已经在计算时做了正确的降权处理。

Treeview tag 实现：

```python
# stock_list_panel.py
TURBULENT_TAG = "turbulent"

# 在 _create_ui() 中配置样式
self.fixed_tree.tag_configure(TURBULENT_TAG, foreground="#888888")
self.main_tree.tag_configure(TURBULENT_TAG, foreground="#888888")

# 在 _update_tree() 中，插入行时判断
tags = ()
if stock.get("turbulent", False):
    tags = (TURBULENT_TAG,)
    symbol_display = f"{symbol} *"
else:
    symbol_display = symbol
self.fixed_tree.insert("", tk.END, iid=symbol, values=(symbol_display,), tags=tags)
self.main_tree.insert("", tk.END, iid=symbol, values=values, tags=tags)
```

### 3.4 默认排序策略变更

当前列表默认按 `signal_count` 降序。需要改为按 `weighted_sum` 降序（与 `scan_signals.py` 终端输出和 `SignalAggregator.aggregate()` 的排序一致）。

**实际上排序逻辑几乎不需要改**：
- JSON 中的 `results` 数组已经是按 `(weighted_sum, signal_count)` 降序排列的（因为 `_results_to_json()` 遍历的 `results: List[SignalStats]` 就是 aggregator 排好序的）
- `StockListPanel.load_data()` 按原序插入数据
- 用户如果点击列头，`sort_by(column)` 的通用逻辑会按数值排序

唯一需要确保的是：初始加载后，列表的"当前排序列"指示器应该标记在 Wt 列上（视觉反馈），而不是 All 列。

### 3.5 Hide Turbulent 过滤

在列表工具栏增加 "Hide Turb" 复选框，提供最小的过滤能力：

```
+------------------------------------------+
| [eye] [Columns] [Label: avg] [x Hide Turb]|  <-- 工具栏增加复选框
+------------------------------------------+
| Symbol   | Wt  | B | V | Y | D | Amp    |
| ...                                      |
```

实现方式：
- `StockListPanel` 增加 `_hide_turbulent_var: BooleanVar`
- 勾选时，`filtered_data` 排除 `turbulent == True` 的条目
- 这与现有的 `filtered_data` / `stock_data` 机制完全兼容
- 切换时调用 `_update_tree()`

**优先级**：P2。这不是核心功能，但在实际使用中可以显著减少噪音。用户在一次会话中可能有 20-30% 的股票是 turbulent，隐藏后可以更专注地浏览剩余的高质量标的。

---

## 四、图表阶段增强方案

### 4.1 用户看图时的信息需求

用户切换到某只股票后，当前看到的是：
- K 线图 + lookback 高亮区域
- 独立的信号标记（B/V/Y/D 标签散布在图上）
- 悬停 tooltip 显示 OHLCV + 当天信号

**缺失的信息**：
1. 这只股票的"信号故事线"是什么？（全局概览）
2. weighted_sum 是多少？在排行榜中的相对位置？
3. 是否 turbulent？如果是，哪些信号不计入排序？
4. 信号之间的时间关系（看标记需要视线在图上跳来跳去）

### 4.2 方案：图表顶部 Info Bar

在 K 线图的**顶部**（标题位置）增加一行紧凑的摘要信息。这是核心推荐方案。

#### 正常股票的 Info Bar

```
+-------------------------------------------------------------+
|  AAPL  Wt:7.0  Cnt:5  Amp:34%  D(2) -> B(3) -> V -> Y      |  <-- Info Bar
+-------------------------------------------------------------+
|                                                              |
|                   K-Line Chart                               |
|              (与现在完全相同)                                  |
|                                                              |
+-------------------------------------------------------------+
```

#### turbulent 股票的 Info Bar

```
+-------------------------------------------------------------+
|  TSLA *  Wt:2.0  Cnt:7  Amp:92% !!  B -> V -> Y -> B -> D(2)|
+-------------------------------------------------------------+
```

显示规则：
- `*` 标记表示 turbulent
- `!!` 跟在 Amp 后面标记异常值
- Wt 显示的是有效 weighted_sum（turbulent 时仅 D 计入，所以是 2.0 而不是 9.0）
- Seq 使用完整格式（图表区域宽度充足，不需要紧凑格式）

#### 实现方式

利用 matplotlib 的 `ax.set_title()` 在图表顶部渲染信息文本。这是零成本的实现方式，不需要新的 UI 组件。

```python
# canvas_manager.py update_chart() 中
# 需要新增 composite_info 参数
def update_chart(self, ..., composite_info: dict = None):
    # ... 现有绑图逻辑 ...
    if composite_info:
        symbol = composite_info.get("symbol", "")
        wt = composite_info.get("weighted_sum", 0)
        cnt = composite_info.get("signal_count", 0)
        amp = composite_info.get("amplitude", 0)
        seq = composite_info.get("sequence_label", "")
        turb = composite_info.get("turbulent", False)

        turb_marker = " *" if turb else ""
        amp_marker = " !!" if amp >= 0.8 else ""
        info = f"{symbol}{turb_marker}  Wt:{wt:.1f}  Cnt:{cnt}  Amp:{amp:.0%}{amp_marker}  {seq}"
        ax_main.set_title(info, fontsize=16, loc='left', pad=8, fontfamily='monospace')
```

### 4.3 方案比较：独立摘要面板 vs Info Bar

| 维度 | 独立摘要面板 | Info Bar（推荐） |
|------|------------|------------------|
| 实现成本 | 需要新增 tkinter Frame + 布局调整 | 1 行 matplotlib API 调用 |
| 信息密度 | 可以展示更多详情（多行） | 紧凑的单行摘要 |
| 视线路径 | 需要在面板和图表之间切换视线 | 视线自然在图表顶部开始 |
| 空间占用 | 占用图表区域高度 | 几乎不占用额外空间 |
| 适配性 | 需要考虑窗口缩放 | 自动跟随图表缩放 |

**推荐 Info Bar** 的理由：遵循奥卡姆剃刀原则。用户快速浏览时（按 Down 切换），3-5 秒内需要获取的信息用一行文本已经足够。如果未来需要更复杂的分析面板（比如 Layer 2 的五维评分），可以再考虑独立面板。

### 4.4 信号序列在 K 线图上的可视化增强

**问题**：是否需要在图表上增强信号之间的关系可视化（如连线、箭头）？

**分析后的结论：不建议增加。** 原因：

1. K 线图本身信息密度已经很高：蜡烛 + 成交量背景 + peak/trough 标记 + 阻力带/支撑带 + 信号标签
2. 信号之间的连线会与这些元素交叉，降低可读性
3. 信号的**时间顺序**通过 x 轴位置已经隐含表达
4. 顶部 Info Bar 的 sequence_label 已经以文字形式提供了序列信息
5. 用户已经可以通过 SymbolFilterPanel（B/V/Y/D 复选框）控制哪些信号类型显示

**额外的可视化只会增加认知负荷，而不减少。** 信号之间的关系理解应该通过 Info Bar 的文字标签来辅助，而不是通过更多的图形元素。

### 4.5 悬停 tooltip 增强（可选，低优先级）

当前的 tooltip 已经在信号日的 K 线上显示信号类型。可以额外增加 `strength` 信息：

```
当前:    B [1,3,5]              (B 信号突破了 peak #1, #3, #5)
增强:    B [1,3,5] (wt:3)       (额外显示 pk_num=3)
```

对于 D 信号：
```
当前:    D: [1,2]               (D 信号对应 support trough #1, #2)
增强:    D: [1,2] (wt:2)        (额外显示 tr_num=2)
```

这个改动的实现位置在 `canvas_manager.py` 的 `on_hover()` 函数中（第 678-707 行），在构建 `sig_line` 字符串时读取 `sig.get("strength")` 并追加。改动约 4 行代码。

---

## 五、从"浏览"到"决策"的工作流转变

### 5.1 核心问题

当前 UI 的隐含假设是"用户打开 UI 是为了看看有什么信号"。但用户的真实目标是"找到值得买入的股票"。这两个目标的差异决定了 UI 的设计方向。

| 浏览导向 | 决策导向 |
|---------|---------|
| 展示所有信号 | 高亮最有价值的信号组合 |
| 按数量排序 | 按加权强度排序 |
| 无过滤 | 可过滤 turbulent、低权重 |
| 无标记 | 可标记/收藏感兴趣的 |
| 单次浏览 | 多次回访，追踪关注列表 |

通过本次联合信号集成，前三项差距可以被弥合（weighted_sum 排序 + turbulent 标记/过滤）。后两项（标记/收藏、多次回访）是独立的功能需求，建议后续迭代。

### 5.2 快捷标记/收藏功能（后续迭代建议）

**需求分析**：用户反复需要在浏览过程中记录感兴趣的股票。当前只能依赖脑记或外部工具。

**最小实现方案设想**：

```
操作：用户在列表中按 Space 键 -> 当前股票标记为 "starred"
显示：Symbol 列前追加 [*] 标记，行背景色轻微变化
持久化：标记存储在一个独立的 JSON 文件中（与扫描结果分离）
过滤：列表工具栏增加 "Show Starred Only" 复选框
```

**设计考量**：
- 标记应该跨扫描结果持久化（同一个 symbol 在不同日期的扫描中都应该保持标记状态）
- 不应该阻塞现有的 Up/Down 导航流程（Space 键不会与 Up/Down 冲突）
- 标记状态独立于扫描结果，不应该修改 JSON 文件

**但是**，这个功能与联合信号 UI 集成是**独立的需求**。建议作为后续迭代，不在本次联合信号集成中一起实现。原因：
1. 避免一次性改动过大
2. 标记功能的持久化方案需要独立设计（独立文件 vs 嵌入 JSON vs 配置系统）
3. 联合信号集成本身已经通过 weighted_sum 排序显著改善了"找到值得关注的股票"这一核心需求

### 5.3 信息过载 vs 信息不足的平衡点

当前的平衡点分析：

```
列表区域:
  信息不足 <---[当前]---------> 信息过载
           x                     (缺少 weighted_sum/turbulent)

  信息不足 <---------[建议]----> 信息过载
                      x          (增加 Wt/Amp/Seq 三列)

图表区域:
  信息不足 <-----------[当前]--> 信息过载
                        x        (信号标记 + peak/trough 已经较密集)

  信息不足 <----------[建议]---> 信息过载
                       x         (仅增加 Info Bar，不增加图形元素)
```

关键原则：
- **列表区域可以承载更多信息**，因为 Treeview 天然支持多列，且用户可以通过列配置菜单自由控制可见列
- **图表区域应该克制**，只增加不占用图表面积的 Info Bar，不增加新的图形元素

---

## 六、完整 UI 布局方案

### 6.1 列表区域（改造后）

```
+------------------------------------------------------+
| [eye] [Columns] [Label: avg] [_ Hide Turb]           |
+----------+------+-----+---+---+---+---+------+-------+
| Symbol   | Wt   | All | B | V | Y | D | Amp  | Seq   |
+----------+------+-----+---+---+---+---+------+-------+
| AAPL     | 7.0  |  5  | 2 | 1 | 1 | 1 | 0.34 | D2-B3 |  <- 正常股票
| NVDA     | 5.0  |  4  | 1 | 1 | 1 | 1 | 0.28 | D-B3-V|
| MSFT     | 4.0  |  3  | 1 | 1 | 0 | 1 | 0.22 | B2-V-D|
| TSLA   * | 2.0  |  7  | 3 | 2 | 1 | 1 | 0.92 | B-V-Y |  <- turbulent，灰色字
| GME    * | 0.0  |  5  | 2 | 2 | 1 | 0 | 1.15 | B-V-Y |  <- turbulent 无 D
+----------+------+-----+---+---+---+---+------+-------+
```

观察要点：
- TSLA 有 7 个信号但 Wt 仅 2.0（turbulent，仅 D(2) 计入）
- GME 有 5 个信号但 Wt 为 0.0（turbulent，无 D 信号，B/V/Y 全部归零）
- 按 Wt 排序后，高价值股票自然在前
- turbulent 行灰色前景色 + `*` 标记，视觉上降权但不隐藏

### 6.2 图表区域（改造后）

```
+-------------------------------------------------------------+
|  AAPL  Wt:7.0  Cnt:5  Amp:34%  D(2) -> B(3) -> V -> Y      |  <- Info Bar
+-------------------------------------------------------------+
|                                                              |
|   +-------------------------------------------------------+  |
|   |                                                       |  |
|   |    K 线图 + 信号标记 (B/V/Y/D)                        |  |
|   |    + Peak/Trough 标记                                 |  |
|   |    + 灰色高亮 lookback 窗口                            |  |
|   |    + 阻力带/支撑带                                    |  |
|   |                                                       |  |
|   +-------------------------------------------------------+  |
|                                                              |
|  [xB] [xV] [_Y] [xD] [xPk] [_Tr] | Before:[6m] After:[1m]  |
+-------------------------------------------------------------+
```

turbulent 股票的 Info Bar 变化：

```
+-------------------------------------------------------------+
|  TSLA *  Wt:2.0  Cnt:7  Amp:92% !!  B -> V -> Y -> B -> D(2)|
+-------------------------------------------------------------+
```

### 6.3 整体布局（改造前后对比）

改造前：

```
+----------------------------------------------------------------------+
| [Mode: Analysis] [Config: default.yaml] | [Load] [Scan] [Edit] [Rsn] |
+------------------+---------------------------------------------------+
|                  |                                                    |
|  [eye] [Cols]    |  (无标题信息)                                       |
|  +--------+-----+  +----------------------------------------------+  |
|  | Symbol | All |  |                                              |  |
|  +--------+-----+  |              K-Line Chart                    |  |
|  | AAPL   |  5  |  |                                              |  |
|  | GOOGL  |  4  |  |                                              |  |
|  +--------+-----+  +----------------------------------------------+  |
|                  |  [xB][xV][_Y][xD][xPk][_Tr] | Before After       |
+------------------+---------------------------------------------------+
```

改造后：

```
+----------------------------------------------------------------------+
| [Mode: Analysis] [Config: default.yaml] | [Load] [Scan] [Edit] [Rsn] |
+---------------------+------------------------------------------------+
|                     |                                                 |
| [eye][Cols][_Turb]  |  AAPL  Wt:7.0  Cnt:5  Amp:34%  D2->B3->V->Y   |
| +--------+-----+   |  +-------------------------------------------+  |
| | Symbol | Wt  |   |  |                                           |  |
| +--------+-----+   |  |              K-Line Chart                 |  |
| | AAPL   | 7.0 |   |  |         (与现在完全相同)                    |  |
| | NVDA   | 5.0 |   |  |                                           |  |
| | TSLA * | 2.0 |   |  +-------------------------------------------+  |
| +--------+-----+   |  [xB][xV][_Y][xD][xPk][_Tr] | Before After     |
+---------------------+------------------------------------------------+
```

---

## 七、数据管道改造要点

### 7.1 composite_info 数据结构

为了在 Browse Mode 和 Analysis Mode 之间统一数据格式（遵循 `.claude/rules/UI.md` 中的代码复用原则），建议定义一个标准的 composite 信息字典格式：

```python
composite_info = {
    "symbol": str,          # 股票代码
    "weighted_sum": float,  # 有效加权强度
    "signal_count": int,    # 信号总数
    "amplitude": float,     # 价格振幅
    "turbulent": bool,      # 异常走势标记
    "sequence_label": str,  # 信号序列标签（完整格式）
}
```

- **Browse Mode**：从 JSON 的 result 字典中直接构建
- **Analysis Mode**：从 `_compute_signals_for_stock()` 的计算结果构建

两种模式在 `_on_stock_selected()` 中各自构建 `composite_info`，然后传递给同一个 `chart_manager.update_chart(composite_info=...)` 接口。

### 7.2 Analysis Mode 的额外工作

当前 `_compute_signals_for_stock()` 返回 `signals_dict: list`（信号字典列表），但未返回 `metadata`。而 `metadata` 中包含了 `amplitude` 字段，是构建 `composite_info` 的必要数据。

**建议改动**：修改 `_compute_signals_for_stock()` 的返回值为 `(signals_dict, metadata_dict)`，让调用方可以访问 amplitude。

这个改动影响 `_on_stock_selected()` 中的一处调用：

```python
# 当前
signals = self._compute_signals_for_stock(symbol, scan_date=scan_date)

# 改为
signals, compute_meta = self._compute_signals_for_stock(symbol, scan_date=scan_date)
```

### 7.3 向后兼容性

旧的 JSON 文件不包含 composite 字段。使用 `.get(key, default)` 模式确保兼容：

```python
item["weighted_sum"] = result.get("weighted_sum", 0.0)    # 旧 JSON -> 0.0
item["sequence_label"] = result.get("sequence_label", "")  # 旧 JSON -> ""
item["amplitude"] = result.get("amplitude", 0.0)           # 旧 JSON -> 0.0
item["turbulent"] = result.get("turbulent", False)          # 旧 JSON -> False
```

**特殊情况**：加载旧 JSON 时，`weighted_sum` 全为 0.0，按 Wt 排序会失去意义。建议在 `load_data()` 完成后检测是否所有 `weighted_sum` 都为 0.0，如果是则回退到按 `signal_count` 排序。

---

## 八、实现优先级与依赖关系

### 8.1 分层实施计划

```
Phase 1: 数据管道打通 (前置条件)
  |
  +--> 1a. signal_scan_manager.py: JSON 序列化增加 4 字段
  |    1b. stock_list_panel.py: load_data() 解析新字段
  |    1c. ui_config.yaml: 列标签配置
  |
  v
Phase 2: 列表增强 (核心价值)
  |
  +--> 2a. stock_list_panel.py: 列定义增加 Wt/Amp/Seq
  |    2b. stock_list_panel.py: turbulent 行视觉降权 (tag)
  |    2c. stock_list_panel.py: Hide Turbulent 复选框 (可选)
  |
  v
Phase 3: 图表 Info Bar (体验提升)
  |
  +--> 3a. canvas_manager.py: update_chart() 接收 composite_info + set_title()
  |    3b. main.py: _on_stock_selected() 构建 composite_info (Browse + Analysis)
  |    3c. main.py: _compute_signals_for_stock() 返回 metadata (Analysis Mode)
  |
  v
Phase 4: 体验优化 (可选)
  |
  +--> 4a. canvas_manager.py: tooltip 增加 strength 信息
  |    4b. composite.py: 新增 generate_compact_label() 函数
```

### 8.2 各 Phase 的价值与成本

| Phase | 核心价值 | 代码改动量 | 文件数 |
|-------|---------|-----------|--------|
| 1 | 数据可用（后续 Phase 的前置条件） | ~15 行 + 配置 | 3 |
| 2 | 用户可以按 weighted_sum 排序，一眼识别 turbulent | ~30-40 行 | 1-2 |
| 3 | 用户看图时有即时的信号摘要和上下文 | ~30-50 行 | 2-3 |
| 4 | 细节打磨 | ~15 行 | 2 |

总计约 100-120 行代码变更，4-5 个文件。

---

## 九、结论

联合信号系统的 UI 集成是一个**数据已就绪、管道缺失**的典型问题。`weighted_sum`、`sequence_label`、`amplitude`、`turbulent` 四个字段已经在后端计算完毕，只需要打通从 JSON 序列化到 UI 展示的数据通道。

从用户工作流分析得出的核心设计原则：

1. **不改变信息架构** -- 仍然是左列表 + 右图表的布局，不引入新的 panel 或 dialog
2. **不增加操作步骤** -- 用户的 Up/Down 浏览流程不变，新信息通过"被动展示"而非"主动操作"获取
3. **让数据自动说话** -- weighted_sum 排序 + turbulent 降权让有价值的股票自然浮现，不需要用户手动判断
4. **渐进式增强** -- 先打通管道（Phase 1），再增强列表（Phase 2），最后增强图表（Phase 3），每个 Phase 独立可用
5. **克制** -- 图表区域只增加 Info Bar（1 行文本），不增加新的图形元素。列表区域利用现有的列配置系统，让用户自由选择可见列
