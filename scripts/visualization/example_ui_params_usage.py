"""UI参数加载器使用示例"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from BreakthroughStrategy.UI import get_ui_param_loader


def main():
    """主函数 - 演示UI参数加载器的使用"""

    print("="*60)
    print("UI参数加载器使用示例")
    print("="*60)

    # 获取参数加载器（单例模式）
    param_loader = get_ui_param_loader()

    print("\n【1. 项目根目录】")
    proj_root = param_loader.get_project_root()
    print(f"  项目根目录: {proj_root}")

    print("\n【2. 参数文件路径】")
    print(f"  ui_params.yaml: {param_loader._params_path}")
    print(f"  文件是否存在: {'✓' if param_loader._params_path.exists() else '✗'}")

    print("\n【3. BreakthroughDetector 参数】")
    detector_params = param_loader.get_detector_params()
    for key, value in detector_params.items():
        print(f"  {key}: {value}")

    print("\n【4. 完整参数配置】")
    all_params = param_loader.get_all_params()
    print(f"  配置sections: {list(all_params.keys())}")

    print("\n【5. 参数重新加载测试】")
    print("  执行 reload_params()...")
    param_loader.reload_params()
    reloaded_params = param_loader.get_detector_params()
    print(f"  重新加载后 window: {reloaded_params['window']}")
    print(f"  重新加载后 exceed_threshold: {reloaded_params['exceed_threshold']}")

    print("\n【6. 使用说明】")
    print("  1. 在UI中点击 'Edit Parameters' 按钮打开参数编辑器")
    print("  2. 直接在编辑器中修改参数并点击 'Apply' 按钮")
    print("  3. 参数将自动保存到 ui_params.yaml 并应用到检测算法")

    print("\n【7. 参数范围】")
    print("  window: 3-20 (超出范围会自动修正)")
    print("  exceed_threshold: 0.001-0.02 (超出范围会自动修正)")
    print("  peak_supersede_threshold: 0.01-0.1 (超出范围会自动修正)")

    print("\n" + "="*60)
    print("示例运行完成")
    print("="*60)


if __name__ == "__main__":
    main()
