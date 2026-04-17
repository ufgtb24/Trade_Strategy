# UI 共享包架构意图

> 最后更新：2026-04-17

## 定位

`BreakoutStrategy/UI/` 是 **dev 与 live 两个应用共用的纯 UI 基础设施**，
不含任何业务逻辑、策略参数或应用特定的交互流程。任何"两个应用都要用到"
的界面原语都可以放在这里。

## 组成

- `charts/` — K 线图渲染子包
  - `canvas_manager.py`: 图表画布 + matplotlib + tkinter 整合
  - `range_utils.py`: 三层范围（scan/compute/display）的 `ChartRangeSpec` 语义
  - `axes_interaction.py`: 坐标轴缩放 / 拖动
  - `filter_range.py`: 基于数据范围的过滤规则
  - `tooltip_anchor.py`: tooltip 锚点计算
  - `components/`: 蜡烛、标记、分析面板等原子绘图组件
- `styles.py` — Tkinter/matplotlib 共用字体、颜色常量、ttk 样式

## 边界

**允许放入 UI/ 的**：纯粹的界面原语，不依赖任何特定应用流程。

**不允许放入 UI/ 的**：
- 策略参数加载（→ 顶层 `param_loader.py`）
- dev 专属的编辑器 / 面板 / 对话框（→ `dev/`）
- live 专属的盯盘面板 / pipeline（→ `live/`）

## 依赖方向

- `UI/` 可依赖：`analysis/`（仅为画图需要的类型）、标准库、matplotlib / tkinter
- `UI/` 不应依赖：`dev/`、`live/`、`mining/`、`news_sentiment/`——会造成循环或反向依赖

## 历史

历史上 `charts/` 和 `styles.py` 曾埋在 `dev/`（当时叫 `UI/`）里，live
开发时直接复用，产生 `live → dev` 的反向依赖。2026-04-17 重构把这些共享件
抽到顶层 `BreakoutStrategy/UI/`，dev 和 live 都从 UI/ 引用，恢复单向依赖。
