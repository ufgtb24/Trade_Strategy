# Stock List 列显示自定义实现计划

## 📋 需求总结

用户希望在 stock list 中实现列显示的自定义功能，满足以下需求：

1. **隐藏不重要的列**：如 `scan_start_date`, `scan_end_date`, `data_points` 等技术细节
2. **操作要简单**：支持多种交互方式（工具栏按钮、右键菜单）
3. **配置持久化**：保存到 YAML，下次启动时保持
4. **一键开关**：快速显示/隐藏所有属性列，同时保留用户配置
5. **默认精简**：新用户看到核心指标即可（Symbol + Bts + Active Peaks + Max Quality）

## 🎯 设计方案

### 交互模式：混合模式 + 一键开关

```
┌─────────────────────────────────────────────────────────┐
│ [Configure Columns] [👁 Toggle] [Use UI Params]        │  ← 工具栏
├─────────────────────────────────────────────────────────┤
│ Symbol │ Bts │ Active Peaks │ Max Quality │            │  ← 列标题（右键菜单）
│  AAPL  │ 60  │      12      │    49.01    │            │
│  TSLA  │ 63  │       2      │    57.71    │            │
└─────────────────────────────────────────────────────────┘
```

### 三种操作方式

1. **工具栏"Configure Columns"按钮**
   - 打开对话框，显示所有可用列
   - 复选框批量选择/取消
   - Apply 后保存到 YAML
   - 适合：新用户、批量配置

2. **工具栏"👁 Toggle"按钮**（一键开关）
   - **关闭状态**：隐藏所有属性列，只显示 Symbol（固定列）
   - **打开状态**：恢复上次配置的属性列
   - 状态持久化到 YAML
   - 适合：快速对比股票代码、演示模式

3. **右键列标题菜单**
   - 显示所有列的复选框列表
   - 勾选/取消勾选立即生效
   - 自动保存到 YAML
   - 适合：资深用户、单列快速调整

### 配置状态（两层）

```yaml
# configs/UI/ui_config.yaml
ui:
  stock_list_columns:
    # 第一层：总开关（一键显示/隐藏）
    columns_enabled: true  # false = 只显示Symbol

    # 第二层：具体哪些列可见（用户自定义）
    visible_columns:
      - "bts"
      - "active_peaks"
      - "max_quality"

    # 列排序优先级
    column_priority:
      - "bts"
      - "active_peaks"
      - "avg_quality"
      - "max_quality"

    # 自定义列标签（可选）
    column_labels:
      bts: "Breakthroughs"
      active_peaks: "Active Peaks"
      avg_quality: "Avg Quality"
      max_quality: "Max Quality"
```

## 🏗️ 技术架构

### 数据流

```
用户操作 → UI组件 → UIConfigLoader → YAML持久化
                ↓
         StockListPanel.load_data()
                ↓
         应用列过滤逻辑
                ↓
         _configure_tree_columns()
                ↓
            Treeview显示
```

### 关键决策

1. **持久化方式**：YAML 配置文件（复用现有 `ui_config_loader`）
2. **配置作用域**：全局配置（所有扫描结果共享）
3. **动态发现**：加载时发现所有标量字段，从配置过滤
4. **向后兼容**：如果配置不存在，使用默认值（4个核心列）
5. **性能优化**：列切换时只更新显示，不重新加载数据

## 📁 文件修改清单

### 1. UIConfigLoader (`ui_config_loader.py`)
**改动点**：添加列配置的 getter/setter 方法

```python
def get_stock_list_column_config(self) -> Dict:
    """获取列显示配置（包含总开关和具体列）"""
    default = {
        "columns_enabled": True,
        "visible_columns": ["bts", "active_peaks", "max_quality"],
        "column_priority": ["bts", "active_peaks", "avg_quality", "max_quality"],
        "column_labels": {}
    }
    return self._config.get("ui", {}).get("stock_list_columns", default)

def set_columns_enabled(self, enabled: bool):
    """设置列总开关"""
    if "stock_list_columns" not in self._config["ui"]:
        self._config["ui"]["stock_list_columns"] = self.get_stock_list_column_config()
    self._config["ui"]["stock_list_columns"]["columns_enabled"] = enabled
    self.save_config()

def set_visible_columns(self, columns: List[str]):
    """设置可见列列表"""
    if "stock_list_columns" not in self._config["ui"]:
        self._config["ui"]["stock_list_columns"] = self.get_stock_list_column_config()
    self._config["ui"]["stock_list_columns"]["visible_columns"] = columns
    self.save_config()
```

**代码量**：约 30 行

---

### 2. StockListPanel (`stock_list_panel.py`)
**改动点**：
- `load_data()` 方法：从配置过滤列
- `set_visible_columns()` 新方法：动态切换列显示
- `toggle_columns_enabled()` 新方法：一键开关

```python
def load_data(self, scan_results: Dict):
    """加载数据（应用列配置）"""
    # ... 现有代码：构建 stock_data ...

    # 动态发现所有标量字段
    if self.stock_data:
        first_item = self.stock_data[0]
        all_columns = [k for k in first_item.keys()
                       if k not in ["symbol", "raw_data"]]

        # 从配置加载
        config_loader = get_ui_config_loader()
        config = config_loader.get_stock_list_column_config()

        # 第一层：总开关
        columns_enabled = config.get("columns_enabled", True)
        if not columns_enabled:
            # 只显示 Symbol（无其他列）
            columns = []
        else:
            # 第二层：过滤可见列
            visible_columns = config.get("visible_columns", all_columns)
            columns = [c for c in visible_columns if c in all_columns]

            # 排序
            priority = config.get("column_priority", [])
            columns.sort(key=lambda x: priority.index(x) if x in priority else 999)

        self._configure_tree_columns(columns)

    self.filtered_data = self.stock_data.copy()
    self._update_tree()

def set_visible_columns(self, columns: List[str]):
    """动态设置可见列（不重新加载数据）"""
    config_loader = get_ui_config_loader()
    config_loader.set_visible_columns(columns)

    # 只更新列配置，复用现有数据
    self._configure_tree_columns(columns)
    self._update_tree()

def toggle_columns_enabled(self):
    """一键开关：显示/隐藏所有属性列"""
    config_loader = get_ui_config_loader()
    config = config_loader.get_stock_list_column_config()

    # 切换状态
    current_state = config.get("columns_enabled", True)
    new_state = not current_state
    config_loader.set_columns_enabled(new_state)

    # 重新加载列显示（不重新加载数据）
    if new_state:
        # 恢复用户配置的列
        visible_columns = config.get("visible_columns", [])
        self._configure_tree_columns(visible_columns)
    else:
        # 隐藏所有列
        self._configure_tree_columns([])

    self._update_tree()
    return new_state
```

**代码量**：约 50 行

---

### 3. ParameterPanel (`parameter_panel.py`)
**改动点**：添加两个按钮和回调处理

```python
def _create_ui(self):
    # ... 现有代码 ...

    # 新增：列配置按钮区域
    column_config_frame = ttk.Frame(container)
    column_config_frame.pack(fill=tk.X, pady=(5, 0))

    # 按钮1：Configure Columns（批量配置）
    ttk.Button(
        column_config_frame,
        text="Configure Columns",
        command=self._on_configure_columns_clicked
    ).pack(side=tk.LEFT, padx=5)

    # 按钮2：👁 Toggle（一键开关）
    self.toggle_columns_var = tk.BooleanVar(value=True)
    self.toggle_button = ttk.Checkbutton(
        column_config_frame,
        text="👁 Show Columns",
        variable=self.toggle_columns_var,
        command=self._on_toggle_columns_clicked,
        style="Toolbutton"  # 按钮样式
    )
    self.toggle_button.pack(side=tk.LEFT, padx=5)

    # 加载初始状态
    config_loader = get_ui_config_loader()
    config = config_loader.get_stock_list_column_config()
    self.toggle_columns_var.set(config.get("columns_enabled", True))

def _on_configure_columns_clicked(self):
    """打开列配置对话框"""
    from .column_config_dialog import ColumnConfigDialog

    # 获取当前所有可用列
    stock_list = self.parent.stock_list_panel  # 假设从主UI传入
    if not stock_list.stock_data:
        return  # 没有数据时不打开

    # 动态发现所有字段
    first_item = stock_list.stock_data[0]
    available_columns = [k for k in first_item.keys()
                         if k not in ["symbol", "raw_data"]]

    # 当前可见列
    config_loader = get_ui_config_loader()
    config = config_loader.get_stock_list_column_config()
    visible_columns = config.get("visible_columns", [])

    # 打开对话框
    dialog = ColumnConfigDialog(
        parent=self.root,
        available_columns=available_columns,
        visible_columns=visible_columns,
        on_apply_callback=self._on_columns_applied
    )

def _on_columns_applied(self, new_visible_columns: List[str]):
    """应用列配置回调"""
    stock_list = self.parent.stock_list_panel
    stock_list.set_visible_columns(new_visible_columns)

def _on_toggle_columns_clicked(self):
    """一键开关回调"""
    stock_list = self.parent.stock_list_panel
    new_state = stock_list.toggle_columns_enabled()
    self.toggle_columns_var.set(new_state)
```

**代码量**：约 60 行

---

### 4. ColumnConfigDialog（新文件）(`column_config_dialog.py`)
**功能**：列配置对话框，多选列表 + 快捷按钮

```python
"""列配置对话框"""

import tkinter as tk
from tkinter import ttk
from typing import List, Callable


class ColumnConfigDialog:
    """列配置对话框（多选Listbox）"""

    def __init__(
        self,
        parent: tk.Widget,
        available_columns: List[str],
        visible_columns: List[str],
        on_apply_callback: Callable[[List[str]], None]
    ):
        """
        初始化对话框

        Args:
            parent: 父窗口
            available_columns: 所有可用列
            visible_columns: 当前可见列
            on_apply_callback: Apply按钮回调
        """
        self.available_columns = available_columns
        self.visible_columns = visible_columns
        self.on_apply_callback = on_apply_callback

        # 创建模态窗口
        self.window = tk.Toplevel(parent)
        self.window.title("Configure Columns")
        self.window.geometry("400x500")
        self.window.transient(parent)
        self.window.grab_set()

        self._create_ui()

        # 居中显示
        self.window.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.window.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.window.winfo_height()) // 2
        self.window.geometry(f"+{x}+{y}")

    def _create_ui(self):
        """创建UI组件"""
        # 说明标签
        ttk.Label(
            self.window,
            text="Select columns to display in the stock list:",
            font=("", 10, "bold")
        ).pack(pady=10)

        # 列表区域（带滚动条）
        list_frame = ttk.Frame(self.window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.MULTIPLE,
            yscrollcommand=scrollbar.set,
            font=("", 10)
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        # 填充数据并预选中
        for idx, col in enumerate(self.available_columns):
            # 格式化显示名称
            display_name = col.replace("_", " ").title()
            self.listbox.insert(tk.END, display_name)

            if col in self.visible_columns:
                self.listbox.selection_set(idx)

        # 快捷按钮区域
        shortcut_frame = ttk.Frame(self.window)
        shortcut_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(
            shortcut_frame,
            text="Select All",
            command=self._select_all
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            shortcut_frame,
            text="Clear All",
            command=self._clear_all
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            shortcut_frame,
            text="Reset to Default",
            command=self._reset_default
        ).pack(side=tk.LEFT, padx=5)

        # 底部按钮
        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(
            button_frame,
            text="Apply",
            command=self._apply
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            button_frame,
            text="Cancel",
            command=self.window.destroy
        ).pack(side=tk.RIGHT, padx=5)

    def _select_all(self):
        """全选"""
        self.listbox.selection_set(0, tk.END)

    def _clear_all(self):
        """清空"""
        self.listbox.selection_clear(0, tk.END)

    def _reset_default(self):
        """重置为默认（4个核心列）"""
        self.listbox.selection_clear(0, tk.END)
        default_columns = ["bts", "active_peaks", "max_quality"]
        for idx, col in enumerate(self.available_columns):
            if col in default_columns:
                self.listbox.selection_set(idx)

    def _apply(self):
        """应用选择"""
        # 获取选中的列
        selected_indices = self.listbox.curselection()
        selected_columns = [self.available_columns[i] for i in selected_indices]

        # 调用回调
        if self.on_apply_callback:
            self.on_apply_callback(selected_columns)

        # 关闭窗口
        self.window.destroy()
```

**代码量**：约 150 行

---

### 5. 右键菜单（集成到 StockListPanel）
**改动点**：为列标题绑定右键菜单

```python
def _configure_tree_columns(self, columns):
    """动态配置Treeview列（添加右键菜单）"""
    self.main_tree["columns"] = columns

    for col in columns:
        title = col.replace("_", " ").title()
        self.main_tree.heading(
            col,
            text=title,
            command=lambda c=col: self.sort_by(c)
        )
        width = len(title) * 15 + 15
        self.main_tree.column(col, width=width, anchor=tk.CENTER, stretch=False)

    # 绑定右键菜单
    self.main_tree.bind("<Button-3>", self._show_column_context_menu)

def _show_column_context_menu(self, event):
    """显示列右键菜单"""
    # 获取所有可用列
    if not self.stock_data:
        return

    first_item = self.stock_data[0]
    all_columns = [k for k in first_item.keys()
                   if k not in ["symbol", "raw_data"]]

    # 获取当前可见列
    config_loader = get_ui_config_loader()
    config = config_loader.get_stock_list_column_config()
    visible_columns = config.get("visible_columns", [])

    # 创建上下文菜单
    menu = tk.Menu(self.main_tree, tearoff=0)

    for col in all_columns:
        display_name = col.replace("_", " ").title()
        is_visible = col in visible_columns

        menu.add_checkbutton(
            label=display_name,
            command=lambda c=col: self._toggle_column(c),
            variable=tk.BooleanVar(value=is_visible),
            onvalue=True,
            offvalue=False
        )

    menu.post(event.x_root, event.y_root)

def _toggle_column(self, column: str):
    """切换单个列的显示/隐藏"""
    config_loader = get_ui_config_loader()
    config = config_loader.get_stock_list_column_config()
    visible_columns = config.get("visible_columns", [])

    if column in visible_columns:
        visible_columns.remove(column)
    else:
        visible_columns.append(column)

    self.set_visible_columns(visible_columns)
```

**代码量**：约 50 行

---

### 6. YAML配置文件 (`ui_config.yaml`)
**改动点**：添加 `stock_list_columns` 配置节

```yaml
ui:
  # ... 现有配置 ...

  # 新增：股票列表列配置
  stock_list_columns:
    # 总开关（一键显示/隐藏）
    columns_enabled: true

    # 可见列列表（默认：4个核心列）
    visible_columns:
      - "bts"
      - "active_peaks"
      - "max_quality"

    # 列排序优先级
    column_priority:
      - "bts"
      - "active_peaks"
      - "avg_quality"
      - "max_quality"

    # 自定义列标签（可选）
    column_labels:
      bts: "Breakthroughs"
      active_peaks: "Active Peaks"
      avg_quality: "Avg Quality"
      max_quality: "Max Quality"
```

**代码量**：约 15 行

---

## 🧪 测试计划

### 功能测试

1. **加载测试**
   - [ ] 首次启动显示默认4列
   - [ ] 配置文件存在时加载正确的列
   - [ ] 动态发现JSON中的新字段

2. **对话框测试**
   - [ ] 打开对话框显示所有可用列
   - [ ] 预选中当前可见列
   - [ ] Select All / Clear All 按钮正常工作
   - [ ] Reset to Default 恢复核心4列
   - [ ] Apply 后列显示立即更新
   - [ ] 配置保存到YAML文件

3. **一键开关测试**
   - [ ] Toggle关闭后只显示Symbol
   - [ ] Toggle打开后恢复用户配置
   - [ ] 状态持久化到YAML
   - [ ] 重启后保持上次状态

4. **右键菜单测试**
   - [ ] 右键列标题显示菜单
   - [ ] 菜单显示所有可用列
   - [ ] 当前可见列被勾选
   - [ ] 勾选/取消勾选立即生效
   - [ ] 配置自动保存

5. **向后兼容测试**
   - [ ] 旧配置文件自动迁移
   - [ ] 配置不存在时使用默认值
   - [ ] 旧JSON（无avg_quality等字段）正常工作

### 性能测试

- [ ] 100只股票 × 10列 < 1秒加载
- [ ] 列切换无闪烁
- [ ] 右键菜单响应流畅

---

## 📦 实施步骤

### Phase 1：配置系统（1-2小时）
1. 修改 `UIConfigLoader`：添加getter/setter方法
2. 更新 `ui_config.yaml`：添加默认配置
3. 测试配置加载/保存

### Phase 2：核心功能（2-3小时）
1. 修改 `StockListPanel.load_data()`：应用列过滤
2. 添加 `set_visible_columns()` 方法
3. 添加 `toggle_columns_enabled()` 方法
4. 测试列显示逻辑

### Phase 3：UI组件（2-3小时）
1. 创建 `ColumnConfigDialog` 对话框
2. 修改 `ParameterPanel`：添加两个按钮
3. 实现右键菜单绑定
4. 测试所有交互方式

### Phase 4：测试和优化（1小时）
1. 功能测试
2. 性能测试
3. 边界情况处理
4. 代码审查

**总计**：约 6-9 小时

---

## 🎨 用户体验流程

### 新用户首次使用
```
1. 启动UI → 看到4个核心列（Symbol + Bts + Active Peaks + Max Quality）
2. 界面简洁，不拥挤
3. 发现 "Configure Columns" 按钮（明显提示）
4. 点击查看所有可用列，按需勾选
```

### 资深用户日常使用
```
1. 右键列标题 → 快速切换单列显示
2. 或使用 "👁 Toggle" 按钮快速隐藏所有列（对比股票代码）
3. 再次点击恢复之前的列配置
4. 配置自动保存，下次启动无需重新配置
```

### 演示/分享场景
```
1. 点击 "👁 Toggle" 关闭所有属性列
2. 只显示 Symbol，界面极简
3. 逐个展开讲解时，右键添加相关列
4. 结束后点击 Toggle 恢复完整配置
```

---

## 🔧 扩展性设计

### 未来可扩展功能

1. **列宽调整持久化**
   ```yaml
   column_widths:
     bts: 120
     avg_quality: 150
   ```

2. **列预设方案**
   ```yaml
   column_presets:
     trader:   ["bts", "max_quality"]
     analyst:  ["bts", "avg_quality", "max_quality", "data_points"]
     minimal:  ["bts"]
   ```

3. **默认排序持久化**
   ```yaml
   default_sort:
     column: "max_quality"
     reverse: true
   ```

4. **列分组折叠**
   ```
   [Basic Info] > Symbol, Bts, Active Peaks
   [Quality]    > Avg Quality, Max Quality
   [Technical]  > Data Points, Scan Date
   ```

---

## ✅ 完成标准

- [x] 用户可以通过对话框批量选择列
- [x] 用户可以通过右键菜单快速切换列
- [x] 用户可以通过Toggle按钮一键隐藏/显示所有列
- [x] 配置持久化到YAML文件
- [x] 默认显示4个核心列
- [x] 列切换无需重新加载数据
- [x] 向后兼容旧配置文件
- [x] 代码复用现有架构（UIConfigLoader、display_options模式）
- [x] 文档完善（注释、docstring）

---

## 📝 注意事项

1. **Symbol列永远固定**：不可隐藏，不在配置列表中
2. **动态发现新字段**：JSON新增字段自动出现在可选列表
3. **配置冲突处理**：如果配置列在JSON中不存在，自动跳过
4. **UI状态同步**：Toggle按钮状态要实时反映配置
5. **性能优化**：列切换只更新显示，不触发数据重新计算
