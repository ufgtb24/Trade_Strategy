# path2_apps 应用层架构意图

> 最后更新：2026-06-12
> 覆盖：`path2_apps/<走势>/`（走势-特异应用层，与 `path2/` 顶层平级）。
> 框架见 [path2.md](path2.md)。当前唯一应用：`bottom_breakout_burst`。

---

## 定位

path2_apps 是**走势-特异层**：每个子包声明一个具体形态。与 path2/（走势-无关框架）顶层平级而非其子包——框架不该知道任何具体走势，走势包按需组合框架的 atoms + 类型化边 + where。带形状偏见的命名（`RoundedBottom` 等）只能落这里，不能进 `path2/atoms`。

新增走势 = 新建 `path2_apps/<id>/dag_spec.py` 并定义模块级 `PATTERN_DAG`，即被 path2_web 的 discovery 自动发现，无需改框架或后端。

---

## 声明范式（dag_spec.py）

`build_pattern(params: Params) -> PatternSpec` 是参数化声明工厂：给定 params 实例化 detector + 闭合 where 阈值，产纯声明的 nodes/edges。**零手搓成簇/谓词/编排**——所有业务约束降为 NodeSpec / 类型化边 / where 声明，匹配交库引擎 `path2.dag.engine.analyze`。

对外 API（`__init__.py` 导出）：`build_pattern(params)`、`PATTERN_DAG`（默认参数的模块级常量，供 `to_topology` / discovery）、`analyze(df, params)`、`matches(df, params)`、`eval_meta(params)`、`Params`。

**`eval_meta(params) -> {end_role, head_buffer_trading_days}`** 是 path2_web 的**可选协议**：声明买点 role（手声明，如 `"tb"`）与首部缓冲深度。head_buffer = 本 app 全部 rolling lookback 字段的 **max 推导**（参数改动自动传导，不手写常量；dead 参数如 `pred4_lookback_bars` 不计入）。app 不提供该协议 → web 整链回退严格窗、无 label。app 特异知识（role 名、lookback 值）只经此协议出境，web 端零硬编码。

---

## bottom_breakout_burst：7 业务约束 → 5 节点 + 3 边

pattern 链：**下跌(down) → 横盘(side) → 连续突破(burst) → 回踩(tb)**。7 个约束全部降为声明：

| 业务约束 | 归宿 |
|---|---|
| ④ 下跌段紧邻横盘段 | `TemporalEdge(down→side, gap[1,5])` + down.where（`regime==down` ∧ `drawdown>=阈值`） |
| ① 突破首 bo 落横盘段内 | `ContainmentEdge(side, Child(burst,"first_bo"))` + side.where（`regime==sideways`） |
| ② 突破串基数 ≥ MIN_BOS | `BurstDetector(min_bos)`（切段时弃不足 min_bos 的段） |
| ③ 首 bo `drought` ≥ 阈值 | burst.where `W.attr("first_drought")`（读预算标量） |
| ⑤ distinct 峰数 ≥ 阈值 | burst.where `W.attr("distinct_pk")` |
| ⑥ 任一 bo 放量 | burst.where `W.attr("max_vol_ratio")` |
| ⑦ 突破后回踩确认（锚首 bo） | `ThrowbackDetector`（consumes bo）+ `TemporalEdge(Child(burst,"first_bo")→tb, gap[1,span+N])` |

五节点：`bo`（BODetector，**孤立流源**，无边、无 where）/ `down` / `side` / `burst`（BurstDetector，consumes bo，复合宽事件）/ `tb`（ThrowbackDetector，consumes bo）。三边链：**down→side（紧邻 gap[1,5]）→ side→burst 首 bo → burst 首 bo→tb**。

关键设计：
- **bo 是孤立流源 node**：只为产 bo 流给 burst（聚合）与 tb（回踩锚点）消费，自身无边——其单 role 残缺 match 由引擎**出口过滤**丢弃（见 path2.md）。
- **「一串 bo」= 复合宽事件 burst**：`BurstDetector` 切极大段聚合成 `BurstEvent`（start=首 bo / end=尾 bo，携 members + 预算标量）。② = detector 的 `min_bos`；③⑤⑥ = burst 节点 where 直读预算标量（与单实例同式、零特例）。
- **pattern 链 down→side→burst，down 不直连 burst**：下跌段经 side 衔接（④ = 下跌段**紧邻**横盘段，`gap[1,5]`——横盘紧接下跌；不再用 `pred4_lookback_bars`），符合 下跌→横盘→突破 的真实时序；旧 down→burst 直连越过横盘、语义错位。
- **side 与 tb 均经 `Child("burst",...)` 连 burst 的内部端点**（标准 nested 表达）：① `ContainmentEdge(side, Child(burst,"first_bo"))`——引擎投影出 `burst.child("first_bo")`（点事件）再 satisfies；与旧 `StartContainmentEdge(side, burst)` match-preserving。⑦ `TemporalEdge(Child(burst,"first_bo"), tb, gap[1,span+N])`——回踩**锚 burst 首 bo 而非末 bo**（强突破带回踩的常是首 bo；末 bo 可能弱/在窗末无回踩，锚末 bo 会系统性漏匹配），`tb.start = 锚 bo.end+1`，`max_gap=burst_max_span+throwback_N` 覆盖"回踩落在 burst 内任一突破之后"。src_selector 出边健全性同 ContainmentEdge（C1 经 dst_selector 已对 burst 关闭）。
- **down / side 各持独立 `TrendSegmentDetector` 实例**（down_det / side_det，非共享）——引擎 `assign_auto_source_tags` 自动编 trend0 / trend1，event_id 前缀不撞、可按角色分轨。这激活了框架「同类多实例自动消歧」机制（web band-UI 的真实驱动场景）。
- `root="burst"` 是退化字段，引擎不读，填合法 node_id 即可。

---

## 参数 SSoT（params.py）

`Params`（frozen dataclass）是该走势的**唯一参数源**：聚合 BO / Trend / Throwback / Burst 四组 detector 参数 + 顶层判定阈值（`MIN_BOS` / `THR_DROUGHT` / `THR_PK` / `THR_VOL` / `pred4_*`）。提供 `default()` / `from_yaml(path)`（只收 dataclass 字段）构造，+ 各 `*_kwargs()` 把分组参数展开成 detector 构造字典。`build_pattern` 在此处把 params 闭合进 detector 实例与 where 阈值。
