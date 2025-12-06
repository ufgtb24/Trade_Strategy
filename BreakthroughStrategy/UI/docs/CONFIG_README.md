# 可视化界面配置说明

## 配置文件位置

`BreakthroughStrategy/visualization/interactive/ui_config.yaml`

## 配置项说明

### 1. 股票扫描结果路径设置 (`scan_results`)

```yaml
scan_results:
  # 默认的扫描结果存放路径（相对于项目根目录）
  default_dir: "scan_results"

  # 最近使用的扫描结果文件（可选，留空表示无）
  recent_file: ""
```

**说明**：
- `default_dir`：点击"Load Scan Results"按钮时，文件选择对话框默认打开的目录
- `recent_file`：保留字段，用于未来实现"最近打开"功能

### 2. 股票数据路径设置 (`stock_data`)

```yaml
stock_data:
  # 股票数据搜索路径（按优先级顺序，第一个为默认优先路径）
  search_paths:
    - "datasets/test_pkls"
    - "datasets/pkls"
```

**说明**：
- `search_paths`：按优先级排列的股票数据搜索路径列表
  - 加载股票数据时，会依次尝试这些路径
  - 找到第一个存在的文件后立即返回
  - 第一个路径即为默认优先使用的数据源

### 3. UI显示设置 (`ui`)

```yaml
ui:
  # 默认窗口大小
  window_width: 1600
  window_height: 900

  # 左侧股票列表面板宽度比例（0-1）
  left_panel_weight: 0.3

  # 右侧图表面板宽度比例（0-1）
  right_panel_weight: 0.7
```

**说明**：
- `window_width` / `window_height`：启动时的默认窗口大小（像素）
- `left_panel_weight` / `right_panel_weight`：面板宽度比例（保留字段，暂未实现）

## 使用方式

### 方式一：直接编辑配置文件

修改 `ui_config.yaml` 文件中的路径设置即可。

**示例**：如果你的股票数据在 `data/stocks/` 目录下：

```yaml
stock_data:
  search_paths:
    - "data/stocks"        # 新路径将作为默认优先路径
    - "datasets/test_pkls"
    - "datasets/pkls"
```

### 方式二：通过代码加载配置

```python
from BreakthroughStrategy.visualization.interactive.ui_config_loader import get_ui_config_loader

# 获取配置加载器（单例）
config_loader = get_ui_config_loader()

# 获取项目根目录
project_root = config_loader.get_project_root()

# 获取各项配置（默认返回绝对路径）
scan_dir = config_loader.get_scan_results_dir()  # 绝对路径
stock_dir = config_loader.get_stock_data_dir()  # 绝对路径
search_paths = config_loader.get_stock_data_search_paths()  # 绝对路径列表
width, height = config_loader.get_window_size()

# 也可以获取相对路径
scan_dir_rel = config_loader.get_scan_results_dir(absolute=False)
stock_dir_rel = config_loader.get_stock_data_dir(absolute=False)

print(f"项目根目录: {project_root}")
print(f"扫描结果目录 (绝对): {scan_dir}")
print(f"扫描结果目录 (相对): {scan_dir_rel}")
print(f"股票数据目录: {stock_dir}")
print(f"搜索路径: {search_paths}")
print(f"窗口大小: {width}x{height}")
```

### 方式三：使用自定义配置文件

```python
from BreakthroughStrategy.visualization.interactive.ui_config_loader import get_ui_config_loader

# 使用自定义配置文件
config_loader = get_ui_config_loader("/path/to/custom_config.yaml")
```

## 代码集成

配置加载器已集成到以下模块：

### `parameter_panel.py`
- 点击"Load Scan Results"按钮时，自动使用配置中的 `scan_results.default_dir`

### `interactive_ui.py`
- 启动时使用配置中的窗口大小 (`ui.window_width` / `ui.window_height`)
- 加载股票数据时，按 `stock_data.search_paths` 顺序查找文件

## 路径说明

所有路径均为**相对于项目根目录**的相对路径。

**项目根目录**：`/home/yu/PycharmProjects/Trade_Strategy/`

**示例**：
- 配置中的 `"scan_results"` 实际指向 `/home/yu/PycharmProjects/Trade_Strategy/scan_results/`
- 配置中的 `"datasets/test_pkls"` 实际指向 `/home/yu/PycharmProjects/Trade_Strategy/datasets/test_pkls/`

## 配置加载机制

- **单例模式**：全局只会有一个配置加载器实例，多次调用 `get_ui_config_loader()` 返回同一实例
- **延迟加载**：第一次调用时才会读取配置文件
- **默认配置**：如果配置文件中缺少某项，会使用代码中的默认值
- **自动路径转换**：配置加载器会自动检测项目根目录，并将相对路径转换为绝对路径
  - `get_scan_results_dir()` 默认返回绝对路径
  - `get_stock_data_dir()` 默认返回绝对路径
  - `get_stock_data_search_paths()` 默认返回绝对路径列表
  - 可通过 `absolute=False` 参数获取相对路径

## 常见问题

### Q: 修改配置后需要重启程序吗？
A: 是的，配置文件在程序启动时读取一次，修改后需要重启可视化界面。

### Q: 可以使用绝对路径吗？
A: 不推荐。建议始终使用相对路径，便于项目移植和团队协作。

### Q: 如何添加新的搜索路径？
A: 在 `stock_data.search_paths` 列表中添加新路径即可：

```yaml
stock_data:
  search_paths:
    - "my_custom_data"     # 新增路径
    - "datasets/test_pkls"
    - "datasets/pkls"
```

### Q: 搜索路径的优先级如何确定？
A: 按列表顺序从上到下依次尝试，找到第一个存在的文件后立即返回。

### Q: 为什么文件对话框能正确打开配置的目录？
A: 配置加载器会自动将相对路径转换为绝对路径。无论程序从哪个目录启动，都能正确找到配置的目录。配置加载器通过配置文件的位置自动推导项目根目录，然后拼接相对路径得到绝对路径。
