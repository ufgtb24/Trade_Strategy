# 多流 bo detector · PeakEvent · 三态显示 · 大阴线 kind — 设计 spec

> **日期**:2026-09-01 · **分支**:`pk_modify`(worktree `Trade_Strategy-tune_v1`)
> **状态**:设计定稿,待实施
> **前置**:多流引擎已落地(`docs/superpowers/specs/2026-09-01-multistream-engine-and-refs-design.md`,13 task 完成)——本 spec 用该引擎能力造**第一个真实多流消费者**
> **触发背景**:pk 三态显示(broken/eaten/alive)是本次大修改的导火索;用户裁定三态走**多流(方案③)**,否决方案①(consumes_stream);本轮同时纳入**大阴线 kind(bear)** 需求
> **参考**:`docs/research/2026-08-31_pk-display-three-approaches/方案3_多stream引擎扩展.md`(多流论证+三态概念) · `docs/superpowers/specs/2026-08-31-pk-as-event-tri-state-and-bear-kind-design.md`(三态显示**外观**+大阴线 kind 检测,本轮只参考其外观与检测逻辑,**机制用本 spec 的**)

---

## 1 · 背景与动机

pk(突破峰)现在是 `BODetector` 私有的可变 `Peak`,不出流、不是 `Event`。它在图上唯一的现身通道是「作为 bo 的 `referenced_points` 被渲染成卫星 ▽」,且**只显示被突破的峰**。

三态显示需求:峰的三种结局——**broken**(被 bo 突破)、**eaten**(被其他 pk 吃掉、未被突破)、**alive**(从未被突破、也没被吃掉)——都要在图上可视。alive 无任何 owner,结构性不可能靠「挂在别人身上」显示,必须 pk **自己出流**。

多流引擎已提供能力:一个 detector 一个 detect 调用产多条命名流(`produces` + `yield (流名, event)` + `ref_slots` 引用翻译)。本 spec 用它对 `BODetector` 做**本体多流化**,产 `bo` + `pk` 两条流,并新增 `PeakEvent` 事件支撑三态显示,一并纳入大阴线 kind。

## 2 · 目标 / 非目标

**目标**:
- `BODetector` 本体多流化:`produces = {"bo": BOEvent, "pk": PeakEvent}`,**算法与当前完全一致**(突破判定、语义字段逐字;数据结构自由——取消渲染辅助的 `referenced_points`,由 PeakEvent 物化 + `ref_slots` 引用覆盖)
- 新增 `PeakEvent`(物化全部登记峰,含 convex 与 bear 两种 kind),支撑 broken/eaten/alive 三态显示
- 三态显示:**机制用本 spec 的**(PeakEvent.state 字段,detect 内演化),**外观参考 2026-08-31 spec**(主图 marker + 色盲纪律 + kind 区分标记)
- 大阴线 kind(bear):大阴线的 high 也是突破目标,与凸点峰共用活跃峰池
- 保留引用(`ref_slots`):bo 引用它突破的峰、吃掉者引用它 supersede 的峰——完备保留对象间关系
- 新建基于 bb_v1 的多流 app(bo + pk + burst + tb),pk 为 solve=False 孤立显示 node

**非目标**:
- **方案①(consumes_stream 拆两个 detector)**:用户已否决,本轮不讨论
- **三态由渲染层从引用合成**:本 spec 用 state 字段(见 §3.3),不采纳 2026-08-31 spec 的「关系合成」机制
- **前端精确 join/删 `/^pk(\d+)$/` 之外的「缺失 X」前端部分**:本轮只做 pk 独立 node 渲染所需的最小前端改动
- **tune-gates 工具链同步(A9)**:仍属多流 plan 的延期项,触发条件不变(首次给多流 app 调参前)

## 3 · 机制设计

### 3.1 `BODetector` 本体多流化 + 合一

`path2/atoms/breakout.py`:
- `BODetector` 声明 `produces = {"bo": BOEvent, "pk": PeakEvent}`(类级 ClassVar)
- `detect` 内活跃峰从 `Peak` 换成 `PeakEvent`(**合一**:一个对象两种角色——内部活跃峰 + 已出流事件)
- 同一趟 detect:`yield ("pk", PeakEvent)`(登记时)与 `yield ("bo", BOEvent)`(突破时)
- 物化键 `(id(detector), consumes_stream)` 不变;两个流是兄弟,`run_streams` 一次填完(引擎已支持)

**合一的可变性**:`PeakEvent` 是 frozen Event,但活跃峰需要可变(elevation 改 `price`、supersede 锚定 `original_price`、state 演化)。detect 期间用 `object.__setattr__` 显式演化(与 `annotate_stream` 注入 instance_id 同一手段),detect 结束定稿后不再改。

### 3.2 `PeakEvent` 定义

`@dataclass(frozen=True)`,继承 `Event`,`is_point = True`。

```
start_idx = confirm_idx = end_idx = 登记 bar   # 因果诚实:峰存在在登记时确定(见 2026-08-31 spec §3.3)
pk_id: int                                      # 峰唯一标识(convex/bear 共用计数器)
kind: str                                       # 'convex' | 'bear'
peak_idx: int                                   # 峰 bar(窗口 argmax 精确位置;≠ 登记 bar start_idx)
price: float                                    # 峰价(初始=登记价);detect 内 elevation 演化(object.__setattr__)
original_price: Optional[float] = None          # supersede 锚;首次抬升记录
relative_height: float                          # 峰相对窗口最低价的抬升幅度
volume_peak: float                              # 峰 bar 的 vol_ratio
state: str = 'alive'                            # 'alive' | 'broken' | 'eaten';detect 内演化,detect 结束定稿
superseded_refs: Tuple[Event, ...] = ()         # 引用被本峰 supersede 的旧峰(吃掉者记录);ref_slots 槽
```

- `ref_slots()` 返回 `{"superseded": self.superseded_refs}` if 非空 else `{}` → 引擎翻译成 `superseded_ref_ids`——这是多流引用协议的**标准载体**;峰位(`peak_idx`/`price`)是普通字段,不走引用协议(它不是「引用别人」的关系)
- 不引入 `referenced_points` 到 PeakEvent——那是 BOEvent 的渲染辅助字段(裸三元组),不是协议标准命名;峰位由 `peak_idx`/`price` 承载,显示价格前端查 df 或读 price

### 3.3 三态:PeakEvent.state 字段(detect 内演化)

**机制用本 spec 的 state 字段**,不复刻 2026-08-31 spec 的「关系合成」机制(那份 spec 否决 state 字段的理由是「未来信息破坏因果封闭」;本设计接受这一处框架纪律豁免——state 只供显示,禁止进 where 判据/评估,detect 结束即定稿,见 §9 风险 1)。

**state 突变规则**(detect 内,`object.__setattr__`):
- 登记:`state = 'alive'`
- 被 bo 突破:`state = 'broken'`——**一旦 broken 永久 broken**(小幅突破残留的峰后续被 supersede 也保持 broken)
- 被 supersede(新峰登记杀旧峰):仅当 `old.state == 'alive'` → `'eaten'`;已 `'broken'` 保持

**引用保留**(完备保留关系,三态显示不依赖它):
- `BOEvent.broken_refs` → 引用它突破的峰(突破循环里的 `broken_peaks` 就是 PeakEvent 对象列表)→ `ref_slots()={"broken": ...}` → `broken_ref_ids`
- 吃掉者 `PeakEvent.superseded_refs` → 引用它 supersede 的旧峰(登记瞬间,被杀旧峰列表已知)→ `superseded_ref_ids`
- alive 峰无引用

**yield 时序**(detect 内逐 bar):
1. `_detect_peak_in_window`:
   - convex 峰检测(现状逻辑)→ 登记
   - **bear 峰检测**(新,§4)→ 登记
   - 登记时 supersede 已发生:先收集被杀旧峰(其 state alive→eaten),再构造新峰 PeakEvent(`superseded_refs` = 被杀旧峰,`state='alive'`),yield `("pk", 新峰)`,append 入 active
2. 突破循环:被突破峰 `state='broken'`;构造 `BOEvent`(`broken_refs` = 被突破峰列表),yield `("bo", BOEvent)`

### 3.4 `BOEvent` 字段

- **语义字段逐字不变**(drought/pk_count/broken_peak_ids/vol_ratio/peak_vol_max/peak_age_max 等)——where 判据(distinct_pk/peak_age 等)与评估依赖它们,算法一致是硬约束
- **取消 `referenced_points`**(渲染辅助裸三元组,无任何 where/评估消费,已核实):其信息由 PeakEvent 物化(`peak_idx`/`pk_id`)+ `broken_refs`(一等引用)完全覆盖——多流架构不需要自定义渲染数据结构
- 新增 `broken_refs: Tuple[Event, ...] = ()`(带默认值,既有 kwargs 构造点兼容)+ `ref_slots()`

## 4 · 大阴线 kind(bear)

参考 2026-08-31 spec §四,适配到合一架构(单一 detector,无「两个 detector 共享函数」问题):

- **检测位置**:`_detect_peak_in_window` 内、convex 检测之后追加 bear 检测(写死 convex 先、bear 后)
- **进活跃池**:bear 峰与 convex 峰**共用同一活跃峰池**,参与同一套 supersede 与突破判定——大阴线的 high 同样是被突破目标,bo 突破它时该峰 state=broken、进 `broken_refs`
- **判据**:看 **bar i-1**(与凸点峰窗口口径一致,只看当根之前已确认的 bar):
  - 实体跌幅 `(open-close)/open ≥ bear_drop`
  - 相对高度 `(high - 窗口最低 low)/窗口最低 low ≥ bear_min_rh`
- **同 bar 冲突**:bear 跳过已在 `_active_peaks` 的 bar,kind 以先到的 convex 为准
- **无需侧翼**(`min_side_bars`):大阴线显著性来自当根形态,当根收盘即可判定——不受窗口热身期限制
- **参数**:`bear_drop = 0.05`、`bear_min_rh = 0.20`,默认开启;加入 `params.bo`(与峰检测参数同源)
- **出口**:`kind` 字段(`'convex'` / `'bear'`)+ `peak_idx`(峰 bar);convex/bear 共用 `pk_id` 计数器(全局唯一)

## 5 · 前端显示(外观参考 2026-08-31 spec)

### 5.1 serialize 扩展
- topology node 带 `solve` 标志(前端 level 免疫判据)
- `PeakEvent` 的 `state`/`kind`/`pk_id` 字段:schema-driven(`_event_to_dict` 全量平铺)自动带出,后端序列化零改动

### 5.2 chart.ts
- **level 门控免疫**(chart.ts:143-145):`solve=False` 的 node 跳过 `RANK[eventTier] >= RANK[level]` 过滤——pk 全 level 可见(否则 pk 事件 tier 恒为 detected,level=matched 时被整体滤掉)。判据按 node 的 `solve` 标志,类型无关
- **pk 独立 marker**:pk 事件画主图(`render_grid='price'`,点事件 `is_point=True` 过校验),位置 = `peak_idx`(峰 bar,精确局部高点),价格前端查 `df[peak_idx]`(不读演化后的 `price`),颜色 = 三态色(`state`),bear 的 ▽ 下方加一条短横线(`kind`)
- **副图不显示 pk**:`render_grid='price'` 既有语义=主 marker 钉主图、不占副图轨道(`visible.ts` 剔除逻辑已有),零新增引擎枚举
- **删 `/^pk(\d+)$/` 解析与 bo 卫星逻辑**:bo 的 `referenced_points` 已取消,前端不再从它画 pk 卫星;pk 由独立 node 渲染(`peak_idx` 位置 + `state` 三态色)。`satelliteData` 的 pk 部分整体移除(该通道不再被任何事件使用)
- **类型无关判据**:事件带 `state` 字段 → 三态色;不带 → 沿用 tier 色。不硬编码 node 名「pk」

### 5.3 三态配色(色盲纪律:不依赖色相)
- broken(被突破):高饱和/亮 + 态名标签
- eaten(被吃):中饱和/中亮度
- alive(存活):低饱和/暗,区分于背景
- 标签(pk_id + 态名)作第三重区分;bear 用横线标记与 convex 区分

## 6 · 现存 app 影响

`BODetector` 本体多流化后,`stream_schema` 无 None 键,现存用它的 app 的 bo node(不写 produces_stream)会构造报错。**6 个 app 的 bo node 各加一行 `produces_stream="bo"`**(行为逐字不变):

`bb_v0` / `bb_v1` / `bb_v3` / `bottom_burst` / `bo_only` / `try_conplex_where` 的 `dag_spec.py` 中 `NodeSpec("bo", BODetector(...))` → `NodeSpec("bo", BODetector(...), produces_stream="bo")`

## 7 · 新 app(基于 bb_v1)

`path2_apps/bb_pk/`(暂定名):
- 同一 detector 实例喂两个 node(多流兄弟,引擎一次填完):
  - `NodeSpec("bo", det, produces_stream="bo", render_grid="price")`
  - `NodeSpec("pk", det, produces_stream="pk", solve=False, render_grid="price")`——孤立显示 node,不参与匹配
- `burst`(consumes_stream="bo")与 `tb`(consumes_stream="burst")沿用 bb_v1 结构(where 判据、TemporalEdge 不变)
- 参数:`params.bo`(含新增 bear_drop/bear_min_rh)单一来源派生

## 8 · 验收标准

1. **bo 算法对拍**:多流版 `BOEvent` 的语义字段(drought/pk_count/broken_peak_ids/vol_ratio/peak_vol_max/peak_age_max 等)与当前 BODetector 输出**逐字一致**(真实数据对拍,零差;`referenced_points` 已取消,不在对拍范围)
2. **大阴线 kind**:bear 峰正确登记(大阴线 high 成为被突破目标),kind 字段与 label 正确
3. **pk 流**:物化全部登记峰(convex+bear),点事件几何(登记 bar),`state` 分布符合三态(breakdown:broadcast via on 真数据,含 alive 占比非零)
4. **引用翻译**:`broken_ref_ids`/`superseded_ref_ids` 与 state 一致(bo 引用的峰 state=broken;被吃峰 state=eaten)
5. **前端**:pk 主图 marker 三态色、bear 横线、副图无 pk、level=matched 时 pk 仍可见(solve 免疫)
6. **现存 app 回归**:6 个 app 加一行后全量测试零回归,单流行为逐字不变

## 9 · 风险与已知边界

1. **state 字段是未来信息**(相对 confirm_idx=登记 bar):接受为显示专用豁免——**禁止任何 where 判据/评估消费 state**(它携带登记 bar 之后才知道的信息);文档与代码注释写明。若未来有消费诉求,回归 2026-08-31 spec 的「关系合成」机制
2. **合一的可变期纪律**:活跃峰 = PeakEvent 在 detect 期间可被 `object.__setattr__` 演化,detect 结束定稿;禁止 detect 外改 state/price(物化标注后即冻结语义)
3. **6 个现存 app 各加一行**:改动面小但触碰现存文件;全量回归兜底逐字等价
4. **bear 参数未在真实数据验证**:`bear_drop=0.05`/`bear_min_rh=0.20` 来自早期 spec 的合成数据实测;真实数据待验(验收标准 2 覆盖)
5. **前端 pk 精确峰位依赖 `peak_idx`**:PeakEvent.peak_idx 恒为峰 bar;若某峰缺失(理论不发生),前端 marker 退化为登记 bar 示意位置

## 10 · 参考

- `docs/research/2026-08-31_pk-display-three-approaches/方案3_多stream引擎扩展.md` §13.2(三态概念)、§13.5b(单一真源)
- `docs/superpowers/specs/2026-08-31-pk-as-event-tri-state-and-bear-kind-design.md` §3.3(几何)、§3.5.3/§4(bear 检测)、§3.5.4(色盲纪律)
- `docs/superpowers/specs/2026-09-01-multistream-engine-and-refs-design.md`(多流引擎,前置)
