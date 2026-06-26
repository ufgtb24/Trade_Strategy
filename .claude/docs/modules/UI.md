# UI 共享包架构意图

> 最后更新：2026-05-28

## 定位

`BreakoutStrategy/UI/` 是 **dev/live 共享的纯渲染基础设施**（无状态原子组件）。
当前消费方：`BreakoutStrategy.dev`、`BreakoutStrategy.live`。

**唯一红线**：
- 进 UI/ 的必须是 **无状态原子组件**（纯绘图函数 / 几何工具）或 **无业务知识的适配函数**
- 有状态应用胶水（holds Figure/Canvas/hover state）留应用层

## 组成

- `charts/` — K 线图渲染子包
  - `canvas_manager.py`: 图表画布 + matplotlib + tkinter 整合（BO 业务渲染器，见历史包袱）
  - `range_utils.py`: 三层范围（scan/compute/display）的 `ChartRangeSpec` 语义
  - `axes_interaction.py`: 坐标轴缩放 / 拖动（无状态原子）
  - `filter_range.py`: 基于数据范围的过滤规则
  - `tooltip_anchor.py`: tooltip 锚点计算
  - `components/`: 蜡烛、标记、分析面板等原子绘图组件
- `styles.py` — Tkinter/matplotlib 共用字体、颜色常量、ttk 样式

## 边界

**允许放入 UI/ 的**：纯粹的界面原语，不依赖任何特定应用流程；无业务知识的适配函数。

**不允许放入 UI/ 的**：
- 策略参数加载（→ 顶层 `param_loader.py`）
- dev 专属的编辑器 / 面板 / 对话框（→ `dev/`）
- live 专属的盯盘面板 / pipeline（→ `live/`）
- 走势-特异判定逻辑（→ `path2_apps/<走势>/`）

## 依赖方向

- `UI/` 可依赖：`analysis/`（仅为画图需要的类型）、`path2/`、`path2_apps/`、标准库、matplotlib / tkinter
- `UI/` 不应依赖：`dev/`、`live/`、`mining/`、`news_sentiment/`——会造成循环或反向依赖

## 历史包袱（future work，本次不动）

`UI/charts/canvas_manager.py` 和 `UI/charts/components/{markers, panels, score_tooltip}.py`
实际是 BO 业务渲染器，被错放在 UI/（2026-04-17 重构时随手搬过来的）。
- dev/live 中工作良好，本次不动
- 长期重构方向：搬到 `BreakoutStrategy/UI_BO/` 或 `dev_live_shared/`
- 触发条件：有第三个应用需要 K 线绘图，或 dev/live UI 大版本重构时顺手

## 历史

历史上 `charts/` 和 `styles.py` 曾埋在 `dev/`（当时叫 `UI/`）里，live
开发时直接复用，产生 `live → dev` 的反向依赖。2026-04-17 重构把这些共享件
抽到顶层 `BreakoutStrategy/UI/`，dev 和 live 都从 UI/ 引用，恢复单向依赖。
