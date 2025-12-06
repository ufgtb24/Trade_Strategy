"""
交互式查看器启动脚本

启动交互式UI，用于查看和分析突破检测结果
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import tkinter as tk
import matplotlib
matplotlib.use('TkAgg')  # 切换到交互式后端

from BreakthroughStrategy.UI import InteractiveUI, configure_global_styles


def main():
    """主函数"""
    root = tk.Tk()

    # 配置全局UI样式（必须在创建UI组件之前）
    configure_global_styles(root)

    app = InteractiveUI(root)

    # 可选：自动加载最新扫描结果
    # import os
    # scan_dir = project_root / 'outputs' / 'analysis'
    # if scan_dir.exists():
    #     json_files = sorted(scan_dir.glob('*.json'), key=os.path.getmtime, reverse=True)
    #     if json_files and 'test_scan.json' in str(json_files[0]):
    #         app.load_scan_results(str(json_files[0]))

    root.mainloop()


if __name__ == '__main__':
    main()
