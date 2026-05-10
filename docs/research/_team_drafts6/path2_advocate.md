# 路径二倡导 — EventChain 作主干,簇/Platform 是一等公民

> 立场:**第一性原理**视角下,对"7 特征复合形态"这个具体场景,路径二(EventChain 主干 + 高层事件 row)在产品语义、统计学正确性、信号语义清晰度三个维度上,**比路径一更本质地契合问题本身**。
> 范围:不考虑改造成本。只问"这个问题的自然形状是什么"。

---

## 0. 一句话主张

用户描述的形态,**评估单位本来就是"簇 + 后续平台"这个复合事件**,不是"5 个 BO 中的某一个"。路径一把它建模成"5 行 BO + 广播因子",在**统计学上把 1 个事件复制成 5 个伪样本**,在**产品语义上把 1 个交易决策时刻碾平成 K+5 天的连续 partial→confirmed 渐变**;路径二的"1 簇 1 row + 1 个决策时刻"是对**事件本体**的直接建模,**所有绕路都消失**。

---

## 1. 评估单位:这是统计学第一性问题,不是工程口味问题

### 1.1 用户的图说明了什么

用户标注的 simulator-terminator 图右上角:**4-12 个 BO 在短时间内聚集成簇,簇结束后股价稳定到一个新平台**。用户问"这是不是值得交易的形态" — 这里的"这"指的是什么?

是**那个聚集成簇的过程 + 稳到平台的整体形象**,也就是**整个右上角那块区域**。不是其中第 4 根 BO,也不是第 5 根,也不是第 7 根。**人眼锁定的、人脑判定的、人手买入的,都是"整个簇 + 平台"这一个事件**。

第一性问题:**统计单位应该是"人眼判定的事件",还是"事件的内部组件"**?

### 1.2 路径一的 5 行 BO 在统计上是什么

路径一把这个簇拆成 5 行 BO row,每行带 `cluster_size=5, cluster_first_drought=X, vol_burst_cluster=True, ...` 完全相同的簇属性。然后 mining 时这 5 行进入训练集。

这意味着什么?这 5 行的 X 矩阵高度相关(簇属性列完全相同),y(未来涨幅)也高度相关(因为 5 个 BO 在时间上重叠,它们各自的"BO+30 天涨幅"窗口共享了大量未来 K 线)。**5 行表面上是 5 个独立样本,实际上是 1 个事件的 5 次过拟合复印件**。

搭档在 `_team_drafts5/higher_event_on_entrance1.md` §2 末尾**已经诚实承认**了这一点:"簇内 BO 共享相同的簇属性,在统计层面会让 mining 出现伪相关...解决方法是 mining 时把 cluster_id 当 group key 做 stratified split,或只取簇首 BO 进入训练集。"

注意这句"**只取簇首 BO 进入训练集**" — 这本质上就是**承认了真正的样本只有 1 个,其余 4 个是冗余**。如果训练集最终只用簇首 BO,那为什么要先生成 5 行再扔掉 4 行?**因为路径一的统计单位 = BO 这个前提,本来就和"评估单位是簇"这个事实不兼容,只能在 mining 阶段补救**。

路径二直接把统计单位设为簇,**1 簇 1 行**。X 矩阵无重复列,y 无重叠窗口,**统计学上干净**。这不是"路径二碰巧更好",这是**统计建模的第一性原则**:统计单位应当与评估单位对齐。

### 1.3 决策时刻在哪一刻

第二个第一性问题:**用户实际下单是哪一刻**?

- BO 当日下单?第一根 BO 出现时,簇还没成形,簇属性都不可测(cluster_size 至少要等到第 N 根 BO 才能定阈值),无法用簇因子判定
- 第 N 根 BO 当日?可以,但簇是否已结束、是否还会再有第 N+1 根 BO,**不知道**
- 簇结束 + 平台确认后?**这才是用户描述的"右上角那块"完整呈现的时刻**,也是特征 7(post-BO 平台)能够被消费的唯一时刻

用户描述的 7 特征里,**特征 7 必须等簇结束后才能判定**。这意味着:**这套形态的真实决策时刻只有一个 — 平台确认那一刻**。

路径一的语义:每个 BO 当日发一个 partial signal,K 天后(平台是否形成可知后)再 refresh 为 confirmed。**5 个 BO 就发 5 次 partial signal**,每次都告诉用户"现在是 BO,可能在簇内,可能簇有 5 根,可能...再等等"。这是**把 1 个决策时刻拉成 K+5 天的渐变流**。

路径二的语义:平台形成那一刻发 1 次 signal,signal 内携带簇的全貌(first_drought=X, bo_count=5, broken_pk_total=8, post_platform_stability=Y)。**1 个事件,1 次信号,1 个决策时刻**。

这个差别**不是 UI 体验差别,是产品语义差别**。partial→confirmed 二段语义只在"评估单位 = BO"的前提下才必要;一旦评估单位回到事件本体(簇),它就完全消失。**路径一的 partial signal 是路径一架构强行产出的中间产物,不是用户需要的产品**。

---

## 2. 7 特征逐条对照:谁在绕路

### 特征 1 — 企稳(BO 之前股价稳定)

- 路径一:BO 锚点的标量因子,**直接,优雅**
- 路径二:簇 row 的 `pre_cluster_stability = first_bo.pre_stability`,**也直接**

平手。这是 BO-local 属性,两条路径都不绕。

### 特征 2 — 连续突破(簇内 BO 数 ≥ N)

- 路径一:`cluster_size = groupby(cluster_id).transform('size')` 然后 `where(is_bo)` 然后 broadcast 到 5 行 BO row,每行的值都是 5。**5 次重复存储 1 个簇属性**
- 路径二:`cluster.bo_count = len(cluster.bos)`,**1 次**

路径二更直接 — 簇大小本来就是簇的属性,不是 BO 的属性。在路径一里它**被强行变成 BO 的属性**。

### 特征 3 — 簇首 BO drought 较大(开闸特征)

- 路径一:`drought.where(is_bo).groupby(cluster_id).transform('first')` 再广播。注意"first"这个动作:**它在 5 行 BO 上选第一行的值,广播给 5 行**。这本质是"我想要簇的属性,但我的 row 是 BO,所以我必须用 first 把 BO 的局部属性提升为簇的属性,再广播回 BO" — **三步绕路**
- 路径二:`cluster.first_drought = cluster.bos[0].drought`,**一步**

路径一的 `transform('first')` + 广播,本质就是"用 groupby 模拟一个簇 row",然后再投影回 BO row。**这是用 SQL 的 join 模拟一个本应是 first-class 的实体**。

### 特征 4 — 簇累计破 pk 数 ≥ N(关键证据)

这是搭档**已经承认**入口一闭合不掉的特征(见 `higher_event_on_entrance1.md` §4 §6 表格):

> "broken_peaks 是 BreakoutInfo 的成员,不是 t-indexed series,EventChain 拿不到。EventChain 只能输出簇 id,不能输出每个簇的 pk 累计数...入口一的诚实形态是分工 — EventChain 只负责'簇 id 这种可以放进 series 的东西',其余事件级元数据由 BO 因子层处理。"

**这段话翻译过来就是**:路径一在这个特征上需要"EventChain 跨到 BO 因子层,枚举簇成员,reduce broken_peaks",还要给 detector 增加 `iter_breakouts_in_cluster()` 辅助方法。**它没闭合,只是被分工**。

路径二:`cluster.broken_pk_total = sum(bo.broken_peaks.num_peaks for bo in cluster.bos)`。**簇 row 持有 BO 列表,sum 一行解决**。`broken_peaks` 是 BO 的元数据,簇是 BO 的容器,容器对其成员的元数据做 reduce 是**最自然的数据建模**。

第一性视角:为什么路径一要绕?**因为路径一的 EventChain 抽象被限制在"t-indexed series"范畴**(搭档原文:"两个范畴的乘积")。这个限制是**架构选择带来的**,不是问题本身的限制。问题本身根本不需要"t-indexed series"这个抽象 — 簇就是一组 BO,**对 BO 列表做 reduce 是 Python list comprehension 一行能写的事**。路径二让事件 row 直接持有成员列表,所有 reduce 都是一等操作,**没有"两个范畴"的张力**。

### 特征 5 — 簇内放量

- 路径一:`vol_spike.where(is_bo).groupby(cluster_id).transform('any')` 然后广播。注意还要在 EventChain 里把"放量"这个 BO-local 属性转成 series。`.where(is_bo).transform('any')` 这个组合是**在用 series 抽象模拟一个 OR-reduce-over-cluster-members**
- 路径二:`cluster.has_vol_burst = any(bo.vol_spike for bo in cluster.bos)`,**一行**

再次:路径一在用 SQL/series 范式模拟"对成员列表做 reduce",路径二里这就是 list 操作。

### 特征 6 — 簇前未超涨

- 路径一:`first_bo_pos = (... .where(is_bo).groupby(cluster_id).transform('first'))` + `ret_M.shift(1).iloc[first_bo_pos]` + 再广播。**四步**
- 路径二:`cluster.pre_cluster_overshoot = ret_M_at(cluster.first_bo_idx - 1)`,**一步**

### 特征 7 — 簇之后稳定到平台(关键证据,绕路最严重)

路径一不可能优雅闭合这一条。原因:

1. 平台形成是**簇结束之后的 K 天事件**。BO 当日不可知 → 必须 lookforward
2. lookforward 因子在路径一的因子注册表里需要三态(unknown / true / false)
3. 三态语义在 mining 时要 mask 掉 unknown,在 live 信号语义里要做 partial→confirmed 二段
4. 这个 lookforward 因子要广播到簇内**所有 5 行 BO**,每行 BO 都拥有"簇结束后是否平台"这个未来标签 — **这个标签和 BO 当根没有任何关系**,它和簇有关系。把它挂在 BO row 上,**语义错配**

路径二:`cluster.post_platform = detect_platform_after(cluster.last_bo_idx, K)`。**簇结束 + K 天**就是簇 row 的字段消费时刻。决策时刻 = 簇 row 落地时刻 = 平台判定时刻,**没有 lookforward 三态,没有 partial→confirmed,没有跨成员广播**。

第一性观察:**lookforward 三态本身就是路径一架构的副产物**。它存在的理由是"我必须在 BO 当日发一个因子值,但因子语义又依赖未来,所以我得有 unknown 态"。但**这个'必须在 BO 当日发因子值'的前提是路径一的统计单位 = BO 强加的**。统计单位换成簇,因子值的发出时刻换成"簇 row 落地时刻",**lookforward 的'未来'就变成'当下'**,三态消失。

---

## 3. 信号语义:partial vs confirmed 是真需求还是架构副作用

路径一的 live 信号:每个 BO 当日发 partial,K 天后 refresh confirmed。

逼问一句:**用户拿这个 partial signal 干什么**?

- 如果用户基于 partial 下单 → 用户没看到"簇是否真的形成 5 根""平台是否真的确认",这相当于**用未完成的形态做交易决策**,不符合用户描述的 7 特征(特征 4 和 7 都需要"簇结束")
- 如果用户基于 confirmed 下单 → partial signal 在 K 天里只是噪声,用户得忽略它

二选一,**partial signal 都不被产品需要**。它存在仅仅因为路径一的架构(评估单位 = BO,因子在 BO 当日必须有值)**强行要求"BO 当日要有信号"**。

路径二的信号:**平台形成那一刻发一次,以簇为单位,携带簇的全部因子**。这与"用户实际想做什么"完全对齐 — 用户在那一刻看到完整的形态,做出 1 次决策。

**没有 partial→confirmed 二段语义,不是路径二缺失了什么,而是这个二段语义本来就是路径一架构的副作用,问题本身不需要**。

---

## 4. "BO 是被审视者"是不是真的

用户原话:"连续突破的判断是比 BO 更高一层的事件,BO 成为被审视者"。

搭档对此的回应(`higher_event_on_entrance1.md` §1):

> "用户视角:簇是 first-class 事件,BO 只是簇的成员,应该有'簇 row'。入口一工程视角:评估单位仍然是 BO(每个 BO 一行),只是 BO 上多挂几个'以簇为视角的统计量'作为因子。这两个描述在数学上等价。"

**"在数学上等价"是 OOP 与 Relational 的等价,不是语义等价**。任何"实体 + 一对多容器"关系都可以被打平成"成员 row + 容器属性广播",这是 SQL denormalization 的标准操作。但 denormalization **不改变语义本体**,只是降维存储。问题是:**这个降维存储正确吗**?

判断标准:如果"簇"在产品语义里是一个**独立判断对象**(用户问"这个簇好不好""这个簇值不值得交易"),那它**就应该是一个一等公民 row**。把它打平成"BO row 上的标签"是**让审视者(簇)变成被审视者(BO)的属性**,**层级倒置**。

路径一里"BO 是被审视者"是修辞 — 实际上 BO 仍然占据 row 中心,簇属性是 BO 的标签。审视者(簇)在哪里?**没有实体,只是 groupby 出来的中间状态**。每次需要簇属性都要重做 groupby + broadcast,**簇没有持久身份,没有 PK,没有可被追溯的 row**。

路径二里 BO 是真的被审视者 — 簇是 row,簇有 PK(cluster_id),簇持有 `bos: List[BO]`,任何对簇的查询(它有几根 BO?它的 first_drought?)都是对簇 row 的字段访问,**不需要重做 groupby**。

第一性问题:**事件能不能被命名、被持有、被传引用、被 reduce、被 join**?路径一里簇不能;路径二里簇能。这就是"一等公民"的实质区别。

---

## 5. 三级派生:扩展性的本质考验

用户已经暗示未来需求:**BO → 平台 → 二次确认 step**。三级派生事件。

路径一上怎么做?

- 平台是 BO 之后 K 天的事件 → BO row 上挂 `lookforward_platform`(三态)
- step 是平台之后 M 天的事件 → BO row 上挂 `lookforward_platform_then_step`(也是 lookforward,但 baseline 是平台时刻)
- **第二层 lookforward 的 baseline 不是 BO 当日,是平台形成日**。但路径一的因子注册表是 BO-anchored 的,所有因子的"当下"都是 BO 当日 → 第二层 lookforward 在 BO 当日要等 K+M 天
- 三态变七态?(BO 后 platform unknown / true / false × platform 后 step unknown / true / false / N/A)语义闭合度急剧下降

路径二上怎么做?

- 簇 row 派生 platform row(`platform = cluster.after(K).detect_platform()`)
- platform row 派生 step row(`step = platform.after(M).detect_step()`)
- 每一级 row 都有自己的"当下"(落地时刻),每一级 row 都是一等事件,**EventChain.after() 算子是组合运算符**

**三级派生在路径一是 lookforward 的 lookforward,组合性不闭合**;在路径二是事件链的链式扩展,**组合性自然闭合**。

第一性观察:**lookforward 在因子注册表里是个例外机制**(它打破了"因子是 BO 当下可计算量"的契约,引入三态);**事件 row 链式派生在路径二里是常规操作**(每级 row 落地时刻就是其因子的"当下")。**例外机制不能组合,常规操作能组合**。这是建模水平的差距,不是工程偏好的差距。

---

## 6. 承认路径二的劣势,但论证它们更不本质

诚实承认:

1. **路径二在"BO-local 标量因子"(特征 1 类)上没有简化收益** — BO-local 的事情在哪种架构下都是 BO 因子,路径二把它放进 cluster.bos[0] 的属性也只是包装。**对这一类没有架构红利**
2. **路径二的事件 row 数比 BO row 数少** — mining 时单个簇就是 1 行,样本数变少。但这是**正确的样本数**,统计上更诚实。路径一虚增样本数让 mining 看起来"数据多",这是**自欺**
3. **路径二在 live 端等簇结束 + 平台确认才发信号** — 信号延迟 K+M 天。但这个延迟**不是路径二的问题,是 7 特征的真实决策时刻就在那一刻**。路径一发 partial 提早通知不解决问题(用户不能基于 partial 下单),只制造噪声

这三点的共同点:**它们是问题本身的属性**,不是架构选错带来的额外代价。路径一的"提前通知""样本多""BO-local 简单"都是**用错配换便利**,代价记在了 mining 的伪相关、信号的二段语义、特征 4 和 7 的跨层绕路上。

---

## 7. 综合判定

**问题本身**(7 特征复合形态)的形状是:

- 评估单位 = 簇 + 后续平台(1 个事件)
- 决策时刻 = 平台确认那一刻(1 个时刻)
- 因子集合 = 簇内 reduce(BO 数、首 drought、累计破 pk、簇内放量)+ 簇前 baseline(超涨)+ 簇后派生(平台)

**路径二与这个形状同构**:1 簇 1 row,1 个落地时刻,因子是 row 的字段,簇后派生是事件链的下一级 row。

**路径一与这个形状不同构**:N 个 BO N 行,K+N 个 partial signal 时刻,簇属性靠广播,簇后派生靠 lookforward 三态,特征 4 靠跨层 reduce。每一处"靠"都是**填补抽象错配的补丁**。

第一性结论:**当问题的本体是高层事件时,把高层事件作为一等公民 row 是更优雅的建模**。这不是新观点,是 ER 建模的标准答案 — **如果"簇"是用户语言里的一个名词,在数据模型里它就应该是一个表**。路径一把它压成"BO 表的几列广播标签",是**为了既有架构延续而做出的妥协**。在"不考虑改造成本"的前提下,这个妥协**没有第一性原理上的辩护**。

---

**报告结束**。
