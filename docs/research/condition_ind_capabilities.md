# Condition_Ind 全部功能客观枚举 (Doc 1)

> **范围**: `/home/yu/PycharmProjects/new_trade/screener/state_inds/` 全部文件,以及 git 历史中已删除的 `screener/state_inds/Condition_ind.py`(参考 commit `2f2582c:screener/state_inds/base.py` 的完整字段版本)。
>
> **方法**: 客观枚举,不做评价、不与外部方案对比。每条功能给出 file:line 定位与一句话语义说明。
>
> **生产代码采样**: `screener/scrs_train/scr_rv/define_scr.py` (当前使用)、`screener/scrs/wide_scr.py` 等(历史使用 `Condition_ind.py` 中已删除字段)。

---

## A. 基础字段语义(`Condition_Ind` 类参数及 cond dict 字段)

### A.0 类级参数(`params`)

| 字段 | 定位 | 默认值 | 语义 | 是否生产使用 |
|------|------|--------|------|-------------|
| `conds` | `base.py:9` | `None` | cond dict 列表;若为 `None` 则跳过条件聚合逻辑,`valid = signal`。 | 是 |
| `min_score` | `base.py:9` | `-1` | 最低分数阈值;`sum(scores) >= min_score` 才允许触发。`-1` 表示不限。 | 是(隐式默认) |

### A.1 cond dict 字段 (当前 base.py)

注:以下为 `base.py:24-33` 内 `__init__` 中 default-fill 逻辑标准化后的字段语义。

| 字段 | 定位 | 默认值 | 语义 | 是否生产使用 |
|------|------|--------|------|-------------|
| `ind` | `base.py:43-45` | 必填 | 子条件 indicator 对象;读取其 `.valid` line 来判断子条件是否满足。 | 是(`scr_rv/define_scr.py:46,47,60,61`) |
| `exp` | `base.py:26-27, 48` | `0` | "前置事件寿命",单位 bar;`last_meet_pos[i]` 之后 `exp` 根 bar 内,此 cond 仍计为满足(分数 1)。 | 是(`scr_rv/define_scr.py:60` `exp=bounce_exp5*5`) |
| `must` | `base.py:28-29, 50` | `True` | 是否必须满足。`must_pos` 中所有 cond 的 score 必须全为 1 才能触发,否则即使 `min_score` 达标也不触发。 | 是(隐式默认 True) |
| `causal` | `base.py:30-31, 45` | `False` | 是否使用因果(前一根 bar)读取 cond.valid;`True` 用 `valid[-1]`,`False` 用 `valid[0]`。用于解决"自身依赖于尚未计算完成的 cond"的循环依赖。 | 是(`scr_rv/define_scr.py:60,61` `causal=True`) |

### A.2 cond dict 字段 (历史完整版本,来自 git commit `2f2582c:screener/state_inds/base.py`)

以下字段在当前 base.py 已删除,但仍可在历史 `wide_scr.py`、`dyn_hole.py` 等代码中看到使用痕迹。

| 字段 | 历史定位 (commit 2f2582c) | 默认值 | 语义 | 生产使用痕迹 |
|------|--------------------------|--------|------|------------|
| `keep` | base.py L37-38, L57-59 | `1` | 连续满足 bar 数门槛;`keep_time[i] >= cond['keep']` 才记录为 `last_meet_pos[i]`。即 "子条件必须连续保持 keep 根 bar 都成立,才视为被满足"。 | `wide_scr.py:50,53` (`keep=40, keep=22`)、`dyn_hole.py:48,51` |
| `keep_prop` | base.py L39-40, L66-72 | `None` | "宽松连续度":允许中间有空缺,只要满足占比 `>= keep_prop` 就维持 `keep_time` 不清零;一旦低于占比阈值则重置。即 "在 keep 计数窗口内最多允许多少比例的空缺仍算保持中"。 | `wide_scr.py:50` (`keep_prop=0.7`)、`dyn_hole.py:48` (`keep_prop=self.p.ma_prop`) |
| `relaxed` | base.py L41-42, L63-64, L79-80 | `False` | "粘性已满足":一旦满足过(`keep_time >= keep`)就永久标记 `relaxed_met[i] = True`,此后每根 bar 都自动给 score=1,不再需要重新评估。即"达成一次后永久 sticky"。 | `wide_scr.py:53` (`relaxed=True`)、`dyn_hole.py:51` |
| `exp_cond` | base.py L74-77 | (未在 default-fill 中,只在 next() 检测 `'exp_cond' in cond`) | exp 寿命窗口内的"二级条件":在 `last_meet_pos` 之后 `exp` 寿命期内,如果当前 bar 上 `exp_cond.valid[-1]` 为 True 才给 score=1;否则不给分。即"前置事件触发后,还要再叠加一个时间窗口内的条件"。生效仅在 `last_meet_pos > 0`(即前置事件已经发生过)的 bar 上。 | `wide_scr.py:71` (`exp_cond=self.rsi`)、`dyn_hole.py:68` |

### A.3 实例属性(由 `__init__` 创建,bar-by-bar 维护)

| 属性 | 定位 | 语义 |
|------|------|------|
| `self.last_meet_pos` | `base.py:20` | 每个 cond 上一次"被满足"的 bar 索引(`len(self)`);初值 `-inf`,在 `next()` 中根据 cond.valid 更新。 |
| `self.scores` | `base.py:22` | 每个 cond 在当前 bar 上的得分(0/1);每根 bar 重置然后重新计算。 |
| `self.must_pos` | `base.py:33` | `must=True` 的 cond 索引列表;在触发判断时用 `all(scores[must_pos])` 校验必选条件。 |
| `self.keep_time`(历史) | 历史 base.py L19 | 每个 cond 当前连续满足的 bar 数,用于 `keep` 字段。 |
| `self.relaxed_met`(历史) | 历史 base.py L20 | 每个 cond 是否已被永久 sticky 标记。 |
| `self.keep_prop_count`(历史) | 历史 base.py L21 | 每个 cond 在 keep 窗口内"真正满足"的累计计数,用于 `keep_prop` 占比判断。 |

### A.4 输出 line

| line | 定位 | 语义 |
|------|------|------|
| `valid` | `base.py:8` | 唯一固定输出 line。表达当前 bar 是否触发:若 conds 聚合通过,等于子类的 `signal[0]`;否则为 `False`。 |
| `signal`(子类自定义) | (子类) | 子类通常在 `lines` 元组里加 `signal`,在 `local_next()` 中赋值;父类用 `lines.signal[0]` 决定触发时的 `valid` 取值。 |

---

## B. 链式组合机制

### B.1 cond 接受任意 `Condition_Ind` 子类实例

cond dict 的 `ind` 字段读取 `.valid` line(`base.py:45`),而 `valid` 是 Condition_Ind 的固定输出 line,因此任何 `Condition_Ind` 子类实例都可以作为另一个 Condition_Ind 的 cond。

**示例**(`scr_rv/define_scr.py:44-49`):
```python
self.bounce = Empty_Ind(name='bounce',
                       conds=[
                           {'ind': self.narrow},      # Narrow_bandwidth instance
                           {'ind': self.ma_bull},     # Simple_MA_BullishAlign instance
                       ])
```
`bounce` 自己又被嵌套作为 `self.rv` 的 cond:
```python
self.rv = Vol_cond(conds=[{'ind': self.bounce, 'exp': ..., 'causal': True}, ...])
```

### B.2 递归命名复用(同一 indicator 多处引用)

同一个 indicator 实例可在多处出现:既可以是某个 Condition_Ind 的 `ind`,也可以是另一个 cond 的 `exp_cond`。这是普通 Python 对象引用,非框架特殊机制。

**示例**(`wide_scr.py:57, 71`):
```python
self.rsi = Compare(threshold=[30, 70], indicator='rsi', period=20, operation='within')
# rsi 一方面是 self.vol_cond 的 cond.exp_cond
self.vol_cond = Vol_cond(conds=[
    {'ind': self.flat_conv, 'exp': 20, 'exp_cond': self.rsi, 'keep': 0},
])
```

### B.3 嵌套子类作为 cond 的语义

外层 Condition_Ind 看到的是子 cond 的 `.valid` line,即子 cond **自己已经完成 conds 聚合后**的最终触发结果。这形成"逐层封装"的语义:

- 内层 `bounce.valid` = `narrow.valid AND ma_bull.valid` (因为 bounce 是 Empty_Ind,signal 恒为 True,所以 valid 完全由 conds 聚合决定)
- 外层 `rv.valid` = `rv.signal` AND `bounce` 在 exp 窗口内 AND `rsi_range` 在 exp 窗口内

### B.4 多 cond 同时存在的组合语义

参见 `base.py:50-53`:
```python
if sum(self.scores) >= self.p.min_score and all(np.array(self.scores)[self.must_pos]):
    self.lines.valid[0] = self.lines.signal[0]
else:
    self.lines.valid[0] = False
```

- **AND-of-musts**: 所有 `must=True` 的 cond 必须当前 bar score=1。
- **score-threshold**: 所有 cond(含非 must)的 score 求和 >= `min_score`。
- **bridging-to-signal**: 上述条件全部通过时,`valid` 取子类 `signal[0]` 的值(可以是布尔,也可以是带数值意义的"信号强度",见 B.5)。

### B.5 valid 输出可以携带数值(非纯布尔)

`base.py:51` `self.lines.valid[0] = self.lines.signal[0]`,signal 是子类自定义,可以赋数值。生产中常见:
- `Vol_cond.local_next`(`functional_ind.py:516`)赋 `-self.lines.rv * bt.If(signal,1,0)`,即"放量条件触发时输出负的 rv 值,作为强度排序信号"。
- `MACD_CrossOver`(`enhance_ind.py:251`)赋 `self.lines.macd[0]`(金叉发生时输出 macd 值)。
- `Narrow_bandwidth.local_next`(`functional_ind.py:429`)赋当前命中周期编号 `period`。

---

## C. 时序与寿命语义

### C.1 `valid` line 的逐 bar 计算逻辑(`base.py:40-55`)

每根 bar `next()` 流程:
1. **call `local_next()`** (子类逻辑,负责给 `lines.signal[0]` 赋值)。
2. **若有 conds**:
   - 对每个 cond,reset `scores[i] = 0`。
   - 读 `cond['ind'].valid[-1 if causal else 0]` (`base.py:45-46`):若值为真(且非 NaN),更新 `last_meet_pos[i] = len(self)`(记录本 bar 已满足)。
   - 检查 `len(self) - last_meet_pos[i] <= cond['exp']` (`base.py:48`):若仍在 exp 寿命窗口内,给 `scores[i] = 1`。
   - 聚合 score:`sum(scores) >= min_score AND all(scores[must_pos])` → `valid[0] = signal[0]`;否则 `valid[0] = False`。
3. **若无 conds**:`valid[0] = signal[0]`(纯透传子类 signal)。

注: NaN 防御 (`base.py:46`) — 即使预热(prenext)结束后,子 cond 的 valid 可能仍是 NaN(子 cond 的 minperiod 比 self 长时),所以读取时强制排除 NaN。

### C.2 `last_meet_pos` 的作用

- 类型: `List[int|float('-inf')]`,长度 = len(conds)。
- 初值: `-inf` (`base.py:20`),保证未发生过的 cond 不会被误判为"在 exp 窗口内"。
- 更新: 每根 bar,若 cond.valid 真,则 `last_meet_pos[i] = len(self)`。
- 用途: 用 `len(self) - last_meet_pos[i] <= exp` 判断"前置事件是否仍在寿命窗口内"。

### C.3 `exp` 的 bar 维度寿命语义

- `exp = 0` 表示"必须当前 bar 满足"(因为只有 `len(self) == last_meet_pos[i]` 时差值为 0)。
- `exp = N` 表示"前置事件后 N 根 bar 内都视为有效"(允许时间错位的事件叠加,例如:放量是在 5 根 bar 前发生的,只要在 exp 窗口内,当前 bar 仍可触发)。
- 这是一个**单调衰减的 sticky 标记**:cond 满足后,`scores[i]` 在接下来 `exp` 根 bar 内自动为 1,直到窗口过期。

### C.4 `keep` / `keep_prop` 的连续性语义(历史完整版)

参考 commit `2f2582c:base.py:54-72`:

- **keep**: 子条件需要**连续 keep 根 bar** 都满足才被"记一次有效":
  ```python
  if cond['ind'].valid[...]:
      self.keep_time[i] += 1
      if self.keep_time[i] >= cond['keep']:
          self.last_meet_pos[i] = len(self)  # 这一刻才正式登记
  ```
- **keep_prop**: "宽松连续度":若 `keep_time` 已 > 0 但当前 bar 不满足,只要历史满足占比 `keep_prop_count / keep_time >= keep_prop`,则 `keep_time` 继续 +1(允许有断点的连续);否则才清零。
  ```python
  if self.keep_prop_count[i] / self.keep_time[i] >= cond['keep_prop']:
      self.keep_time[i] += 1
  else:
      self.keep_time[i] = 0
      self.keep_prop_count[i] = 0
  ```

### C.5 `relaxed` 的弱化匹配语义(历史完整版)

参考历史 base.py L63-64, L79-80:

- 一旦 cond 第一次"keep 达标"(即 `keep_time >= cond['keep']`),就置 `relaxed_met[i] = True`。
- 此后每根 bar,在 score 聚合时:`if relaxed_met[i]: scores[i] = 1`(无视当前是否仍满足、是否在 exp 窗口内)。
- 即"一次达标后永久 sticky",直到 indicator 被销毁。这等价于将 exp 设为 +∞,但语义更明确(达成后永久有效)。

---

## D. 异质聚合

### D.1 `must` + `min_score` 同时存在(必选 + 评分)

参见 `base.py:50`:
```python
if sum(self.scores) >= self.p.min_score and all(np.array(self.scores)[self.must_pos]):
```

两段逻辑同时成立才触发:
- **必选段**: `must=True` 的 cond 必须全部 score=1。
- **评分段**: 所有 cond(含 must 与非 must)的 score 求和 >= `min_score`。

这允许混合"硬条件 + 软条件":硬条件(必选)缺一不可,软条件(非必选)在数量上达到阈值即可。

**例**(假设 5 个 cond,其中 2 个 must=True):
- 必选段:这 2 个 must cond 当前 bar 都要 score=1。
- 评分段:5 个 cond 总分 >= min_score(例如 4)。等价于"2 个 must 必满足,再从 3 个可选中至少满足 2 个"。

### D.2 `exp_cond` 在 exp 时间窗内叠加另一条件(历史)

参考历史 base.py L74-77:
```python
if len(self) - self.last_meet_pos[i] <= cond['exp']:
    if 'exp_cond' in cond and len(self) - self.last_meet_pos[i] > 0:
        if cond['exp_cond'].valid[-1] and not math.isnan(cond['exp_cond'].valid[-1]):
            self.scores[i] = 1
    else:
        self.scores[i] = 1
```

语义:
- "前置事件在过去 `exp` 根 bar 内发生过(不含当前 bar,因为有 `> 0` 的条件)"
- **且** "在当前 bar 上,叠加另一个 indicator `exp_cond.valid[-1]` 也为真"
- 才给 `scores[i] = 1`。

这等于在"前置事件触发"和"当前需要叠加的环境条件"之间引入逻辑 AND,实现"事件-环境复合判断"。生产用例:`wide_scr.py:71` 将 flat_conv 的 exp 窗口内,叠加 rsi_range 作为环境过滤。

### D.3 score 数值(0/1)

注: 当前实现 score 只取 0 或 1,不携带强度。即每个 cond 满足时只贡献固定的 1 分。

---

## E. 子类生态(已知子类各自扩展了什么)

### E.1 `Empty_Ind` (`meta_ind.py:116-125`)

- 无 `__init__` 计算,只把 `lines.signal[0] = True`(`local_next` L124)。
- 用途: "纯聚合容器" — 当只想做 conds 逻辑组合、不想引入自身 signal 语义时使用。`valid` 完全由 `conds` 聚合决定。
- 生产用例: `scr_rv/define_scr.py:44` 用 `Empty_Ind` 包 `narrow + ma_bull` 形成 `bounce`。
- (历史等价物: `Result_ind`,见 git `794d0c9^:Condition_ind.py:364-374`,代码 100% 同语义,只是命名不同。)

### E.2 `Duration` (`meta_ind.py:64-99`)

- 扩展参数: `time`、`valid_proportion`、`force_end`。
- `local_next` (L80-99): 在 `local_next` 中计算"过去 `time` 天内输入 line 非零 bar 的占比",超过 `valid_proportion` 才把 signal 置 1。
- `force_end=True`(默认): 额外要求当前 bar 输入也非零。
- 用途: 用于实现"前置事件需要持续一段时间"的统计型 indicator。与 base 的 `keep`(历史)是两种实现路径:`keep` 写在 cond dict 里,`Duration` 是 indicator-level 子类。

### E.3 `Compare` (`meta_ind.py:30-61`)

- 扩展参数: `indicator`、`period`、`operation`(`<`/`>`/`within`)、`name`。
- `__init__`: 接受外部 `input` 或按 indicator 名(`adx`/`atr`/`rsi`)创建一个内置 backtrader indicator,然后基于 `operation` 构造 `signal = indicator * bt.If(condition, 1, 0)`。
- `local_next`: **未定义**,继承父类 `pass`。
- 用途: 把"指标值与阈值比较"这一普适操作泛化成一个可复用 Condition_Ind。
- 生产用例: `scr_rv/define_scr.py:50-52` 构造 rsi range 检查。

### E.4 `BreakoutPullbackEntry` (`functional_ind.py:8-318`)

- 复杂状态机子类,完全在 `local_next` 中实现"放量 → 回踩 → 企稳"四阶段评分门槛。
- 扩展参数:阶段时长、阶段评分阈值、上影线/下影线比例等(L14-41)。
- 输出 lines: `signal` + 三条调试 line `breakout/pullback/stable`。
- 用途: 复杂事件序列的内嵌检测;不依赖 conds 聚合,**也不与 conds 字段交互**(它只重写 local_next)。

### E.5 `PriceStability` (`functional_ind.py:321-365`)

- 状态机模式:接收外部 volume_signal,触发后跟踪 `stability_days` 天,检查价格相对均值的范围,最终在第 `stability_days` 天输出最终结论。
- 注: L355-360 中用 `self.valid` 当作可变状态变量(直接覆写 indicator 默认的 `lines.valid`,这是子类对父 line 的隐式滥用)。

### E.6 `Narrow_bandwidth` / `Narrow_realtime` / `Vol_cond` / `Vol_cond_realtime` (`functional_ind.py:367-547`)

- 自定义 signal 计算,通常用 `local_next` 实现;架构与 base 兼容(继承 conds、min_score 字段)。
- `Vol_cond.local_next`(L508-516): 支持可选 `rv_date` 参数,只在指定日期输出 signal,否则恒为 0。

### E.7 `MA_CrossOver` / `MA_BullishAlign` / `Simple_MA_BullishAlign` (`functional_ind.py:552-758`)

- 均线类信号子类,统一用 `local_next` 输出 signal 值(可以是 1,也可以是均线绝对值)。
- 接受 `external_mas` 参数允许从外部传入均线,避免重复计算。

### E.8 `MA_EarlyBullish` / `MA_CrossOver`(增强版) / `MACD_CrossOver` / `MACD_ZeroCross` / `OBV_Divergence` (`enhance_ind.py`)

- 各种额外的事件性 indicator,均为 `Condition_Ind` 子类,只重写 `local_next` 计算 signal。

### E.9 backup_ind.py 中的子类

`ATR_ratio`、`BBandratio`、`Regression`、`LogIndicator`、`MA_Converge0`、`MA_Converge`、`MAParallel`、`BuyPoint`、`Narrow_bandwidth`、`OBV_platform`、`BBand_converge` — 多数仍在使用或备份,模式同上(`local_next` 重写)。

特别:
- **`BuyPoint`** (`backup_ind.py:132-286`): 大型状态机,实现"放量 → 下跌 → 企稳 → 反弹"的多阶段买点判定。带 `self.state` 字段进行 FSM 管理。
- **`OBV_platform`** (`backup_ind.py:334-386`): OBV 平台累积判定 FSM。
- **`BBand_converge`** (`backup_ind.py:389-417`): 布林带收敛 FSM。

### E.10 `ConstantIndicator` (`meta_ind.py:128-132`)

- 直接继承 `bt.Indicator`(**不**继承 `Condition_Ind`),只输出常量 `valid=1`。
- 用途: 占位 indicator,可作为 cond 但永远为真。

### E.11 子类如何通过继承获得统一接口

所有 `Condition_Ind` 子类:
1. 在自己的 `lines` 元组里通常加上 `'signal'`(自定义信号),`valid` 由父类自动注册。
2. 重写 `local_next()` 实现自己的核心信号逻辑。
3. 继承 `params = dict(conds=None, min_score=-1)`,允许在实例化时传 `conds=[...]` 形成嵌套。
4. `next()` 由父类管理:先 call `local_next()`,然后做 conds 聚合,最后写 `valid[0]`。

---

## F. 派生 indicator 机制

### F.1 写一个新 Condition_Ind 子类的标准模式

```python
from screener.state_inds.base import Condition_Ind

class MyInd(Condition_Ind):
    lines = ('signal', 'helper_line')   # 至少有 signal,可加调试 line
    params = dict(my_param=...)          # 自定义参数

    def __init__(self, external_input=None):
        super().__init__()
        # backtrader-level 计算(预构建 line 算子)
        self.something = bt.indicators.SimpleMovingAverage(...)
        self.addminperiod(...)            # 显式声明最小预热周期

    def local_next(self):
        # 逐 bar 实现 signal 计算
        self.lines.signal[0] = ...
```

实例化时既可独立使用,也可作为另一个 Condition_Ind 的 cond:
```python
ind = MyInd(my_param=5, conds=[{'ind': prev_ind, 'exp': 10, 'must': True}])
```

### F.2 与 backtrader Indicator 框架的耦合度

- `Condition_Ind` 直接继承 `bt.Indicator`(`base.py:7`),所以保留了:
  - `lines` 声明机制 (`base.py:8`)
  - `params` 字典 (`base.py:9`)
  - `plotlines` 绘图样式 (`base.py:10`)
  - `next()` / `prenext()` 周期回调
  - `addminperiod()` 控制预热
  - line 算子组合(`bt.And` / `bt.If` / `bt.Min` 等可在 `__init__` 中用于构造 self.lines.X)
- 唯一的扩展:在 `next()` 中加了"conds 聚合 + score 阈值"这一通用逻辑层,把"基础信号 vs 衍生信号"的两阶段语义压到一个父类里。
- 因此,子类既能享受 backtrader 的预构建 line 表达式(在 `__init__`),也能享受 Python 状态机风格的逐 bar 计算(在 `local_next`)。

---

## G. 历史扩展(已删除模块的能力推断)

### G.1 `Result_ind` (来自 git `794d0c9^:Condition_ind.py:364-374`)

```python
class Result_ind(Condition_Ind):
    params = dict(name='')
    lines = ('signal',)
    def __init__(self):
        super().__init__()
        self.plotinfo.plotname = self.p.name or self.__class__.__name__
    def local_next(self):
        self.lines.signal[0] = True
```

- **能力**: signal 恒为 True,完全靠 conds 聚合驱动 valid。
- **生产用例(历史)**: `wide_scr.py:48,88`、`narrow_scr.py:131`、`narrow_scr1.py:119`、`vol_explode.py:61`、`trade_scr.py:38`、`dyn_hole.py:46,87`、`scr_buy/define_scr.py:41` 等多处用作"最终聚合输出 indicator"。
- **当前替代**: `Empty_Ind` (`meta_ind.py:116-125`) 行为等价。

### G.2 `Breakout` / `Vol_cond` / `BBand_converge` / `OBV_platform` / `Platform` 历史版本(`Condition_ind.py`)

git `794d0c9^:Condition_ind.py` 中存在这些类的早期实现:
- `Vol_cond` (L13-30): 早期实现简单很多,只有 period/threshold 两参数。
- `Breakout` (L180-): 早期 FSM 实现。
- `OBV_platform` (L237-): 早期 FSM 实现。
- 当前 `functional_ind.py`、`backup_ind.py` 中的同名类是这些的演化版本。

### G.3 `keep` / `keep_prop` / `relaxed` / `exp_cond` 字段(历史 base.py)

参见 A.2 节。这四个字段在 git 历史里曾存在于 `base.py` 的 `__init__` default-fill 与 `next()` 聚合逻辑中。当前 base.py 中已删除,但相关生产文件(`wide_scr.py`、`dyn_hole.py`、`train_before_hole.py`)仍以"传入字典 key"的方式书写这些字段(实际不再生效)。

历史完整 base.py 中,`Condition_Ind` 的 cond dict 字段完整集合为:

| 字段 | 默认 | 角色 |
|------|------|------|
| `ind` | (必填) | 子条件 indicator |
| `exp` | 0 | 前置事件 bar 寿命 |
| `must` | True | 是否必选(参与 `all(scores[must_pos])`) |
| `causal` | True (历史) / False (当前) | 是否读上一根 bar 的 valid |
| `keep` | 1 (历史) | 连续 bar 数门槛 |
| `keep_prop` | None (历史) | 宽松连续度占比 |
| `relaxed` | False (历史) | 一次满足后永久 sticky |
| `exp_cond` | — (历史,非 default-fill) | exp 窗口内叠加的二级条件 indicator |

### G.4 已删除模块的功能能力总览

历史 Condition_Ind 是一个比当前更宽的"条件复合 DSL":
1. 支持**事件 sticky 行为**(`exp` + `relaxed`)。
2. 支持**连续性要求**(`keep` + `keep_prop`)。
3. 支持**嵌套环境条件**(`exp_cond`)。
4. 支持**必选 + 评分**混合聚合(`must` + `min_score`)。
5. 支持**任意嵌套** Condition_Ind 子类作为 cond,递归形成树状条件依赖图。

当前简化版本只保留了 (1) 中的 `exp` 和 (4) 全部。

---

## H. 完整字段-语义速查表

| 维度 | 字段 | 当前/历史 | 一句话 |
|------|------|----------|--------|
| 类级参数 | `conds` | 当前 | cond dict 列表 |
| 类级参数 | `min_score` | 当前 | 总分门槛 |
| cond 字段 | `ind` | 当前 | 子条件 indicator(必填) |
| cond 字段 | `exp` | 当前 | 前置事件寿命(bar) |
| cond 字段 | `must` | 当前 | 是否必选 |
| cond 字段 | `causal` | 当前 | 是否读 valid[-1] 而非 valid[0] |
| cond 字段 | `keep` | 仅历史 | 连续 bar 数门槛 |
| cond 字段 | `keep_prop` | 仅历史 | 宽松连续度占比 |
| cond 字段 | `relaxed` | 仅历史 | 永久 sticky |
| cond 字段 | `exp_cond` | 仅历史 | exp 窗口内叠加二级条件 |
| 子类输出 | `signal` line | 当前 | 子类自定义信号(可数值) |
| 父类输出 | `valid` line | 当前 | 最终触发输出 |
| 实例状态 | `last_meet_pos[i]` | 当前 | 上次满足的 bar |
| 实例状态 | `scores[i]` | 当前 | 本 bar 的 cond 得分(0/1) |
| 实例状态 | `must_pos` | 当前 | must=True 的 cond 索引 |
| 实例状态 | `keep_time[i]` | 仅历史 | 连续满足 bar 数 |
| 实例状态 | `relaxed_met[i]` | 仅历史 | 是否已被 sticky 标记 |
| 实例状态 | `keep_prop_count[i]` | 仅历史 | 占比分母 |
| 状态机模式 | `state = 'none'/'breakout'/...` | (子类约定) | 子类内部 FSM 状态字符串 |

---

## I. 来源对照清单

- 当前 base.py: `/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py`
- 历史完整 base.py(含 keep/keep_prop/relaxed/exp_cond): git commit `2f2582c:screener/state_inds/base.py`
- 历史 Condition_ind.py(Result_ind 等): git commit `794d0c9^:screener/state_inds/Condition_ind.py`(commit `794d0c9` 删除了此文件)
- 子类:`meta_ind.py`、`functional_ind.py`、`enhance_ind.py`、`Signal_ind.py`、`backup_ind.py`
- 生产用法采样: `screener/scrs_train/scr_rv/define_scr.py`(当前)、`screener/scrs/wide_scr.py`(历史)、`screener/scrs_train/define_scr/dyn_hole.py`(历史)
