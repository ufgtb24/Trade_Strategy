"""
评估上下文构建器

构建买入条件评估所需的上下文数据，包括：
- 价格数据 (OHLCV)
- 技术指标 (volume_ma20, atr_value)
- 参考价格 (prev_close, baseline_volume)

使用示例：
    builder = EvaluationContextBuilder()

    # 构建单个条目的上下文
    context = builder.build_context_for_entry(symbol, df, breakout, as_of_date)

    # 批量构建
    contexts = builder.build_batch_context(entries_with_breakouts, df_cache, as_of_date)
"""
from datetime import date
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from BreakoutStrategy.analysis import Breakout
    from BreakoutStrategy.observation import PoolEntry


class EvaluationContextBuilder:
    """
    构建买入评估所需的上下文数据

    职责：
    - 从 DataFrame 计算技术指标（volume_ma20 等）
    - 构建评估器所需的 price_data 和 context
    - 支持单条目和批量构建

    上下文字段来源：
        atr_value       - Breakout.atr_value（已在 JSON 中保存）
        volume_ma20     - DataFrame 计算 20 日均量
        prev_close      - df['close'].iloc[idx-1]
        baseline_volume - 同 volume_ma20
    """

    def __init__(self, volume_ma_period: int = 20):
        """
        初始化构建器

        Args:
            volume_ma_period: 成交量均线周期，默认 20
        """
        self.volume_ma_period = volume_ma_period

    def build_price_data(
        self,
        symbols: List[str],
        df_cache: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> Dict[str, pd.Series]:
        """
        构建价格数据字典

        Args:
            symbols: 股票代码列表
            df_cache: {symbol: DataFrame} 缓存
            as_of_date: 截止日期

        Returns:
            {symbol: Series(open, high, low, close, volume)}
        """
        price_data = {}

        for symbol in symbols:
            df = df_cache.get(symbol)
            if df is None or df.empty:
                continue

            idx = self._get_date_index(df, as_of_date)
            if idx is None:
                continue

            # 提取当日 OHLCV
            row = df.iloc[idx]
            price_data[symbol] = pd.Series({
                'open': row.get('open', row.get('Open', 0)),
                'high': row.get('high', row.get('High', 0)),
                'low': row.get('low', row.get('Low', 0)),
                'close': row.get('close', row.get('Close', 0)),
                'volume': row.get('volume', row.get('Volume', 0)),
            })

        return price_data

    def build_context_for_entry(
        self,
        symbol: str,
        df: pd.DataFrame,
        breakout: 'Breakout',
        as_of_date: date
    ) -> Dict:
        """
        构建单个条目的评估上下文

        Args:
            symbol: 股票代码
            df: DataFrame
            breakout: Breakout 对象（用于获取 atr_value）
            as_of_date: 截止日期

        Returns:
            {
                'atr_value': float,
                'volume_ma20': float,
                'prev_close': float,
                'baseline_volume': float
            }
        """
        idx = self._get_date_index(df, as_of_date)
        if idx is None:
            return self._empty_context()

        # 获取 volume 列名（兼容大小写）
        volume_col = 'volume' if 'volume' in df.columns else 'Volume'
        close_col = 'close' if 'close' in df.columns else 'Close'

        # 计算 volume_ma20
        start_idx = max(0, idx - self.volume_ma_period)
        volume_ma20 = df[volume_col].iloc[start_idx:idx].mean() if idx > 0 else 0.0

        # 获取 prev_close
        prev_close = df[close_col].iloc[idx - 1] if idx > 0 else df[close_col].iloc[idx]

        return {
            'atr_value': breakout.atr_value if breakout else 0.0,
            'volume_ma20': volume_ma20,
            'prev_close': prev_close,
            'baseline_volume': volume_ma20,  # 与 volume_ma20 相同
        }

    def build_batch_context(
        self,
        entries_with_breakouts: List[Tuple['PoolEntry', Optional['Breakout']]],
        df_cache: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> Dict[str, Dict]:
        """
        批量构建评估上下文

        Args:
            entries_with_breakouts: [(PoolEntry, Breakout), ...] breakout 可能为 None
            df_cache: {symbol: DataFrame} 缓存
            as_of_date: 截止日期

        Returns:
            {symbol: context_dict}
        """
        contexts = {}

        for entry, breakout in entries_with_breakouts:
            symbol = entry.symbol
            df = df_cache.get(symbol)

            if df is None or df.empty:
                contexts[symbol] = self._empty_context()
                continue

            # 如果没有 breakout 对象，从 entry 获取 atr_value（如果有的话）
            if breakout is None:
                # 创建一个临时对象来传递 atr_value
                class _MockBreakout:
                    atr_value = 0.0
                breakout = _MockBreakout()

            contexts[symbol] = self.build_context_for_entry(
                symbol, df, breakout, as_of_date
            )

        return contexts

    def build_full_evaluation_data(
        self,
        entries_with_breakouts: List[Tuple['PoolEntry', Optional['Breakout']]],
        df_cache: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> Tuple[Dict[str, pd.Series], Dict[str, Dict]]:
        """
        一次性构建 price_data 和 context

        Args:
            entries_with_breakouts: [(PoolEntry, Breakout), ...]
            df_cache: {symbol: DataFrame} 缓存
            as_of_date: 截止日期

        Returns:
            (price_data, contexts) 元组
        """
        symbols = [entry.symbol for entry, _ in entries_with_breakouts]

        price_data = self.build_price_data(symbols, df_cache, as_of_date)
        contexts = self.build_batch_context(entries_with_breakouts, df_cache, as_of_date)

        return price_data, contexts

    # ===== 内部方法 =====

    def _get_date_index(self, df: pd.DataFrame, target_date: date) -> Optional[int]:
        """
        获取日期在 DataFrame 中的索引位置

        Args:
            df: DataFrame
            target_date: 目标日期

        Returns:
            索引位置，如果找不到返回 None
        """
        try:
            # 尝试精确匹配
            ts = pd.Timestamp(target_date)
            if ts in df.index:
                idx = df.index.get_loc(ts)
                if isinstance(idx, slice):
                    return idx.start
                return int(idx)

            # 如果精确匹配失败，找最接近的前一个日期
            mask = df.index <= ts
            if mask.any():
                return int(mask.sum()) - 1

            return None
        except Exception:
            return None

    def _empty_context(self) -> Dict:
        """返回空的上下文字典"""
        return {
            'atr_value': 0.0,
            'volume_ma20': 0.0,
            'prev_close': 0.0,
            'baseline_volume': 0.0,
        }
