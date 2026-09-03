# A9 · tune-gates 多流改造 —— 可行性确认 + 方法记录

> 2026-09-01 · 用户确认「先不实现，但需确定可行，记录方法供下一期参考」。
> 前置：多流引擎 spec/plan（`docs/superpowers/specs/2026-09-01-multistream-engine-and-refs-design.md`，A9 已延期）。
> 代码现状核实基于 commit `50dbc16`，行号对应 `multivar_core.py`。

## 一 · 可行性结论：无危机

**tune-gates 算法可精确改造为支持多流 detector，不存在可行性危机。** 理由：多流对 tune-gates 的全部影响集中在「物化单位与缓存键」一处；其余环节要么天然正确、要么结构性免疫（下表）。改造是「适配物化层」，不是「重写算法」。

## 二 · 逐环节分析（多流影响面）

| 环节 | 多流影响 | 结论 |
|---|---|---|
| `influence_dims`（200 行） | 判据 = `upstream_closure(nid) ∩ detector_nodes[d]`。多流兄弟**共享同一 detector 实例** → `probe_dim`/`_det_state` 探测到参数变化同时改两兄弟 → 两兄弟同时标为受影响 | ✅ **天然正确，零改**（改 `min_relative_height` 确实同时影响 bo+pk 两流） |
| `probe_dim` / `_det_state`（44/85 行） | 按 detector 实例状态比对 | ✅ 天然正确，零改 |
| `upstream_closure`（191 行） | 走 `consumes_stream` 单链；兄弟同 `consumes_stream` → 同 closure、无环（Kahn 保证，`_graph` C1 已核实免疫） | ✅ 零改 |
| `detection_combos`（211 行） | 与 node 无关 | ✅ 零改 |
| `check_predicate_axes`（176 行） | where 谓词轴，多流不新增轴 | ✅ 零改 |
| label / eval 侧 | `end_node` 不变；eval 在 match 上算，多流 `solve=False` 的 node 不进 match | ✅ 零改 |
| **反转循环物化**（306-315 行） | `run()` 拒多流；按 `nid` 缓存会让兄弟各跑一遍（双跑 + instance_id 分裂） | 🔧 **必改**（见 §三） |
| **硬拒判据**（266-273 行） | 「同一 detector 实例」会误伤多流兄弟 | 🔧 **必改**（见 §三） |
| **annotate 时序**（310-315 行内） | 兄弟无拓扑序，「首现 node 获胜」须按声明序 | 🔧 **必改**（与 run_streams 对齐） |

## 三 · 三段式改法（下一期参考）

### 1. 硬拒判据：从「同一 detector 实例」→「同一流身份」

现状（266-273）：`len({id(n.detector)}) != len(nodes)` → raise。
改为按 **(id(detector), consumes_stream, produces_stream) 三元组**（流身份）：

```python
    call_ids = {(id(n.detector), n.consumes_stream, n.produces_stream) for n in det_nodes}
    if len(call_ids) != len(det_nodes):
        raise ValueError(
            "本工具不支持同一条流被多 node 绑定(run_streams 会折叠物化、反转循环不会);"
            "请拆成独立 node 或改走逐格 scan")
```

多流兄弟三元组不同（bo=(det,None,'bo')、pk=(det,None,'pk')）→ 合法放行；只有「同一流被多 node 绑定」才是真问题（instance_id 归属无真值）。

### 2. 反转循环：物化单位从「每 node」→「每调用」，缓存键换调用身份

现状：`run(node.detector, ...)` 返回单流 list，缓存键 `(nid, combo[infl[nid]])`。
改为：物化入口 `run_bundle`，缓存值 `{流名: list}`，缓存键 = **(id(detector), consumes_stream)**：

```python
        for nid in order:
            node = by_id[nid]
            if node.detector is None:
                continue
            call_key = (id(node.detector), node.consumes_stream)   # ★ 调用身份,不含 produces_stream
            key = (call_key, tuple(combo[d] for d in infl[nid]))
            if key not in stream_cache:
                bundle = (run_bundle(node.detector, win)
                          if node.consumes_stream is None
                          else run_bundle(node.detector, streams[node.consumes_stream], win))
                for sib in siblings[call_key]:                     # 兄弟一次填完 + 按声明序标注
                    if sib.node_id in streams:
                        continue
                    streams[sib.node_id] = bundle[sib.produces_stream]
                    annotate_stream(counts, sib.node_id, streams[sib.node_id], children_of)
                stream_cache[key] = bundle
            streams[nid] = stream_cache[key][node.produces_stream]
```

（`siblings` 收集 = run_streams Task 4 同款逻辑。）

### 3. annotate：兄弟按声明序一次填完

与 `run_streams` 的「声明序兄弟一次填完」语义对齐（B2 修复），否则 instance_id 桶计数错。

## 四 · 三个必须避开的雷区（最容易错）

1. **缓存键不含 `produces_stream`**——它是流下标不是物化身份。含进去会让 bo/pk 兄弟各物化一次 = 双跑（1.80×）+ instance_id 与生产分裂。**硬拒判据用流身份、缓存键用调用身份，是两把不同的键，别混。**
2. **annotate 必须按声明序兄弟一次填完**——不是逐 node 独立标（首现 node 获胜会让无序兄弟抢命名权）。
3. **缓存命中后取流下标**——`stream_cache[key]` 是 bundle，`[node.produces_stream]` 取流，不能把整个 bundle 当 node 的流。

## 五 · 验证策略（下一期实施时）

1. **对拍**：多流 fixture spec（如 plan Task 12 的 `RangeNoteDetector`）用 `scan_one_stock` 跑，与生产 `run_streams` + `analyze` 的结果对照——**逐流 instance_id 一致**。
2. **双跑检测**：断言 `detector.calls == 1`（物化只一次，验证缓存键正确）。
3. **单流回归**：现有单流 app 的 scan 结果逐字不变（`stream_cache` 键从 `(nid, …)` 变 `(call_key, …)`，单流下两者等价）。
4. **influence 对拍**：多流下改某个 D 维参数，断言两兄弟都被标记受影响、都重跑。

## 六 · 为什么本期延期不产生风险

本 plan 落地后多流能力只被测试 fixture 消费，无真实 app 调参；`multivar_core` 旧逻辑对单流 app 行为逐字不变。**一旦开始 pk 应用层（`后续待办_真实app践行.md`），A9 是硬前置**——因为那时才有第一个需要调参的多流 app。
