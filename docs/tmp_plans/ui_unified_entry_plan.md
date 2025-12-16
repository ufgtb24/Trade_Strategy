# UI 统一入口架构规划

> 创建时间: 2025-12-15
> 状态: 待实施

## 一、背景与问题

### 当前架构的问题

```
┌─────────────────────────────────────────────────────────────────┐
│                     当前架构（双入口）                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   batch_scan.py ──→ config.yaml ──→ 扫描 ──→ JSON               │
│        ↑                                        ↓                │
│    命令行入口                               手动加载              │
│                                                ↓                │
│                                              UI ←── params.yaml │
│                                                       ↓         │
│                                              Rescan All         │
│                                              (❌ 缺失时间范围)    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**核心矛盾**：
1. `batch_scan.py` 知道时间范围（config.yaml），但用户需要切到命令行
2. UI 的 `Rescan All` 不知道时间范围，使用全部数据
3. 两套配置，两个入口，用户认知负担重

---

## 二、目标

将 `batch_scan.py` 的功能完全集成到 UI 中，让 UI 成为系统的统一入口。

### 统一入口方案的优势

| 维度 | 当前架构 | 统一入口 |
|------|---------|---------|
| **用户体验** | 需要在命令行和 UI 之间切换 | 全部操作在 UI 完成 |
| **配置一致性** | config.yaml 和 UI 参数可能不同步 | 单一配置源 |
| **可视化** | 扫描参数需要编辑 YAML 文件 | UI 表单编辑，直观清晰 |
| **反馈速度** | 扫描完成后手动加载 JSON | 扫描完成自动刷新 |
| **学习成本** | 需要理解两套流程 | 一套流程 |

---

## 三、实现方案设计

### 方案架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     新架构（UI 统一入口）                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                        UI (main.py)                          │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │                                                              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │    │
│  │  │ Scan Config  │  │ Params       │  │ Display Options  │   │    │
│  │  │ Editor       │  │ Editor       │  │                  │   │    │
│  │  │              │  │              │  │ ☑ Peak Score     │   │    │
│  │  │ data_dir     │  │ total_window │  │ ☑ BT Score       │   │    │
│  │  │ csv_file     │  │ min_side     │  │                  │   │    │
│  │  │ start_date   │  │ ...          │  └──────────────────┘   │    │
│  │  │ end_date     │  │              │                         │    │
│  │  │ mon_before   │  │              │                         │    │
│  │  │ mon_after    │  │              │                         │    │
│  │  │ num_workers  │  └──────────────┘                         │    │
│  │  └──────────────┘                                           │    │
│  │                                                              │    │
│  │  [New Scan] [Rescan All] [Load Results]                     │    │
│  │                                                              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                   ScanManager (内嵌)                         │    │
│  │                                                              │    │
│  │   config.yaml ←──→ UIScanConfigLoader                       │    │
│  │   params.yaml ←──→ UIParamLoader (已有)                     │    │
│  │                                                              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 四、核心组件设计

### 1. UIScanConfigLoader（新增）

```python
# BreakthroughStrategy/UI/config/scan_config_loader.py

class UIScanConfigLoader:
    """管理 config.yaml 的加载、编辑、保存"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or self._default_path()
        self._config = {}
        self._listeners = []
        self.load()

    # ===== 数据源配置 =====
    def get_data_dir(self) -> str: ...
    def set_data_dir(self, path: str): ...

    def get_scan_mode(self) -> str:  # "global" or "csv"
        return "csv" if self._config["data"].get("csv_file") else "global"

    # 全局模式
    def get_date_range(self) -> Tuple[str, str]: ...
    def set_date_range(self, start: str, end: str): ...

    # CSV模式
    def get_csv_file(self) -> str: ...
    def set_csv_file(self, path: str): ...
    def get_relative_months(self) -> Tuple[int, int]: ...
    def set_relative_months(self, before: int, after: int): ...

    # ===== 性能配置 =====
    def get_num_workers(self) -> int: ...
    def set_num_workers(self, n: int): ...

    # ===== 参数配置引用 =====
    def get_params_file(self) -> str: ...
    def set_params_file(self, path: str): ...

    # ===== 持久化 =====
    def save(self): ...
    def reload(self): ...
```

### 2. ScanConfigPanel（新增 UI 面板）

两种实现方式可选：

**方式A：独立面板（推荐）**
```
┌─────────────────────────────────────────────────────────────────┐
│ [Load Results] │ [○ Analysis] [▼ ui_params.yaml] [Edit]        │
├─────────────────────────────────────────────────────────────────┤
│ Scan Config:  [Global ▼]  [2023-01-01] to [____]  [New Scan]   │
│               Workers: [8]  Max Stocks: [___]                   │
└─────────────────────────────────────────────────────────────────┘
```

**方式B：弹出对话框**
```
点击 [New Scan] 或 [Scan Settings] 弹出配置对话框
```

### 3. 修改 Rescan All 逻辑

```python
# main.py - _do_background_rescan() 修改

def _do_background_rescan(self, symbols, params):
    """使用 config.yaml 的时间范围进行扫描"""

    # 从 scan_config_loader 获取配置
    scan_config = self.scan_config_loader

    if scan_config.get_scan_mode() == "csv":
        # CSV模式：每只股票有独立时间范围
        csv_file = scan_config.get_csv_file()
        mon_before, mon_after = scan_config.get_relative_months()
        stock_time_ranges = load_csv_stock_list(csv_file, mon_before, mon_after)

        manager = ScanManager(
            output_dir=...,
            start_date=None,
            end_date=None,
            **params
        )
        results = manager.parallel_scan(
            symbols,
            data_dir=scan_config.get_data_dir(),
            stock_time_ranges=stock_time_ranges,  # 传递 per-stock 时间范围
        )
    else:
        # 全局时间范围模式
        start_date, end_date = scan_config.get_date_range()

        manager = ScanManager(
            output_dir=...,
            start_date=start_date,
            end_date=end_date,
            **params
        )
        results = manager.parallel_scan(
            symbols,
            data_dir=scan_config.get_data_dir(),
        )
```

---

## 五、技术挑战与解决方案

| 挑战 | 解决方案 |
|------|---------|
| **性能：批量扫描耗时** | 后台线程 + 进度窗口（已实现框架） |
| **CSV解析复杂性** | 复用 batch_scan.py 的 `load_csv_stock_list()` 函数 |
| **配置同步** | 引入 observer 模式，配置变更通知所有依赖方 |
| **UI复杂度增加** | 可选：基础功能在主面板，高级配置在对话框 |
| **向后兼容** | 保留 `batch_scan.py` 作为命令行快捷方式，内部调用同样的 ScanManager |

---

## 六、实施路线图

```
Phase 1: 基础架构（解决 Rescan All 时间范围问题）
├── 创建 UIScanConfigLoader
├── 修改 Rescan All 使用 config.yaml 时间范围
└── 验证扫描结果与 batch_scan.py 一致

Phase 2: UI 配置编辑
├── 添加 Scan Config 面板/对话框
├── 支持切换全局/CSV模式
└── 支持编辑并保存 config.yaml

Phase 3: New Scan 功能
├── 添加 [New Scan] 按钮
├── 支持选择数据目录
└── 自动发现股票列表（扫描 pkl 文件）

Phase 4: 优化（可选）
├── 扫描历史记录
├── 参数预设管理
└── 批量导出功能
```

---

## 七、config.yaml 结构参考

```yaml
# 批量扫描通用配置文件
# 版本: v2.0 (支持CSV索引模式)

# 数据设置
data:
  # 股票数据目录
  data_dir: "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"

  # 最大扫描股票数（null表示不限制）
  max_stocks: null

  # 模式1：全局时间范围模式（当 csv_file = null 时使用）
  start_date: "2023-01-01"
  end_date: null

  # 模式2：CSV索引模式（优先级高于全局时间范围）
  csv_file: "/path/to/csv_file.txt"
  mon_before: 6  # 基准日期前N个月
  mon_after: 1   # 基准日期后N个月

# 输出设置
output:
  output_dir: "outputs/scan_results"

# 性能设置
performance:
  num_workers: 8

# 参数配置引用
params:
  config_file: "configs/analysis/params/ui_params.yaml"
```

---

## 八、结论

**可行性：完全可行 ✅**

这个想法不仅可行，而且是正确的架构演进方向：

1. **技术上**：所有需要的组件（ScanManager、parallel_scan、load_csv_stock_list）已经存在，只需要：
   - 新增 UIScanConfigLoader（~150行代码）
   - 修改 Rescan All 逻辑（~50行代码）
   - 新增配置 UI（~200行代码）

2. **用户体验**：显著提升，从"命令行+UI双入口"变为"UI统一入口"

3. **代码复用**：可以将 batch_scan.py 的核心逻辑提取出来，让 batch_scan.py 成为 UI 的命令行快捷方式

**建议**：先实施 Phase 1（修复 Rescan All 时间范围问题），这是最小可行改动，能立即解决当前问题。后续 Phase 可以逐步实施。
