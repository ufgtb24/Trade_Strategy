"""批量扫描管理器"""

import json
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List

import pandas as pd

from BreakthroughStrategy.analysis import BreakthroughDetector
from BreakthroughStrategy.analysis.features import FeatureCalculator
from BreakthroughStrategy.analysis.quality_scorer import QualityScorer

from .utils import ensure_dir


def _scan_single_stock(args):
    """
    扫描单只股票（用于多进程）

    Args:
        args: (symbol, data_dir, window, exceed_threshold, peak_merge_threshold, start_date, end_date)

    Returns:
        结果字典
    """
    (
        symbol,
        data_dir,
        window,
        exceed_threshold,
        peak_merge_threshold,
        start_date,
        end_date,
    ) = args

    file_path = Path(data_dir) / f"{symbol}.pkl"

    if not file_path.exists():
        return {"symbol": symbol, "error": "File not found"}

    try:
        # 加载数据
        df = pd.read_pickle(file_path)

        # 数据截取
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]

        if df.empty:
            return {"symbol": symbol, "error": "Empty dataframe after filtering"}

        # 运行突破检测
        detector = BreakthroughDetector(
            symbol=symbol,
            window=window,
            exceed_threshold=exceed_threshold,
            peak_merge_threshold=peak_merge_threshold,
            use_cache=False,  # 扫描时不使用缓存
        )
        breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

        if not breakout_infos:
            return {
                "symbol": symbol,
                "data_points": len(df),
                "active_peaks": len(detector.active_peaks),
                "total_breakthroughs": 0,
                "breakthroughs": [],
            }

        # 特征计算和评分
        feature_calc = FeatureCalculator()
        quality_scorer = QualityScorer()

        breakthroughs = []
        for info in breakout_infos:
            # 为峰值评分
            for peak in info.broken_peaks:
                if peak.quality_score is None:
                    quality_scorer.score_peak(peak)

            # 特征计算
            bt = feature_calc.enrich_breakthrough(df, info, symbol)
            breakthroughs.append(bt)

        # 批量评分
        quality_scorer.score_breakthroughs_batch(breakthroughs)

        # 转换为可序列化格式
        result = {
            "symbol": symbol,
            "data_points": len(df),
            "active_peaks": len(detector.active_peaks),
            "total_breakthroughs": len(breakthroughs),
            "breakthroughs": [
                {
                    "date": bt.date.isoformat(),
                    "price": float(bt.price),
                    "index": int(bt.index),
                    "num_peaks_broken": int(bt.num_peaks_broken),
                    "breakthrough_type": bt.breakthrough_type,
                    "price_change_pct": float(bt.price_change_pct)
                    if bt.price_change_pct
                    else None,
                    "volume_surge_ratio": float(bt.volume_surge_ratio)
                    if bt.volume_surge_ratio
                    else None,
                    "quality_score": float(bt.quality_score)
                    if bt.quality_score
                    else None,
                    "broken_peaks": [
                        {
                            "price": float(p.price),
                            "date": p.date.isoformat(),
                            "quality_score": float(p.quality_score)
                            if p.quality_score
                            else None,
                        }
                        for p in bt.broken_peaks
                    ],
                }
                for bt in sorted(
                    breakthroughs,
                    key=lambda x: x.quality_score if x.quality_score else 0,
                    reverse=True,
                )
            ],
        }

        return result

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


class ScanManager:
    """扫描管理器"""

    def __init__(
        self,
        output_dir="outputs/analysis",
        window=5,
        exceed_threshold=0.005,
        peak_merge_threshold=0.03,
        start_date=None,
        end_date=None,
    ):
        """
        初始化扫描管理器

        Args:
            output_dir: 输出目录
            window: 检测窗口大小
            exceed_threshold: 突破阈值
            peak_merge_threshold: 峰值合并阈值
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        self.output_dir = Path(output_dir)
        ensure_dir(self.output_dir)

        self.window = window
        self.exceed_threshold = exceed_threshold
        self.peak_merge_threshold = peak_merge_threshold
        self.start_date = start_date
        self.end_date = end_date
        self.scan_date = datetime.now().isoformat()

    def scan_stock(self, symbol: str, data_dir: str = "datasets/pkls") -> Dict:
        """
        扫描单只股票

        Args:
            symbol: 股票代码
            data_dir: 数据目录

        Returns:
            结果字典
        """
        return _scan_single_stock(
            (
                symbol,
                data_dir,
                self.window,
                self.exceed_threshold,
                self.peak_merge_threshold,
                self.start_date,
                self.end_date,
            )
        )

    def parallel_scan(
        self,
        symbols: List[str],
        data_dir: str = "datasets/pkls",
        num_workers: int = 8,
        checkpoint_interval: int = 100,
    ) -> List[Dict]:
        """
        并行扫描多只股票

        Args:
            symbols: 股票代码列表
            data_dir: 数据目录
            num_workers: 并行worker数
            checkpoint_interval: checkpoint间隔

        Returns:
            结果列表
        """
        print(f"开始扫描 {len(symbols)} 只股票...")
        print(f"使用 {num_workers} 个并行进程")
        print(
            f"参数: window={self.window}, exceed_threshold={self.exceed_threshold}, peak_merge_threshold={self.peak_merge_threshold}"
        )
        if self.start_date or self.end_date:
            print(f"时间范围: {self.start_date} - {self.end_date}")

        all_results = []

        # 分批处理，支持checkpoint
        for batch_start in range(0, len(symbols), checkpoint_interval):
            batch_end = min(batch_start + checkpoint_interval, len(symbols))
            batch_symbols = symbols[batch_start:batch_end]

            print(
                f"\n处理批次 {batch_start // checkpoint_interval + 1} "
                f"({batch_start + 1}-{batch_end}/{len(symbols)})"
            )

            # 并行扫描
            args = [
                (
                    sym,
                    data_dir,
                    self.window,
                    self.exceed_threshold,
                    self.peak_merge_threshold,
                    self.start_date,
                    self.end_date,
                )
                for sym in batch_symbols
            ]

            with Pool(processes=num_workers) as pool:
                batch_results = pool.map(_scan_single_stock, args)

            all_results.extend(batch_results)

            # 保存checkpoint
            checkpoint_file = self.output_dir / f"checkpoint_{batch_end}.json"
            self._save_results_internal(all_results, checkpoint_file)
            print(f"Checkpoint已保存: {checkpoint_file}")

        print(f"\n扫描完成！共 {len(all_results)} 只股票")
        return all_results

    def _save_results_internal(self, results: List[Dict], output_path: Path):
        """内部方法：保存结果"""
        # 统计信息
        successful_scans = [r for r in results if "total_breakthroughs" in r]
        error_scans = [r for r in results if "error" in r]

        # 计算统计数据
        total_breakthroughs = sum(
            r.get("total_breakthroughs", 0) for r in successful_scans
        )
        stocks_with_breakthroughs = sum(
            1 for r in successful_scans if r.get("total_breakthroughs", 0) > 0
        )

        # 收集所有质量评分
        all_quality_scores = []
        for r in successful_scans:
            for bt in r.get("breakthroughs", []):
                if bt.get("quality_score"):
                    all_quality_scores.append(bt["quality_score"])

        output_data = {
            "scan_metadata": {
                "scan_date": self.scan_date,
                "total_stocks": len(results),
                "stocks_scanned": len(successful_scans),
                "scan_errors": len(error_scans),
                "window": self.window,
                "exceed_threshold": self.exceed_threshold,
                "peak_merge_threshold": self.peak_merge_threshold,
                "start_date": self.start_date,
                "end_date": self.end_date,
            },
            "results": results,
            "summary_stats": {
                "total_breakthroughs": total_breakthroughs,
                "stocks_with_breakthroughs": stocks_with_breakthroughs,
                "avg_breakthroughs_per_stock": total_breakthroughs
                / len(successful_scans)
                if successful_scans
                else 0,
                "avg_quality_score": sum(all_quality_scores) / len(all_quality_scores)
                if all_quality_scores
                else 0,
            },
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    def save_results(self, results: List[Dict], filename: str = None):
        """
        保存扫描结果

        Args:
            results: 结果列表
            filename: 文件名（可选）

        Returns:
            保存路径
        """
        if filename is None:
            filename = f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = self.output_dir / filename
        self._save_results_internal(results, output_path)

        print(f"\n结果已保存: {output_path}")
        print(f"总股票数: {len(results)}")

        # 打印简要统计
        successful_scans = [r for r in results if "total_breakthroughs" in r]
        error_scans = [r for r in results if "error" in r]

        print(f"成功扫描: {len(successful_scans)}")
        print(f"扫描错误: {len(error_scans)}")

        if successful_scans:
            total_bts = sum(r.get("total_breakthroughs", 0) for r in successful_scans)
            print(f"总突破数: {total_bts}")

        return output_path

    def load_results(self, input_path: str) -> Dict:
        """
        加载已保存的扫描结果

        Args:
            input_path: 输入文件路径

        Returns:
            扫描结果字典
        """
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"加载扫描结果: {input_path}")
        print(f"扫描日期: {data['scan_metadata']['scan_date']}")
        print(f"总股票数: {data['scan_metadata']['total_stocks']}")
        print(f"成功扫描: {data['scan_metadata']['stocks_scanned']}")

        return data
