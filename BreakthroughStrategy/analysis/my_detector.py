import pickle
import json
import os
from datetime import datetime
from pathlib import Path
import hashlib


class BreakoutDetectorWithCache:
    """带持久化缓存的突破检测器"""
    
    def __init__(self, stock_symbol, window=5, cache_dir="./cache"):
        self.stock_symbol = stock_symbol
        self.window = window
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.prices = []
        self.active_peaks = []
        self.last_updated = None
        
        # 尝试加载缓存
        self._load_cache()
    
    def _get_cache_path(self):
        """获取缓存文件路径"""
        safe_symbol = self.stock_symbol.replace('/', '_')
        return self.cache_dir / f"{safe_symbol}_w{self.window}.pkl"
    
    def _get_metadata_path(self):
        """获取元数据文件路径（用于验证）"""
        safe_symbol = self.stock_symbol.replace('/', '_')
        return self.cache_dir / f"{safe_symbol}_w{self.window}_meta.json"
    
    def _calculate_data_hash(self):
        """计算数据哈希，用于完整性检查"""
        data_str = str(self.prices[-100:])  # 只用最近100天计算哈希
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def _save_cache(self):
        """保存缓存到磁盘"""
        try:
            cache_data = {
                'prices': self.prices,
                'active_peaks': self.active_peaks,
                'last_updated': datetime.now().isoformat(),
                'window': self.window
            }
            
            # 保存主数据
            with open(self._get_cache_path(), 'wb') as f:
                pickle.dump(cache_data, f)
            
            # 保存元数据（用于快速验证）
            metadata = {
                'stock_symbol': self.stock_symbol,
                'last_updated': cache_data['last_updated'],
                'data_points': len(self.prices),
                'active_peaks_count': len(self.active_peaks),
                'data_hash': self._calculate_data_hash(),
                'window': self.window
            }
            
            with open(self._get_metadata_path(), 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✓ 缓存已保存: {self.stock_symbol}, "
                  f"{len(self.prices)}个数据点, "
                  f"{len(self.active_peaks)}个活跃峰值")
        
        except Exception as e:
            print(f"✗ 保存缓存失败: {e}")
    
    def _load_cache(self):
        """从磁盘加载缓存"""
        cache_path = self._get_cache_path()
        meta_path = self._get_metadata_path()
        
        if not cache_path.exists():
            print(f"ℹ 未找到缓存文件: {self.stock_symbol}")
            return False
        
        try:
            # 先检查元数据
            if meta_path.exists():
                with open(meta_path, 'r') as f:
                    metadata = json.load(f)
                
                # 验证window参数是否匹配
                if metadata.get('window') != self.window:
                    print(f"⚠ 缓存参数不匹配 (window: {metadata.get('window')} vs {self.window})")
                    return False
                
                print(f"ℹ 发现缓存: {metadata['last_updated']}, "
                      f"{metadata['data_points']}个数据点")
            
            # 加载主数据
            with open(cache_path, 'rb') as f:
                cache_data = pickle.load(f)
            
            self.prices = cache_data['prices']
            self.active_peaks = cache_data['active_peaks']
            self.last_updated = cache_data.get('last_updated')
            
            # 验证数据完整性
            if meta_path.exists():
                current_hash = self._calculate_data_hash()
                if current_hash != metadata.get('data_hash'):
                    print(f"⚠ 数据哈希不匹配，缓存可能已损坏")
                    return False
            
            print(f"✓ 缓存加载成功: {self.stock_symbol}, "
                  f"{len(self.prices)}个数据点, "
                  f"{len(self.active_peaks)}个活跃峰值")
            
            return True
        
        except Exception as e:
            print(f"✗ 加载缓存失败: {e}")
            return False
    
    def clear_cache(self):
        """清除缓存文件"""
        try:
            cache_path = self._get_cache_path()
            meta_path = self._get_metadata_path()
            
            if cache_path.exists():
                cache_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            
            print(f"✓ 缓存已清除: {self.stock_symbol}")
        except Exception as e:
            print(f"✗ 清除缓存失败: {e}")
    
    def add_price(self, price, auto_save=True):
        """
        添加新价格

        Args:
            price: 新价格
            auto_save: 是否自动保存缓存
        """
        current_idx = len(self.prices)
        self.prices.append(price)
        
        # 检查突破
        breakouts = self._check_breakouts(current_idx, price)
        
        # 检查新峰值
        if current_idx >= self.window * 2:
            self._check_and_add_peak(current_idx - self.window)
        
        # 自动保存缓存
        if auto_save:
            # 策略：每10个数据点保存一次，或有突破时保存
            if len(self.prices) % 10 == 0 or breakouts:
                self._save_cache()
        
        return breakouts
    
    def batch_add_prices(self, prices, save_after=True):
        """
        批量添加价格（初始化或恢复时使用）

        Args:
            prices: 价格列表
            save_after: 完成后是否保存缓存
        """
        for price in prices:
            self.add_price(price, auto_save=False)
        
        if save_after:
            self._save_cache()
    
    def _check_and_add_peak(self, idx):
        """检查并添加峰值"""
        if idx < self.window or idx >= len(self.prices) - self.window:
            return
        
        price = self.prices[idx]
        is_peak = True
        
        for i in range(idx - self.window, idx):
            if self.prices[i] >= price:
                is_peak = False
                break
        
        if is_peak:
            for i in range(idx + 1, idx + self.window + 1):
                if self.prices[i] >= price:
                    is_peak = False
                    break
        
        if is_peak:
            # 移除被新峰值超越的旧峰值
            self.active_peaks = [
                (peak_idx, peak_price)
                for peak_idx, peak_price in self.active_peaks
                if peak_price > price
            ]
            self.active_peaks.append((idx, price))
    
    def _check_breakouts(self, current_idx, current_price):
        """检查突破"""
        breakouts = []
        remaining_peaks = []
        
        for peak_idx, peak_price in self.active_peaks:
            if current_price > peak_price:
                breakouts.append((peak_idx, peak_price))
            else:
                remaining_peaks.append((peak_idx, peak_price))
        
        self.active_peaks = remaining_peaks
        return breakouts
    
    def get_status(self):
        """获取状态信息"""
        return {
            'stock_symbol': self.stock_symbol,
            'total_prices': len(self.prices),
            'active_peaks': len(self.active_peaks),
            'last_updated': self.last_updated,
            'cache_exists': self._get_cache_path().exists()
        }


# ============ 使用示例 ============

def example_usage():
    print("=== 示例1: 首次运行（无缓存） ===\n")
    
    detector = BreakoutDetectorWithCache('AAPL', window=5)
    
    # 模拟历史数据
    import random
    random.seed(42)
    history = [100 + random.uniform(-5, 5) + i * 0.05 for i in range(100)]
    
    detector.batch_add_prices(history)
    
    print("\n=== 示例2: 重启程序（有缓存） ===\n")
    
    # 模拟程序重启
    detector2 = BreakoutDetectorWithCache('AAPL', window=5)
    # 自动加载了缓存！
    
    # 继续添加新数据
    new_price = 110
    breakouts = detector2.add_price(new_price)
    
    if breakouts:
        print(f"\n*** 突破检测: 价格{new_price}突破了 {breakouts} ***")
    
    print("\n=== 状态信息 ===")
    print(json.dumps(detector2.get_status(), indent=2))


if __name__ == "__main__":
    example_usage()