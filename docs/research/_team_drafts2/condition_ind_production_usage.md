# Condition_Ind 在 new_trade 项目中的真实生产使用

> 实证来源：`new_trade/screener/state_inds/{base.py, functional_ind.py, meta_ind.py}` 与 `scrs_train/scr_rv/define_scr.py`、`scrs_train/define_scr/train_before_hole.py`。本报告以 `scr_rv`（活的生产链）为主，参考 `define_scr/`（旧但保留了关键设计意图的代码）作为侧证。

## 1. 关键事实先于结论

- `Condition_Ind` 在 `base.py` 只有一个 line `('valid',)` 和两个参数 `conds, min_score`。它本身**不定义信号**——`next()` 末尾写的是 `self.lines.valid[0] = self.lines.signal[0]`（base.py:51, 55），而 `signal` 这条 line 必须由子类定义。换言之 `Condition_Ind` 是一个"valid = signal AND (conds 满足条件)"的过滤壳。
- `Result_ind` 这个被多处 import 的类（`scrs_train/define_scr/train_before_hole.py:2`、`scrs/wide_scr.py:4` 等）实际**已不存在**——其源文件 `screener/state_inds/Condition_ind.py` 已被删除，只剩 `base.py:41` 一句注释 `# self.__class__.__name__=='Result_ind'` 作为遗迹。所有依赖 `Condition_ind` 的模块（`scrs/`、`scrs_train/define_scr/`、`scrs_train/scrs/`、`scrs_train/scr_buy/`）目前均无法 import，是历史代码。
- 唯一的 active 生产链是 `scrs_train/scr_rv/`，它通过 `scr.py:2` 直接 import `define_scr` 并在 `SCR(bt.Analyzer)` 里组装。

## 2. base.py Condition_Ind 在 production 的实际使用范围

在 `scr_rv/define_scr.py` 里，`Condition_Ind` 的 `conds=` 机制只被使用了两处：

```python
# scr_rv/define_scr.py:44-49 —— Empty_Ind 当 AND-门
self.bounce = Empty_Ind(name='bounce',
                        conds=[
                            {'ind': self.narrow},
                            {'ind': self.ma_bull},
                        ])

# scr_rv/define_scr.py:54-63 —— Vol_cond 触发当天再叠加历史 bounce
self.rv = Vol_cond(rv_date=rv_date, period=..., vol_threshold=..., ...,
                   conds=[
                       {'ind': self.bounce, 'exp': self.p.bounce_exp5*5, 'causal': True},
                       {'ind': self.rsi_range, 'causal': True},
                   ])
```

参数使用情况（统计自 scr_rv 与 define_scr 全部调用点）：

| 参数 | scr_rv 使用？ | define_scr/（历史）使用？ |
|---|---|---|
| `exp`（多少天内满足都算） | 是（`bounce_exp5*5`） | 是 |
| `must`（默认 True） | 全部默认，未显式覆盖 | 一处显式 `must:True` |
| `causal`（看 `[-1]` 而非 `[0]`） | 是（`bounce`、`rsi_range`、`buy_point`） | 主流写法是 `causal:False` |
| `min_score` | **从未使用**（已注释掉 `# min_score=3`） | 同 |
| `keep / keep_prop` | **不存在**（base.py 没这个字段） | 频繁出现 `'keep': 40, 'keep_prop': 0.8` |
| `relaxed` | 不存在 | 出现于 `train_before_hole.py:51` |
| `exp_cond` | 不存在 | 出现于 `train_before_hole.py:68`：`{'ind': self.flat_conv, 'exp': self.p.flat_exp_days, 'exp_cond': self.rsi}` |

**结论**：当前 `base.py:Condition_Ind` 是**已删除的旧实现的精简版**。旧 `Result_ind`（在被删的 `Condition_ind.py` 里）支持 `keep`（条件需连续满足 N 天）、`keep_prop`（满足比例）、`relaxed`（弱化匹配）、`exp_cond`（exp 时间窗内还要叠加另一条件）。这些字段揭示出真实需求：**纯"曾经满足"语义不够，需要"持续满足""比例满足""到期前还要再卡一道"**。新版 `base.py` 把这些都砍掉了，scr_rv 也只用 `exp + causal` 就够，说明项目的实际需求收敛回了一个非常窄的子集。

## 3. functional_ind.py 的"原子条件 indicator"分类

按设计模式可分三类：

**A. 纯组合器/比较器（无内部状态）**
- `Compare`（`meta_ind.py:30`）：把任意 indicator 与阈值比较，输出 `signal = indicator * If(cond, 1, 0)`。靠 backtrader lazy-eval 表达式实现。
- `Empty_Ind`（`meta_ind.py:116`）：`signal=True` 常量。**专门用作 AND-门**——把 `conds` 都填进它，依靠 `Condition_Ind` 父类的 `must` 默认 True 实现"全部满足才 valid"。
- `Duration`（`meta_ind.py:64`）：在 N 天滑窗内统计 input 非零比例，超过阈值则 signal=1。这就是被 `base.py` 砍掉的 `keep/keep_prop` 语义的独立化产物。
- `MA_CrossOver`、`Simple_MA_BullishAlign`：纯结构判断，每根 K 线独立。

**B. 单步形态判断（有外部依赖但无显式状态机）**
- `Narrow_bandwidth` / `Narrow_realtime`（functional_ind.py:367, 433）：基于 `max_period / min_period` 数据线计算 `range_ratio` 和 `bottom_ratio`，多周期循环，找到任一满足则 signal=period。"本根 K 线 + 历史窗口"，无跨 bar 状态。
- `Vol_cond`（functional_ind.py:485）：`rv = volume / avgvol(-1)`，再 `bt.And` 阈值化。同样用 backtrader 表达式 lazy 计算，唯一的 next() 工作只是按 `rv_date` 控制是否输出。

**C. 内部状态机（重点）**
- `BreakoutPullbackEntry`（functional_ind.py:8-318）：典型的多阶段状态机，状态 ∈ `{none, breakout, pullback, pending_stable, end}`，每个阶段有"门槛分数"`*_threshold`。`local_next()` 每根 K 线根据当前状态执行不同分支，记录 `breakout_time / before_break / max_break_price / min_pullback_price / breakout_vol / break_vol_avg` 等历史变量，最终在 `state=='end' and ever_stable` 时把 `signal[0]=True`（functional_ind.py:80-83）。
- `PriceStability`（functional_ind.py:321-364）：状态机精简版。`triggered` 标志 + 跨 bar 持有 `last_volume_point / last_ma_price / valid`。当 `days_after_volume == stability_days` 时一次性输出 `stable[0]`。

**关键观察**：B 类用 `bt.And/bt.If` 等 lazy-eval 表达式，本质是**指标级 DSL**——把"K 线 + 滚动统计"压缩成一个新的时间序列。C 类则把无法用 lazy-eval 表达的**有序、跨阶段、有记忆的形态**封装在 Python `next()` 里，以"成员变量"形式持有跨 bar 状态。

更关键的是：**C 类的形态判断完全不走 `Condition_Ind.conds`**。`BreakoutPullbackEntry.__init__` 调 `super().__init__()` 时不传 conds（functional_ind.py:51-52）。它只是借用 Condition_Ind 这个壳让 `next()` → `local_next()` 的钩子生效，并让自己的 `signal` line 出现在 base.py 的 `valid = signal` 这一句里。换言之，**真正的形态在 local_next 状态机里写 Python，conds 机制并未参与**。

## 4. define_scr.py 的真实组装方式

scr_rv 的策略链（functional_ind.py + meta_ind.py + scr.py）是这样的：

```
narrow      ─┐
ma_bull     ─┤ Empty_Ind(conds=[narrow, ma_bull])  →  bounce
                                  │
rsi_range  ─────────────────────  │
                                  ▼
            Vol_cond(conds=[bounce(exp=5, causal=True),
                            rsi_range(causal=True)])  →  rv
                                  │
                                  ▼
            BreakoutPullbackEntry(rv=rv, ...)  →  entry  → 真正的 buy signal
```

- **嵌套深度：3 层**（Empty_Ind → Vol_cond → BreakoutPullbackEntry），并且**最深的一层不靠 conds 嵌套**——而是靠 `BreakoutPullbackEntry` 直接接收 `rv=self.rv` 作为构造参数，在 `__init__` 里 `self.volume_signal = rv.lines.valid`（functional_ind.py:55）。`BreakoutPullbackEntry` 只是把 `rv.valid` 当输入信号读取，不再走 conds。
- **每条策略都需要 Python 编程组合**：`init_indicators` 是手写函数，不是声明式配置。`inds_params` 字典只是参数表（define_scr.py:7-33），所有的拓扑结构（哪个 ind 接谁）都写死在 `init_indicators` 里。
- **参数化程度：高度被搜索过的"窄数值参数"**。`inds_params` 里所有名字都带数字（`ma1_period3=3`、`bounce_exp5=1`、`rsi_high10=7`），命名约定是 `<语义><基数>=<乘数>`，使用时 `self.p.ma1_period3*3`，意味着这些参数被某个搜索过程（应该是 `optimize.py`/`optnew.py`）以整数倍数空间扫过。换句话说，**策略结构固定，参数被网格/贝叶斯搜索**。

## 5. 对两个判断题的回答

**「Condition_Ind 是一个完整的形态描述 DSL」—— 错觉。**

`Condition_Ind.conds` 提供的是"在 N 天内是否曾满足某条件"的 AND/OR/带分数的合成器，仅适合扁平的、独立的、无序的条件叠加。它**无法表达**：放量 → 回踩 → 企稳这种**有时序依赖、有阶段门槛、需要跨 bar 记忆中间值（如 max_break_price）**的复合形态。一旦真要写"形态"，生产代码立刻跳出 conds 机制，回到 Python 状态机（BreakoutPullbackEntry / PriceStability）。所以"形态描述 DSL"是 base.py 的接口给人的假象，**真正的形态描述全部分散在每个子类的 `local_next()` 里**。

**「Condition_Ind 鼓励嵌套」—— 边缘特性，不是核心。**

scr_rv 全链总共只出现了 2 处 conds（Empty_Ind 一层、Vol_cond 一层），最终的核心形态 BreakoutPullbackEntry 根本不通过 conds 嵌套，而是通过构造参数 `rv=self.rv` 直接持有上游 indicator 的 `lines.valid`。历史代码（`train_before_hole.py`）确实嵌套更多（Result_ind 嵌套 Vol_cond 嵌套 flat_conv），但即使在那时也不过 2-3 层，并且上层的 Result_ind 几乎只做"信号转发"（`conds=[{'ind': self.buy_point, 'causal': False}]`，等价于 pass-through）。

更准确的描述是：**Condition_Ind 是一个被故意保持薄的"信号挂载点"**——它的两个真实价值是 (1) 提供 `next()` 之上的 `local_next()` 钩子，(2) 让一个 indicator 输出 `valid` 时可以叠加几个轻量副条件（曾满足、必须、带因果延迟）。形态描述、状态机、阶段门槛 —— 这些都是子类自己用 Python 写的。

## 6. 设计意图小结

1. base.py 的 `Condition_Ind` 是**接口骨架**，不是 DSL；它负责"挂钩 + 副条件过滤"。
2. 真正的"形态描述"在 functional_ind.py 子类的 `local_next()` 里，用**显式状态机 + 阶段评分**实现。这种写法的代价是每写一个新形态都要写一坨 Python 状态机，但好处是表达力不被 DSL 限制。
3. 历史上 `Result_ind` 引入过 `keep / keep_prop / relaxed / exp_cond` 等扩展字段，证明用户曾试图把"持续 N 天""比例满足""到期还要叠加另一条件"等需求塞进 DSL；但当前 base.py 已**主动删除这些字段并删除 Result_ind 整个文件**，需求被分流到独立 indicator（如 `Duration` 处理 keep/keep_prop）。这个回退说明：把表达力堆在 conds 字典里会让接口越来越复杂，**项目最终选择"薄 DSL + 厚状态机子类"**这条路。
4. 策略组装是命令式 Python（`init_indicators` 函数），不是声明式 YAML/JSON。可参数化的只是数字（被外部搜索器扫描），结构是写死的。
