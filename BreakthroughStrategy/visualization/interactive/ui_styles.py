"""UI样式配置

集中管理所有UI组件的字体和样式配置
便于统一调整界面外观
"""

from tkinter import ttk

# ============================================================================
# 字体配置
# ============================================================================

# 主字体：Arial，清晰易读
FONT_FAMILY = "Arial"

# 字体大小（所有大小 >= 14）
FONT_SIZE_XLARGE = 17   # 超大：主窗口标题
FONT_SIZE_LARGE = 16   # 大号：按钮、重要标签
FONT_SIZE_MEDIUM = 15   # 中号：普通标签、输入框（默认）
FONT_SIZE_SMALL = 14    # 小号：提示文字（保持>=14）

# 常用字体组合（family, size, weight）
FONT_TITLE = (FONT_FAMILY, FONT_SIZE_LARGE )      # 窗口标题
FONT_BUTTON = (FONT_FAMILY, FONT_SIZE_MEDIUM)              # 按钮
FONT_LABEL = (FONT_FAMILY, FONT_SIZE_SMALL)              # 标签
FONT_LABEL_BOLD = (FONT_FAMILY, FONT_SIZE_SMALL,'bold') # 加粗标签
FONT_INPUT = (FONT_FAMILY, FONT_SIZE_MEDIUM)              # 输入框
FONT_HINT = (FONT_FAMILY, FONT_SIZE_SMALL)                # 提示文字

# 参数编辑器专用字体
FONT_SECTION_TITLE = (FONT_FAMILY, 15)            # 折叠分组标题
FONT_PARAM_LABEL = (FONT_FAMILY, 14)                      # 参数标签
FONT_PARAM_INPUT = (FONT_FAMILY, 14)                      # 参数输入框
FONT_PARAM_HINT = (FONT_FAMILY, 14)                       # 参数范围提示（保持14）
FONT_STATUS = (FONT_FAMILY, 14)                           # 状态栏
FONT_WEIGHT_SUM = (FONT_FAMILY, 14, "bold")               # 权重总和显示


# ============================================================================
# 样式配置函数
# ============================================================================

def configure_global_styles(root=None):
    """
    配置全局UI样式（字体、颜色等）

    必须在创建任何UI组件之前调用此函数！

    Args:
        root: Tk根窗口（可选，如果不提供则使用默认）

    使用示例：
        root = tk.Tk()
        configure_global_styles(root)  # 必须在创建UI组件前调用
        app = InteractiveUI(root)
    """
    style = ttk.Style(root)

    # ========================================
    # 通用组件样式
    # ========================================

    # 按钮：16号字体
    style.configure("TButton", font=FONT_BUTTON)

    # 标签：14号字体
    style.configure("TLabel", font=FONT_LABEL)

    # 输入框：14号字体
    style.configure("TEntry", font=FONT_INPUT)

    # 数字选择框：14号字体
    style.configure("TSpinbox", font=FONT_INPUT)

    # 复选框：14号字体
    style.configure("TCheckbutton", font=FONT_LABEL)

    # 单选框：14号字体
    style.configure("TRadiobutton", font=FONT_LABEL)

    # 下拉框：14号字体
    style.configure("TCombobox", font=FONT_INPUT)

    # Frame（无特殊样式，但需要定义）
    style.configure("TFrame")

    # LabelFrame：14号加粗标题
    style.configure("TLabelframe", font=FONT_LABEL)
    style.configure("TLabelframe.Label", font=FONT_LABEL_BOLD)

    # Notebook（选项卡）：14号字体
    style.configure("TNotebook.Tab", font=FONT_LABEL)

    # ========================================
    # Treeview（列表/树形视图）样式
    # ========================================

    # Treeview标题行：14号加粗
    style.configure("Treeview.Heading", font=FONT_LABEL_BOLD)

    # Treeview内容行：14号
    style.configure("Treeview", font=FONT_LABEL, rowheight=25)  # 增加行高以适应字体

    # ========================================
    # 自定义样式（用于特殊场景）
    # ========================================

    # 错误状态的输入框（红色边框）
    style.configure("Error.TEntry",
                    font=FONT_INPUT,
                    fieldbackground="white",
                    bordercolor="red")

    # 成功状态的标签（绿色文字）
    style.configure("Success.TLabel",
                    font=FONT_LABEL,
                    foreground="green")

    # 警告状态的标签（橙色文字）
    style.configure("Warning.TLabel",
                    font=FONT_LABEL,
                    foreground="orange")

    # 标题样式（超大字体）
    style.configure("Title.TLabel", font=FONT_TITLE)

    print(f"✓ UI样式配置完成：字体={FONT_FAMILY}，最小字号={FONT_SIZE_SMALL}")


# ============================================================================
# 便捷函数
# ============================================================================

def get_font(component_type: str = "label") -> tuple:
    """
    获取指定组件类型的字体配置

    Args:
        component_type: 组件类型，可选值：
            - "title": 窗口标题
            - "button": 按钮
            - "label": 普通标签
            - "label_bold": 加粗标签
            - "input": 输入框
            - "hint": 提示文字
            - "section_title": 分组标题
            - "param_label": 参数标签
            - "param_input": 参数输入框
            - "status": 状态栏

    Returns:
        字体元组 (family, size, weight)

    使用示例：
        label = ttk.Label(parent, text="Hello", font=get_font("label"))
    """
    fonts = {
        "title": FONT_TITLE,
        "button": FONT_BUTTON,
        "label": FONT_LABEL,
        "label_bold": FONT_LABEL_BOLD,
        "input": FONT_INPUT,
        "hint": FONT_HINT,
        "section_title": FONT_SECTION_TITLE,
        "param_label": FONT_PARAM_LABEL,
        "param_input": FONT_PARAM_INPUT,
        "param_hint": FONT_PARAM_HINT,
        "status": FONT_STATUS,
        "weight_sum": FONT_WEIGHT_SUM,
    }

    return fonts.get(component_type, FONT_LABEL)


# ============================================================================
# 使用说明
# ============================================================================

"""
使用方法：

1. 在主入口文件中配置全局样式：

    import tkinter as tk
    from BreakthroughStrategy.visualization.interactive.ui_styles import configure_global_styles

    root = tk.Tk()
    configure_global_styles(root)  # 必须在创建UI组件前调用！
    app = InteractiveUI(root)
    root.mainloop()

2. 在创建组件时使用预定义字体：

    from BreakthroughStrategy.visualization.interactive.ui_styles import get_font

    # 方法1：使用get_font()函数
    label = ttk.Label(parent, text="Hello", font=get_font("label"))
    button = ttk.Button(parent, text="Click", font=get_font("button"))

    # 方法2：直接导入字体常量
    from BreakthroughStrategy.visualization.interactive.ui_styles import FONT_LABEL, FONT_BUTTON
    label = ttk.Label(parent, text="Hello", font=FONT_LABEL)
    button = ttk.Button(parent, text="Click", font=FONT_BUTTON)

3. 调整字体大小：

    只需修改本文件顶部的字体大小常量，所有使用该常量的组件都会自动更新：

    FONT_SIZE_LARGE = 18   # 将按钮字体从16改为18
    FONT_SIZE_MEDIUM = 16  # 将普通字体从14改为16

4. 更换字体：

    只需修改 FONT_FAMILY 常量：

    FONT_FAMILY = "Microsoft YaHei"  # 改为微软雅黑
    FONT_FAMILY = "Helvetica"        # 改为Helvetica

注意事项：
- configure_global_styles() 必须在创建任何UI组件之前调用
- 所有字体大小保证 >= 14，满足清晰度要求
- ttk组件会自动使用配置的样式，无需手动指定（除非需要特殊样式）
"""
