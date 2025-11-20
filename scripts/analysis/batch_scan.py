"""
批量扫描脚本

扫描所有股票并保存结果到JSON文件
"""

import os
import sys
from pathlib import Path

import yaml

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from BreakthroughStrategy.visualization.interactive import ScanManager


def load_config(config_path: str = None) -> dict:
    """Load scan configuration from YAML file

    Args:
        config_path: Path to config file. If None, uses default configs/analysis/config.yaml

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = project_root / "configs" / "analysis" / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def load_params(params_path: str = None) -> dict:
    """Load params configuration from YAML file

    Args:
        params_path: Path to params file. If None, uses default configs/analysis/params/breakthrough_0.yaml

    Returns:
        Params configuration dictionary
    """
    if params_path is None:
        params_path = (
            project_root / "configs" / "analysis" / "params" / "breakthrough_0.yaml"
        )
    else:
        params_path = Path(params_path)

    if not params_path.exists():
        raise FileNotFoundError(f"Params file not found: {params_path}")

    with open(params_path, "r", encoding="utf-8") as f:
        params = yaml.safe_load(f)

    return params


def main():
    # Default configuration
    config_path = project_root / "configs" / "analysis" / "config.yaml"
    params_path = (
        project_root / "configs" / "analysis" / "params" / "breakthrough_0.yaml"
    )
    data_dir = "datasets/test_pkls"
    output_dir = "outputs/analysis"
    window = 5
    exceed_threshold = 0.005
    peak_merge_threshold = 0.03
    num_workers = 8
    max_stocks = None
    checkpoint_interval = 100
    start_date = None
    end_date = None

    try:
        config = load_config(config_path)
        params = load_params(params_path)

        data_dir = config["data"]["data_dir"]
        output_dir = config["output"]["output_dir"]
        num_workers = config["performance"]["num_workers"]
        max_stocks = config["data"]["max_stocks"]
        checkpoint_interval = config["performance"]["checkpoint_interval"]

        window = params["breakthrough_detector"]["window"]
        exceed_threshold = params["breakthrough_detector"]["exceed_threshold"]
        peak_merge_threshold = params["breakthrough_detector"]["peak_merge_threshold"]

        # 获取数据过滤参数
        start_date = config["data"].get("start_date")
        end_date = config["data"].get("end_date")

        print(f"Loaded configuration from: {config_path}")
        print(f"Loaded parameters from: {params_path}")
        print(f"  - Window: {window}")
        print(f"  - Exceed threshold: {exceed_threshold}")
        print(f"  - Peak merge threshold: {peak_merge_threshold}")
        print(f"  - Date range: {start_date} to {end_date}")
    except FileNotFoundError as e:
        print(f"Warning: {e}")
        print("Using default parameters")
    except Exception as e:
        print(f"Error loading config: {e}")
        print("Using default parameters")

    # 获取所有股票代码
    # data_dir 使用 CWD (终端所在目录) 解析，以便复用主分支数据
    data_dir_path = Path(data_dir)
    if not data_dir_path.exists():
        print(f"错误: 数据目录不存在: {data_dir_path}")
        print(f"当前工作目录: {Path.cwd()}")
        return

    symbols = [f[:-4] for f in os.listdir(data_dir_path) if f.endswith(".pkl")]
    print(f"发现 {len(symbols)} 只股票")

    if max_stocks:
        symbols = symbols[:max_stocks]
        print(f"限制扫描前 {len(symbols)} 只股票")

    # output_dir 使用 project_root (脚本所在目录) 解析，以便在不同分支独立输出
    output_dir_path = project_root / output_dir

    # 创建扫描管理器
    manager = ScanManager(
        output_dir=output_dir_path,
        window=window,
        exceed_threshold=exceed_threshold,
        peak_merge_threshold=peak_merge_threshold,
        start_date=start_date,
        end_date=end_date,
    )

    # 并行扫描
    results = manager.parallel_scan(
        symbols,
        data_dir=str(data_dir_path),
        num_workers=num_workers,
        checkpoint_interval=checkpoint_interval,
    )

    # 保存结果
    output_file = manager.save_results(results)

    print("\n" + "=" * 60)
    print("Scan completed!")
    print(f"Result file: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
