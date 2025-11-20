# 可视化界面配置系统实现总结

## 实现时间
2025-11-27

## 需求背景
用户需要一个配置文件来管理可视化软件运行时的默认路径设置，包括：
1. 股票扫描结果的存放路径
2. 股票数据文件夹路径

所有路径均使用项目相对路径。

## 实现方案

### 1. 创建配置文件

**文件位置**: `BreakthroughStrategy/visualization/interactive/ui_config.yaml`

**配置结构**:
```yaml
# 股票扫描结果路径设置
scan_results:
  default_dir: "scan_results"
  recent_file: ""

# 股票数据路径设置
stock_data:
  search_paths:
    - "datasets/test_pkls"
    - "datasets/pkls"
  default_dir: "datasets/test_pkls"

# UI显示设置
ui:
  window_width: 1600
  window_height: 900
  left_panel_weight: 0.3
  right_panel_weight: 0.7
```

**设计特点**:
- 所有路径均为相对于项目根目录的相对路径
- `stock_data.search_paths` 支持多路径按优先级查找
- 扩展性强，预留了 UI 显示配置和最近文件功能

### 2. 创建配置加载器

**文件**: `BreakthroughStrategy/visualization/interactive/ui_config_loader.py`

**核心类**: `UIConfigLoader`

**设计模式**: 单例模式

**主要方法**:
- `get_scan_results_dir()`: 获取扫描结果默认目录
- `get_recent_scan_file()`: 获取最近使用的扫描文件（预留功能）
- `set_recent_scan_file(path)`: 设置最近使用的扫描文件
- `get_stock_data_dir()`: 获取股票数据默认目录
- `get_stock_data_search_paths()`: 获取股票数据搜索路径列表
- `get_window_size()`: 获取窗口大小配置
- `get_panel_weights()`: 获取面板权重配置
- `get_all_config()`: 获取完整配置
- `save_config(path)`: 保存配置到文件

**全局访问函数**: `get_ui_config_loader(config_path=None)`

### 3. 集成到现有模块

#### 3.1 `parameter_panel.py`

**修改位置**: `_on_load_clicked()` 方法

**修改内容**:
```python
# 从配置文件加载默认目录
config_loader = get_ui_config_loader()
default_dir = config_loader.get_scan_results_dir()

file_path = askopenfilename(
    parent=root,
    title="Select Scan Results",
    initialdir=default_dir,  # 使用配置的默认目录
    filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    font_size=15,
)
```

**效果**: 点击"Load Scan Results"按钮时，文件选择对话框自动打开配置中指定的目录。

#### 3.2 `interactive_ui.py`

**修改点 1**: 窗口大小配置
```python
# 从配置文件加载窗口大小
self.config_loader = get_ui_config_loader()
width, height = self.config_loader.get_window_size()
self.root.geometry(f"{width}x{height}")
```

**修改点 2**: 股票数据加载逻辑
```python
def _load_stock_data(self, symbol: str) -> pd.DataFrame:
    # 从配置文件获取搜索路径列表
    search_paths = self.config_loader.get_stock_data_search_paths()

    # 按优先级依次尝试
    for path_str in search_paths:
        data_path = Path(path_str) / f'{symbol}.pkl'
        if data_path.exists():
            return pd.read_pickle(data_path)

    # 如果都找不到，抛出异常
    raise FileNotFoundError(
        f"Data file for {symbol} not found in: {', '.join(search_paths)}"
    )
```

**效果**:
- 启动时使用配置的窗口大小
- 加载股票数据时按配置的优先级顺序查找文件
- 提高了路径查找的灵活性

### 4. 创建文档和示例

#### 4.1 配置说明文档

**文件**: `BreakthroughStrategy/visualization/interactive/CONFIG_README.md`

**内容**:
- 配置文件位置和结构说明
- 各配置项的详细说明
- 三种使用方式（直接编辑、代码加载、自定义路径）
- 代码集成说明
- 路径说明和常见问题

#### 4.2 使用示例脚本

**文件**: `scripts/example_ui_config_usage.py`

**功能**:
- 演示如何获取各项配置
- 展示搜索路径是否存在
- 演示动态修改配置
- 打印完整配置内容

**运行效果**:
```bash
$ python scripts/example_ui_config_usage.py

============================================================
UI配置加载器使用示例
============================================================

【1. 扫描结果路径配置】
  默认扫描结果目录: scan_results
  最近打开的文件: (无)

【2. 股票数据路径配置】
  默认股票数据目录: datasets/test_pkls
  搜索路径（按优先级）:
    1. datasets/test_pkls ✓
    2. datasets/pkls ✓

【3. UI显示配置】
  窗口大小: 1600x900
  面板权重: 左侧=0.3, 右侧=0.7
...
```

## 技术亮点

### 1. 单例模式
- 确保全局只有一个配置实例
- 避免重复读取文件，提高性能
- 配置在程序生命周期内保持一致

### 2. 优先级搜索机制
- 支持多个数据源路径
- 按优先级依次查找，找到即返回
- 灵活应对不同环境的数据存放位置

### 3. 相对路径设计
- 所有路径相对于项目根目录
- 便于项目移植和团队协作
- 避免硬编码绝对路径

### 4. 可扩展性
- 预留了 `recent_file` 字段用于"最近打开"功能
- 预留了面板权重配置用于布局调整
- 配置结构清晰，易于添加新配置项

### 5. 向后兼容
- 如果配置文件缺失某项，使用代码中的默认值
- 不会因配置错误导致程序崩溃

## 文件清单

### 新增文件
1. `BreakthroughStrategy/visualization/interactive/ui_config.yaml` - 配置文件
2. `BreakthroughStrategy/visualization/interactive/ui_config_loader.py` - 配置加载器
3. `BreakthroughStrategy/visualization/interactive/CONFIG_README.md` - 配置说明文档
4. `scripts/example_ui_config_usage.py` - 使用示例
5. `docs/tmp_plans/ui_config_implementation_summary.md` - 本总结文档

### 修改文件
1. `BreakthroughStrategy/visualization/interactive/parameter_panel.py` - 集成扫描结果路径配置
2. `BreakthroughStrategy/visualization/interactive/interactive_ui.py` - 集成股票数据路径和窗口配置

## 使用建议

### 开发环境
如果使用测试数据集，保持默认配置即可：
```yaml
stock_data:
  search_paths:
    - "datasets/test_pkls"  # 优先使用测试数据
    - "datasets/pkls"
```

### 生产环境
如果使用完整数据集，调整优先级：
```yaml
stock_data:
  search_paths:
    - "datasets/pkls"       # 优先使用完整数据
    - "datasets/test_pkls"
```

### 自定义数据源
添加自定义路径到搜索列表：
```yaml
stock_data:
  search_paths:
    - "my_data_source"      # 自定义路径
    - "datasets/test_pkls"
    - "datasets/pkls"
```

## 测试验证

### 功能测试
✅ 配置文件正常加载
✅ 所有配置项正确读取
✅ 路径存在性检查正常
✅ 单例模式工作正常
✅ 示例脚本运行成功

### 集成测试
✅ `parameter_panel.py` 使用配置的扫描目录
✅ `interactive_ui.py` 使用配置的窗口大小
✅ `interactive_ui.py` 使用配置的搜索路径加载股票数据

## 后续扩展建议

1. **最近打开功能**:
   - 实现 `recent_file` 字段的保存和加载
   - 在参数面板添加"最近打开"快捷按钮

2. **配置验证**:
   - 添加配置文件格式验证
   - 检查路径是否存在并给出友好提示

3. **配置热重载**:
   - 支持运行时重新加载配置
   - 无需重启程序即可应用新配置

4. **UI配置持久化**:
   - 保存用户调整的窗口大小
   - 保存用户的面板布局偏好

5. **多配置文件支持**:
   - 支持开发/生产等多套配置
   - 通过环境变量切换配置文件

## 总结

本次实现完成了可视化界面的配置系统，主要特点包括：

1. ✅ 使用 YAML 格式，配置清晰易读
2. ✅ 支持相对路径，便于移植
3. ✅ 单例模式，性能优良
4. ✅ 优先级搜索，灵活可扩展
5. ✅ 完整文档和示例，易于使用

配置系统已完全集成到现有代码中，用户可以通过修改 `ui_config.yaml` 文件轻松调整各项路径设置。
