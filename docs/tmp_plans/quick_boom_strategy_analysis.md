# Quick Boom 策略分析

## 文档信息
- **创建日期**: 2025-11-28
- **来源项目**: `/home/yu/PycharmProjects/new_trade/ScreenerDayFeature/`
- **核心文件**:
  - `Picker.py` (主选股逻辑)
  - `picker_configs.py` (quick_boom 配置)
  - `filters.py` (过滤器实现)

---

## 一、策略目的

**Quick Boom** 是一个基于技术分析的股票筛选策略，旨在寻找**满足特定条件并在1个月内有较高概率实现3倍涨幅**的股票。

### 核心目标
- **寻找标的**：低价股（0.5-3元）、成交活跃（平均成交量>1万）
- **预期收益**：买入后1个月内（21个交易日）涨幅达到300%
- **时间范围**：2024年7月1日 - 2025年7月1日（历史回测数据）

---

## 二、策略原理

### 2.1 工作流程

```
历史数据 → 多条件过滤 → 模拟买入 → 计算涨幅 → 标签分类 → 输出结果
```

### 2.2 核心参数配置

```python
quick_boom = dict(
    # 数据源
    data_root='datasets/process_pkls',
    output_path='ext_file/stock_lists/',

    # 时间范围
    start_date=datetime.datetime(2024, 7, 1),
    end_date=datetime.datetime(2025, 7, 1),

    # 筛选条件
    filters=[(basic_filter, {
        'price_range': {'current': [0.5, 3]},  # 当前价格在0.5-3元
        'min_av': 10000,                       # 平均成交量>1万
        'vol_period': 3                        # 成交量统计周期3个月
    })],

    # 买入窗口：选股信号触发后，取次日和第三日的最低价作为买入价
    buy_window=2,

    # 运行周期：买入后观察21个交易日（约1个月）的表现
    run_period=21,

    # 去重机制：同一股票在21天内只记录一次（避免重复计数）
    remove_duplicates=True,

    # 标签目标：使用收盘价计算涨幅（而非最高价或K线实体）
    label_obj='close',

    # 涨幅阈值
    chg_true=3,   # 涨幅>=3倍则标记为 True（成功）
    chg_false=0   # 涨幅<0（下跌）则标记为 False（失败）
    # 涨幅在[0, 3)之间的记录会被丢弃（返回 None）
)
```

---

## 三、关键机制详解

### 3.1 筛选过滤器 (basic_filter)

**位置**: `filters.py:55-102`

**作用**: 对每只股票的每一个交易日进行初步筛选，满足条件的才进入标签计算环节。

**过滤条件**:

1. **价格范围检查**
   - 支持三个位置的价格检查：`left`（前一日）、`current`（当日）、`right`（次日）
   - quick_boom 只限制当前价格在 0.5-3 元区间
   - 支持相对表达式（如 `'0.5*left'` 表示前一日价格的50%）

2. **成交量检查**
   - `min_av`: 平均成交量阈值（10000表示1万股/手）
   - `vol_period`: 统计周期（3表示过去3个月=63个交易日）
   - 计算方式：取过去63个交易日的滚动平均成交量
   - 前一日的平均成交量必须 ≥ 10000

**实现逻辑**:
```python
# 1. 边界检查：position 必须在 [1, len(df)-2] 范围内
if position <= 0 or position >= len(df) - 1:
    return False

# 2. 价格检查：提取三个位置的价格并与配置比对
prices = {
    'left': df.close.iloc[position - 1],
    'current': df.close.iloc[position],
    'right': df.close.iloc[position + 1]
}

# 3. 成交量检查：使用滚动窗口计算平均值
if 'av_3' in df.columns:
    av = df['av_3']  # 如果数据已预计算，直接使用
else:
    av = df.volume.rolling(window=3 * 21).mean()  # 否则实时计算

if av.iloc[position - 1] < 10000:
    return False
```

---

### 3.2 标签生成逻辑 (classify_df)

**位置**: `Picker.py:245-332`

**作用**: 通过过滤器的股票，模拟买入并计算后续涨幅，返回标签结果。

**关键步骤**:

#### Step 1: 确定买入价格
```python
# 买入窗口：position+1 到 position+buy_window（含）
# quick_boom 中 buy_window=2，即次日和第三日
chance_window = df.close.iloc[position + 1 : position + 3]

# 选择窗口内的最低价作为买入价（理想买入）
buy_price = chance_window.min()
buy_idx = chance_window.idxmin()
buy_position = df.index.get_loc(buy_idx)  # 记录实际买入日期的索引
```

**示例**:
```
信号触发日: 2024-07-01 (position)
次日:       2024-07-02 (position+1, close=2.00)
第三日:     2024-07-03 (position+2, close=1.80)  ← 最低价，买入价=1.80
```

#### Step 2: 计算运行期内最高涨幅
```python
# 运行窗口：买入后的第2天到第21天（共20个交易日）
# 买入当天是 buy_position，因此窗口是 buy_position+1 到 buy_position+21
run_window = df.close.iloc[buy_position + 1 : buy_position + 21]

# 找到窗口内收盘价的最高点
max_price = run_window.max()

# 计算涨幅
max_increase = max_price / buy_price  # 例如: 5.40 / 1.80 = 3.0 (涨3倍)
```

**示例时间线**:
```
买入日:     2024-07-03 (buy_position)
观察期:     2024-07-04 ~ 2024-07-31 (共21个交易日)
最高价:     2024-07-20, close=5.40
涨幅:       5.40 / 1.80 = 3.0
```

#### Step 3: 标签判定
```python
if max_increase < chg_false:  # 涨幅 < 0
    return False  # 失败案例
if max_increase > chg_true:   # 涨幅 > 3
    return True   # 成功案例
return None  # 涨幅在 [0, 3) 之间，丢弃该记录
```

**quick_boom 标签分类**:
- `True`: 涨幅 ≥ 3倍（300%）
- `False`: 涨幅 < 0（下跌）
- `None`: 涨幅在 [0, 3) 之间（被丢弃，不计入统计）

---

### 3.3 去重机制 (remove_duplicates)

**位置**: `Picker.py:176-201`

**作用**: 防止同一只股票在短期内被重复选中，导致统计数据失真。

**实现原理**:
```python
# 维护一个字典，记录每只股票最后一次被选中的日期
success_history = {}  # {股票名: 最后成功日期}

# 每个交易日开始前，构建跳过集合
window_start = current_date - pd.Timedelta(days=21)
skip_set = {
    stock_name
    for stock_name, last_date in success_history.items()
    if window_start <= last_date < current_date  # 过去21天内有记录
}

# 筛选时跳过这些股票
for stock_file, status in original_results:
    if stock_file not in skip_set:
        results.append((stock_file, status))
```

**示例**:
```
日期        股票A  操作
2024-07-01  ✓     通过筛选，标记为True
2024-07-05  ✗     在skip_set中，跳过
2024-07-15  ✗     在skip_set中，跳过
2024-07-23  ✓     距离上次>21天，允许再次选中
```

---

### 3.4 结果输出

**文件命名格式**:
```
grow_3times_1month_{success_rate}_{total_num}_{success_num}.txt
```

**示例**: `grow_3times_1month_45_1000_450.txt`
- 成功率: 45%
- 总样本: 1000
- 成功样本: 450

**内容格式** (每行):
```csv
日期,股票代码,标签
2024-07-01,600000,True
2024-07-02,000001,False
```

---

## 四、策略特点与优缺点

### 4.1 优点

1. **明确的风险收益比**
   - 目标明确：3倍涨幅
   - 止损隐含：跌破买入价（涨幅<0）标记为失败

2. **理想化买入假设**
   - 使用2天窗口内的最低价，避免了"必须在信号当天买入"的限制
   - 更贴近实际操作（盘中可能有更好的买点）

3. **去重机制**
   - 避免同一股票在21天内重复计数
   - 统计数据更真实反映策略表现

4. **灵活的筛选器架构**
   - `filters` 列表可组合多个过滤器
   - 每个过滤器独立开发和测试

### 4.2 缺点/局限性

1. **丢弃中等涨幅样本**
   - 涨幅在 [0, 3) 的样本被丢弃（返回 None）
   - 可能遗失有用的信息（如1-2倍涨幅也是盈利）

2. **无回撤控制**
   - 虽然有 `drawdown_limit` 参数，但 quick_boom 中未启用
   - 可能选中"高位大涨后又回落"的股票

3. **低价股风险**
   - 0.5-3元的价格区间多为ST股、亏损股
   - 存在退市风险、基本面恶化风险

4. **历史数据拟合**
   - 策略基于2024-2025年的历史数据
   - 未来市场环境变化可能导致策略失效

5. **成交量阈值固定**
   - `min_av=10000` 对所有股票一视同仁
   - 未考虑行业、市值差异

---

## 五、与其他配置的对比

| 配置名            | 目标涨幅 | 观察期 | 价格范围  | 去重 |
|-------------------|----------|--------|-----------|------|
| **quick_boom**    | 3倍      | 21天   | 0.5-3元   | ✓    |
| boom_yesterday    | 1.3倍    | 2天    | 无限制    | ✓    |
| jump_bar          | 1.5倍    | 63天   | 无限制    | ✗    |
| gap_up_stable     | 1.4倍    | 63天   | 无限制    | ✗    |

**quick_boom 的独特性**:
- **最激进**: 目标涨幅3倍（其他配置多为1.3-1.5倍）
- **最聚焦**: 只筛选低价股（0.5-3元）
- **最短期**: 观察期仅21天（其他配置多为63天）

---

## 六、代码关键位置索引

1. **配置定义**: `picker_configs.py:30-50`
2. **主入口**: `Picker.py:433-442`
3. **筛选逻辑**: `Picker.py:398-411` (iterate_stocks)
4. **标签计算**: `Picker.py:245-332` (classify_df)
5. **去重机制**: `Picker.py:176-201` (pick方法中)
6. **成交量过滤器**: `filters.py:55-102` (basic_filter)

---

## 七、使用方式

### 运行命令
```python
# 在 Picker.py 中
if __name__ == "__main__":
    picker = Picker(**quick_boom)
    picker.pick()
```

### 输出示例
```
start picking
iterating dates: 100%|██████████| 365/365
picked 1000 stocks, success: 450, success rate: 0.45
结果已保存到 ext_file/stock_lists/grow_3times_1month_45_1000_450.txt
总耗时: 0:12:34
```

---

## 八、后续优化建议

1. **保留中等涨幅样本**
   - 修改标签逻辑，将 [0, chg_true) 的样本标记为中性标签
   - 用于训练多分类模型

2. **增加回撤控制**
   - 启用 `drawdown_limit` 参数（如0.9）
   - 排除"涨后又跌"的股票

3. **动态成交量阈值**
   - 根据股票市值、行业调整 `min_av`
   - 避免"一刀切"的硬编码阈值

4. **多策略组合**
   - 结合 `boom_yesterday`（短期快涨）和 `gap_up_stable`（缺口稳定）
   - 降低单一策略失效的风险

---

## 附录：参数速查表

| 参数名              | 类型     | quick_boom取值       | 说明                                   |
|---------------------|----------|----------------------|----------------------------------------|
| data_root           | str      | datasets/process_pkls| 股票数据目录                           |
| output_path         | str      | ext_file/stock_lists/| 结果输出目录                           |
| start_date          | datetime | 2024-07-01           | 回测起始日期                           |
| end_date            | datetime | 2025-07-01           | 回测结束日期                           |
| filters             | list     | [(basic_filter, {})] | 筛选条件列表                           |
| buy_window          | int      | 2                    | 买入窗口天数（>=2）                    |
| run_period          | int      | 21                   | 观察期天数（>=2）                      |
| remove_duplicates   | bool     | True                 | 是否启用去重机制                       |
| label_obj           | str      | 'close'              | 标签目标（'close'/'high'/'body'）      |
| chg_true            | float    | 3                    | 成功标签阈值（涨幅>=3倍）              |
| chg_false           | float    | 0                    | 失败标签阈值（涨幅<0）                 |
| drawdown_limit      | float    | None                 | 回撤限制（未启用）                     |
| result_prefix       | str      | grow_3times_1month   | 结果文件前缀                           |
