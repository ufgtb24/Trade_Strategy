"""键盘导航管理器"""
import tkinter as tk


class NavigationManager:
    """键盘导航管理器"""

    def __init__(self, root, tree_widget, chart_update_callback):
        """
        初始化导航管理器

        Args:
            root: root窗口
            tree_widget: Treeview控件
            chart_update_callback: 图表更新回调函数
        """
        self.root = root
        self.tree = tree_widget
        self.chart_update_callback = chart_update_callback

        # 绑定键盘事件
        self._bind_events()

    def _bind_events(self):
        """绑定键盘事件"""
        # 全局键盘事件
        self.root.bind('<Up>', self._on_up)
        self.root.bind('<Down>', self._on_down)
        self.root.bind('<Return>', self._on_enter)

    def _on_up(self, event):
        """上键：选择上一个"""
        # 检查焦点是否在可编辑控件上
        focus_widget = self.root.focus_get()
        if self._is_editable_widget(focus_widget):
            return None  # 允许事件继续传播

        children = self.tree.get_children()
        if not children:
            return "break"

        selection = self.tree.selection()
        if not selection:
            # 没有选择，选择第一个
            self.tree.selection_set(children[0])
            self.tree.see(children[0])
            if self.chart_update_callback:
                self.chart_update_callback()
            return "break"

        current = selection[0]
        try:
            idx = list(children).index(current)
            if idx > 0:
                new_target = children[idx - 1]
                self.tree.selection_set(new_target)
                self.tree.see(new_target)
                if self.chart_update_callback:
                    self.chart_update_callback()
        except ValueError:
            pass

        return "break"

    def _on_down(self, event):
        """下键：选择下一个"""
        # 检查焦点是否在可编辑控件上
        focus_widget = self.root.focus_get()
        if self._is_editable_widget(focus_widget):
            return None  # 允许事件继续传播

        children = self.tree.get_children()
        if not children:
            return "break"

        selection = self.tree.selection()
        if not selection:
            # 没有选择，选择第一个
            self.tree.selection_set(children[0])
            self.tree.see(children[0])
            if self.chart_update_callback:
                self.chart_update_callback()
            return "break"

        current = selection[0]
        try:
            idx = list(children).index(current)
            if idx < len(children) - 1:
                new_target = children[idx + 1]
                self.tree.selection_set(new_target)
                self.tree.see(new_target)
                if self.chart_update_callback:
                    self.chart_update_callback()
        except ValueError:
            pass

        return "break"

    def _on_enter(self, event):
        """Enter键：刷新当前图表"""
        # 检查焦点是否在可编辑控件上
        focus_widget = self.root.focus_get()
        if self._is_editable_widget(focus_widget):
            return None  # 允许事件继续传播

        if self.chart_update_callback:
            self.chart_update_callback()

        return "break"

    def _is_editable_widget(self, widget):
        """
        判断是否是可编辑控件

        Args:
            widget: 控件

        Returns:
            是否可编辑
        """
        if widget is None:
            return False

        try:
            widget_class = widget.winfo_class()
        except Exception:
            return False

        # 可编辑控件类型
        editable_classes = {'Entry', 'TEntry', 'Spinbox', 'TSpinbox', 'Text', 'Combobox', 'TCombobox'}
        return widget_class in editable_classes
