# Path 2 #3 设计稿:stdlib 标准 PatternDetector(Chain / Dag / Kof / Neg)

> 日期:2026-05-16 · 上游:roadmap #3 · brainstorming 产出
> 范围声明:Path 2 是独立的多级事件表达框架,**与 mining / TPE / 因子框架 / Condition_Ind 等概念无关**,本设计严禁引入。
> 协议层(`path2/`)已冻结;本设计**不改协议层任何字段/类型**,只在其上叠 stdlib。
> 决策依据:四轮第一性原理裁定(根基方向 → 产出类 → 算法心脏 → 范围边界)。

---

## 0. 目标与定位

stdlib 提供**消费 `TemporalEdge` 声明的标准 PatternDetector 系列**,带最优实现,**用户只写声明(edges),不写实现**(2026-05-15 用户明确,spec §7.1)。

- 用户写**声明**:`edges: list[TemporalEdge]` + 每个角色一条事件流。
- stdlib 跑**执行**:标签解析 → 多路单调归并 → 约束推进 → 产出聚合事件。
- 同一份 `edges` 可喂不同 Detector(Chain/Dag/...),实现策略不同,**语义统一**。

四种 Detector = **一个核心算法的四种约束形态**:Chain=线性偏序、Dag=偏序、Kof=k-of-n 边松弛、Neg=偏序+排除谓词。Chain 是 Dag 加严校验的退化特例。

---

## 1. 根基裁定:`earlier`/`later` 是声明期标签,不是 event_id

### 1.1 矛盾与裁定

spec §1.3 把 `TemporalEdge.earlier`/`later` 注解为 "event_id"。但 pattern 声明发生在**跑数据之前**,此刻无任何实例存在 —— 用户能引用的只能是**声明期稳定的角色标签**。这是因果时序硬约束,不是设计偏好。

**裁定**:`earlier`/`later` = **端点标签(endpoint label)**,声明期稳定、用户可知的角色标识。这是 spec §1.3 的**单点表述缺陷**(证据:spec §1.1.1 推荐 event_id 格式 `<kind>_<idx>`,作者潜意识里指的就是 kind 前缀段)。

- 协议层语境与 stdlib 消费语境**同一含义**,不分裂语义、不引新概念。
- `TemporalEdge` 字段名 / 类型 / frozen / gap 公式 **全部不动**。
- spec §1.3 **只改文字注解**,并入 roadmap #2(v0.2 正式修订),不单开 cycle。详见 §7。

### 1.2 三段标签解析(4 种 Detector 共享前置层)

PatternDetector 把"标签"解析为运行期实例流,优先级:

| 优先级 | 机制 | 场景 |
|---|---|---|
| 1(默认主路径) | **具名流绑定** `Chain(A=sA, B=sB, edges=[Edge('A','B')])` | 每角色一条独立流(dogfood 现实:用户本就分别持有两条 generator),零样板 |
| 2(逃生舱) | **key 函数** `key=lambda e: e.role` | 多角色挤在单条合并流里 |
| 3(降噪兜底) | **类名 / pattern_label 默认** | positional 传流且来源类各不同时,连 kwarg 都不用写 |

- 解析结果 = `{label: 物化列表}`,每个列表按 `end_idx` 升序(输入流本就 §1.2.2 升序,物化后稳定)。
- **冲突一律构造期报错**(`ValueError`,"构造点拦截"哲学,与协议层 §9.3 bool 决议同源):
  - edges 出现的 label 解析不到唯一来源 → 报错。
  - positional 传流且两条流事件类名相同(同类不同角色)→ 报错,强制用户改 kwarg 显式命名,**绝不静默合并**。
- key 函数返回 label 不在 edges 端点集合 → 默认**宽松**(该事件丢弃,允许"流里有杂事件 pattern 只关心部分角色");可选严格模式报错。严格/宽松默认值在 spec 正文拍(默认宽松)。

---

## 2. 产出类:单一 `PatternMatch(Event)`

4 种 Detector **全产出同一个 frozen Event 子类**。每 Detector 专属子类(ChainMatch/...)被否决:它把"哪种算法拼出的"这种运行期实现细节固化进声明期类型系统,而下游穷举只有 4 项消费需求(时间区间 / 成员 / 按角色回查 / 溯源),无"需要知道是 Chain 还是 Kof"的第五项。专属子类 = 单一类 + 一个无人消费的类型分叉。

### 2.1 字段

```python
@dataclass(frozen=True)
class PatternMatch(Event):
    # 协议层继承:event_id, start_idx, end_idx
    children: tuple[Event, ...]                       # 命中实例,按 start_idx 升序(§3.3)
    role_index: Mapping[str, tuple[Event, ...]]       # 标签 → 该标签命中实例,值恒为 tuple
    pattern_label: str                                # 声明期溯源标识
```

### 2.2 关键裁定

- **`role_index` 值恒为 `tuple`**:Chain 命中 1 个也返回长度 1 的 tuple。理由:Kof 一标签多命中;若 Chain 返裸 Event、Kof 返 tuple,下游须按 Detector 类型分叉 → 统一类型当场失效。**字段类型必须跨 4 Detector 恒定**(底线)。代价:Chain 用户写 `match.role_index['B'][0]`;#4 可加 `single(label)` 糖(命中≠1 报错)降噪,但**不进协议/产出类**。
- **回查接口形状**:属性 `match.role_index['B']`,不是 `match['B']`(避免 `__getitem__` 与 frozen dataclass 属性心智 / 未来序列化语义冲突)。
- **`pattern_label` 解决方向 1 嵌套硬伤**:4 种都产出 `PatternMatch` 类 → 嵌套时"类名默认"失效。解法:`pattern_label` 由**用户声明时给**(`Chain(..., label='vol_buildup')`,属声明非实现),三段解析精化为"PatternMatch 用 `pattern_label` 替代类名默认"。未给则按 Detector 种类默认 `'chain'`/`'dag'`/`'kof'`/`'neg'`;嵌套同种未命名 → 构造期报错并给清晰引导信息(逼用户命名,与 §1.2 冲突规则自洽)。
- **不存 edges/trace**:edges 是声明(Detector 构造参数),不属产出事件。`pattern_label` 足够回指声明;细粒度"哪条 edge 怎么匹配"是调试需求,走可选 debug 旁路,不污染 frozen 产出类。
- **一致性不变式(构造期校验,违反 `ValueError`)**:`set(flatten(role_index.values())) == set(children)`;children 按 start_idx 升序(§3.3);role_index 各 tuple 内部也按 start_idx 升序。两视图永不漂移。
- **已知表达力边界(spec 须显式声明防误用)**:`role_index` 是"时序集合"非"匹配序列"——按 start_idx 升序,不保留匹配轨迹顺序。要匹配轨迹走 debug 旁路。

### 2.3 event_id 默认生成器

- **归属**:#3/#4 **共享 stdlib 件** `default_event_id(kind: str, start_idx: int, end_idx: int) -> str`。#3 spec 内联 5 行私有桩实现契约,#4 落地后替换为共享件,**签名冻结不变** → 零改 #3。
- **格式**:`f"{kind}_{start_idx}_{end_idx}"`,kind = `pattern_label`,沿用 dogfood `vc_{s}_{e}` 惯例。
- **run() 单次唯一性**:Chain/Dag/Neg 在 earliest-feasible + 非重叠下 (start,end) 区间天然不重复 → `{label}_{s}_{e}` 足够。**Kof 例外**:同窗口选不同成员可产出 (s,e) 相同的不同匹配 → 追加单调序号 `#<seq>`(`kof_30_45`、`kof_30_45#1`)。seq 是 `detect()` 内局部计数器(协议 §1.2.4 状态局部于 detect(),单 run 唯一天然成立;跨 run 不要求,符合 §1.1.1)。常态(无撞)id 仍是干净的 `{label}_{s}_{e}`。
- **已知边界**:Kof `#<seq>` 兜底使 event_id 跨 run 不稳定;协议 §1.1.1 只要求单 run 唯一,不违约;远期 #7 流水线若需跨 run 稳定 id,此处需重审。现记为已知边界,不阻塞 #3。

---

## 3. 四种 Detector:语义 + 最优实现

### 3.0 通用前置层(4 种共享,#3 自包含)

1. 标签解析(§1.2 三段规则)→ `{label: 物化列表}`。
2. edges 拓扑构建:`edges` → 有向图 `G`(节点=label,边=TemporalEdge 带 min_gap/max_gap)。
3. 构造期静态校验(违反 `ValueError`):见各 Detector。
4. 约束推进:四种各异(§3.1~§3.4)。

**Chain = Dag + "线性"构造期断言**:核心写 Dag 推进,Chain 复用并加严校验。这是 #3 单一实现的支点。

### 3.0.1 edges 拓扑约束 + 构造期校验

| Detector | edges 必须构成 | 构造期校验(失败即 ValueError) |
|---|---|---|
| **Chain** | 单一线性路径:节点入度≤1、出度≤1,弱连通,恰一源一汇,无环 | 任一节点入/出度 >1 / 不连通 / 有环 → 报错 |
| **Dag** | 任意 DAG(多入度多出度、多源多汇) | 环(拓扑排序失败)/ 孤立节点 → 报错 |
| **Kof** | 节点集 + 候选 edge 集(edges 端点定义 n 个 label) | k 未声明 / k<1 / k>边数 / 端点 label 数<2 → 报错 |
| **Neg** | 正向子图(Chain 或 Dag 形态)+ ≥1 条否定 edge | 正向子图按 Chain/Dag 校验;无否定 edge / 否定 edge 的 later 不在正向子图 → 报错 |

### 3.1 Chain

- **语义**:线性路径 `L1→...→Lm`。一次命中 = 实例序列 `(e1∈L1,...,em∈Lm)`,每条相邻边 gap 满足 `min_gap ≤ e_{i+1}.start_idx - e_i.end_idx ≤ max_gap`。
- **锚定** = earliest-feasible + 非重叠贪心:从最早 e1 起锚,每节贪心取满足前一节 gap 的**最早可行实例**;凑齐 m 节产出一个 PatternMatch,下次起锚从所有已用实例之后继续。**一起锚一匹配,不枚举组合**(枚举是 Kof 的事)。
- **最优实现**:单调双指针 O(ΣN)。m 个游标各指物化列表;`e_i` 定后 `p_{i+1}` 单调右移到首个满足 min_gap 处,检查 max_gap;超界则 e1 指针 +1 重试;凑齐则所有指针跳到已用实例之后。earliest-feasible + min_gap 单调 ⇒ 指针**永不回退** ⇒ 线性。
- **封口**:跨匹配成员严格后移 ⇒ 产出 end_idx 天然单调不减 ⇒ 凑齐即可 yield,**零缓冲**。

### 3.2 Dag

- **语义**:为每节点选一实例使**所有边** gap 同时满足。多入度节点 `c`(`a→c`,`b→c`):start_idx 下界 = `max(各前驱.end_idx + min_gap)`,上界 = `min(各前驱.end_idx + max_gap)`;下界>上界则起锚失败。
- **锚定**:earliest-feasible 推广到拓扑序,非重叠贪心,一起锚一匹配。多源 DAG:多个入度 0 节点各起锚指针,按"所有源实例 max end_idx 最早"贪心。
- **最优实现**:拓扑序(构造期算好可缓存)+ 区间剪枝。节点 v 可行 start 区间 = ∩(各已定前驱施加的 [u.end+min_gap, u.end+max_gap]);指针单调右移到下界,超上界则回溯到最近"有备选"的源指针 +1(回溯受非重叠+单调约束,均摊近线性)。复杂度 O(ΣN·d),d=最大入度(实务 2~3)≈O(ΣN)。
- **封口**:end_idx = max(成员 end_idx);earliest-feasible+非重叠下产出 end_idx 单调不减 ⇒ **零缓冲**。

### 3.3 Kof

- **k 与 edges 关系裁定**:**n = edges 条数**(非端点数),k = 至少需满足的 edge 条数。每条 TemporalEdge 是一个二元时间约束命题,k-of-n 是对命题集的阈值。把松弛单位定在"边/约束"上无歧义(边不满足就是不满足);定在端点数会产生"label 缺席怎么算"的歧义。声明:`Kof(k=3, edges=[e1..e5], **streams)`。
- **语义**:为所有出现的 label 各选一实例(同 Dag 选取),使 edges 中**任意 ≥k 条** gap 满足(另 ≤n−k 条可违反)。不指定具体满足子集(指定子集 = 用户用多 Dag + 上层 OR 表达,非 Kof 职责)。
- **锚定**:earliest-feasible 选实例 + 非重叠贪心。松弛 ⇒ 同窗口不同组合可给不同"满足 k 条"解 ⇒ event_id `#<seq>` disambiguator 场景来源(§2.3 闭合一致)。
- **最优实现**:无法纯单调双指针(松弛破坏"全满足"单调前提)。按 end_idx 滑动窗口推进(窗口=当前起锚到 max_gap 视界),窗口内对 n 条 edge 做满足性计数,≥k 产出。复杂度 O(ΣN·n),n=边数(常数级)≈O(ΣN)。
- **封口**:**4 种里唯一非平凡**。松弛意味"再往后可能出现满足更多边、end_idx 更小但起锚更晚"的匹配。裁定:**窗口右界封口**——`detect()` 处理到的输入 end_idx 越过某锚 max_gap 视界,该锚最优解已定,封口 yield。需**有界小缓冲**(深度 = max_gap 跨度内匹配数,非全量),产出前按 end_idx 排序弹出。不破坏流式与 O(ΣN·n)。

### 3.4 Neg

- **否定性如何声明**(不动冻结 TemporalEdge 硬约束下):**不给 TemporalEdge 加"否定"标记字段**;否定性由**声明结构**承载。裁定:`Neg(edges=[...正向...], forbid=[...否定 TemporalEdge...], **streams)`。`forbid` 里复用同一冻结 TemporalEdge,语义被 `forbid` 参数位置翻转为"不允许存在"。**协议层零改动**,与"语义由消费方赋予,协议只认结构"的根基裁定同构。
- **forbid 中一条 `TemporalEdge(earlier='A', later='N', min_gap, max_gap)` 语义**:正向匹配里扮演 A 的实例 `e_A` 定后,**不存在**任何标签 N 实例 `e_N` 满足 `min_gap ≤ e_N.start_idx − e_A.end_idx ≤ max_gap`;存在即该匹配作废。
- **never_before**:"A 之前 W 内不得有 N" = `forbid=[TemporalEdge(earlier='N', later='A', min_gap=0, max_gap=W)]`(语义="不存在 N 使 A 在 N 后 W 内"="A 前 W 无 N")。gap 公式 `later.start - earlier.end` 原样复用,无新公式。
- **N 的实例不进 children/role_index**(否定标签是排除条件非匹配成员;§2.2 已定,此处闭合)。`role_index` 只含正向标签。
- **最优实现**:先按正向子图(Chain/Dag)跑候选匹配 O(ΣN);对每候选每条 forbid edge,在否定标签物化列表上双指针检查区间内是否存在实例(指针随候选 end_idx 单调前移 → O(ΣN_neg) 全程)。存在则丢弃,全 forbid 通过则产出。总 O(ΣN)。
- **封口**:不改正向 end_idx,只做通过/丢弃过滤;正向升序产出过滤后仍升序 ⇒ **零缓冲**。

### 3.5 "输入物化、输出有序流"调和

| Detector | 产出 end_idx 天然升序 | 缓冲 | 封口判据 |
|---|---|---|---|
| Chain | 是(earliest-feasible+非重叠⇒成员严格后移) | 零缓冲 | 凑齐 m 节即 yield |
| Dag | 是(偏序保持不变式) | 零缓冲 | 所有节点定下即 yield |
| Neg | 是(继承正向,谓词过滤不改序) | 零缓冲 | 正向封口 + forbid 通过 |
| **Kof** | **否**(松弛破坏单调) | **有界小缓冲**(max_gap 限界) | 输入 end_idx 越过锚 max_gap 视界 |

输入物化只为前瞻(吃掉 dogfood §5 头号痛点:用户不再手写 `list(spikes)`+贪心),不影响输出有序。earliest-feasible 锚定的决定性价值 = 让 Chain/Dag/Neg 产出顺序自动等于 end_idx 升序,§1.2.2 零成本满足。Kof 唯一例外但缓冲被 max_gap 严格限界,不退化为全量。"输入物化、输出有序流"**不阻碍任何最优实现**。

---

## 4. 公开 API 形状

四个 Detector 类统一签名骨架(`path2/stdlib/` 下新建,经 `path2/__init__.py` 出口):

```python
Chain(*positional_streams, edges=[...], key=None, label=None,
      anchoring='earliest-feasible', **named_streams)
Dag  (*positional_streams, edges=[...], key=None, label=None,
      anchoring='earliest-feasible', **named_streams)
Kof  (*positional_streams, edges=[...], k=<int>, key=None, label=None,
      anchoring='non-overlapping-greedy', **named_streams)
Neg  (*positional_streams, edges=[...], forbid=[...], key=None, label=None,
      anchoring='earliest-feasible', **named_streams)
```

- 均实现 `Detector` 协议:`detect(self, source) -> Iterator[PatternMatch]`,经 `run()` 驱动。
- `anchoring` 默认值拍死(Chain/Dag/Neg=`earliest-feasible`,Kof=`non-overlapping-greedy`,沿用 dogfood VolCluster 已验证贪心),均允许显式覆盖。dogfood §5 第二痛点闭合。
- 构造期(`__init__`)做全部静态校验(拓扑、标签解析可行性、k 范围、forbid 存在性、环检测)。

---

## 5. 范围边界(#3 单一 plan 可覆盖,不溢出)

### 5.1 #3 自包含

1. `PatternMatch(Event)` 产出类 + 构造期一致性校验。
2. 四个 Detector 类 + 通用前置层(三段标签解析、edges 拓扑构建、构造期静态校验)。
3. 四套约束推进算法(§3.1~§3.4),含 Kof 有界缓冲封口。
4. 锚定语义实现(earliest-feasible / non-overlapping-greedy)+ 显式覆盖。
5. 内联 `default_event_id` 私有桩(契约 `(str,int,int)->str`)。

### 5.2 #3 跨界依赖(唯一)

| 件 | 归属 | #3 依赖契约 |
|---|---|---|
| `default_event_id(kind,s,e)` | #4(#3/#4 共享) | `(str,int,int)->str` 返回 `f"{kind}_{s}_{e}"`。#3 内联 5 行桩;#4 落地替换,签名冻结 → 零改 #3 |
| `single(label)` 糖 | #4 | **非 #3 依赖**(纯下游消费糖,#3 只产 role_index) |
| 流 merge helper | #4 | **非 #3 依赖**(多源归一是用户/输入侧职责,#3 只接受每 label 一条升序流) |
| 常用 Event 类 / Detector 模板 | #4 | **非 #3 依赖**(#3 消费任意 Event 子类,测试用桩 Event 即可,dogfood 已证) |

**#3 唯一真实跨界依赖 = `default_event_id` 一个函数契约**,内联桩先行 → #3 完全独立实现与测试,范围不溢出。

---

## 6. 测试策略

- 单元:每 Detector 的 edges 拓扑校验(合法/各类非法报错)、标签解析三段优先级 + 冲突报错、锚定语义、封口/yield 顺序(§1.2.2 升序)。
- 算法正确性:用纯测试桩 Event(类比 dogfood VolSpike/VolCluster,**不进 path2 包**)构造已知形态,pin 死匹配结果。
- 复杂度回归:构造放大输入,断言指针移动 / 缓冲深度 O 界(Kof 缓冲 ≤ max_gap 跨度)。
- 不变式:`run()` 驱动下 end_idx 升序、event_id 单 run 唯一(含 Kof `#<seq>` 路径)、role_index/children 一致性。
- Neg:正向命中但被 forbid 否决的用例 + never_before 特例。

---

## 7. spec 回写动作(并入 roadmap #2,不单开 cycle)

- §1.3 `earlier`/`later` 注释:"较早事件的 event_id" → "较早/较晚**端点的标签(endpoint label)**",声明期稳定角色标识;标签到运行期实例的绑定由消费方(stdlib PatternDetector)规定,协议层不约束。
- §1.3.1 gap 公式**不变**(`gap = later.start_idx - earlier.end_idx`,这里 later/earlier 指被解析到该标签的具体实例,公式天然成立)。
- §7.1 补一句:标签解析机制(流绑定/key/类名默认)属 stdlib,协议层只认标签是不透明字符串。
- 字段名 `earlier`/`later`、类型、frozen、可作 dict key **全部不动**。

---

## 8. 待 plan 阶段细化(非本设计决策项)

- `path2/stdlib/` 包内模块切分(单文件 vs 按 Detector 拆)。
- 构造期校验的具体异常信息文案。
- `anchoring` 显式覆盖支持哪些可选值(本设计只定默认值)。
- key 函数严格/宽松模式的开关参数命名(本设计定默认宽松)。
- 与协议层既有算子(`Before/After/...`)/`Pattern.all` 是否需互操作示例(教学项,可推迟到 #6)。

---

**设计稿结束。** 下一步:写实现 plan(`superpowers:writing-plans`)。
