# 入口一上的"高一层事件"建模 — 7 特征形态(特征 1-6)

> 范围:用户提出的 7 特征形态,本文回答特征 1-6;特征 7(post-BO 平台)由搭档 non-causal-factor-modeler 处理。
> 立场:入口一架构(BO 主干 + EventChain 单向 Adapter 接入因子注册表)。
> 关联:`docs/research/cind_compute_layer_design.md`。

---

## 0. 一句话结论

> **入口一能闭合特征 1-6,但要承认两件事**:(a) BO 簇属性必须以"广播投影到簇内每个 BO"的方式回到 BO 因子层 — 这个动作其实就是"在 EventChain 层识别簇,在 BO 行上消费";(b) **特征 4(簇累计破 pk 数)** 不在 EventChain 的 t-indexed series 抽象内,必须由 EventChain 输出"簇 id series",然后**在 BO 因子层**汇总每个 BO 的 `broken_peaks.num_peaks`,这一步走的是因子层(标量)的路径,不是 EventChain 的路径。**入口一不是优雅地闭合 — 是诚实地分工**。

---

## 1. Q5(framing)先回答 — 这是同一件事的两种描述

用户的 framing("BO 簇是更高层事件,BO 是被审视者")与入口一的工程形态("EventChain 识别簇 → 簇属性 broadcast 到 BO 因子")**在事实层面是同一件事,但视角不同**:

- **用户视角**:"簇"是 first-class 事件,BO 只是簇的成员,应该有"簇 row"
- **入口一工程视角**:评估单位仍然是 BO(每个 BO 一行),只是 BO 上多挂几个"以簇为视角的统计量"作为因子

这两个描述**在数学上等价**(BO row 上挂 cluster_id + cluster_attrs == cluster row × BO row 一对多投影),**但在产品语义上不等价**:
- 如果未来需要 mining"簇级 PnL""簇级 hit rate"(以簇为评估单位),入口一就开始绷紧
- 当前需求是"用簇属性挑出更优的 BO 入场点",评估单位仍是 BO — **入口一够用**

**给团队的诚实判断**:用户那句"BO 是被审视者"是更高层的 framing,入口一确实没有提供"簇 row"作为 first-class 数据结构。如果团队接受"评估单位是 BO,簇属性只是 BO 的因子来源",入口一闭合;如果坚持"簇是 first-class 事件",必须升级到入口二。**当前需求接受前者**。

---

## 2. Q1 投影方式 — 选项 A(广播到簇内所有 BO)

**直接判定:选 A**。

理由:
- 簇属性(`cluster_size`、`cluster_first_drought`、`cluster_pk_total`、`vol_burst_in_cluster`、`pre_cluster_overshoot`)对**簇内任意 BO 来说都成立**,它们是簇的"环境属性",不是"终点属性"
- 选项 B(只投到最后一个 BO)假设我们已经知道"哪个 BO 是最后一个" — 这是**未来信息**(后面是否还会有 BO 不可知,违反 causality)。即使勉强用"K 天无新 BO 才认定簇结束"补救,也意味着所有因子要延迟 K 天才能被消费 — 实盘盯盘场景下不可接受
- 调试视角:把 BO 行打开,看 cluster_id / cluster_size / cluster_first_drought 一目了然,不用回溯"该 BO 属于哪个簇的终端"

**唯一的小坑**:簇内 BO 共享相同的簇属性,在统计层面会让 mining 出现"伪相关"(同一簇的 5 个 BO 取了 5 行重复样本)。这是 mining 层的考量,**不在本研究范围内** — 解决方法是 mining 时把 cluster_id 当 group key 做 stratified split,或只取簇首 BO 进入训练集。

---

## 3. Q2 簇识别 — pandas 向量化

输入:`is_bo: pd.Series[bool]`(BO 当根为 True)。簇定义:相邻 BO 间隔 ≤ K 天属同簇。

```python
def assign_cluster_id(is_bo: pd.Series, K: int = 7) -> pd.Series:
    """
    返回 cluster_id series:
    - BO 当根:对应簇 id(0,1,2,...)
    - 非 BO 根:NaN
    """
    bo_idx = np.flatnonzero(is_bo.values)             # BO 行下标
    if len(bo_idx) == 0:
        return pd.Series(np.nan, index=is_bo.index)

    gaps = np.diff(bo_idx)                            # 相邻 BO 距离
    new_cluster = np.r_[0, (gaps > K).astype(int)]    # 第一个 BO 起一个新簇
    cluster_id_at_bo = new_cluster.cumsum()           # 0,0,0,1,1,2,...

    out = pd.Series(np.nan, index=is_bo.index)
    out.iloc[bo_idx] = cluster_id_at_bo
    return out
```

放进 EventChain 抽象:`ClusterChain(deps=[bo_chain], K=7).evaluate_batch(df) -> Series[float]`(NaN 表示该 t 不是 BO)。

---

## 4. Q3 特征 1-6 的 EventChain 表达

约定共享 series:
- `is_bo: Series[bool]`(BO 当根)
- `cluster_id: Series[float]`(上面那个 chain 的输出)
- `vol_spike: Series[bool]`(放量当根的判定,例如 `volume / vol_ma20 > 2.0`)

### 特征 1 — 企稳(BO 当根/之前的窗口因子,不需要簇语义)

这是**纯 BO 锚点的标量因子**,与簇无关,走入口一原生路径(`_calculate_*`):

```python
def _calculate_pre_bo_stability(df, idx, window=20, max_dev=0.03):
    """BO 之前 window 天 close 相对 MA 的最大偏离 ≤ max_dev → 视为企稳"""
    seg = df['close'].iloc[idx-window:idx]
    ma  = seg.mean()
    return float((seg - ma).abs().max() / ma)
```

注册为标量 FactorInfo,**不需要 EventChain**。这一项与簇无关,直接作用于 BO 当根。

### 特征 2 — 连续突破(簇内 BO 数 ≥ N)

```python
# EventChain 层
cluster_size = (
    cluster_id
    .groupby(cluster_id)
    .transform('size')
    .where(is_bo)               # 只在 BO 行有值
)
# 上面那行的 size 是"该簇所有 t",但因为 cluster_id 只在 BO 行有值,
# transform('size') 自动只在 BO 行展开 — 等于"簇内 BO 数"
```

通过 `factor_from_chain(cluster_size_chain)` 投影到 BO 因子 `cluster_size`,在阈值层比 ≥ N。

### 特征 3 — 簇首 BO 的 drought 较大

`drought_at_bo: Series[int]`(detector 已有 `get_days_since_last_breakout`,可以包成 chain):

```python
# EventChain 层
first_drought_per_cluster = (
    drought_at_bo
    .where(is_bo)
    .groupby(cluster_id)
    .transform('first')        # 簇内第一个 BO 的 drought,广播到簇所有 BO
)
```

注册为 `cluster_first_drought` 因子,阈值比 ≥ X。

### 特征 4 — 簇累计破 pk 数 ≥ N(**入口一的痛点**)

`broken_peaks` 是 `BreakoutInfo` 的成员(见 `breakout_detector.py:57`),**不是 t-indexed series**,EventChain 拿不到。**EventChain 只能输出簇 id,不能输出每个簇的 pk 累计数**。

诚实方案 — **跨层协作**:
1. EventChain 负责输出 `cluster_id_series`(到 BO 因子层)
2. **BO 因子层**(标量因子)消费 cluster_id + 当前 BO 的 `breakout_info.num_peaks`,做"簇内累计 sum"

```python
# 标量因子(走 _calculate_* 路径,但需要访问 detector 的历史 BO 列表)
def _calculate_cluster_pk_total(self, breakout_info, idx, detector, cluster_id):
    """
    遍历 detector.get_recent_breakouts() 找出当前簇的所有 BO,
    sum(b.broken_peaks.num_peaks for b in those_bos)
    """
    cur_cid = cluster_id.iloc[idx]
    if pd.isna(cur_cid):
        return None
    total = 0
    for b in detector.iter_breakouts_in_cluster(cur_cid, cluster_id):
        total += len(b.broken_peaks)
    return total
```

**这一项不能优雅地放进 EventChain**。原因:`broken_peaks` 是 BO-specific 元数据,不在 EventChain 的"t-indexed series"范畴(见 `cind_compute_layer_design.md` §1.2 第 3 类不可表达项)。**入口一的诚实形态是分工** — EventChain 只负责"簇 id 这种可以放进 series 的东西",其余事件级元数据由 BO 因子层处理。

**反方案(扩展 EventChain 接受 broken_peaks)被驳回** — 这会把 `Breakout` dataclass 的"事件级元数据"语义灌进 EventChain,使 EventChain 不再纯粹是 t-indexed,触碰 §1.2 已经划清的边界。

### 特征 5 — 簇内放量(任一 BO 当根曾放量)

```python
vol_burst_in_cluster = (
    vol_spike.where(is_bo)
    .groupby(cluster_id)
    .transform('any')          # 簇内任一 BO 放量 → True 广播
)
```

注册为 `vol_burst_cluster` 因子,阈值比 == True。**注意 `vol_spike` 必须只在 BO 当根上判定**(`.where(is_bo)`),否则就变成"簇区间内任一天放量",语义不同。

### 特征 6 — 簇前未超涨

`cluster_start_idx_per_cluster` = 每个簇第一个 BO 的位置;之前 M 天累计涨幅 < 阈值。

```python
# EventChain 层
first_bo_pos = (
    pd.Series(np.arange(len(df)), index=df.index)
    .where(is_bo)
    .groupby(cluster_id)
    .transform('first')        # 簇首 BO 的下标(广播到簇所有 BO)
)

ret_M = df['close'] / df['close'].shift(M) - 1.0   # M 天累计涨幅 series
pre_cluster_ret = (
    ret_M.shift(1).iloc[first_bo_pos.dropna().astype(int).values]
)
# 然后把 pre_cluster_ret 按 cluster_id 广播回每个 BO
```

注册为 `pre_cluster_overshoot` 因子,阈值比 ≤ 阈值。

---

## 5. Q4 入口一是否真能闭合 — 部分闭合,诚实分工

**结论**:特征 1、2、3、5、6 在 EventChain + 单向 Adapter 内闭合;**特征 4 必须跨层协作**(EventChain 出簇 id,BO 因子层 reduce broken_peaks)。

这不是入口一的"破产",是入口一的设计前提:
> 因子是"BO-anchored scalar"范畴,EventChain 是"t-indexed series"范畴,**它们是两个范畴**(`cind_compute_layer_design.md` §0)。

特征 4 涉及"簇内 BO 列表的 broken_peaks 累计",这是**两个范畴的乘积** — 既要簇语义(EventChain),又要 BO 元数据(因子层)。在两个范畴之间,**让因子层做 join 是更自然的方向**(因子层本来就持有 detector 引用 + BO 历史)。

**不要做的事**:
- 不要把 `broken_peaks` 灌进 EventChain。会污染 §1.2 已经划清的边界
- 不要把"簇 row"作为新数据结构引入。这是入口二的工作,不是入口一的工作
- 不要把特征 4 写成"假装簇尾 BO 才有值"的 EventChain — 簇尾判定是未来信息

**要做的事**:
- 接受"簇 id 是 EventChain 的产物,但簇属性的 reduce 可以发生在因子层"这个分工
- 在 `FeatureCalculator` 给一类新因子开辟"cluster-aware 标量因子"分组(参数包含 `cluster_id_series`)
- 给 detector 增加 `iter_breakouts_in_cluster(cluster_id_series)` 辅助方法,让因子层能够枚举簇成员

---

## 6. 综合判定

入口一对这个 7 特征形态(特征 1-6 部分):

| 特征 | 路径 | 闭合度 |
|---|---|---|
| 1 企稳 | 标量因子(原生)| 完全闭合 |
| 2 簇内 BO 数 | EventChain → Adapter | 完全闭合 |
| 3 簇首 drought | EventChain → Adapter | 完全闭合 |
| 4 簇累计破 pk 数 | EventChain 出簇 id + 因子层 reduce broken_peaks | **跨层,诚实分工** |
| 5 簇内放量 | EventChain → Adapter | 完全闭合 |
| 6 簇前未超涨 | EventChain → Adapter | 完全闭合 |

**6/6 都能表达;但 4 走的是跨层路径,不在 EventChain 单一抽象内**。

这是入口一的真实代价,也正好是 §1.2 早就承认的"两个范畴"的体现 — 不是新出现的破绽。

---

**报告结束**。
