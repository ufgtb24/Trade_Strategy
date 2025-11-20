# 技术分析模块可视化方案

**创建日期**: 2025-11-24
**状态**: 调研完成，待实施

---

## 一、需求背景

用户希望为已完成的技术分析模块（模块02）添加可视化功能，用于：
- 直观展示突破检测结果
- 调整检测器参数（window, exceed_threshold, peak_merge_threshold）
- 分析高质量突破案例
- 优化评分系统权重

---

## 二、现状分析

### 2.1 已有基础

**技术分析模块**:
- 位置: `BreakthroughStrategy/analysis/`
- 核心功能: 增量式峰值检测、多峰值突破、质量评分
- 测试数据: AAPL.pkl (1255天，2020-10-19 ~ 2024-10-24)
- 测试结果: 59个突破，10个多峰值突破

**测试脚本**:
- `test_integrated_system.py`: 文本输出，无可视化
- `test_quality_improvement.py`: 评分对比测试

**环境**:
- 已安装: matplotlib 3.8.2
- 需安装: mplfinance（静态图），plotly（交互式，可选）

### 2.2 核心参数

需要可视化调整的参数：

```python
# BreakthroughDetector 参数
window = 5                    # 峰值识别窗口（建议范围: 3-10）
exceed_threshold = 0.005      # 突破确认阈值（建议范围: 0.003-0.01）
peak_merge_threshold = 0.03   # 峰值共存阈值（建议范围: 0.02-0.05）

# QualityScorer 权重参数（10+个）
# 峰值评分权重
peak_weight_volume = 0.25
peak_weight_candle = 0.20
peak_weight_suppression = 0.25
# ... 等等
```

**参数影响**:
- `window` ↑ → 峰值数量↓，阻力位更强
- `exceed_threshold` ↑ → 突破确认更严格，假突破↓
- `peak_merge_threshold` ↑ → 峰值共存↑，多峰值突破↑

---

## 三、技术方案

### 3.1 推荐方案（分阶段实施）

**阶段一：核心静态可视化（优先）**
- 技术栈: `matplotlib` + `mplfinance`
- 优势: 利用已有环境，快速验证效果
- 适用场景: 参数对比、案例分析、报告生成
- 安装需求: `mplfinance`（轻量级）

**阶段二：交互式调参（可选）**
- 技术栈: `plotly` + `ipywidgets`/`dash`
- 优势: 实时参数调整、交互探索
- 适用场景: 参数优化、策略演示
- 安装需求: `plotly`

### 3.2 可视化库对比

| 库 | 优势 | 劣势 | 推荐度 |
|---|---|---|---|
| **matplotlib + mplfinance** | 已安装、稳定、K线简单 | 交互性弱 | ⭐⭐⭐⭐ |
| **plotly** | 交互性强、内置金融图表 | 需安装、学习曲线 | ⭐⭐⭐⭐⭐ |

---

## 四、实施计划

### 4.1 文件结构设计

```
BreakthroughStrategy/analysis/
├── visualization/                    # 新建可视化模块
│   ├── __init__.py
│   ├── static_plotter.py            # 静态图（matplotlib）
│   ├── interactive_plotter.py       # 交互式图（plotly，可选）
│   └── utils.py                     # 辅助函数
│
├── test/
│   ├── test_integrated_system.py    # 现有测试
│   └── visual_demo.py               # 新建：可视化演示脚本
│
└── scripts/                          # 新建：独立脚本目录
    ├── parameter_tuning.py          # 参数调整工具
    ├── case_analysis.py             # 案例分析工具
    └── batch_comparison.py          # 批量对比工具
```

### 4.2 核心类设计

**BreakthroughPlotter（静态图绘制器）**

```python
class BreakthroughPlotter:
    """突破检测可视化工具（基于 matplotlib + mplfinance）"""

    def plot_full_analysis(self, df, breakthroughs, detector,
                          title=None, save_path=None):
        """
        绘制完整分析图

        包含:
        - K线图 + 峰值标注 + 突破标注
        - 成交量图（下方）
        - 统计信息面板
        """

    def plot_breakout_detail(self, df, breakthrough,
                            context_days=50, save_path=None):
        """
        绘制单个突破的详细视图

        包含:
        - 局部K线图（突破前后N天）
        - 被突破峰值详细信息
        - 阻力区高亮
        - 质量评分分解
        """

    def plot_parameter_comparison(self, df, param_results,
                                 param_name, param_values):
        """
        绘制参数对比图

        包含:
        - 多子图布局（每个参数值一张图）
        - 突破数量统计
        - 质量分布对比
        """

    def plot_multi_peak_cases(self, df, multi_peak_breakthroughs,
                             top_n=5):
        """
        绘制多峰值突破案例集

        包含:
        - 网格布局（2x3）
        - 每个案例的局部图
        - 密集度和质量信息
        """
```

### 4.3 核心可视化元素

1. **K线图**（基础）
   - OHLC数据
   - 时间范围可调整

2. **峰值标注**
   - 活跃峰值：三角形标记
   - 已突破峰值：灰色标记
   - 颜色编码：红（高质量≥60）、橙（中等40-60）、灰（低质量<40）

3. **突破点标注**
   - 突破位置：星形标记
   - 多峰值突破：大星形
   - 颜色编码：同峰值质量

4. **阻力区可视化**
   - 密集峰值区域：半透明矩形高亮
   - 价格范围标注

5. **成交量图**
   - 下方子图
   - 放量突破高亮

6. **统计信息面板**
   - 突破总数
   - 平均质量
   - 多峰值数量

---

## 五、关键场景

### 5.1 场景1：Top突破可视化

**目标**: 展示质量评分最高的5个突破

**图表内容**:
- K线图 + 所有峰值 + Top5突破标注
- 成交量图
- 统计面板

### 5.2 场景2：多峰值突破案例

**目标**: 展示一次突破多个峰值的详细信息

**图表内容**:
- 局部K线图（突破前后50天）
- 被突破的3-5个峰值标注
- 阻力区高亮（密集度<3%）
- 质量评分分解

### 5.3 场景3：参数对比

**目标**: 对比不同window值的效果

**图表布局**: 1×4网格（4个参数值）

**对比内容**:
- 突破数量
- 平均质量
- Top5平均分

**示例结果**:
```
┌────────┬──────────┬──────────┬──────────┐
│ Metric │ window=3 │ window=5 │ window=7 │
├────────┼──────────┼──────────┼──────────┤
│ 突破数 │ 72       │ 59       │ 45       │
│ 平均分 │ 21.3     │ 23.2     │ 25.8     │
│ Top5   │ 18.5     │ 21.0     │ 24.3     │
└────────┴──────────┴──────────┴──────────┘

结论：window↑ → 突破数↓，质量↑
推荐：window=7（平衡识别率和质量）
```

---

## 六、参数调整工作流

### 工作流1：快速参数对比（静态图）

```
步骤：
1. 运行 scripts/parameter_tuning.py
2. 设置参数范围：window=[3,5,7,10]
3. 生成对比图：4张子图 + 统计表
4. 分析结果，选择最优参数

输出：
- PNG图片：param_comparison_window.png
- 统计CSV：param_stats.csv
```

### 工作流2：交互式探索（Jupyter，可选）

```
步骤：
1. 在Jupyter Notebook中运行
2. 使用滑块调整参数
3. 实时查看K线图变化
4. 点击突破查看详情
5. 记录最优参数组合

输出：
- 交互式HTML（可保存）
- 参数配置JSON
```

### 工作流3：案例深度分析（静态图）

```
步骤：
1. 运行 scripts/case_analysis.py
2. 选择分析目标：
   - Top N质量突破
   - 多峰值突破案例
   - 特定日期范围
3. 生成详细分析报告

输出：
- 多页PDF报告
- 每个案例的详细图
```

---

## 七、实施阶段

### 阶段一：核心静态可视化（1-2天）

**优先级**: 高

**内容**:
1. 安装 `mplfinance`
2. 实现 `BreakthroughPlotter` 类：
   - `plot_full_analysis()`
   - `plot_breakout_detail()`
3. 创建 `scripts/visual_demo.py` 基础演示

**交付物**:
- 基础可视化功能
- 演示脚本
- 示例PNG输出

### 阶段二：参数调整工具（1天）

**优先级**: 中

**内容**:
1. 实现 `plot_parameter_comparison()`
2. 创建 `scripts/parameter_tuning.py`
3. 生成对比报告和统计CSV

**交付物**:
- 参数调整工作流
- 对比图和统计表

### 阶段三：交互式探索（2-3天，可选）

**优先级**: 低

**内容**:
1. 安装 `plotly`
2. 实现 `InteractiveBreakthroughExplorer`
3. 创建Jupyter Notebook演示

**交付物**:
- 交互式仪表板
- 实时参数调整界面

---

## 八、预期效果

### 输出1：全局分析图

```
文件：output/AAPL_full_analysis.png
尺寸：16×10英寸（高清）
内容：
- 上部：K线图（1255根）+ 59个突破标记 + 活跃峰值
- 中部：成交量图（放量突破高亮）
- 下部：统计信息（突破数、平均分、多峰值数）
```

### 输出2：多峰值案例集

```
文件：output/multi_peak_cases.png
尺寸：16×12英寸
布局：2×3网格（6个案例）
每个子图：
- 局部K线（突破前后50天）
- 被突破峰值标注（3-5个）
- 阻力区高亮
- 质量评分和密集度
```

### 输出3：参数对比报告

```
文件：output/param_comparison_window.png
尺寸：20×10英寸
布局：1×4网格（4个参数值）
附带统计表CSV
```

---

## 九、依赖安装

### 最小依赖（阶段一）

```bash
# 使用配置的镜像源
pip install mplfinance
```

### 完整依赖（阶段三）

```bash
pip install mplfinance plotly ipywidgets
```

---

## 十、风险与注意事项

### 10.1 性能风险

**问题**: 1255天K线 + 59个突破，图表可能拥挤

**解决**: 提供时间范围过滤，支持局部绘图

### 10.2 数据格式兼容性

**问题**: mplfinance对DataFrame格式有要求（必须是DatetimeIndex）

**解决**: 在绘图前转换格式，或直接使用matplotlib绘制K线

### 10.3 参数调整实时性

**问题**: 静态图无法实时调参，需要重新运行

**解决**: 阶段一使用批量对比，阶段三提供交互式工具

---

## 十一、核心代码示例

### 示例1：基础绘图函数

```python
# visualization/static_plotter.py

import matplotlib.pyplot as plt
import mplfinance as mpf

class BreakthroughPlotter:
    def __init__(self, style='charles', figsize=(16, 10)):
        self.style = style
        self.figsize = figsize

    def plot_full_analysis(self, df, breakthroughs, detector,
                          title=None, save_path=None):
        """绘制完整分析图"""

        # 创建图表布局
        fig = plt.figure(figsize=self.figsize)
        gs = fig.add_gridspec(3, 1, height_ratios=[3, 1, 0.3], hspace=0.1)
        ax_candle = fig.add_subplot(gs[0])
        ax_volume = fig.add_subplot(gs[1], sharex=ax_candle)
        ax_info = fig.add_subplot(gs[2])

        # 1. K线图（使用mplfinance）
        mc = mpf.make_marketcolors(up='r', down='g', edge='inherit',
                                   wick='inherit', volume='inherit')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='-',
                              gridcolor='lightgray')

        mpf.plot(df, type='candle', style=s, ax=ax_candle,
                volume=ax_volume, show_nontrading=False)

        # 2. 添加峰值标注
        self._add_peak_markers(ax_candle, detector.active_peaks, df)

        # 3. 添加突破标注
        self._add_breakout_markers(ax_candle, breakthroughs, df)

        # 4. 添加阻力区高亮
        self._add_resistance_zones(ax_candle, breakthroughs, df)

        # 5. 统计信息面板
        self._add_info_panel(ax_info, breakthroughs)

        # 6. 保存或显示
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        else:
            plt.show()

        plt.close()

    def _get_quality_color(self, score):
        """根据质量分数返回颜色"""
        if score is None:
            return 'gray'
        elif score >= 60:
            return 'red'
        elif score >= 40:
            return 'orange'
        else:
            return 'gray'
```

### 示例2：参数调整脚本

```python
# scripts/parameter_tuning.py

import sys
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy')

import pickle
from BreakthroughStrategy.analysis import (
    BreakthroughDetector, FeatureCalculator, QualityScorer
)
from BreakthroughStrategy.analysis.visualization import BreakthroughPlotter

def main():
    # 配置参数（不使用parser，按用户要求）
    symbol = 'AAPL'
    data_path = '/home/yu/PycharmProjects/Trade_Strategy/datasets/process_pkls/AAPL.pkl'
    param_name = 'window'
    param_values = [3, 5, 7, 10]
    save_path = f'output/param_comparison_{param_name}.png'

    # 加载数据
    df = pickle.load(open(data_path, 'rb'))
    print(f'加载数据: {len(df)}天')

    # 测试不同参数
    results = {}
    for value in param_values:
        print(f'\n测试 {param_name}={value}...')

        detector = BreakthroughDetector(
            symbol=symbol,
            window=value if param_name == 'window' else 5,
            use_cache=False
        )

        breakout_infos = detector.batch_add_bars(df, return_breakouts=True)

        # 计算特征和评分
        feature_calc = FeatureCalculator()
        scorer = QualityScorer()

        breakthroughs = []
        for info in breakout_infos:
            for peak in info.broken_peaks:
                if peak.quality_score is None:
                    scorer.score_peak(peak)
            bt = feature_calc.enrich_breakthrough(df, info, symbol)
            breakthroughs.append(bt)

        scorer.score_breakthroughs_batch(breakthroughs)
        results[value] = (breakthroughs, detector)

        # 统计
        total = len(breakthroughs)
        avg_score = sum(b.quality_score for b in breakthroughs) / total if total > 0 else 0
        print(f'  突破数: {total}, 平均质量: {avg_score:.1f}')

    # 绘制对比图
    plotter = BreakthroughPlotter()
    plotter.plot_parameter_comparison(df, results, param_name, param_values)
    print(f'保存到: {save_path}')

if __name__ == '__main__':
    main()
```

---

## 十二、总结

### 核心推荐

1. **技术栈**: 优先使用 `matplotlib + mplfinance`（静态图）
2. **实施路径**: 分阶段实现，先静态后交互
3. **文件结构**: 新建 `visualization/` 模块 + `scripts/` 工具目录
4. **关键场景**: Top突破、多峰值案例、参数对比

### 实现优先级

1. ⭐⭐⭐ 全局分析图（`plot_full_analysis`）- 必须
2. ⭐⭐⭐ 突破详情图（`plot_breakout_detail`）- 必须
3. ⭐⭐ 参数对比图（`plot_parameter_comparison`）- 推荐
4. ⭐ 交互式仪表板（`InteractiveBreakthroughExplorer`）- 可选

### 下一步行动

等待用户确认后，开始实施阶段一：
1. 安装 `mplfinance`
2. 创建可视化模块结构
3. 实现核心绘图类
4. 创建演示脚本
5. 测试验证

---

**文档版本**: v1.0
**创建日期**: 2025-11-24
**状态**: 调研完成，待用户确认
