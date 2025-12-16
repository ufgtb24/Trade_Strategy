"""UI样式配置

集中管理所有UI组件的字体、颜色和样式配置
便于统一调整界面外观
"""

from tkinter import ttk

# ============================================================================
# JSON 参数对比颜色
# ============================================================================

JSON_DIFF_BG = "#FFFACD"      # 浅黄色 (LemonChiffon) - UI 值与 JSON 值不同时
JSON_MATCH_BG = "#F0F0F0"     # 默认浅灰背景 - 值相同时
JSON_NA_FG = "#999999"        # N/A 文字颜色 (灰色) - JSON 中不存在该参数时


# ============================================================================
# 图表颜色配置
# ============================================================================

CHART_COLORS = {
    # K线颜色
    "candlestick_up": "#4CAF50",      # 阳线（绿色）
    "candlestick_down": "#B71C1C",    # 阴线（红色）
    # 成交量颜色
    "volume_up": "#D3D3D3",           # 普通成交量（浅灰）
    "volume_down": "#696969",         # 下跌成交量（深灰）
    "volume_highlight": "#FFD700",    # 高亮成交量（金色）
    # 峰值标记
    "peak_marker": "#000000",         # 峰值标记（黑色）
    "peak_text_id": "#000000",        # 峰值ID文字（黑色）
    "peak_text_score": "#969696",     # 峰值分数文字（灰色）
    # 突破标记
    "breakthrough_marker": "#0000FF",      # 突破标记（蓝色）
    "breakthrough_text_bg": "#FFFFFF",     # 突破文字背景（白色）
    "breakthrough_text_score": "#FF0000",  # 突破分数文字（红色）
    # 阻力区
    "resistance_zone": "#5D5932",     # 阻力区颜色（橄榄色）
    # 十字线
    "crosshair_normal": "#0088CC",    # 普通模式十字线（蓝色）
    "crosshair_ctrl": "#FF6600",      # Ctrl模式横线（橙色）
}


def get_chart_colors() -> dict:
    """
    获取图表颜色配置

    Returns:
        颜色配置字典
    """
    return CHART_COLORS.copy()


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

# ============================================================================
# 组件尺寸配置
# ============================================================================

# Checkbutton 复选框尺寸（指示器直径，单位：像素）
CHECKBUTTON_INDICATOR_SIZE = 18  # 复选框方框的大小

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

    # 复选框：14号字体 + 统一尺寸
    style.configure("TCheckbutton",
                    font=FONT_LABEL,
                    indicatordiameter=CHECKBUTTON_INDICATOR_SIZE)

    # 单选框：14号字体 + 统一尺寸
    style.configure("TRadiobutton",
                    font=FONT_LABEL,
                    indicatordiameter=CHECKBUTTON_INDICATOR_SIZE)

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

    # 可选择 Label 样式（去除边框，背景透明）
    style.configure("SelectableLabel.TEntry",
                    font=FONT_PARAM_LABEL,
                    fieldbackground="#F0F0F0",
                    borderwidth=0,
                    relief="flat")
    # 设置只读状态下的样式
    style.map("SelectableLabel.TEntry",
              fieldbackground=[("readonly", "#F0F0F0")],
              foreground=[("readonly", "black")])

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
# 评分详情浮动窗口样式配置
# ============================================================================

SCORE_TOOLTIP_COLORS = {
    # 峰值主题（蓝色系）
    "peak_header_bg": "#1E3A5F",
    "peak_header_fg": "#FFFFFF",
    "peak_border": "#2E5A8F",
    # 突破主题（绿色系）
    "bt_header_bg": "#1E5F3A",
    "bt_header_fg": "#FFFFFF",
    "bt_border": "#2E8F5A",
    # 分数颜色（用于浅色背景）
    "score_high": "#2E7D32",    # >=80 绿色
    "score_medium": "#F57C00",  # 50-79 橙色
    "score_low": "#C62828",     # <50 红色
    # 分数颜色（用于深色背景，如标题栏）
    "score_high_light": "#7FFF7F",    # >=80 亮绿色
    "score_medium_light": "#FFD700",  # 50-79 金色
    "score_low_light": "#FF6B6B",     # <50 亮红色
    # 表格
    "row_bg": "#F8F9FA",
    "row_alt_bg": "#FFFFFF",
    "formula_bg": "#FFFDE7",
    "separator": "#E0E0E0",
    # 通用
    "window_bg": "#FFFFFF",
    "text_primary": "#212121",
    "text_secondary": "#757575",
    "sub_feature_bg": "#F0F0F0",
}

SCORE_TOOLTIP_FONTS = {
    "header": (FONT_FAMILY, 14, "bold"),
    "header_small": (FONT_FAMILY, 12),
    "table_header": (FONT_FAMILY, 12, "bold"),
    "table_cell": (FONT_FAMILY, 12),
    "formula": ("Consolas", 11),
    "sub_feature": (FONT_FAMILY, 11),
}


def get_score_tooltip_colors() -> dict:
    """获取评分详情浮动窗口颜色配置"""
    return SCORE_TOOLTIP_COLORS.copy()


def get_score_tooltip_fonts() -> dict:
    """获取评分详情浮动窗口字体配置"""
    return SCORE_TOOLTIP_FONTS.copy()


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
    from BreakthroughStrategy.UI.interactive.ui_styles import configure_global_styles

    root = tk.Tk()
    configure_global_styles(root)  # 必须在创建UI组件前调用！
    app = InteractiveUI(root)
    root.mainloop()

2. 在创建组件时使用预定义字体：

    from BreakthroughStrategy.UI.interactive.ui_styles import get_font

    # 方法1：使用get_font()函数
    label = ttk.Label(parent, text="Hello", font=get_font("label"))
    button = ttk.Button(parent, text="Click", font=get_font("button"))

    # 方法2：直接导入字体常量
    from BreakthroughStrategy.UI.interactive.ui_styles import FONT_LABEL, FONT_BUTTON
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
