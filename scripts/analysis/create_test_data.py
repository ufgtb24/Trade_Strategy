"""
创建测试数据用于开发UI

使用yfinance下载少量股票数据
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import yfinance as yf
import pandas as pd
from BreakthroughStrategy.UI import ScanManager


def main():
    # 下载5只股票的数据用于测试
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']

    print("下载测试数据...")
    test_dir = project_root / 'datasets' / 'test_pkls'
    test_dir.mkdir(parents=True, exist_ok=True)

    for symbol in test_symbols:
        print(f"下载 {symbol}...")
        df = yf.download(symbol, start='2020-01-01', end='2025-11-25', progress=False)

        # 处理MultiIndex列
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 标准化列名
        df.columns = [col.lower() if isinstance(col, str) else col for col in df.columns]

        # 保存
        df.to_pickle(test_dir / f'{symbol}.pkl')
        print(f"  {len(df)} 天数据已保存")

    # 运行扫描
    print("\n运行扫描...")
    manager = ScanManager(output_dir='outputs/analysis')
    results = manager.parallel_scan(test_symbols, data_dir=str(test_dir), num_workers=2)

    # 保存结果
    manager.save_results(results, 'test_scan.json')

    print("\n测试数据创建完成！")


if __name__ == '__main__':
    main()
