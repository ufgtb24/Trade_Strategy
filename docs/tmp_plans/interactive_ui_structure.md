# 交互式 UI 结构分析 (Interactive UI Structure)

基于 `BreakthroughStrategy/visualization/interactive` 目录下的文件结构分析，该模块采用了组件化的设计模式，整体呈现为经典的 **Top-Left-Right** 布局。

## 1. 整体 UI 架构树

```text
Root Window (由 interactive_ui.py 创建)
├── [顶部区域] ParameterPanel (来自 parameter_panel.py)
│   └── container (Frame)
│       ├── 按钮组 (Load Scan, Load Params, Reload)
│       └── 状态栏 (Status Label)
│
└── [主体区域] PanedWindow (水平分割窗口，由 interactive_ui.py 管理)
    │
    ├── [左侧面板] StockListPanel (来自 stock_list_panel.py)
    │   └── Frame
    │       ├── 搜索/过滤框 (推测)
    │       └── Treeview (股票列表表格)
    │           └── Scrollbar (滚动条)
    │
    └── [右侧面板] Chart Area (由 chart_canvas_manager.py 管理)
        └── Frame
            ├── Matplotlib Toolbar (顶部或底部的工具栏)
            └── FigureCanvasTkAgg (核心绘图画布，显示 K 线)
```

## 2. 各个文件的 UI 职责划分

### A. 总容器：`interactive_ui.py`
*   **角色**：主窗口 (Main Window) / 协调者。
*   **职责**：
    *   创建主窗口根容器。
    *   **顶部**放置 `ParameterPanel` 实例。
    *   **中间**创建一个 `ttk.PanedWindow`（可拖动调整大小的分隔窗格），方向为水平 (`orient=tk.HORIZONTAL`)。
    *   将 `StockListPanel` 添加到 PanedWindow 的左侧。
    *   创建一个 Frame 作为图表容器，添加到 PanedWindow 的右侧，并交给 `ChartCanvasManager` 去填充。
    *   定义回调函数，协调各组件间的通信（如：点击列表 -> 更新图表）。

### B. 顶部面板：`parameter_panel.py`
*   **角色**：控制面板。
*   **职责**：
    *   提供加载扫描结果、加载参数、重载参数的按钮。
    *   显示当前状态（Ready, Loaded 等）。
    *   通过回调函数通知主窗口进行数据更新。

### C. 左侧列表：`stock_list_panel.py`
*   **角色**：显示扫描结果的股票清单。
*   **职责**：
    *   展示股票代码、名称、日期、信号类型等信息。
    *   处理用户的选择事件（点击行）。
    *   通常包含 `ttk.Treeview` 和 `ttk.Scrollbar`。

### D. 右侧图表：`chart_canvas_manager.py`
*   **角色**：负责 K 线图的绘制和交互。
*   **职责**：
    *   管理 `matplotlib.figure.Figure` 对象。
    *   将 `FigureCanvasTkAgg` 嵌入到 Tkinter 界面中。
    *   提供图表工具栏 (`NavigationToolbar2Tk`)。
    *   处理具体的绘图逻辑（调用底层的 plotters）。

## 3. 辅助模块 (非 UI 显示)

*   **`navigation_manager.py`**：
    *   负责逻辑导航，监听键盘事件（如 Up/Down 键），在 `StockListPanel` 中自动切换股票并触发图表更新。
*   **`scan_manager.py`**：
    *   负责数据逻辑：读取 JSON 扫描结果文件，解析数据，提供给 `StockListPanel` 显示。
*   **`ui_config_loader.py` / `ui_param_loader.py`**：
    *   负责读取配置文件（YAML/JSON），保存和加载 UI 状态及分析参数。
