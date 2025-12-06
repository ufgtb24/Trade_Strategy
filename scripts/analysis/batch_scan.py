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

from BreakthroughStrategy.UI import ScanManager


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


def load_csv_stock_list(csv_path: str, mon_before: int, mon_after: int) -> dict:
    """从CSV文件加载股票列表并计算相对时间范围

    Args:
        csv_path: CSV文件路径（格式：date,name,label）
        mon_before: 基准日期前N个月
        mon_after: 基准日期后N个月

    Returns:
        Dict[symbol, (start_date, end_date)]
        例如：{"VRAX": ("2024-04-19", "2024-08-19"), ...}

    Raises:
        FileNotFoundError: CSV文件不存在
        ValueError: CSV格式错误或无有效数据
    """
    import pandas as pd
    from dateutil.relativedelta import relativedelta

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # 读取CSV
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        raise ValueError(f"Failed to read CSV file: {e}")

    # 验证必需列
    if "date" not in df.columns or "name" not in df.columns:
        raise ValueError(
            f"CSV must contain 'date' and 'name' columns. "
            f"Found columns: {list(df.columns)}"
        )

    # 参数验证
    if mon_before < 0 or mon_after < 0:
        raise ValueError(
            f"mon_before and mon_after must be non-negative, "
            f"got mon_before={mon_before}, mon_after={mon_after}"
        )

    # 计算相对时间范围
    stock_time_ranges = {}
    failed_symbols = []

    for idx, row in df.iterrows():
        try:
            symbol = str(row["name"]).strip()
            if not symbol:
                raise ValueError("Empty symbol name")

            base_date = pd.to_datetime(row["date"])

            # 使用 relativedelta 精确计算月份
            # 优势：正确处理不同月份长度（28/29/30/31天）
            start_date = base_date - relativedelta(months=mon_before)
            end_date = base_date + relativedelta(months=mon_after)

            stock_time_ranges[symbol] = (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )
        except Exception as e:
            failed_symbols.append(f"Row {idx + 2}: {symbol} - {str(e)}")

    # 报告解析失败
    if failed_symbols:
        print(f"警告: {len(failed_symbols)} 条记录解析失败:")
        for msg in failed_symbols[:5]:
            print(f"  - {msg}")
        if len(failed_symbols) > 5:
            print(f"  ... 还有 {len(failed_symbols) - 5} 个错误")

    # 确保至少有一只有效股票
    if not stock_time_ranges:
        raise ValueError(
            f"No valid stocks found in CSV file. "
            f"Total rows: {len(df)}, Failed: {len(failed_symbols)}"
        )

    return stock_time_ranges


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
    peak_supersede_threshold = 0.03
    num_workers = 8
    max_stocks = None
    checkpoint_interval = 100
    start_date = None
    end_date = None
    feature_calc_config = {}
    quality_scorer_config = {}

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
        peak_supersede_threshold = params["breakthrough_detector"]["peak_supersede_threshold"]

        # 提取 FeatureCalculator 和 QualityScorer 配置
        feature_calc_config = params.get("feature_calculator", {})
        quality_scorer_config = params.get("quality_scorer", {})

        # 获取数据过滤参数
        start_date = config["data"].get("start_date")
        end_date = config["data"].get("end_date")

        print(f"Loaded configuration from: {config_path}")
        print(f"Loaded parameters from: {params_path}")
        print(f"  - Window: {window}")
        print(f"  - Exceed threshold: {exceed_threshold}")
        print(f"  - Peak merge threshold: {peak_supersede_threshold}")
        print(f"  - Date range: {start_date} to {end_date}")
    except FileNotFoundError as e:
        print(f"Warning: {e}")
        print("Using default parameters")
    except Exception as e:
        print(f"Error loading config: {e}")
        print("Using default parameters")

    # ========== 核心改动：判断扫描模式 ==========
    csv_file = config["data"].get("csv_file")
    data_dir_path = Path(data_dir)
    output_dir_path = project_root / output_dir

    if csv_file:
        # ============ CSV索引模式 ============
        print("\n" + "=" * 60)
        print("使用CSV索引模式")
        print("=" * 60)
        print(f"CSV文件: {csv_file}")

        mon_before = config["data"].get("mon_before", 3)
        mon_after = config["data"].get("mon_after", 1)
        print(f"相对时间范围: {mon_before}个月前 ~ {mon_after}个月后")

        # 读取CSV并计算时间范围
        try:
            stock_time_ranges = load_csv_stock_list(csv_file, mon_before, mon_after)
            symbols = list(stock_time_ranges.keys())

            print(f"从CSV加载 {len(symbols)} 只股票")
            # 打印前3只股票的时间范围作为示例
            for symbol, (start, end) in list(stock_time_ranges.items())[:3]:
                print(f"  - {symbol}: {start} ~ {end}")
            if len(symbols) > 3:
                print(f"  ... (共{len(symbols)}只)")
        except (FileNotFoundError, ValueError) as e:
            print(f"错误: {e}")
            return

        # 应用 max_stocks 限制
        if max_stocks and len(symbols) > max_stocks:
            print(f"限制扫描前 {max_stocks} 只股票")
            symbols = symbols[:max_stocks]
            stock_time_ranges = {k: stock_time_ranges[k] for k in symbols}

        # 创建ScanManager（不使用全局时间范围）
        manager = ScanManager(
            output_dir=output_dir_path,
            window=window,
            exceed_threshold=exceed_threshold,
            peak_supersede_threshold=peak_supersede_threshold,
            start_date=None,  # CSV模式下忽略全局时间
            end_date=None,
            feature_calc_config=feature_calc_config,
            quality_scorer_config=quality_scorer_config,
        )

        # 并行扫描（传递 per-stock 时间范围）
        results = manager.parallel_scan(
            symbols,
            data_dir=str(data_dir_path),
            num_workers=num_workers,
            checkpoint_interval=checkpoint_interval,
            stock_time_ranges=stock_time_ranges,  # ← 新增参数
        )
    else:
        # ============ 全局时间范围模式（原有逻辑）============
        print("\n" + "=" * 60)
        print("使用全局时间范围模式")
        print("=" * 60)
        print(f"时间范围: {start_date} ~ {end_date}")

        # 获取所有股票代码
        # data_dir 使用 CWD (终端所在目录) 解析，以便复用主分支数据
        if not data_dir_path.exists():
            print(f"错误: 数据目录不存在: {data_dir_path}")
            print(f"当前工作目录: {Path.cwd()}")
            return

        symbols = [f[:-4] for f in os.listdir(data_dir_path) if f.endswith(".pkl")]
        print(f"发现 {len(symbols)} 只股票")

        if max_stocks:
            symbols = symbols[:max_stocks]
            print(f"限制扫描前 {len(symbols)} 只股票")

        # 创建ScanManager（使用全局时间范围）
        manager = ScanManager(
            output_dir=output_dir_path,
            window=window,
            exceed_threshold=exceed_threshold,
            peak_supersede_threshold=peak_supersede_threshold,
            start_date=start_date,
            end_date=end_date,
            feature_calc_config=feature_calc_config,
            quality_scorer_config=quality_scorer_config,
        )

        # 并行扫描（不传递 per-stock 时间范围）
        results = manager.parallel_scan(
            symbols,
            data_dir=str(data_dir_path),
            num_workers=num_workers,
            checkpoint_interval=checkpoint_interval,
            # stock_time_ranges 参数未传递，默认为 None
        )

    # 保存结果（两种模式共用）
    output_file = manager.save_results(results)

    print("\n" + "=" * 60)
    print("Scan completed!")
    print(f"Result file: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
