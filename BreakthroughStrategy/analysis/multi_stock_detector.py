from BreakthroughStrategy.analysis.my_detector import BreakoutDetectorWithCache


class MultiStockBreakoutMonitor:
    """多股票突破监控器"""
    
    def __init__(self, watch_list, window=5, cache_dir="./cache"):
        self.watch_list = watch_list
        self.detectors = {}
        
        # 为每只股票创建检测器
        for symbol in watch_list:
            self.detectors[symbol] = BreakoutDetectorWithCache(
                symbol, window=window, cache_dir=cache_dir
            )
    
    def initialize_from_history(self, symbol, history_prices):
        """用历史数据初始化某只股票"""
        if symbol in self.detectors:
            self.detectors[symbol].batch_add_prices(history_prices)
    
    def on_new_prices(self, price_dict):
        """
        处理多只股票的新价格

        Args:
            price_dict: {symbol: price} 字典
        """
        all_breakouts = {}
        
        for symbol, price in price_dict.items():
            if symbol in self.detectors:
                breakouts = self.detectors[symbol].add_price(price)
                if breakouts:
                    all_breakouts[symbol] = breakouts
        
        return all_breakouts
    
    def get_all_status(self):
        """获取所有股票的状态"""
        return {
            symbol: detector.get_status()
            for symbol, detector in self.detectors.items()
        }
    
    def save_all(self):
        """手动保存所有股票的缓存"""
        for detector in self.detectors.values():
            detector._save_cache()


# 使用示例
monitor = MultiStockBreakoutMonitor(['AAPL', 'GOOGL', 'MSFT'], window=5)

# 初始化历史数据（只需一次）
for symbol in ['AAPL', 'GOOGL', 'MSFT']:
    history = fetch_history(symbol, days=100)
    monitor.initialize_from_history(symbol, history)

# 实时监控循环
while True:
    # 获取实时价格
    current_prices = {
        'AAPL': get_price('AAPL'),
        'GOOGL': get_price('GOOGL'),
        'MSFT': get_price('MSFT')
    }
    
    # 检测突破
    breakouts = monitor.on_new_prices(current_prices)
    
    if breakouts:
        print(f"突破信号: {breakouts}")
        # 执行交易逻辑...
    
