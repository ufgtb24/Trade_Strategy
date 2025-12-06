# 交互式UI使用指南

## 快速开始

### 1. 创建测试数据（如果还没有）

```bash
python scripts/create_test_data.py
```

这将下载5只股票（AAPL, MSFT, GOOGL, AMZN, TSLA）的数据并执行扫描，生成 `scan_results/test_scan.json`。

### 2. 启动交互式查看器

```bash
python scripts/interactive_viewer.py
```

### 3. 加载扫描结果

1. 点击"加载扫描结果"按钮
2. 选择 `scan_results/test_scan.json`
3. 股票列表将显示所有扫描结果

### 4. 查看图表

- **点击**股票列表中的任意股票查看图表
- 使用 **↑/↓箭头键** 快速切换股票
- **鼠标悬停**在K线上查看详细数据

### 5. 调整参数

- 修改 **Window** 或 **Threshold** 参数
- 500ms后自动刷新当前图表
- 或点击"刷新图表"按钮立即刷新

### 6. 筛选股票

- **Min Quality**: 最低质量分数
- **Min Breakthroughs**: 最少突破数量
- 点击"重置"清除筛选

### 7. 排序

点击列头（Symbol, Breakthroughs, Active Peaks等）进行排序。

## 功能特性

### ✅ 已实现

- [x] 批量扫描股票（并行处理）
- [x] 交互式股票列表（筛选、排序）
- [x] 实时参数调整（500ms防抖）
- [x] 键盘导航（↑/↓/Enter）
- [x] 鼠标悬停显示详细数据
- [x] 内存自动清理（防泄漏）
- [x] LRU缓存（最近10只股票）
- [x] 完全复用现有可视化组件

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| ↑ | 上一只股票 |
| ↓ | 下一只股票 |
| Enter | 刷新当前图表 |

## 批量扫描

如果需要扫描更多股票：

```bash
# 扫描前100只股票
python scripts/batch_scan.py --max-stocks 100

# 扫描所有股票（10855只，需要数据文件兼容）
python scripts/batch_scan.py

# 自定义参数
python scripts/batch_scan.py --window 7 --threshold 0.01 --workers 16
```

## 注意事项

### PKL文件兼容性

项目中的 `datasets/pkls/` 目录下的PKL文件是旧版pandas格式，当前pandas版本无法读取。

**解决方案**：
1. 使用测试数据（已通过yfinance下载）：`datasets/test_pkls/`
2. 或使用yfinance重新下载所需股票数据

### 性能

- 图表刷新时间：< 1秒
- LRU缓存：最近10只股票数据
- 参数调整防抖：500ms
- 并行扫描：8个worker进程

## 文件结构

```
BreakthroughStrategy/visualization/interactive/
├── __init__.py                  # 模块导出
├── scan_manager.py              # 批量扫描管理器
├── interactive_ui.py            # 主窗口
├── stock_list_panel.py          # 股票列表面板
├── parameter_panel.py           # 参数配置面板
├── chart_canvas_manager.py      # 图表Canvas管理
├── navigation_manager.py        # 键盘导航管理
├── utils.py                     # 工具函数
└── README.md                    # 本文档

scripts/
├── batch_scan.py               # 批量扫描脚本
├── create_test_data.py         # 创建测试数据
└── interactive_viewer.py       # 交互式查看器启动脚本
```

## 保留的静态功能

交互式UI不影响现有静态图片生成功能：

```bash
# 仍然可以使用静态模式
python scripts/visual_demo.py
```

所有可视化组件（CandlestickComponent, MarkerComponent, PanelComponent）完全复用，无需修改。
