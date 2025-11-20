"""UI配置加载器使用示例"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from BreakthroughStrategy.visualization.interactive.ui_config_loader import (
    get_ui_config_loader,
)


def main():
    """主函数 - 演示UI配置加载器的使用"""

    print("="*60)
    print("UI配置加载器使用示例")
    print("="*60)

    # 获取配置加载器（单例模式）
    config_loader = get_ui_config_loader()

    print("\n【1. 项目根目录】")
    proj_root = config_loader.get_project_root()
    print(f"  项目根目录: {proj_root}")

    print("\n【2. 扫描结果路径配置】")
    scan_dir_abs = config_loader.get_scan_results_dir(absolute=True)
    scan_dir_rel = config_loader.get_scan_results_dir(absolute=False)
    print(f"  默认扫描结果目录 (相对): {scan_dir_rel}")
    print(f"  默认扫描结果目录 (绝对): {scan_dir_abs}")
    print(f"  目录是否存在: {'✓' if Path(scan_dir_abs).exists() else '✗'}")

    recent_file = config_loader.get_recent_scan_file()
    print(f"  最近打开的文件: {recent_file or '(无)'}")

    print("\n【3. 股票数据路径配置】")
    stock_dir_abs = config_loader.get_stock_data_dir(absolute=True)
    stock_dir_rel = config_loader.get_stock_data_dir(absolute=False)
    print(f"  默认股票数据目录 (相对): {stock_dir_rel}")
    print(f"  默认股票数据目录 (绝对): {stock_dir_abs}")
    print(f"  目录是否存在: {'✓' if Path(stock_dir_abs).exists() else '✗'}")

    search_paths_abs = config_loader.get_stock_data_search_paths(absolute=True)
    search_paths_rel = config_loader.get_stock_data_search_paths(absolute=False)
    print(f"  搜索路径（按优先级）:")
    for i, (rel_path, abs_path) in enumerate(zip(search_paths_rel, search_paths_abs), 1):
        exists = "✓" if Path(abs_path).exists() else "✗"
        print(f"    {i}. {rel_path} {exists}")
        print(f"       → {abs_path}")

    print("\n【4. UI显示配置】")
    width, height = config_loader.get_window_size()
    print(f"  窗口大小: {width}x{height}")

    left_weight, right_weight = config_loader.get_panel_weights()
    print(f"  面板权重: 左侧={left_weight}, 右侧={right_weight}")

    print("\n【5. 完整配置】")
    all_config = config_loader.get_all_config()
    import yaml
    print(yaml.dump(all_config, allow_unicode=True, default_flow_style=False))

    print("\n【6. 动态修改配置（示例）】")
    # 注意：修改后需要调用 save_config() 才会保存到文件
    config_loader.set_recent_scan_file("scan_results/latest_scan.json")
    print(f"  设置最近文件为: {config_loader.get_recent_scan_file()}")
    print("  提示: 如需持久化，请调用 config_loader.save_config()")

    print("\n" + "="*60)
    print("示例运行完成")
    print("="*60)


if __name__ == "__main__":
    main()
