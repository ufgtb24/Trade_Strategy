# Dev UI → path2_web 交互复刻调研

调研对象：`BreakoutStrategy/dev/` + `BreakoutStrategy/UI/charts/` 中的本地桌面 UI（matplotlib + tkinter）。
复刻目标：`path2_web`（FastAPI + Vue3 + ECharts）忠实复刻其 4 块行为。

---

## 1. 概览

Dev UI 把 K 线主图、成交量背景柱、被突破峰值/突破点的标记、悬停十字线与 tooltip annotation 全部画在**同一个 matplotlib axes**（无 twinx、无双图、无 subplot 上下分割）。这是一个一体化的"价格图叠加成交量底带"设计：

- **K 线和成交量共用同一个 y 轴**（价格单位）。成交量被线性缩放到价格图底部 20% 高度内显示，本质上是把成交量"伪装成"价格区间的一部分。布局比例为 **80% 价格 / 10% 顶部留白 / 10% 底部留白**，成交量在底部留白区作为背景柱。
- **十字线**由 matplotlib 原生的 `motion_notify_event` 驱动，垂直竖线锁在最近 bar 的整数索引、水平横线默认锁在该 bar 的 close。tooltip 是一个 `ax.annotate` artist，内容动态拼接。
- **Ctrl 切换**走 tkinter 层的 `<Control_L/R>` / `<KeyRelease-Control_*>` 绑定（不是 matplotlib 的 `key_press_event`），翻转一个状态标志位，hover 回调和 ctrl 回调共同读它来决定横线行为：按下时横线脱离 close、跟随鼠标 ydata、变橙色；释放时复位回 close、变蓝色。

四块行为耦合点都在 `BreakoutStrategy/UI/charts/canvas_manager.py` 的 `ChartCanvasManager` 类里；动态 y 轴重算与 volume bar 同步缩放在 `axes_interaction.py` 的 `AxesInteractionController._rescale_y`。

---

## 2. 每块的机制描述

### (1) 成交量柱叠加显示

**用户体验**：成交量灰色柱画在 K 线下方，作为同一张图的背景层，红涨绿跌（与 K 线红绿一致），突破日金色高亮。

**实现机制**：

- 入口：`canvas_manager.py:175` 在 K 线之前先画体积背景：
  ```
  _vol_bars = self.candlestick.draw_volume_background(
      ax_main, df, highlight_dates=breakout_dates, colors=colors
  )
  ```
  紧接着 `:180` 才 `candlestick.draw(...)` 画 K 线。zorder 体现这层关系：volume bar `zorder=1`（`candlestick.py:154`），K 线上下影线 `zorder=2`、实体 `zorder=3`（`candlestick.py:47, 62`）。

- 共用 ax：成交量和 K 线**共用 `ax_main` 这一个 axes**，**没有 twinx**。整段 codebase 对此 ax 都直接 `set_ylim`、`axhline`、`axvline`，无任何 secondary axis。

- y 轴几何（`candlestick.py:106-126`）：
  - 取可见区间内 OHLC 的 `price_min`、`price_max`，`price_range = price_max - price_min`。
  - `display_height = price_range / 0.8`，即把价格区间放大到占 ylim 总高的 80%。
  - `display_bottom = price_min - display_height * 0.1`，即底部留 10% 空白用于装成交量背景，顶部留 10% 用于标记。
  - 最终 `ax.set_ylim(display_bottom, display_bottom + display_height)`。
  - 体积缩放因子 `volume_scale_factor = (display_height * 0.2) / volume_max`，即体积柱最大高度 = 总展示高度 × 20%（参数 `volume_scale_ratio` 默认 0.2，见 `canvas_manager.py:175` 没显式传，走 default）。

- 单条柱绘制（`candlestick.py:144-156`）：`ax.bar(i, volume_height, bottom=display_bottom, width=1.0, color=..., edgecolor='black', linewidth=0.5, alpha=0.8, zorder=1)`。返回 `Rectangle` artist 列表，供动态缩放。

- 颜色（`styles.py:24-29`）：
  - `volume_up = "#D3D3D3"`（浅灰，对应 close >= open）
  - `volume_down = "#696969"`（深灰，对应 close < open）
  - `volume_highlight = "#FFD700"`（金色，对应突破日 `highlight_dates`）
  - K 线本体 `candlestick_up = "#4CAF50"`（绿）、`candlestick_down = "#B71C1C"`（红）
  - **注意**：体积柱用的是灰阶（浅灰/深灰），**不是**与 K 线一致的绿/红；只有"是否高亮（金色）"是特殊配色。柱宽 `width=1.0`，K 线实体宽 `width=0.8`（`candlestick.py:30`）——成交量柱比 K 线略宽，视觉上贴满 bar 间距。

- y 轴标签：`ax.set_ylabel("Price ($)", ...)` 在 `candlestick.py:69` **被注释掉**——主图没有显式 y 轴 label。Y 轴 ticklabels 是默认价格刻度。**成交量没有独立 y 轴标签**（同图同 y 轴，原生看不出体积绝对值）。

- 动态缩放联动（`axes_interaction.py:323-353`）：滚轮 zoom / 拖拽 pan 后调用 `_rescale_y()`：
  - 重算可见区间内 `price_min/max`，重计 `display_height`, `y_bottom`。
  - 关键：重算 `vol_scale = (display_height * volume_scale_ratio) / vis_vol_max`（**用可见区间内的最大 volume**，不是全集），逐根更新 `bar.set_y(y_bottom)` + `bar.set_height(volumes[i] * vol_scale)`。即体积柱跟随 zoom 比例**自适应缩放**，保持视觉上始终占据底部 20% 高度。

**Corner case**：
- 突破日的 highlight 颜色比 down/up 优先（`candlestick.py:136-141` 先判 highlight）。
- 全黑边框 `edgecolor='black', linewidth=0.5`，无论上涨下跌都有边。
- alpha=0.8。
- 初始绘制时 `volume_max` 是全集最大；之后 zoom/pan 才用可见区间最大重算。

---

### (2) hover 时的横竖虚线（crosshair）

**用户体验**：鼠标在图上移动时，蓝色虚十字线跟随；竖线吸附在最近 bar 中心，横线吸附在该 bar 的 close 价。

**实现机制**：

- 创建（`canvas_manager.py:732-738`）：
  ```
  self.crosshair_v = ax.axvline(0, color=colors["crosshair_normal"],
                                 linestyle="--", linewidth=1.5, alpha=0.7, visible=False)
  self.crosshair_h = ax.axhline(0, color=colors["crosshair_normal"],
                                 linestyle="--", linewidth=1.5, alpha=0.7, visible=False)
  ```
  两条线初始 `visible=False`，作为长期 artist 复用（只 `set_xdata`/`set_ydata`/`set_visible`，不重建）。

- 事件 hook（`canvas_manager.py:917`）：`self.canvas.mpl_connect("motion_notify_event", on_hover)`。
  - matplotlib 的 `motion_notify_event` 携带 `event.xdata, event.ydata`（数据坐标）和 `event.x, event.y`（像素坐标，原点左下）。

- 默认锁定逻辑（`canvas_manager.py:773, 892-895`）：
  ```
  x = int(round(event.xdata))             # 最近 bar 整数索引
  ...
  self.crosshair_v.set_xdata([x])         # 竖线 = 最近 bar 中心
  self.crosshair_h.set_ydata([row["close"]])  # 横线 = 该 bar close
  self.crosshair_h.set_color(colors["crosshair_normal"])
  ```
  即：
  - **竖线 x = 最近 bar 索引**（`int(round(event.xdata))`，吸附 bar 中心而非鼠标 x）。
  - **横线 y = 该 bar 的 close**（不是鼠标 ydata，不是 high/low/open）。
  - **颜色** = `crosshair_normal`（`#0088CC`，蓝色，`styles.py:45`），样式 `--` 虚线、宽 1.5、alpha 0.7。

- 隐藏/退出（`canvas_manager.py:759-766, 774-781`）：
  - `event.inaxes != ax`（鼠标飞出绘图区）→ 两条线 `set_visible(False)`，annotation 隐藏。
  - `x < 0 or x >= len(df)`（鼠标在 x 范围外但还在 ax 内，比如右侧留白）→ 同样隐藏。
  - 拖拽 pan 期间整段 `on_hover` 直接 return（`canvas_manager.py:757-758`，避免与 pan 控制器冲突）。

- pan 期间的额外隐藏（`canvas_manager.py:493-500` `_hide_on_pan`）：手动把 crosshair `set_visible(False)`。

**Corner case**：
- 锁定到 bar 中心而非鼠标 x：跨 bar 半幅的吸附是"四舍五入"语义（`round`），不是 floor/ceil。
- crosshair 复用同一对 artist 对象、不重建（性能 + 状态延续）。

---

### (3) hover tooltip / 数据条

**用户体验**：鼠标停在某根 bar 上时，附近弹出一个白底圆角 annotation 框，列出日期、OHLC、涨幅、Volume、RV、ATR，以及可选的 Active peaks 列表 / BO 信息 / Peak 信息。

**实现机制**：

- 创建（`canvas_manager.py:741-752`）：
  ```
  self.annotation = ax.annotate(
      "", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
      bbox=dict(boxstyle="round", fc="w", alpha=0.9),
      arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
      fontsize=22, zorder=100,
  )
  self.annotation.set_linespacing(1.5)
  self.annotation.set_visible(False)
  ```
  长期 artist，每次 hover 改 `set_text` + `xy` + `xyann` + `set_ha/va` + `set_visible(True)`。

- 文本拼接（普通模式，`canvas_manager.py:814-845`）：
  ```
  Date: 2024-...
  Open: ...
  High: ...
  Low: ...
  Close: ...
  Chg: +X.XX% 或 -X.XX%
  Volume: 1,234,567   (整数 + 千分位逗号)
  RV: 1.23            (两位小数；vol_ratio <=0 时显示 N/A)
  ATR_14: ...         (atr_period 默认 14，从 param_loader 读)
  ```
  日期格式 `'%Y-%m-%d'`。

- 字段算法：
  - **OHLC**：直接从 `df.iloc[x]` 读 `open/high/low/close` 四列。
  - **Chg（涨跌幅）**（`:817-822`）：`chg = (close[x] - close[x-1]) / close[x-1] * 100`，**相对前一根 close**（不是 `(close-open)/open`）。首根 bar 显示 `N/A`。格式：`+X.XX%` / `-X.XX%`。
  - **Volume**：`int(row['volume'])` + Python f-string `:,` 千分位。
  - **RV（相对成交量）**（`:824-829`）：调用 `FeatureCalculator.precompute_vol_ratio_series(df, lookback=63)` 预计算的序列（一次性算好，hover 时只查 `iloc[x]`）。算法（`analysis/features.py:960-975`）：
    ```
    vol_ratio[d] = volume[d] / mean(volume[max(0, d-lookback) : d])
    ```
    实现：`avg_vol = df["volume"].rolling(lookback, min_periods=1).mean().shift(1)`，再 `volume / avg_vol`，inf/nan 清零。**注意 shift(1)——分母不含当日**。`lookback` 默认 63（约 3 个月），从 `param_loader` 的 `feature_calculator_params.vol_lookback` 读，可被全局参数覆盖。RV `>0` 才显示数值，否则 `N/A`。
  - **ATR_N**（`:842-845`）：优先读 `df["atr"]` 列（preprocess 阶段预计算、含缓冲区，更准）；缺失时回退到 `TechnicalIndicators.calculate_atr(high, low, close, period)` 实时算。`period` 默认 14，从 `param_loader` 的 `atr_period` 读。NaN 则不显示。

- 额外的 BO 域相关字段（普通模式特有，path2_web 不一定要全复刻）：
  - `Active: [id1,id2,...]`：当前 x 时刻仍未被 supersede 的 active peaks ids，每次 hover 重算。
  - 若 `x` 命中某 BO（`bo.index == x`）：追加 `BO:\n[broken_peak_ids],score`，并附 `Label: key:val%` 列表（如有）。
  - 若 `x` 命中某 Peak（`peak.index == x`）：追加 `Peak:\n{id}`。

- 位置（边缘感知）（`canvas_manager.py:900-911`）：
  - `compute_tooltip_anchor(cursor_px=(event.x, event.y), fig_size=(fig_w, fig_h), est_tooltip_size=(400, 350))` 返回 `(offset_x, offset_y, ha, va)`：
    - `arrow_offset=40` 点（距 cursor 的 near corner 偏移）。
    - 若 cursor + tooltip 会越出右/上边界，自动 flip 偏移方向和 ha/va。
  - 把 `xy` 设为 `(event.xdata, event.ydata)`（箭头尖端），`xyann` 设为 `(offset_x, offset_y)`（文本框相对 xy 的偏移），用 `textcoords="offset points"` 解释偏移。

- 样式：圆角白底（`boxstyle="round"`, `fc="w"`, `alpha=0.9`），fontsize 22（rcParams 在 `:160-167` 设过整体放大字号到 32 base），linespacing 1.5，zorder 100（盖在所有内容上方）。带箭头 `arrowstyle="->", connectionstyle="arc3,rad=0"`（直箭头从 annotation 指向 xy）。

**Corner case**：
- RV 用 `>0` 判断而非 `notna`——分母为 0 时算出 0，显示 `N/A`。
- 涨幅在第一根 bar 是 `N/A`。
- ATR 在 `_atr_series` 不存在或 NaN 时直接不追加 ATR 行（不显示 `N/A`）。
- tooltip 在 ctrl 模式下只显示 `Price: {ydata:.2f}` 一行，不显示 OHLC（见下节）。
- 拖拽 pan 期间整段 hover 跳过，tooltip 不更新。

---

### (4) Ctrl 键解锁横线

**用户体验**：按住 Ctrl 时，水平虚线脱离"锁在 close"状态，改为跟随鼠标 ydata，颜色变橙；tooltip 内容也精简为只显示 `Price: {ydata:.2f}`。松开 Ctrl 立刻复位。

**实现机制**：

- 事件 hook：**不是** matplotlib 的 `key_press_event`，而是 **tkinter 层的 `canvas.get_tk_widget().bind`**（`canvas_manager.py:943-947`）：
  ```
  canvas_widget.bind("<Control_L>", self._on_ctrl_press)
  canvas_widget.bind("<Control_R>", self._on_ctrl_press)
  canvas_widget.bind("<KeyRelease-Control_L>", self._on_ctrl_release)
  canvas_widget.bind("<KeyRelease-Control_R>", self._on_ctrl_release)
  ```
  左右 Ctrl 都覆盖。

- 焦点保障（`canvas_manager.py:923, 949-957`）：
  - `canvas_widget.configure(takefocus=True)` + 鼠标 `<Enter>` 时 `focus_set()` + 鼠标 `<Button-1>` 也 `focus_set()`（add="+"，不覆盖 mpl 原绑定）。
  - `<FocusOut>` 强制 `_ctrl_pressed = False`：防止"按住 Ctrl 切窗"导致状态卡死。

- 状态机：单个 bool `self._ctrl_pressed`；三方读写：
  - `_on_ctrl_press`（`:1030-1060`）：去重（已按则 return）、置 True、立即把 crosshair_h 颜色改 `crosshair_ctrl`（`#FF6600` 橙）、若有保存的 `_last_mouse_y/x` 立即把横竖线移到鼠标位置（脱离 K 线吸附）、`canvas.draw_idle()`。
  - `_on_ctrl_release`（`:1062-1092`）：去重（未按则 return）、置 False、颜色复位 `crosshair_normal`（蓝）、横线 ydata 复位到 `df.iloc[_last_hover_x]["close"]`、竖线 xdata 复位到 `_last_hover_x`（最近 bar 索引）、`draw_idle()`。
  - `on_hover` 在每次鼠标移动也读 `self._ctrl_pressed`（`:805-812`）：True 则把横线设到 `event.ydata`、竖线设到 `event.xdata`（**不 round 到 bar 中心**），颜色橙；False 则走默认锁定（竖线 round 到 bar 索引、横线锁 close、颜色蓝）。

- ctrl 模式下的 tooltip 文本（`canvas_manager.py:807`）：
  ```
  text = f"Price: {event.ydata:.2f}"
  ```
  只一行，两位小数。没有日期/OHLC/RV/ATR。

- 状态保存（`canvas_manager.py:795-798`）：每次 hover 都更新 `_last_mouse_x/y`（数据坐标，鼠标实际位置）和 `_last_hover_x`（最近 bar 索引）。这些值供 press/release 复位时使用——意味着 ctrl 切换发生在 hover 之后才有可用的"上次位置"，否则首次按 ctrl 时 crosshair 不会跳（保持上次 hover 位置）。

**Corner case**：
- 按住 Ctrl 拖到图外再回来：`event.inaxes != ax` 时 hover 走隐藏分支，crosshair 不可见；回来后 hover 重新激活，仍读 `_ctrl_pressed` 决定显示模式。
- 窗口失焦自动复位（前面提到 `<FocusOut>`），防止状态泄漏。
- 释放 Ctrl 时**自动复位**：横线立刻回到最近 hover bar 的 close、颜色变蓝、tooltip 下一次 hover 才会刷新成完整 OHLC（release 本身不刷 tooltip 文本）。
- press/release 在已是同状态时早 return，避免重复 redraw。
- 颜色：`crosshair_normal = "#0088CC"`、`crosshair_ctrl = "#FF6600"`（`styles.py:45-46`）。
- Ctrl 模式下**竖线也跟随鼠标 xdata**（不只是横线脱离 close）——这一点用户描述里没强调，但代码实际两条线一起脱离吸附。

---

## 3. path2_web 复刻的关键差异点

path2_web 用 ECharts；matplotlib 和 ECharts 在事件模型、绘图模型、坐标轴模型上差异显著。下面把 4 块每块的复刻难度按"直接映射 / 等价机制 / 折中或放弃"三档分类。

### (1) 成交量柱叠加显示

**关键差异**：

- **多 y 轴 vs 单 y 轴**：Dev UI 用**单 y 轴**，把成交量缩放进价格区底部 10% 留白；ECharts 的官方惯例（candlestick + volume）是**双 grid 两图上下** 或 **单 grid + dataZoom 联动**。复刻 Dev UI 的"叠加在同一图"语义有两种选择：
  - **等价机制**：单 grid + 双 yAxis（价格 yAxis 主、成交量 yAxis 副，副轴隐藏）——但这是 twinx 语义，Dev UI 用的是 manual rescale 进入单 yAxis。
  - **直接映射**：把成交量按 `(display_height * 0.2) / vis_vol_max` 缩放后作为 bar series 画到价格 yAxis 上（与 Dev UI 1:1 同语义）——需要前端在 zoom 触发时手动重算 vol scale 并更新 bar data。
- **动态联动**：matplotlib 是 imperative artist update，ECharts 是 setOption 重渲染。横向 zoom（dataZoom）时需要前端监听 `datazoom` 事件，重算可见区间内 `vis_vol_max`，重设 series data —— 这是**需要选择 ECharts 等价机制**的关键约束。
- **颜色与宽度**：直接可映射（hex 颜色、`barWidth`、`itemStyle.opacity`）。
- **bar 与 candlestick 的 zorder**：ECharts series 顺序决定堆叠顺序，把 bar series 放前、candlestick 后即可——直接可映射。

**总结**：核心机制（80/10/10 比例 + 20% 体积带 + 跟随 zoom 重算 scale）需要前端实现；ECharts 提供的 markArea/双轴默认行为不直接给。

### (2) hover 时的横竖虚线（crosshair）

**关键差异**：

- **事件 hook**：matplotlib `motion_notify_event` ↔ ECharts `axisPointer` 内置组件 + `'mouseover'` / `'updateAxisPointer'` 事件。ECharts **天然提供** crosshair（`tooltip.axisPointer.type = 'cross'`），不需要手画 axvline/axhline。
- **吸附 bar 中心**：ECharts `axisPointer.type = 'cross'` 默认在类目轴上吸附 bar 中心、在数值轴上跟随鼠标。Dev UI 的"竖线吸附 bar 中心"语义与 ECharts 默认契合——**直接映射**。
- **横线锁定 close**：ECharts 默认横线跟随鼠标 ydata（数值轴）。**Dev UI 的"横线锁该 bar close"是非默认行为**——需要监听 `updateAxisPointer` 或 `mouseover` 事件，自行 setOption 覆盖 axisPointer 的 y 值，或者干脆禁用内置 axisPointer.y + 用 markLine 手画。这是**需要选择 ECharts 等价机制**的差异点。
- **样式**：虚线 / 颜色 / linewidth / alpha → `lineStyle: { type: 'dashed', color, width, opacity }`，直接可映射。
- **隐藏逻辑**：飞出 ax / 在 x 范围外 → ECharts 内置 axisPointer 鼠标离开自动隐藏；但 Dev UI 在 pan 期间也手动隐藏，path2_web 如果有自定义 pan 操作要同步处理。

**总结**：竖线吸附 bar 中心可直接靠 ECharts axisPointer，但**横线锁 close** 是 Dev UI 的关键自定义行为，必须 override 默认。

### (3) hover tooltip / 数据条

**关键差异**：

- **tooltip artist**：matplotlib `ax.annotate` ↔ ECharts `tooltip.formatter`（函数形式返回 HTML 字符串）。**直接可映射**。
- **字段数据来源**：
  - **OHLC / Volume**：直接从前端数据数组读，**直接可映射**。
  - **Chg（前一根 close 涨跌幅）**：前端可以 `data[i].close - data[i-1].close`，**直接可映射**。算法明确 `(close[x] - close[x-1]) / close[x-1] * 100`。
  - **RV（相对成交量）**：算法 `vol[d] / mean(vol[d-63:d])`（rolling 63 + shift 1）。**需要决定算在哪一层**：
    - 前端算：简单（pandas-like 一维操作）但要传完整 volume 序列。
    - 后端预算后随响应返回 `rv` 字段：与 Dev UI 一致（Dev UI 也是预算后只查 `iloc[x]`），更稳。
    - 注意：path2_web 没有 `FeatureCalculator` 这套，需要独立移植算法（公式简单）。lookback=63 应作为可配参数。
  - **ATR_N**：Dev UI 优先读 `df["atr"]` 列，缺失则用 `TechnicalIndicators.calculate_atr` 实时算。算法是 Wilder's ATR，**需要后端实现**或前端实现。可能是 path2_web 不需要的字段（path2 主线不依赖 ATR）——**可考虑放弃或 nice-to-have**。
- **BO/Peak 域字段**：`Active peaks`、`BO: [ids],score`、`Peak: {id}` 等是 BreakoutStrategy 专属——path2 没有 Peak/Breakout 概念，**应放弃**。path2_web 可以替换为 path2 事件相关的字段（如该 bar 命中的 event_id / role / span）。
- **位置算法**：`compute_tooltip_anchor` 边缘感知 flip 是纯函数（38 行），可以直接移植成 JS 工具函数；但 ECharts `tooltip.position` 函数签名已经把 `(point, params, dom, rect, size)` 全提供，flip 逻辑内嵌即可。**直接可映射**。
- **字体/样式**：`fontsize=22`、白底圆角、行距 1.5 → ECharts `tooltip.textStyle` + CSS，**直接可映射**。

**总结**：OHLC/Chg/Volume 完全直映；RV 需要选算法落点（推荐后端注入）；ATR 与 BO/Peak 字段是项目特异，**应放弃或换成 path2 事件字段**。

### (4) Ctrl 键解锁横线

**关键差异**：

- **事件 hook**：Dev UI 用 tkinter `<Control_L/R>` + `<KeyRelease-Control_*>`，**因为 matplotlib 的 key_press_event 在 TkAgg 后端对修饰键的支持不稳**。Web 端用 `document.addEventListener('keydown'/'keyup', e => e.ctrlKey)` 是**直接可映射**，无平台坑。
- **焦点机制**：Dev UI 要 takefocus + 鼠标 enter 自动 focus + FocusOut 复位（tkinter 焦点是显式的）。Web 端 keydown 默认全局监听 document，**不需要焦点管理**——比 Dev UI 简单。仍要处理"窗口失焦/切 tab 时 release 事件丢失"——可绑 `window.addEventListener('blur', ...)` 强制复位。
- **横线脱离 close**：与第 (2) 点联动——ECharts 默认横线本来就跟随鼠标 ydata。所以 Dev UI 的"按 Ctrl 解锁"在 ECharts 里反而是**默认行为**；"不按 Ctrl 时锁 close" 才是需要 override 的非默认行为。即：**复刻方向反过来——默认锁 close、Ctrl 切回默认跟随鼠标**。
- **颜色切换**：橙/蓝两色直接可映射。
- **tooltip 文本切换**：Ctrl 模式下只显 `Price: {y:.2f}`、普通模式显完整字段——`tooltip.formatter` 内读 `ctrlPressed` 状态分支返回不同 HTML，**直接可映射**。
- **竖线也跟随鼠标**：Dev UI ctrl 模式下竖线也脱离 bar 中心。ECharts axisPointer 在类目轴上默认吸附 bar，**需要 override** 或切换 axisPointer 配置（如 `snap: false`）。

**总结**：事件 hook 比 Dev UI 简单（无焦点管理），但要注意 ECharts 默认行为和 Dev UI 默认相反——"按住 Ctrl"在 ECharts 里要 override 的是"取消 close 锁定"。

---

## 4. 一句话建议

**Must-have**：(1) 成交量叠加底部 20% 高度带（path2 用户也要看量价配合）、(2) 十字线（ECharts axisPointer.cross 改造）、(3) tooltip 的 OHLC/Chg/Volume/RV 四项核心字段——这三块是看 K 线的最低必需配置。

**Nice-to-have / 可放弃**：(3) 中的 ATR 字段（path2 不依赖）、(4) Ctrl 解锁横线（path2 用户场景里"价格读数"远不如"对齐 close 比较"重要，且 ECharts 跟随鼠标本来就是默认，Ctrl 解锁的边际价值在 web 端打折）。BO/Peak 相关字段应该直接换成 path2 事件字段（event_id / role / span 边界）而不是删除——同样信息密度，但口径切到 path2。
