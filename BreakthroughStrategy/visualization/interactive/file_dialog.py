"""自定义文件选择对话框 - 支持大字体和图标"""

import os
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Tuple


class CustomFileDialog(tk.Toplevel):
    """自定义文件选择对话框，支持大字体显示"""

    # 文件图标（Unicode字符）
    FOLDER_ICON = "📁"
    FILE_ICON = "📄"
    PARENT_ICON = "⬆️"

    def __init__(
        self,
        parent,
        title: str = "Select File",
        initialdir: str = ".",
        filetypes: Optional[List[Tuple[str, str]]] = None,
        font_size: int = 14,
    ):
        """
        初始化自定义文件对话框

        Args:
            parent: 父窗口
            title: 对话框标题
            initialdir: 初始目录
            filetypes: 文件类型过滤器列表，如 [("JSON files", "*.json"), ("All files", "*.*")]
            font_size: 字体大小
        """
        super().__init__(parent)
        self.title(title)
        self.result: Optional[str] = None
        self.font_size = font_size
        self.filetypes = filetypes or [("All files", "*.*")]

        # 设置初始目录
        # 将相对路径转换为绝对路径（相对于当前工作目录）
        if initialdir:
            abs_initialdir = os.path.abspath(initialdir)
            if os.path.isdir(abs_initialdir):
                self.current_dir = abs_initialdir
            else:
                self.current_dir = os.path.abspath(".")
        else:
            self.current_dir = os.path.abspath(".")

        # 配置窗口
        self.geometry("700x500")
        self.minsize(500, 400)
        self.transient(parent)
        self.grab_set()

        # 创建UI
        self._create_ui()

        # 加载初始目录
        self._load_directory(self.current_dir)

        # 居中显示
        self._center_window()

        # 等待窗口关闭
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _center_window(self):
        """将窗口居中显示"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _create_ui(self):
        """创建UI组件"""
        # 使用 Arial 字体以保持与全局样式一致
        main_font = ("Arial", self.font_size)
        icon_font = ("Arial", self.font_size + 4)

        # 顶部路径栏
        path_frame = ttk.Frame(self, padding="10 10 10 5")
        path_frame.pack(fill=tk.X)

        ttk.Label(path_frame, text="Path:", font=main_font).pack(side=tk.LEFT)

        self.path_var = tk.StringVar(value=self.current_dir)
        self.path_entry = ttk.Entry(
            path_frame, textvariable=self.path_var, font=main_font
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))
        self.path_entry.bind("<Return>", self._on_path_enter)

        # 返回上级目录按钮
        self.up_btn = tk.Button(
            path_frame,
            text=self.PARENT_ICON,
            font=icon_font,
            command=self._go_up,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.up_btn.pack(side=tk.LEFT, padx=5)

        # 文件列表区域
        list_frame = ttk.Frame(self, padding="10 5")
        list_frame.pack(fill=tk.BOTH, expand=True)

        # 创建Treeview
        self.tree = ttk.Treeview(
            list_frame, columns=("name", "size", "type"), show="headings"
        )
        self.tree.heading("name", text="Name", anchor=tk.W)
        self.tree.heading("size", text="Size", anchor=tk.E)
        self.tree.heading("type", text="Type", anchor=tk.W)

        self.tree.column("name", width=400, anchor=tk.W)
        self.tree.column("size", width=100, anchor=tk.E)
        self.tree.column("type", width=100, anchor=tk.W)

        # 配置Treeview样式
        style = ttk.Style()
        # 使用自定义样式名称，避免影响全局Treeview样式
        style.configure(
            "FileDialog.Treeview", font=main_font, rowheight=int(self.font_size * 2.2)
        )
        style.configure(
            "FileDialog.Treeview.Heading",
            font=("Arial", self.font_size, "bold"),
        )

        # 滚动条
        scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set, style="FileDialog.Treeview")

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 绑定事件
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 底部区域
        bottom_frame = ttk.Frame(self, padding="10")
        bottom_frame.pack(fill=tk.X)

        # 文件名输入
        ttk.Label(bottom_frame, text="File:", font=main_font).pack(side=tk.LEFT)
        self.filename_var = tk.StringVar()
        self.filename_entry = ttk.Entry(
            bottom_frame, textvariable=self.filename_var, font=main_font, width=40
        )
        self.filename_entry.pack(side=tk.LEFT, padx=(10, 15), fill=tk.X, expand=True)

        # 文件类型过滤器
        ttk.Label(bottom_frame, text="Type:", font=main_font).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        filter_values = [f"{name} ({pattern})" for name, pattern in self.filetypes]
        self.filter_combo = ttk.Combobox(
            bottom_frame,
            textvariable=self.filter_var,
            values=filter_values,
            state="readonly",
            font=main_font,
            width=20,
        )
        self.filter_combo.pack(side=tk.LEFT, padx=(10, 0))
        self.filter_combo.current(0)
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter_changed)

        # 按钮区域
        btn_frame = ttk.Frame(self, padding="10 5 10 10")
        btn_frame.pack(fill=tk.X)

        # 配置按钮样式
        style.configure("Dialog.TButton", font=main_font, padding=(20, 10))

        ttk.Button(
            btn_frame, text="Cancel", command=self._on_cancel, style="Dialog.TButton"
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            btn_frame, text="Open", command=self._on_open, style="Dialog.TButton"
        ).pack(side=tk.RIGHT, padx=5)

    def _load_directory(self, path: str):
        """加载目录内容"""
        if not os.path.isdir(path):
            return

        self.current_dir = path
        self.path_var.set(path)

        # 清空列表
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 获取当前过滤器
        filter_idx = self.filter_combo.current()
        _, pattern = self.filetypes[filter_idx]

        try:
            entries = os.listdir(path)
        except PermissionError:
            return

        # 分离文件夹和文件
        folders = []
        files = []

        for entry in entries:
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                folders.append(entry)
            else:
                # 检查文件是否匹配过滤器
                if self._match_filter(entry, pattern):
                    files.append(entry)

        # 排序
        folders.sort(key=str.lower)
        files.sort(key=str.lower)

        # 添加文件夹
        for folder in folders:
            self.tree.insert(
                "",
                tk.END,
                values=(f"{self.FOLDER_ICON}  {folder}", "", "Folder"),
                tags=("folder",),
            )

        # 添加文件
        for file in files:
            full_path = os.path.join(path, file)
            try:
                size = os.path.getsize(full_path)
                size_str = self._format_size(size)
            except OSError:
                size_str = ""

            ext = os.path.splitext(file)[1].lower()
            file_type = ext[1:].upper() if ext else "File"

            self.tree.insert(
                "",
                tk.END,
                values=(f"{self.FILE_ICON}  {file}", size_str, file_type),
                tags=("file",),
            )

    def _match_filter(self, filename: str, pattern: str) -> bool:
        """检查文件是否匹配过滤器"""
        if pattern == "*.*" or pattern == "*":
            return True

        import fnmatch

        # 支持多个模式，如 "*.json;*.txt"
        patterns = pattern.replace(";", " ").split()
        for p in patterns:
            if fnmatch.fnmatch(filename.lower(), p.lower()):
                return True
        return False

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _get_selected_name(self) -> Optional[str]:
        """获取选中项的名称（去除图标）"""
        selection = self.tree.selection()
        if not selection:
            return None

        values = self.tree.item(selection[0], "values")
        if not values:
            return None

        # 去除图标前缀
        name = values[0]
        for icon in [self.FOLDER_ICON, self.FILE_ICON]:
            if name.startswith(icon):
                name = name[len(icon) :].strip()
                break
        return name

    def _is_folder_selected(self) -> bool:
        """检查选中的是否是文件夹"""
        selection = self.tree.selection()
        if not selection:
            return False
        tags = self.tree.item(selection[0], "tags")
        return "folder" in tags

    def _on_select(self, event):
        """选择项目时更新文件名"""
        name = self._get_selected_name()
        if name and not self._is_folder_selected():
            self.filename_var.set(name)

    def _on_double_click(self, event):
        """双击处理"""
        name = self._get_selected_name()
        if not name:
            return

        full_path = os.path.join(self.current_dir, name)

        if self._is_folder_selected():
            # 进入文件夹
            self._load_directory(full_path)
        else:
            # 选择文件
            self.result = full_path
            self.destroy()

    def _on_path_enter(self, event):
        """路径输入框回车"""
        path = self.path_var.get()
        if os.path.isdir(path):
            self._load_directory(path)

    def _go_up(self):
        """返回上级目录"""
        parent = os.path.dirname(self.current_dir)
        if parent and parent != self.current_dir:
            self._load_directory(parent)

    def _on_filter_changed(self, event):
        """文件类型过滤器变化"""
        self._load_directory(self.current_dir)

    def _on_open(self):
        """打开按钮点击"""
        filename = self.filename_var.get()
        if filename:
            full_path = os.path.join(self.current_dir, filename)
            if os.path.isfile(full_path):
                self.result = full_path
                self.destroy()

    def _on_cancel(self):
        """取消按钮点击"""
        self.result = None
        self.destroy()


def askopenfilename(
    parent=None,
    title: str = "Select File",
    initialdir: str = ".",
    filetypes: Optional[List[Tuple[str, str]]] = None,
    font_size: int = 14,
) -> Optional[str]:
    """
    显示自定义文件选择对话框

    Args:
        parent: 父窗口
        title: 对话框标题
        initialdir: 初始目录
        filetypes: 文件类型过滤器
        font_size: 字体大小

    Returns:
        选择的文件路径，或None（如果取消）
    """
    dialog = CustomFileDialog(
        parent=parent,
        title=title,
        initialdir=initialdir,
        filetypes=filetypes,
        font_size=font_size,
    )
    dialog.wait_window()
    return dialog.result
