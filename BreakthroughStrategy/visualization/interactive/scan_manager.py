"""批量扫描管理器"""

import json
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from BreakthroughStrategy.analysis import BreakthroughDetector
from BreakthroughStrategy.analysis.features import FeatureCalculator
from BreakthroughStrategy.analysis.quality_scorer import QualityScorer

from .utils import ensure_dir


def compute_breakthroughs_from_dataframe(
    symbol: str,
    df: pd.DataFrame,
    window: int,
    exceed_threshold: float,
    peak_merge_threshold: float,
    feature_calc_config: dict = None,
    quality_scorer_config: dict = None,
) -> Tuple[List, BreakthroughDetector]:
    """
    从 DataFrame 计算突破（统一函数，供 batch_scan 和 UI 使用）

    Args:
        symbol: 股票代码
        df: 数据 DataFrame
        window: 检测窗口大小
        exceed_threshold: 突破阈值
        peak_merge_threshold: 峰值合并阈值
        feature_calc_config: FeatureCalculator 配置字典
        quality_scorer_config: QualityScorer 配置字典

    Returns:
        (breakthroughs, detector) 元组
    """
    # 运行突破检测
    detector = BreakthroughDetector(
        symbol=symbol,
        window=window,
        exceed_threshold=exceed_threshold,
        peak_merge_threshold=peak_merge_threshold,
        use_cache=False,
    )
    breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

    if not breakout_infos:
        return [], detector

    # 特征计算和评分（使用传入的配置）
    feature_calc = FeatureCalculator(config=feature_calc_config or {})
    quality_scorer = QualityScorer(config=quality_scorer_config or {})

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

    # 为检测器的活跃峰值评分
    for peak in detector.active_peaks:
        if peak.quality_score is None:
            quality_scorer.score_peak(peak)

    return breakthroughs, detector


def _scan_single_stock(args):
    """
    扫描单只股票（用于多进程）

    Args:
        args: (symbol, data_dir, window, exceed_threshold, peak_merge_threshold, start_date, end_date,
               feature_calc_config, quality_scorer_config)

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
        feature_calc_config,
        quality_scorer_config,
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

        # 使用统一函数计算突破
        breakthroughs, detector = compute_breakthroughs_from_dataframe(
            symbol=symbol,
            df=df,
            window=window,
            exceed_threshold=exceed_threshold,
            peak_merge_threshold=peak_merge_threshold,
            feature_calc_config=feature_calc_config,
            quality_scorer_config=quality_scorer_config,
        )

        if not breakthroughs:
            return {
                "symbol": symbol,
                "data_points": len(df),
                "active_peaks": len(detector.active_peaks),
                "total_breakthroughs": 0,
                "avg_quality": 0.0,
                "max_quality": 0.0,
                "breakthroughs": [],
            }

        # 收集所有峰值（active + broken）并分配唯一ID
        all_peaks_dict = {}  # {id: Peak}
        peak_id_counter = 1

        # 1. 收集active peaks并分配ID
        for peak in detector.active_peaks:
            if peak.id is None:
                peak.id = peak_id_counter
                peak_id_counter += 1
            all_peaks_dict[peak.id] = peak

        # 2. 收集broken peaks并分配ID（去重）
        for bt in breakthroughs:
            for peak in bt.broken_peaks:
                if peak.id is None:  # 未分配ID
                    peak.id = peak_id_counter
                    all_peaks_dict[peak_id_counter] = peak
                    peak_id_counter += 1
                elif peak.id not in all_peaks_dict:
                    all_peaks_dict[peak.id] = peak

        # 3. 标记active状态
        active_peak_ids = {p.id for p in detector.active_peaks}

        # 计算质量评分统计（per-stock）
        quality_scores = [
            bt.quality_score
            for bt in breakthroughs
            if bt.quality_score is not None
        ]
        avg_quality = (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        )
        max_quality = max(quality_scores) if quality_scores else 0.0

        # 转换为可序列化格式
        result = {
            "symbol": symbol,
            "scan_start_date": start_date
            if start_date
            else df.index[0].strftime("%Y-%m-%d"),
            "scan_end_date": end_date
            if end_date
            else df.index[-1].strftime("%Y-%m-%d"),
            "data_points": len(df),
            "active_peaks": len(detector.active_peaks),
            "total_breakthroughs": len(breakthroughs),
            "avg_quality": avg_quality,
            "max_quality": max_quality,
            "all_peaks": [
                {
                    "id": peak.id,
                    "price": float(peak.price),
                    "date": peak.date.isoformat(),
                    "index": int(peak.index),
                    "volume_surge_ratio": float(peak.volume_surge_ratio)
                    if peak.volume_surge_ratio
                    else 0.0,
                    "candle_change_pct": float(peak.candle_change_pct)
                    if peak.candle_change_pct
                    else 0.0,
                    "left_suppression_days": int(peak.left_suppression_days)
                    if peak.left_suppression_days
                    else 0,
                    "right_suppression_days": int(peak.right_suppression_days)
                    if peak.right_suppression_days
                    else 0,
                    "relative_height": float(peak.relative_height)
                    if peak.relative_height
                    else 0.0,
                    "quality_score": float(peak.quality_score)
                    if peak.quality_score
                    else None,
                    "is_active": peak.id in active_peak_ids,
                }
                for peak in sorted(all_peaks_dict.values(), key=lambda p: p.index)
            ],
            "breakthroughs": [
                {
                    "date": bt.date.isoformat(),
                    "price": float(bt.price),
                    "index": int(bt.index),
                    "broken_peak_ids": bt.broken_peak_ids,  # 使用ID引用而非完整对象
                    "num_peaks_broken": int(bt.num_peaks_broken),
                    "breakthrough_type": bt.breakthrough_type,
                    "price_change_pct": float(bt.price_change_pct)
                    if bt.price_change_pct
                    else None,
                    "gap_up_pct": float(bt.gap_up_pct)
                    if hasattr(bt, "gap_up_pct") and bt.gap_up_pct
                    else None,
                    "volume_surge_ratio": float(bt.volume_surge_ratio)
                    if bt.volume_surge_ratio
                    else None,
                    "continuity_days": int(bt.continuity_days)
                    if hasattr(bt, "continuity_days") and bt.continuity_days
                    else None,
                    "stability_score": float(bt.stability_score)
                    if hasattr(bt, "stability_score") and bt.stability_score
                    else None,
                    "quality_score": float(bt.quality_score)
                    if bt.quality_score
                    else None,
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
        feature_calc_config=None,
        quality_scorer_config=None,
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
            feature_calc_config: FeatureCalculator 配置字典
            quality_scorer_config: QualityScorer 配置字典
        """
        self.output_dir = Path(output_dir)
        ensure_dir(self.output_dir)

        self.window = window
        self.exceed_threshold = exceed_threshold
        self.peak_merge_threshold = peak_merge_threshold
        self.start_date = start_date
        self.end_date = end_date
        self.scan_date = datetime.now().isoformat()

        # 保存特征计算和评分配置
        self.feature_calc_config = feature_calc_config if feature_calc_config else {}
        self.quality_scorer_config = quality_scorer_config if quality_scorer_config else {}

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
                self.feature_calc_config,
                self.quality_scorer_config,
            )
        )

    def parallel_scan(
        self,
        symbols: List[str],
        data_dir: str = "datasets/pkls",
        num_workers: int = 8,
        checkpoint_interval: int = 100,
        stock_time_ranges: Dict[str, tuple] = None,
    ) -> List[Dict]:
        """
        并行扫描多只股票

        Args:
            symbols: 股票代码列表
            data_dir: 数据目录
            num_workers: 并行worker数
            checkpoint_interval: checkpoint间隔
            stock_time_ranges: 每只股票的时间范围（可选）
                              格式：{symbol: (start_date, end_date)}
                              如果为None，使用全局的 self.start_date 和 self.end_date

        Returns:
            结果列表
        """
        print(f"开始扫描 {len(symbols)} 只股票...")
        print(f"使用 {num_workers} 个并行进程")
        print(
            f"参数: window={self.window}, exceed_threshold={self.exceed_threshold}, peak_merge_threshold={self.peak_merge_threshold}"
        )

        # 打印模式信息
        if stock_time_ranges:
            print(f"扫描模式: CSV索引模式（每只股票独立时间范围）")
        else:
            print(f"扫描模式: 全局时间范围模式")
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

            # ========== 核心改动：构建参数列表 ==========
            args = []
            for sym in batch_symbols:
                # 判断使用 per-stock 时间范围还是全局时间范围
                if stock_time_ranges and sym in stock_time_ranges:
                    start_date, end_date = stock_time_ranges[sym]
                else:
                    start_date, end_date = self.start_date, self.end_date

                args.append(
                    (
                        sym,
                        data_dir,
                        self.window,
                        self.exceed_threshold,
                        self.peak_merge_threshold,
                        start_date,
                        end_date,
                        self.feature_calc_config,
                        self.quality_scorer_config,
                    )
                )

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
                "schema_version": "3.0",  # 升级到v3.0，保存完整参数
                "scan_date": self.scan_date,
                "total_stocks": len(results),
                "stocks_scanned": len(successful_scans),
                "scan_errors": len(error_scans),
                "start_date": self.start_date,
                "end_date": self.end_date,
                # 分组保存参数（v3.0新格式）
                "detector_params": {
                    "window": self.window,
                    "exceed_threshold": self.exceed_threshold,
                    "peak_merge_threshold": self.peak_merge_threshold,
                },
                "feature_calculator_params": self.feature_calc_config,
                "quality_scorer_params": self.quality_scorer_config,
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

        Raises:
            ValueError: 如果JSON版本不支持
        """
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 版本检查和自动迁移
        schema_version = data.get("scan_metadata", {}).get("schema_version", "1.0")
        metadata = data["scan_metadata"]

        if schema_version == "2.0":
            # v2.0 → v3.0 自动迁移
            print(f"检测到 v2.0 格式，自动迁移到 v3.0...")
            # 重构参数结构
            metadata["detector_params"] = {
                "window": metadata.pop("window"),
                "exceed_threshold": metadata.pop("exceed_threshold"),
                "peak_merge_threshold": metadata.pop("peak_merge_threshold"),
            }
            # 添加默认参数
            metadata["feature_calculator_params"] = self._get_default_feature_params()
            metadata["quality_scorer_params"] = self._get_default_scorer_params()
            metadata["schema_version"] = "3.0"
            print("迁移完成（使用默认特征和评分参数）")

        elif schema_version != "3.0":
            raise ValueError(
                f"Unsupported JSON format (version {schema_version}). "
                f"Please re-scan with the latest version to generate v3.0 JSON."
            )

        print(f"加载扫描结果: {input_path}")
        print(f"扫描日期: {data['scan_metadata']['scan_date']}")
        print(f"总股票数: {data['scan_metadata']['total_stocks']}")
        print(f"成功扫描: {data['scan_metadata']['stocks_scanned']}")

        return data

    def _get_default_feature_params(self) -> Dict:
        """获取 FeatureCalculator 默认参数（用于 v2.0 迁移）"""
        return {
            "stability_lookforward": 10,
            "continuity_lookback": 5,
        }

    def _get_default_scorer_params(self) -> Dict:
        """获取 QualityScorer 默认参数（用于 v2.0 迁移）"""
        return {
            "peak_weight_volume": 0.25,
            "peak_weight_candle": 0.20,
            "peak_weight_suppression": 0.25,
            "peak_weight_height": 0.15,
            "peak_weight_merged": 0.15,
            "bt_weight_change": 0.20,
            "bt_weight_gap": 0.10,
            "bt_weight_volume": 0.20,
            "bt_weight_continuity": 0.15,
            "bt_weight_stability": 0.15,
            "bt_weight_resistance": 0.20,
        }
