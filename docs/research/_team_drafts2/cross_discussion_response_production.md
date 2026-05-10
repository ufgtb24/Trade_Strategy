# Phase 2 交叉讨论回答（来自 production-usage-analyst）

> 基于实证文件：`new_trade/screener/state_inds/{base.py, functional_ind.py, meta_ind.py}`、`scrs_train/scr_rv/define_scr.py`、`scrs_train/define_scr/train_before_hole.py`。下文中的判断都以"production 真实代码长什么样"为锚点，不直接借用另两份草稿的论点。

---

## Q1. 状态机能否被 DataFrame 谓词代数取代?

**结论：BreakoutPullbackEntry 这种状态机，DataFrame 谓词代数能"功能等价地写出来"，但写出来的东西是退化版且大概率不是 production 真正在做的事。**

把 BreakoutPullbackEntry 拆开看（functional_ind.py:8-318），它做了三件谓词代数难做的事：

1. **跨阶段持有"具体数值变量"，不是布尔时序**：`self.before_break = self.data.close[-1]`、`self.max_break_price = max(...)`、`self.breakout_vol`、`self.break_vol_avg`（功能_ind.py:90-93、107-109）。这些值是**在状态进入 breakout 那一根 bar 锁定的**，后续阶段拿来与当根价格做比例运算。谓词代数的 `rolling/shift` 是固定 lookback 的，**没法表达"从某个事件触发起算的相对量"**——除非把它平铺成"对每根 bar 都计算 lookback=K 的比例并取最大"，这与"以触发 bar 为锚"语义不同（前者会把不该参与的窗口也算进来）。
2. **多分支的转移函数**：`pullback → pending_stable → pullback`（functional_ind.py:151-202）允许"企稳信号不稳定就回退到 pullback"。谓词代数的合成是**单调累积**的（`A & shift(B)`），无法表达"曾经达到过状态 X，但下一步条件不达就退回 X-1"。
3. **状态切换本身决定何时输出**：`signal[0]=True` 只在 `state=='end' and ever_stable` 那唯一一根 bar 输出（functional_ind.py:80-83、164-168、189-194）。这不是"窗口内任一根 X 满足"或"连续 K 根 X 满足"——这是"自动机首次到达接受态"。要用谓词代数模拟，要么对每根 bar 做 `groupby` 找事件起点+回放，要么写一个 Python `for` 循环逐根更新——后者就是状态机本身。

更关键的实证依据是：**production 代码刻意把这种形态从 conds DSL 里抽出来，单独写状态机**。`BreakoutPullbackEntry.__init__` 调 `super().__init__()` 不传任何 conds（functional_ind.py:51-52），等于完全放弃了 Condition_Ind 的合成机制；它只用 `Condition_Ind` 的 `next() → local_next()` 钩子。这是**项目自己的回退证据**：当形态有"先 X 后 Y、Y 不稳又退回 X、最后到达终态才输出"的语义时，conds 链表表达不了，只能写状态机。

谓词代数不是不能"勉强表达"——可以用 `cumsum + groupby + shift` 把每个潜在 breakout 起点切成事件，对事件级数据做 lookforward 验证。**但这不再是 vectorized 的廉价路径**，而是退化成"事件级标量化"。这条路其实就是 BO 框架已经在做的事（事件 row + lookforward label）。换句话说：

> **DataFrame 谓词代数 ≈ vectorized AND/OR/window 的世界**；
> **状态机 ≈ 在指定起点后逐根 bar 验证、可中途回退、首次达到终态才输出的世界**。
>
> 两者交集很大（B 类 indicator 全在交集），但 C 类内部状态机**不在交集**，是 indicator + next() 模型独有的。

improvement-researcher 把"BreakoutPullbackEntry 在 batch+滚动重算下等价"留给了一个括号说"除了 streaming 状态机一项"——我的实证印证这句话该被加粗：**production 真正不可替代的恰好就是这一项**。

---

## Q2. 上一团队 Stage 2 该不该被修订?

**应该被修订。把"ChainCondition"作为 Stage 2 的核心抽象，是建立在对 Condition_Ind 的过度浪漫想象之上。**

实证有三个支撑：

1. **production 中的 conds 链是退化的扁平 AND-门**。scr_rv/define_scr.py 总共两处使用 conds：Empty_Ind 当 AND-门 + Vol_cond 加两个 causal 副条件。`min_score` 从未启用（被注释 `# min_score=3`），`must` 全用默认 True，`exp` 只在一处出现（`bounce_exp5*5`）。整条链没有任何"链式合成才能解决"的语义复杂度。
2. **历史代码扩展过的字段已被主动删除**。`Result_ind` 整个文件 `Condition_ind.py` 已被删，`keep / keep_prop / relaxed / exp_cond` 全部消失，`keep/keep_prop` 的需求被分流到独立的 `Duration` indicator（meta_ind.py:64）。**这是"链式 DSL 越扩越复杂"被项目主动拒绝的证据**——把表达力堆在 cond 字典里被证明走不通。
3. **真正的语义 weight 在子类的 local_next() 里**。BreakoutPullbackEntry 不通过 conds 嵌套，而是通过构造参数 `rv=self.rv` 直接 wire 上游 indicator（functional_ind.py:55）。Condition_Ind 在这里只是 `next() → local_next()` 的钩子壳。

所以 Stage 2 的合理形态应当改写为两层并立：

- **底层**：DataFrame 谓词代数 + `@feature` 装饰器（improvement-researcher §2.2 的方案）覆盖 90% 的 vectorized 形态判定（B 类 indicator 全部归此）。
- **顶层**：少数无法 vectorized 的形态（C 类状态机：BreakoutPullbackEntry / PriceStability / Platform Formation）写成显式 Python 状态机类，输出**事件 row 上的标量**（参考 bo-vs-cind-comparator §4 的"分工边界"——状态机的产出包装成 BO 因子才进 mining）。

**ChainCondition 这个抽象层应当被砍掉**——它的"价值"原本是"把 Condition_Ind 的链式合成搬到 BO 行级"，但实证已证明 production 根本没在用这个链式合成的复杂用法。把 ChainCondition 留下只会复刻一个被项目自己抛弃过的设计弯路。如果保留，最多是作为 `compose_predicates(funcs, mode='all'|'any'|'count_at_least')` 这种 5 行的小工具，不应当作 Stage 2 的核心抽象。

---

## Q3. Platform-as-Event 在 production 风格下的具体形态

**"薄 conds + 厚 local_next 状态机"确实是 production 真实主流；这意味着 Platform-as-Event 在 production 风格下的实现路径是天然的，不需要 ChainCondition 作为载体。**

实证支撑：

functional_ind.py 里 11 个 `Condition_Ind` 子类的分布是清楚的：

| 类别 | 数量 | conds 用法 |
|---|---|---|
| 纯 lazy-eval 表达式（B 类）：Compare、Vol_cond、Narrow_bandwidth、MA_CrossOver、Simple_MA_BullishAlign | 6 | 全不传 conds |
| 显式状态机（C 类）：BreakoutPullbackEntry、PriceStability | 2 | 全不传 conds |
| 仅做 AND-门的薄壳：Empty_Ind | 1 | 是唯一传 conds 的子类 |
| 滑窗聚合 utility：Duration | 1 | 不传 conds |
| 输入端比较器：Compare（已计） | — | — |

**11 个子类里只有 Empty_Ind 这一个把"传 conds"作为存在意义**。其它都用 `super().__init__()` 不带 conds，把 Condition_Ind 当作"signal line + local_next 钩子"的壳来用。这就是题目里说的"薄 conds + 厚 local_next"——production 的真实主流就是这个形态。

按这个风格写 PlatformFormation 的形态会非常自然：

```python
class PlatformFormation(Condition_Ind):
    lines = ('signal', 'platform_start', 'platform_end')  # 子类自定义 signal line
    params = dict(
        bo_lookback=20,        # BO 必须在过去 N 根内出现过
        confirm_bars=10,       # 接下来 K 根需稳定
        range_eps=0.03,        # 高低点波幅阈值
    )

    def __init__(self, bo_signal):
        super().__init__()      # 不传 conds，仅用钩子
        self.bo_signal = bo_signal       # backtrader line
        self.state = 'waiting'           # waiting → confirming → end
        self.bo_anchor = None            # 锚点 bar
        self.bo_anchor_close = None      # 锚点价格

    def local_next(self):
        self.lines.signal[0] = False
        if self.state == 'waiting':
            if self.bo_signal[0]:
                self.bo_anchor = len(self)
                self.bo_anchor_close = self.data.close[0]
                self.state = 'confirming'
        elif self.state == 'confirming':
            elapsed = len(self) - self.bo_anchor
            if elapsed >= self.p.confirm_bars:
                # 检查这段 confirm 期间高低波幅
                highs = self.data.high.get(size=self.p.confirm_bars)
                lows  = self.data.low.get(size=self.p.confirm_bars)
                if (max(highs) - min(lows)) / self.bo_anchor_close < self.p.range_eps:
                    self.lines.signal[0] = True
                self.state = 'end'
            elif <价格逃逸 confirm 区间>:
                self.state = 'waiting'  # 失败回退
```

可以挂 1-2 个轻量副条件（用 conds 字典，发挥它擅长的扁平 AND-门用法）：

```python
self.platform = PlatformFormation(
    bo_signal=self.rv.lines.valid,
    conds=[
        {'ind': self.ma40_flat},   # 平台期 MA40 也得平
        {'ind': self.vol_dry,      # 平台期成交量缩
         'window': 10, 'mode': 'ratio_at_least'},  # 假设接受 improvement A1
    ],
)
```

这种形态有三个好处直接来自 production 实证：

1. **状态机+锚点价格表达力是 conds 链给不了的**。`bo_anchor_close` 这种"在锚点 bar 锁定的具体数值"无法在 conds 字典里表达；BreakoutPullbackEntry 已经验证这条路。
2. **副条件用 conds 是 Condition_Ind 真正胜任的窄用法**。`ma40_flat` / `vol_dry` 是 vectorized 标量谓词，扁平 AND 即可，不需要 ChainCondition 那种"嵌套合成"的能力。production 中 Empty_Ind+Vol_cond 的写法就是这种用法。
3. **不需要新增"链式抽象"作为载体**。Platform-as-Event 的实现路径天然就是"一个 PlatformFormation 类 + 几个轻量副条件"——这与 production 的 BreakoutPullbackEntry 是同构的。引入 ChainCondition 反而会诱导研究员把"BO 是 Platform 的前缀"塞进 conds 链表，这会撞上 Q1 里指出的状态机不可表达的边界。

**所以 Platform-as-Event 的实现路径在 production 风格下是天然的**——状态机本身解决"先 BO 后稳定"的顺序与回退，副条件解决"附加门槛"。ChainCondition 作为中间载体不增加表达力，只增加抽象层。

---

## 总评

把 Q1-Q3 的回答合起来：

- **改造 Condition_Ind**（improvement-researcher 的 A1-A7）解决的是 indicator 时代留下的 API 坑——它对 new_trade 项目本身有价值。
- **DataFrame 谓词代数 + @feature**（improvement-researcher §2.2）解决 Trade_Strategy 90% 的 vectorized 形态判定——它是 Stage 2 的真正落地形态。
- **显式 Python 状态机类**（production 主流形态）解决剩下 10% 不可 vectorized 的复合形态（包括 Platform Formation）——产出包装成 BO 因子进 mining。

ChainCondition 这一抽象层在这三层之间夹得很尴尬：底层有谓词代数兜底，顶层有状态机兜底，中间这一层既没有 production 实证支撑，也没有真正不可替代的语义。**Stage 2 应改写为"谓词代数为主 + Python 状态机子类为补"，砍掉 ChainCondition 这一层**。
