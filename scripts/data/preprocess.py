import shutil
from multiprocessing import Pool
import pandas as pd
import os
from tqdm import tqdm


class StockPreprocessor:
    """股票数据预处理器"""
    
    def __init__(self, data_root, preprocessed_root, num_workers=os.cpu_count(), dbg_file=None, skip_neg_value=True,**kwargs):
        self.data_root = data_root
        self.preprocessed_root = preprocessed_root
        self.num_workers = num_workers or os.cpu_count()
        self.dbg_file = dbg_file
        self.skip_neg_value=skip_neg_value

        # 如果存在调试文件，则读取调试数据
        if self.dbg_file and os.path.exists(self.dbg_file):
            self.dbg_data = self._read_debug_file()
        else:
            self.dbg_data = None
        
        # 保存其他可能需要的参数
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def _read_debug_file(self):
        """读取调试文件，解析日期和股票信息"""
        """文件格式示例:
        2021-02-01
        ZVRA RSSS
        2021-02-02
        CNTY  BLIN
        """
        debug_data = {}
        current_date = None
        
        with open(self.dbg_file, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 尝试解析为日期
            try:
                date = pd.to_datetime(line).date()
                current_date = date
                debug_data[current_date] = []
            except:
                # 如果不是日期，则是包含股票代码的行
                if current_date:
                    # 分割股票信息
                    stocks_names = line.split(" ")
                    for stock_name in stocks_names:
                        if stock_name:
                            debug_data[current_date].append(stock_name)
        
        return debug_data
    
    def preprocess_all(self):
        print('Starting preprocessing of stock files...')
        """预处理所有股票文件"""
        stock_files = []
        if os.path.exists(self.preprocessed_root):
            shutil.rmtree(self.preprocessed_root)
        os.makedirs(self.preprocessed_root, exist_ok=True)
        
        if self.dbg_data is not None:
            # 从调试数据中收集所有唯一的股票代码
            unique_stocks = set()
            for stocks_list in self.dbg_data.values():
                unique_stocks.update(stocks_list)
        
            # 为每个股票代码构建对应的 pkl 文件名
            stock_files = [f"{stock_code}.pkl" for stock_code in unique_stocks]
        else:
            stock_files = [f for f in os.listdir(self.data_root) if (f.endswith('.csv') or f.endswith('.pkl'))]
        
        processed_files = []
        with Pool(processes=self.num_workers) as pool:
            for result in tqdm(pool.map(self._process_file, stock_files), total=len(stock_files),
                               desc="Processing CSV files"):
                if result:
                    processed_files.append(result)
        
        # # 改为非并行处理，便于单步调试
        # for f in tqdm(stock_files, total=len(stock_files), desc="Processing CSV files"):
        #     result = self._process_file(f)
        #     if result:
        #         processed_files.append(result)
        
        return processed_files
    
    def _process_file(self, f):
        """处理单个文件"""
        df = pd.read_pickle(os.path.join(self.data_root, f))
        df.index = pd.to_datetime(df.index)  # 新下载的数据在下载后会自动完成，不需要在预处理中完成
        
        if self.preprocess_df(df,f):
            preprocessed_path = os.path.join(self.preprocessed_root, f[:-4] + '.pkl')
            df.to_pickle(preprocessed_path)
            return f[:-4] + '.pkl'
        return None
    # 定义一个函数，用于计算排除最大值后的平均值
    def exclude_max_mean(self,x):
        """排除窗口内最大值后计算平均值"""
        valid_values = x.dropna()
        if len(valid_values) == 0:  # 无有效数据时返回NaN
            return float('nan')
        if len(valid_values) == 1:  # 只有一个值时直接返回
            return valid_values.iloc[0]
        # 计算总和减去最大值，再除以(数量-1)
        return (valid_values.sum() - valid_values.max()) / (len(valid_values) - 1)

    def exclude_max_ema(self,series, span, window=21):
        """
        计算排除窗口内最大值的指数移动平均

        参数:
        series: 输入的时间序列数据
        span: EMA的span参数，用于计算alpha = 2/(span+1)
        window: 判断最大值的滚动窗口大小
        """
        alpha = 2 / (span + 1)
        result = series.copy()
        
        # 初始化第一个值
        result.iloc[0] = series.iloc[0]
        
        for i in range(1, len(series)):
            # 确定当前滑动窗口
            start_idx = max(0, i - window + 1)
            window_data = series.iloc[start_idx:i + 1]
            
            # 判断当前值是否为窗口内的最大值
            current_value = series.iloc[i]
            max_value = window_data.max()
            
            if current_value == max_value and len(window_data) > 1:
                # 如果当前值是窗口内的最大值且窗口内有多个值，则不更新EMA
                result.iloc[i] = result.iloc[i - 1]
            else:
                # 否则正常计算EMA
                result.iloc[i] = alpha * current_value + (1 - alpha) * result.iloc[i - 1]
        
        return result
    
    def preprocess_df(self, df, file,**kwargs):
        if self.skip_neg_value:
            # 过滤掉价格或成交量出现负值的股票
            price_volume_cols = ['close', 'open', 'high', 'low', 'volume']
            for col in price_volume_cols:
                if col in df.columns:
                    if (df[col] < 0).any():
                        print(f"Negative values found in column {col} of {file}, skipping this stock.")
                        return False
        
        rolling_vol = [3, 3]
        # rolling_mm = [1, 20]
        # 计算不同周期的平均成交量
        for period in range(rolling_vol[0], rolling_vol[1] + 1):
            # 计算排除异常大成交量后的平均成交量
            # df['av_' + str(period)] = df.volume.rolling(window=period * 21).apply(self.exclude_max_mean)
            df['av_' + str(period)] = self.exclude_max_ema(df.volume, span=period * 21, window=period * 21)
        
        # # 计算不同周期的最高价和最低价
        # for period in range(rolling_mm[0], rolling_mm[1] + 1):
        #     df['min_' + str(period)] = df.low.rolling(window=period * 11).min()
        #     df['max_' + str(period)] = df.high.rolling(window=period * 11).max()
        
        # 之所以不dropna是因为此处会保存处理后的数据，在读取数据后会计算其他周期指标，不同周期指标可能会有nan重叠时段
        # 如果dropna，则到时候还会额外多截取一部分数据
        if df.empty:
            return False
        return True


if __name__ == "__main__":


    data_root = 'datasets/pkls'
    preprocessed_root = 'datasets/process_pkls'
    preprocessor = StockPreprocessor(data_root, preprocessed_root,skip_neg_value=True)
    
    processed_files = preprocessor.preprocess_all()
