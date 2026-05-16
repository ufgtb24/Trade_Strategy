# Path 2 stdlib 约束推进核心算法重设计

> 日期:2026-05-17 · 上游:`docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md`(下称 design)+ `docs/research/path2_spec.md`(下称 spec,协议层,冻结)
> 产出方:`path2-algo-redesign` agent team(architect 提案 / adversary 证伪 / guardian 协议一致性把关 + 本文档编纂),team-lead 裁定。
> 范围声明:Path 2 是独立的多级事件表达框架,**与 mining / TPE / 因子框架 / Condition_Ind 等概念无关**,本文档严禁引入。
> 性质:纯设计文档。**不含任何仓库代码,不改协议层(`path2/` 冻结),不改 spec(无 §9 条目)。** 所有改动落在 stdlib 实现与 design / plan 文本。

---

## 0. 背景与结论

design §3 原定的"单调双指针 O(ΣN) 永不回退"约束推进核心(落地于 `path2/stdlib/_advance.py` 的 `advance_dag`)经逐行审查与可执行复现,确认存在 **5 个根缺陷**:4 个会丢失合法匹配 / 违反协议(CRITICAL-1..4),1 个在重复事件下指针错位(IMPORTANT-1)。本文档:

1. 列出 5 个根缺陷 + 各自**已执行复现**的失败用例与修正后期望输出(回归锚)。
2. 给出修正后的匹配语义(含 `earliest-feasible` 的精确定义)。
3. 给出修正后的核心算法(LEF-DFS,散文 + 伪代码,**无仓库代码**),含 INV-A / INV-B / INV-C 三态分离。
4. Chain / Dag / Kof / Neg 在同一核心上的分层。
5. 复杂度(诚实账:Chain 近线性;病态 DAG 时间与空间同为指数)。
6. §1.2.2 逐 Detector 缓冲分析 + "非重叠全消费"作为承重不变式。
7. §1.2.4 event_id 单 run 唯一性机制。
8. 精确的 design / plan 改写范围;spec 保持不动。

> **mode-ii 澄清(team-lead 裁定,记录以防重启争论)**:迭代过程中曾假设存在一个独立的"多源 mode-ii"失败模式(scan 指针在不可行窗口被推进后跨回溯携带)。逐行审查 `_advance.py` 与可执行复现(CHECK-3,见 §1 CRITICAL-2)证明:`lo>hi` 守卫在 scan 之前,该机制在现行代码中不可达;所有被举出的"多源丢匹配"复现都由 **CRITICAL-2** 完整解释,不是独立根因。**最终缺陷集恰为 5 个根缺陷;CRITICAL-4 为单模式(mode-i)。** 不设第 6 个缺陷,不设独立 latent-risk 围栏。

---

## 1. 5 个根缺陷:旧算法为何失败

旧 `advance_dag` 结构(供定位):拓扑序逐节点赋值;源节点取 `ptr[源]`;非源节点窗口 `lo=max(pred.end+min_gap)`、`hi=min(pred.end+max_gap)`;**先判 `lo>hi` 失败 break(L68-70),再 scan**`while lst[i].start_idx < lo: i+=1` 然后 `ptr[v]=i`(L71-74,"永不回退"),再判 `start_idx>hi`(L75-77);成功则 yield 并对所有用到的标签做 `streams[lab].index(e, ptr[lab])+1`(L80-85);失败则只推进 `sources` 中第一个仍有备选的源 `ptr[s]+=1` 并 `break`(L88-95)。

### CRITICAL-1 — 源-only 回溯不完整(中间节点备选从不探索)

失败 break 时只推进源指针;非源节点一旦选定 earliest 实例就不再尝试它的后续备选。三节点链 `A→B→C` 中,若 `A=e1` 固定、`B=b1` 满足 A 的 gap 但导致 C 无解,算法不会回退去试 `B=b2`,直接判 A 失败前进 `ptr[A]`,丢失合法的 `(e1,b2,c1)`。

- **执行复现(钉死回归锚,canonical)**:`edges=[A→B(0,_), B→C(0,1)]`;`A=[ev(0)]`,`B=[ev(0), ev(1)]`,`C=[ev(2)]`(`ev(x)` 即 `start=end=x`)。`B→C(0,1)` 需 `C.start − B.end ∈ [0,1]`,`C` 仅 `ev(2)`,故需 `B=ev(1)`(索引 1);但源-only 回溯下 earliest `B` 取索引 0 `ev(0)`,`C` 无解,`A` 耗尽 → `[]`。地面真值:`{A0, B1, C2}` 唯一。**修正后期望**:1 个 `PatternMatch`,`children=(A(0,0), B(1,1), C(2,2))`,`start_idx=0`,`end_idx=2`。
- **等价复现(说明用)**:`edges=[A→B(0,0), B→C(0,0)]`;`A=[ev(0,0)]`,`B=[ev(0,1), ev(0,3)]`,`C=[ev(3,4)]`;同理 `B` 须取索引 1 而 earliest 取索引 0 → `[]`;修正后 `{A(0,0),B(0,3),C(3,4)}`。两者皆证 CRITICAL-1;回归套件钉前者。

### CRITICAL-2 — 多源只回溯第一个源

`for s in sources: if ...: ptr[s]+=1; break` 只推进拓扑序里第一个仍有备选的源即 `break`;其余源指针永不独立回溯。多源 DAG 丢匹配。

- **执行复现 A(钉死回归锚,canonical-简单)**:`edges=[A→C(0,_), B→C(0,3)]`;`A=[ev(0)]`,`B=[ev(0), ev(9)]`,`C=[ev(10)]`。`B→C(0,3)` 需 `C.start − B.end ∈ [0,3]`,`C` 仅 `ev(10)`,故需 `B=ev(9)`(索引 1);源-only 回溯只推进第一个源 `A`,`ptr[B]` 永不前进 → `[]`。地面真值:`{A0, B9, C10}` 唯一。**修正后期望**:1 个 `PatternMatch`,`children=(A(0,0), B(9,9), C(10,10))`。
- **执行复现 B(钉死回归锚,CHECK-3 验证)**(已对真实 `advance_dag` 运行,见 CHECK-3 脚本):`edges=[A→C(1,3), B→C(0,0)]`;`A=[ev(0,1), ev(1,3), ev(4,5)]`,`B=[ev(0,1), ev(1,1), ev(5,6)]`,`C=[ev(3,3), ev(3,6), ev(6,7)]`。真实 `advance_dag` 返回 `[]`。
- **地面真值**(穷举 + 精确 gap 公式,**忽略非重叠**):2 个可行赋值 — `{A(1,3), B(5,6), C(6,7)}`、`{A(4,5), B(5,6), C(6,7)}`。**注意二者共用 `B(5,6)` 与 `C(6,7)`(三成员中两成员重叠)**。
- **根因**:`B` 被钉在索引 0 `ev(0,1)`(`B.end=1`),源-only 回溯只推进第一个源 `A` 并 break,`ptr[B]` 永不前进;故 `hi=min(A.end+3, 1+0)=1`,所有 `C.start∈{3,6}>1`,恒无解。匹配需 `B=ev(5,6)`(索引 2),不可达。
- **CHECK-3 隔离实验(裁定依据)**:在现行代码上**只**修 CRITICAL-2(穷举所有源索引组合 = 完整多源回溯),**故意保留**"永不回退" scan 指针不动、保持 `lo>hi` 在 scan 之前的忠实顺序 → 两个地面真值赋值全部恢复。结论:该 `[]` **完全由 CRITICAL-2 造成**,与任何 scan 指针携带无关。这同时证明了 mode-ii 假设在现行代码上不成立(裁定见 §0 注)。**注:CHECK-3 是隔离实验,用穷举枚举且故意不施加非重叠消费,与最终算法语义不同;它证明 `[]` 的归因,不定义最终产出。**
- **修正后期望(回归锚)—— 最终 LEF-DFS + 全成员非重叠语义下**:产出 **1 个 `PatternMatch`**,`children=(A(1,3),B(5,6),C(6,7))`,`start_idx=1,end_idx=7`。理由:lex-min(start-first key)可行 LEF 即 `{A(1,3),B(5,6),C(6,7)}`(`A(0,1)` 无可行 C 被跳过);按 §3.4 INV-B / §6 Part D **全成员非重叠消费**,产出后 `B`、`C` 指针越过 `B(5,6)`/`C(6,7)` 即耗尽,第二个地面真值赋值 `{A(4,5),B(5,6),C(6,7)}` **与第一个重叠两成员,在非重叠序列下不可达**,故不产出。**这仍然完整修复 CRITICAL-2**:旧码返回 `[]`(零匹配),修正核心返回合法的 lex-min 匹配。两个"地面真值赋值"是**忽略非重叠**的可行解集合,非生产序列;生产序列是唯一贪心 LEF(§2.3,非枚举)。**A-C2 回归锚断言 = 恰 1 个匹配 `(A(1,3),B(5,6),C(6,7))`**。

> **历史澄清记录(防重启)**:曾假设此类多源丢匹配是一个区别于 CRITICAL-2 的"mode-ii:scan 指针在 `lo>hi` 不可行窗口被推进后跨回溯携带"。审查 `_advance.py`:`if lo>hi: failed=True; break`(L68-70)**物理上先于** scan 循环(L71-74),不可行窗口下 scan 从不执行、`ptr[v]` 从不被推进;CHECK-3 经验证实 `ptr[C]` 全程为 0。故 mode-ii 在现行代码不可达,被 team-lead 裁定为 CRITICAL-2 的一种表现,不单列。

### CRITICAL-3 — 单 run 内 event_id 重复(违反 spec §1.1.1)

`_emit` 用 `default_event_id(label, s, end)` = `{label}_{s}_{e}`,无消歧。两个区间相同(或值相等)的不同匹配产出同一 `event_id`;`run()`(`path2/runner.py` L30-31)维护 `seen_ids` 集合并对重复 **抛 `ValueError`**。design §2.3 原称"Chain/Dag/Neg 在 earliest-feasible+非重叠下 (s,e) 天然不重复"——**该断言为假**(Kof 显然,且 Chain/Dag/Neg 在值相等实例或同区间不同成员下同样会撞)。

- **执行复现(钉死回归锚,canonical)**:`edges=[A→B(0,0)]`;`A=[ev(5), ev(5)]`,`B=[ev(5), ev(5)]`(值相等实例对)。现行产出 2 个匹配,`event_id` 均为 `"dag_5_5"` → 违反 spec §1.2.4;经 `run()` 驱动时在第二个匹配处抛 `ValueError: event_id 单 run 内重复:dag_5_5`。(更一般地:Kof 同窗口选不同成员、或 Dag 两组不同成员张成同一 `[min start, max end]` 同样撞。)
- **修正后期望(回归锚)**:两个匹配均产出,`event_id` 分别为 `"dag_5_5"` 与 `"dag_5_5#1"`,`run()` 不抛错。

### CRITICAL-4 — 不健全的 start_idx 单调假设(单模式,mode-i)

scan `while lst[i].start_idx < lo: i+=1` 配合 `ptr[v]=i`"永不回退",**假设输入流按 `start_idx` 排序**。但 spec §1.2.2 仅保证按 **`end_idx` 升序** yield(`end_idx` 相同时任意顺序),**从不保证 `start_idx` 有序**。一个起始早但结束晚的长事件会使 `start_idx` 相对 `end_idx` 非单调;scan 在到达窗口内的合法候选前就停下(早停截断),合法匹配被静默丢弃。单边即可触发,与 CRITICAL-1/2 正交。

- **执行复现**(已对真实代码逐行 trace):`edges=[A→B(0,0)]`;`A=[ev(0,0)]`,`B=[ev(5,6), ev(0,7)]`(`B` 按 `end_idx` 升序 6,7 ✓;`start_idx` 非单调 5,0)。`A.end=0`,`B→A` 边 gap∈[0,0] ⇒ `B.start` 必为 0。trace:`lo=hi=0`,`i=0`;`while lst[0].start_idx(5) < 0` → False(i 不动);`ptr[B]=0`;`lst[0].start_idx(5) > hi(0)` → True → 失败。索引 1 的 `ev(0,7)`(唯一合法匹配成员)**从不被检视**。返回 `[]`。
- **地面真值**:`{A(0,0), B(0,7)}` 唯一可行。
- **修正后期望(回归锚)**:产出 1 个 `PatternMatch`,`children=(A(0,0), B(0,7))`,`start_idx=0`,`end_idx=7`。
- **正交性**:单边 `A→B`,无多节点回溯涉及;即使 CRITICAL-1/2 完全修好,scan 早停截断仍丢此匹配 ⇒ CRITICAL-4 与 CRITICAL-1/2 正交,是独立根缺陷。

### IMPORTANT-1 — `.index(e, ptr)` 按值相等返回错误下标

非重叠推进 `streams[lab].index(e, ptr[lab])` 用 `list.index`,按 `__eq__` 匹配。`Event` 是 `@dataclass(frozen=True)` ⇒ 值相等。两个值相等的事件在不同位置时,`.index` 返回**第一个**值相等位置,而非实际被选用实例的真实位置 → 非重叠指针前移到错误位置,后续匹配错乱或重复。

- **执行复现**:任一标签流含两个值相等事件(同 `event_id/start/end` 且业务字段相同),被选用的是靠后那个 → `.index` 返回靠前下标 → `ptr[lab]` 设错 → 同一实例可被再次选用或漏过。
- **修正后期望(回归锚)**:消费按**被选实例的真实整数下标**推进(`ptr[L]=chosen_index+1`),不调用 `.index` / `__eq__`;重复事件下匹配集与不重复时结构一致。

**修正核心对 5 缺陷的覆盖声明**:LEF-DFS(§3)以"任意节点回溯"修复 CRITICAL-1、以"全节点指针独立回溯"修复 CRITICAL-2(因而覆盖上述多源丢匹配)、以"逐 anchor 全后缀新鲜 scan、不跨 anchor 携带 scan 指针"修复 CRITICAL-4 mode-i、以"消费携带整数下标"修复 IMPORTANT-1、以"detect()-局部共享 `seen_ids` + `#<seq>`"修复 CRITICAL-3。

---

## 2. 修正后的匹配语义

### 2.0 逐弱连通分量(WCC)独立处理

- 构造期把 `G` 划分为弱连通分量 `WCC_1..WCC_p`(缓存)。**每个 WCC 是一个独立子问题**:各自的逐标签消费指针、各自的拓扑序、各自的 LEF 贪心序列。
- Detector 输出 = 各分量匹配序列按 emitted `end_idx` 升序的 **p 路归并**。
- 这是 BREAK-1 修复的支点:全成员非重叠消费若跨分量耦合,先耗尽的分量会扼杀其他分量的剩余匹配;按分量独立则各分量完整产出。`p` 是 edges 声明的**数据无关结构常数**(见 §6 缓冲分析)。
- 终止性:每次产出使该分量每个用到的标签指针严格前移 ⇒ 每分量 ≤ ΣN 次产出,无死循环。

### 2.1 输入与可行性

- DAG `G`,节点 = 声明期标签(spec §1.3 的 `earlier`/`later` 在 design §1/§7 已重释为端点标签;本文档不重复,亦不改 spec)。每条边携 `TemporalEdge(min_gap, max_gap)`。
- 每标签 `L` 一条物化列表 `S[L]`,按 `end_idx` 升序(spec §1.2.2 输入侧;`end_idx` 相同任意序)。
- 赋值 `φ: 节点 → 实例`。**可行** iff 每条边 `u→v`:`min_gap ≤ φ(v).start_idx − φ(u).end_idx ≤ max_gap`(精确沿用 spec §1.3.1 gap 公式,**不变**)。

### 2.2 `earliest-feasible` 的精确定义(填补 design 欠定名,非覆盖锁定决策)

> **`earliest-feasible` := 在固定拓扑序上,按 `key(e) = (start_idx, end_idx, position_in_S[L])` 字典序最小的可行赋值。** 即"起始最早,其次结束最早,最后输入位置最靠前"。

- **位置(position)是终极 tiebreak**,使算法**从不依赖输入 `event_id` 的唯一性**(同时为 IMPORTANT-1 提供按真实下标消费的语义基底)。
- **依据**:spec **从未定义**任何 anchoring / `earliest-feasible` 语义(spec §2 的 "anchor" 是 `Before/At/After` 的谓词锚参,与本处无关);design 全文仅以无限定的名字出现"最早 e1 起锚...最早可行实例",**未限定 start 还是 end**;旧代码隐含的 end-first 行为同样**从未被 design 散文授权**。故本定义是对一个**欠定名的填补**,不是对锁定决策的覆盖。
- **验证权威**:design §4 默认锚定声明"沿用 dogfood VolCluster 已验证贪心";`docs/research/path2_dogfood_report.md` §5 第二条明确"**窗口锚定首成员** vs 滑动窗口语义需使用方自决",且 dogfood 实际产出 `vc_60_67`/`vc_264_267` 为**首成员 start** 锚定。这独立佐证 start-first 即已验证语义。Kof 复用同一 key,跨 Detector 规范匹配一致。
- **spec 触碰**:无。**无 §9 条目**(spec 本无 anchoring 定义可"偏离";这是填补 design gap)。

### 2.3 产出与锚定

- 产出按 design §2 锁定形状:单一 `PatternMatch(Event)`,`children` 按 `start_idx` 升序(spec §3.3),`role_index` 标签→升序 `tuple`(即便长度 1),`pattern_label`。形状不变。
- 生产序列:每标签一个消费指针 `ptr[L]`;重复 { 在 `S[L][ptr:]` 后缀上求 LEF;无则停;产出;对**每个**用到的标签 `ptr[L]=被选实例下标+1`(**全成员非重叠消费**)} 。
- 这是**唯一的贪心 LEF 序列,不是枚举**(枚举仅 Kof,design §3.3 不变)。

---

## 3. 修正后的核心算法:LEF-DFS

### 3.1 散文

固定拓扑序。对当前消费前沿后缀,做一次 **LEF-DFS**:按拓扑序逐节点,为节点 `v` 计算窗口 `lo=max_{preds}(pred.end+min_gap)`、`hi=min_{preds}(pred.end+max_gap)`;在 `S[v]` 的**当前消费前沿后缀上做一次新鲜全后缀扫描**,按 `key=(start_idx,end_idx,position)` 序取首个落在 `[lo,hi]` 内的候选并递归;若该选择导致后继无解,**回溯到任意有备选的节点**(不限源),取其 key 序下一个 admissible 候选重试。凑齐全节点即得该 LEF。产出后对每个标签按**被选实例的真实下标**做非重叠消费推进,再求下一个 LEF,直到任一源后缀耗尽。

剪枝:**FAILED 前沿割记忆**(INV-C)。结构事实:一个已选实例只通过其 `end_idx` 影响后继。

- **前沿割签名定义**:`sig_i = ( (u, φ(u).end_idx) | 每个已赋值且为 ≥1 条边 u→w(w 未赋值)的尾端的 u )`,按标签排序。
- **健全性定理**:未赋值节点上的每条约束都是一条边、其已赋值尾端必在割中 ⇒ 相同 `sig` ⇒ 对**所有**剩余节点的可行域完全相同 ⇒ 可完成性相同 ⇒ 记忆健全可剪。(adversary T1 验证:transitive-trap 反例被该签名正确区分,未误剪。)
- 候选级推论:同一 admissible 集合内**只对不同 `end_idx` 递归**(值相等簇塌缩为 1 次探测)。
- 注:早期 v2 曾用"直接前驱"作签名(过粗),会在合法单 WCC DAG 上误剪合法分支(BREAK-V2-1);前沿割签名是 adversary 攻破后的修正,见 §8.5 回归套件。

### 3.2 五步规范节点访问过程(C-ORDER / C-SCAN / C-KEY,**MUST**)

> 这三条是 **stdlib 实现-正确性不变式**,归属 design 文档 + plan Task 5 的规范节,**不进 spec**(spec 只定 schema)。它们**不可被冻结协议层运行时检查捕获**——见 §3.4。

访问节点 `v`:

1. 计算 `lo / hi`(精确 gap 公式)。
2. 在 `S[v]` 当前消费前沿后缀上做**新鲜全后缀扫描**(**C-SCAN**:无 `start_idx` 早停;scan 指针**不跨 anchor / 不跨回溯携带**;每次节点访问全新)。
3. 收集 `[lo,hi]` 内的 **admissible 子集**。
4. **admissibility 过滤 MUST 严格先于 等-end 塌缩(C-ORDER)**;在 admissible 子集内按 `key=(start_idx,end_idx,position)` 序取**第一个**(**C-KEY**;此"第一个"= start-first-key 序第一,**不是输入 `end_idx` 序第一、不是先遇到的**——后者会静默违反 §2.2 start-first 比定,见 C1)。等-end 塌缩保留的代表 = 簇内 `key` argmin。
5. 赋值并递归;无解则回溯到最近有 key-序后续 admissible 候选的节点。

C-KEY 的等-end 塌缩健全性(C1):等 `end_idx` 簇内被丢弃的候选可能有更小 `start_idx`,而 start-first key 恰偏好它;故塌缩保留的代表**必须**是簇内 `(start_idx,end_idx,position)` 字典序最小者(NOT argmin-end——簇内 end 全相等;NOT 输入序先遇者)。回归锚见 §8。

### 3.3 伪代码(设计级,无仓库代码)

```
function PRODUCE(G, S):                       # S[L]: end_idx 升序物化列表
    order ← TOPO(G)                           # 构造期算好可缓存
    ptr   ← { L: 0 for L in nodes(G) }        # INV-B 持久消费指针
    seen_ids ← {}                             # detect()-局部,§1.2.4
    loop:
        if any ptr[s] ≥ len(S[s]) for s in sources(G): return
        memo ← {}                             # INV-C:每个 LEF 调用重置
        result ← LEF_DFS(order, 0, assign={}, ptr, S, G, memo)
        if result is None: 
            # 仅源后缀无新 LEF;按非重叠语义,推进最早仍有备选的源后重试,
            # 或在所有源耗尽时 return(终止性:每次产出 ≥1 指针严格前移)
            advance-or-return
            continue
        φ, chosen_index ← result
        emit PATTERN_MATCH(φ, label, seen_ids)        # §4 命名 + §1.2.4 去重
        for L in φ: ptr[L] ← chosen_index[L] + 1      # INV-B 全成员非重叠,按真实下标

function LEF_DFS(order, k, assign, ptr, S, G, memo):
    if k = len(order): return (assign, chosen_index_of(assign))
    v ← order[k]
    sig ← FRONTIER_CUT_SIGNATURE(assign, G)           # INV-C:跨割边尾 end_idx 集合
    if sig in memo[v]: return None                    # 已证无完成 → 健全剪
    (lo, hi) ← WINDOW(v, assign, G)                   # max/min over preds, 精确 gap
    # C-ORDER: 过滤先于塌缩;C-SCAN: 新鲜全后缀,无 start 早停,scan 指针不携带
    cands ← [ (S[v][i], i) for i in range(ptr[v], len(S[v]))
                            if lo ≤ S[v][i].start_idx ≤ hi ]      # admissible
    cands ← SORT_BY_KEY(cands)                          # C-KEY: (start,end,position)
    cands ← COLLAPSE_EQUAL_END_KEEP_KEYMIN(cands)       # C1: 代表 = 簇内 key argmin
    for (e, i) in cands:                                 # key 序
        assign[v] ← e
        r ← LEF_DFS(order, k+1, assign, ptr, S, G, memo)
        if r ≠ None: return r
        del assign[v]
    memo[v].add(sig)                                    # 记 FAILED 前沿割
    return None
```

### 3.4 三态分离(INV-A / INV-B / INV-C,**永不混淆**)

> 实现者若把三者混为一个指针/状态,会重新引入已修复的缺陷。doc 正确性节**必须**含此三行表。

| 不变式 | 是什么 | 生命周期 | 健全性依据 | 混淆后果 |
|---|---|---|---|---|
| **INV-A** | 逐节点访问的 **scan 指针** | 一次节点访问;**不跨 anchor / 不跨回溯携带** | 全后缀检视(`start_idx` 在 §1.2.2 下无序,不可早停) | 跨 anchor 携带 = 重新引入 CRITICAL-4(scan 早停截断) |
| **INV-B** | 产出后的 **持久消费指针** `ptr[L]` | 整个 `detect()`;**携带**;`ptr[L]=被选下标+1` | Part D(§6):`end_idx` 升序输入 + 全成员非重叠消费 ⇒ 位置严格前进 ⇒ 产出 `end_idx` 单调不减 | 部分消费 = 破坏 §1.2.2 单调;用 `.index` = IMPORTANT-1 |
| **INV-C** | **FAILED 前沿割记忆** | **一次 LEF 调用**;LEF 调用间**重置**;**不跨生产循环的相继 LEF 迭代携带** | 相同前沿割 ⇒ 剩余节点可行域相同 ⇒ 健全剪 | 跨 LEF 迭代携带 = 在某消费前沿下不可行、在后续(已推进)前沿下可行的分支被错剪 = v2-BREAK 级丢匹配在记忆层重现 |

INV-A 是"**不**携带"(搜索正确性);INV-B 是"**正确地**携带"(流式 + 非重叠正确性);INV-C 是"**按 LEF 调用边界重置**"(剪枝健全性)。结构:LEF-DFS 拥有易逝的 scan / 记忆状态;生产循环拥有持久消费指针。无共享可变指针。

> **no-retreat 警告(诚实、与代码一致的措辞)**:旧 `ptr[v]=i`"永不回退"在现行 `_advance.py` 上**恰好健全**——因为 (a) `lo>hi` 守卫在 scan 之前,scan 不在不可行窗口运行;(b) 单源前向回溯下 `lo` 单调不减。修正核心以**逐访问新鲜 scan(INV-A)**取代它,使正确性**不再依赖**这两个前提成立。不要把警告写成"在简单链里携带 scan 指针也会错"——经 CHECK-3 验证,在现行单源链里它不会错;失实的措辞会让实现者不信任整条警告。

---

## 4. Chain / Dag / Kof / Neg 在同一核心上的分层

- **Dag**:LEF-DFS 直接即是 Dag 推进核心(§3)。
- **Chain = Dag + 线性构造期断言**:构造期校验节点入/出度 ≤1、弱连通、恰一源一汇、无环(design §3.0.1);通过则复用同一 LEF-DFS 核心。**单一实现的支点**。Chain 结构上 `f=1`(单边前沿割),近线性。
- **Kof = k-of-n 边松弛**:为所有出现标签各选一实例(同 Dag 选取),使 edges 中**任意 ≥k 条** gap 满足。松弛破坏"全满足"单调,无法纯单调推进;按 `end_idx` 滑窗 + 窗内 n 条边满足性计数,≥k 产出。**有界小缓冲**(深度 = `max_gap` 跨度内匹配数,非全量),产出前按 `end_idx` 排序弹出。design §3.3 枚举仅 Kof,不变。
- **Neg = 正向子图 + forbid 谓词**:先按正向子图(Chain/Dag 形态)跑 LEF-DFS 候选;对每候选每条 `forbid` 边,在否定标签物化列表上按候选 `end_idx` 单调前移的双指针检查区间内是否存在实例,存在即丢弃。否定标签实例**不进** `children`/`role_index`。正向升序经谓词过滤后仍升序。

四者共享:三段标签解析(design §1.2)→ edges 拓扑构建 → 构造期静态校验 → §3 约束推进。

---

## 5. 复杂度(诚实账)

design §3.1/§3.2 的 **"单调双指针 O(ΣN) 永不回退" 断言被推翻**(它依赖输入 `start_idx` 有序——§1.2.2 仅保证 `end_idx` 有序,见 CRITICAL-4)。修正后:

- **参数**:`f` = **前沿割宽度**(最大"已赋值且有约束悬入未赋值后缀"的节点数,一个类 pathwidth 的图参数;**非**最大入度 `d`)。`Δ` = 每标签不同 `end_idx` 数。`M` = 匹配数,`m` = 节点数,`w` = 每节点候选窗口宽度。
- **时间** `Θ(M · m · Δ^f · w)`。**空间** `Θ(Δ^f)` 每 LEF 调用,**LEF 调用结束即释放** ⇒ 峰值 = 单个 LEF 的签名集,**非跨生产循环累积**(与 INV-C 重置边界一致)。
- **Chain**:`f=1`(单边割)⇒ 标量签名 ⇒ **多项式 / 近线性**。这是**承重的常见情形结论**(headline)。
- **病态宽前沿 DAG**:**时间与空间同为指数**(同一内在 interval-CSP-over-DAG 难度),**显式承认**——不做"指数时间换有界空间"的隐瞒。Chain / 有界 `f` 下时间空间**同为**多项式。
- **spec 触碰**:无。spec 全文**零复杂度断言**(已 grep 核验),§9 仅用于协议表面偏差,复杂度非协议表面 ⇒ **design-doc-only,无 §9 条目**。基底("spec 从未声明复杂度")对参数 `d→f` 的修正不变。

---

## 6. §1.2.2 逐 Detector 缓冲分析 + 承重非重叠不变式

design §3.5 原统一标"零缓冲 Chain/Dag/Neg"——多分量 Dag 下**该断言为假**,改写为逐 Detector 精确界。一个声明的 edges 图可有 `p` 个弱连通分量(WCC);每 WCC 跑独立 LEF 贪心序列(各自 ptr/topo/streams),Detector 输出 = 各分量序列按 `end_idx` 的 p 路归并。

| Detector | 产出 `end_idx` 是否天然升序 | 缓冲界 | 依据 |
|---|---|---|---|
| **Chain** | 是 | **零缓冲** | `validate_chain` 强制单源单汇 + 连通 ⇒ 结构保证 `p=1` |
| **Dag** | 是(各分量升序,升序序列归并仍升序) | **≤ (p−1) 结构常数级前沿** | `p`=WCC 数,声明的**数据无关结构常数**,构造期固定;**与输入规模无关**。**非"零"** |
| **Neg** | 是(继承正向,谓词过滤不改序) | **条件**:正向=Chain ⇒ 零;正向=Dag ⇒ ≤(p−1) | 继承正向子图界 |
| **Kof** | 否(松弛破坏单调) | **有界 `max_gap` 视界缓冲** | 窗口右界封口,非全量 |

> design §3.5 的扁平"零缓冲 Chain/Dag/Neg"是被**纠正的过度声明**,不是单纯改写。Dag 不得再保留"零缓冲"字样,改为"结构常数级前沿缓冲 (p−1),与输入规模无关"。

**承重非重叠不变式(Part D,§1.2.2 零/有界缓冲正确性的根据)**:对每标签 `L`,第 `k+1` 个 LEF 的 `φ*(L)` 在 `S[L]` 中的**位置严格大于**第 `k` 个(全成员非重叠消费),`S[L]` 按 `end_idx` 升序 ⇒ `φ*_{k+1}(L).end_idx ≥ φ*_k(L).end_idx` 对所有 `L` ⇒ `E_{k+1}=max_L ≥ E_k=max_L` ⇒ 产出 `end_idx` 单调不减。**此证明要求全成员消费;部分消费会破坏 `end_idx` 单调性**。故:**"非重叠全成员消费"不只是 design 锁定的锚定选择,它是 Chain/Dag/Neg 满足 §1.2.2 零/有界缓冲的承重正确性不变式**(对既有锁定决策的最小化、有理由的强化,非改动;无协议影响)。输入物化只为前瞻(吃掉 dogfood §5 头号痛点),不影响输出有序,不阻碍任何最优实现。

---

## 7. §1.2.4 event_id 单 run 唯一性机制

- **机制**:**无条件、四 Detector 共享**的 detect()-局部 `seen_ids` 去重。`base=default_event_id(label,s,e)`;若 `base ∈ seen_ids` 则用 `base#<n>`(`n` 从 1 起单调)。常见无撞情形 id 仍是干净的 `{label}_{s}_{e}`。
- **生产侧强制 + 协议层校验为后盾(LOCK-1)**:`run()`(`runner.py` L30-31)维护自身 `seen_ids` 并对重复**抛 `ValueError`(不重命名)**。故生产侧去重**必须在 yield 前保证唯一性**,不能依赖 `run()` 兜底。二者一致:生产侧保证、协议层校验验证(producer guarantees what backstop verifies)。
- **分隔符安全(LOCK-1 pin)**:`default_event_id` 格式 `{kind}_{s}_{e}`,`kind=pattern_label`,`#` 为消歧分隔符。`pattern_label` **不得含 `#`**(构造期 `ValueError`,各 Detector `__init__`)。`n` 从 1 起、`base` 永不含 `#` ⇒ `base#<n>` 与任何合法 `{label}_{s}_{e}` 文本不撞。
- **泛化到 4 Detector(LOCK-2)**:design §2.3 原把 `#seq` 限定 Kof 且基于"Chain/Dag/Neg 天然不重复"假断言。**删除该假断言**;`#seq` 无条件共享于四 Detector。这不破坏 design §2 锁定的产出形状统一(id 方案是 §2.3 细节,在改写范围内;`PatternMatch` 形状不变)。
- **§1.1.1 边界**:协议层只要求**单 run 唯一**;`#<seq>` 使 id **跨 run 不稳定**——spec §1.1.1 明确跨 run 不要求唯一,**不违约**。记为已知边界:远期若需跨 run 稳定 id 须重审。
- **`seq` 局部性**:`seen_ids` 与 `seq` 计数器是 `detect()` 内局部状态,spec §1.2.4(状态局部于 `detect()` 调用)天然成立,跨调用不泄漏。

---

## 8. 精确改写范围 + 回归锚

### 8.1 spec(`docs/research/path2_spec.md`)

- **不动。无 §9 条目。** `earlier`/`later` 端点标签重释属 design §1/§7 / roadmap-#2,先于本重设计,不在本范围。复杂度、anchoring 语义、算法 MUST 均非协议表面。

### 8.2 design(`docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md`)

- **§2.3**:删除"Chain/Dag/Neg 在 earliest-feasible+非重叠下 (s,e) 天然不重复"假断言;`#<seq>` 改为**无条件、四 Detector 共享**;保留跨 run 不稳定的已知边界注,泛化到 4 种。
- **§3.1 / §3.2**:删除"单调双指针 O(ΣN) 永不回退";替换为 **LEF-DFS + §5 的 `f`-参数化诚实复杂度**(Chain `f=1` 近线性 headline;病态宽前沿时间空间同指数)。
- **§3.5**:逐 Detector 缓冲表(Chain 零 / Dag ≤(p−1) 数据无关结构常数,**移除"零缓冲"对 Dag** / Neg 条件 / Kof 有界 `max_gap`);附 §6 Part D 证明;显式声明"非重叠全成员消费是 §1.2.2 承重正确性不变式,部分消费不健全"。
- **§4 / §3.x**:写入 §2.2 `earliest-feasible` 规范定义,引 dogfood report §5"窗口锚定首成员"条为权威。
- **§3.0.1**:**文本不变**。"孤立节点"= 度为 0 的未引用节点,仍非法;**多 WCC(多边不连通子 DAG,所有节点度 ≥1)合法**,非 §3.0.1 所禁。

### 8.3 plan(`docs/superpowers/plans/2026-05-16-path2-stdlib-pattern-detectors.md`)

- **Architecture 行 + Task 5**:把 `advance_dag` 重写为 LEF-DFS + 携带整数下标的非重叠消费(IMPORTANT-1)+ INV-A/B/C 三态分离 + 共享 detect()-局部 `seen_ids`+`#seq`(CRITICAL-3)+ 逐 WCC 独立 + p 路归并(§2.0)。把 §8.5 完整回归套件加入 Task 5 测试。复杂度散文按 §5 改。
- **Task 6(Chain)**:复用核心 + 加严线性构造期断言;`pattern_label` 含 `#` 构造期 `ValueError`。
- **Task 7(Dag)**:`validate_dag` 保留环检测,**新增度为 0 孤立节点拒绝**(关闭既有 plan 缺口——现 `_graph.py` 仅检测环),并加显式注释"多分量 DAG 合法;仅拒绝度为 0 未引用节点"。WCC>1 合法。
- **Task 8(Kof)**:emit 采用共享 `seen_ids`+`#seq`;缓冲(`max_gap` 视界)不变;枚举仍仅 Kof。
- **Task 9(Neg)**:正向子图复用修正核心;forbid 谓词过滤;否定标签不进 children/role_index。
- **Task 5 共享件契约不变**:`default_event_id(kind:str, s:int, e:int)->str` 返回 `f"{kind}_{s}_{e}"`,签名冻结。

### 8.4 规范-MUST 归属与可执行性边界(C4)

- C-ORDER / C-SCAN / C-KEY 是 **stdlib 实现-正确性 MUST**,归 design 文档 + plan Task 5 规范节,**不进 spec**(spec 只定 schema;§5 错误分类、§1.2.4 状态局部性不动)。
- **C4(必须在 doc 显式陈述)**:C-ORDER/C-SCAN/C-KEY **不可被冻结协议层运行时检查捕获**。`runner.py` L26-33 只验 (i) `end_idx` 升序、(ii) `event_id` 单 run 唯一。一个 C-ORDER 违例**丢失合法匹配**后,输出仍 `end_idx` 升序、id 仍唯一 → **静默通过所有冻结协议层运行时检查**。协议从不声称校验匹配**完整性**(只管序 + id 唯一,这是其正确范围)。故这三条 MUST 是**测试守护**的不变式,**非协议强制**;它们仅由钉死的回归锚强制——这是回归锚承重(非示意)的原因。
- **A3 C-ORDER 回归锚**(plan Task 5 测试,非 spec 一致性测试):窗口 `[10,12]`,`e1=(s5,e20)`(`start 5∉[10,12]` 非 admissible),`e2=(s11,e20)`(`start 11∈[10,12]` admissible),两者 `end=20`(等-end 簇)。塌缩-先于-过滤会保留 `e1`(start-first key 偏好更小 `start=5`)再被过滤丢弃 → 匹配丢失;过滤-先于-塌缩 → 仅 `e2` admissible → 匹配命中。该锚同时鉴别 C-ORDER 与 C-KEY。
- **C1 等-end 塌缩回归锚**(plan Task 5 测试):构造等-`end_idx` 簇,使"输入序先遇者"≠"start-first key argmin",断言保留代表 = key argmin(否则静默违反 §2.2)。

### 8.5 回归套件(plan Task 5,stdlib-正确性范围,**非 spec 一致性测试**)

钉死锚清单:

1. **5 个根缺陷复现**(§1):CRITICAL-1(canonical `edges=[A→B(0,_),B→C(0,1)]`)、CRITICAL-2(canonical-简单 `edges=[A→C(0,_),B→C(0,3)]` + CHECK-3 验证的 `A→C(1,3),B→C(0,0)`)、CRITICAL-3(`edges=[A→B(0,0)]`,值相等 `A=[ev5,ev5],B=[ev5,ev5]` → id `{dag_5_5, dag_5_5#1}`)、CRITICAL-4 mode-i(`edges=[A→B(0,0)]`,`A=[ev(0,0)]`,`B=[E(s5,e6),E(s0,e7)]` → 修正后 `{A(0,0),B(0,7)}`)、IMPORTANT-1(结构性:消费携带下标,断言重复事件下匹配集与不重复一致)。
2. **BREAK-1 不连通 DAG**:`edges=[A→B, C→D]`(两 WCC),构造使"全成员消费跨分量耦合"只产出多匹配中的 1 个;修正后逐 WCC 独立 → 全部产出。守护 §2.0 per-WCC。
3. **BREAK-V2-1 签名过粗**:`edges=[A→C(0,0), B→D(0,inf), C→D(0,inf)]`,构造 "A-无关签名" 误剪合法分支;修正前沿割签名恢复。守护 §3.1 INV-C 健全性。
4. **值相等 9 边 Chain**:标量记忆下值相等簇塌缩,断言操作量从 ~10^9 降到 ~10(Chain `f=1` 标量签名 + 等-end 塌缩)。守护 §5 Chain 多项式 headline。
5. **宽前沿 Δ^f 探针**:`edges=[A_1..A_k → Z]`(k 个前驱汇入 Z),断言记忆签名数 / 操作量达到 `Δ^f` 紧界(adversary T2 构造的 2^k DAG)。守护 §5 诚实指数承认与紧界。
6. **A3 C-ORDER 锚**(§8.4):窗口 `[10,12]`,`e1=(s5,e20)` 非 admissible,`e2=(s11,e20)` admissible,两者 `end=20`;过滤-先于-塌缩 → 命中,塌缩-先于-过滤 → 丢失。
7. **C1 等-end 塌缩锚**(§8.4):等-`end_idx` 簇,输入序先遇者 ≠ start-first key argmin,断言代表 = key argmin。
8. **T3 四机制组合 DAG**:CRITICAL-1/2 回溯 + CRITICAL-4 scan + INV-C 记忆 + 共享 seen_ids 在同一 DAG 上联合触发,断言修正核心全部正确(adversary T3 目标)。
9. **`run()` 驱动不变式**:`end_idx` 升序、`event_id` 单 run 唯一(含 `#seq` 路径)、`role_index`/`children` 一致性(`set(flatten(role_index.values())) == set(children)`,各 tuple 内 `start_idx` 升序)。

> mode-ii **不在套件中**(裁定 (B):非复现缺陷,无回归锚,见 §1 CRITICAL-2 历史澄清记录)。修正核心对 mode-ii 的鲁棒性是 INV-A 正确性的**附带后果**,非定向修复——不得据此声称存在过 mode-ii 缺陷。

---

## 9. 一致性把关结论(guardian)

全部经协议/spec 一致性核验:**零冻结协议层改动**(Event/TemporalEdge/Detector/run() 不动),**零 spec 改动(无 §9 条目)**,design §2 锁定产出形状不变。被纠正的 design-doc 过度声明 / 填补,均最小化、有理由、协议中立:(1) §3.5 扁平"零缓冲"→ 逐 Detector 精确界(过度声明纠正);(2) §3.1/§3.2 假 O(ΣN) → `f`-参数化诚实复杂度;(3) `earlier-feasible` 由欠定名 → 显式 start-first 定义(gap 填补,dogfood §5 为权威);(4) `validate_dag` 增度为 0 检查(关闭既有 plan 缺口);(5) §2.3 假"天然不重复"删除,`#seq` 泛化四 Detector。Part D 把既有"非重叠"决策**强化**为 §1.2.2 承重正确性不变式(强化非改动)。

mode-ii 经 team-lead 裁定为 CRITICAL-2 的表现并以 CHECK-3 可执行实验经验证实;最终缺陷集 = 5 根缺陷(CRITICAL-1/2/3/4 + IMPORTANT-1),CRITICAL-4 单模式。adversary 终判"无法攻破 v3"成立未被推翻。

**文档结束。**
