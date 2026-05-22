# Path 2 stdlib:PatternMatch.role_index 收敛 — 设计稿

> 日期:2026-05-19
> 状态:已通过用户分节审批,待用户审阅本稿 → 转 writing-plans
> 上游:`path2/stdlib/pattern_match.py`、`path2/stdlib/_advance.py`;#3 设计稿 `docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md` L63-74;`docs/research/path2_roadmap.md`
> 约束:走 superpowers 管线;本次**不使用 tom 裁定**,澄清问题直接问用户

## 0. 目标

把 stdlib 统一产出类型 `PatternMatch.role_index` 从 `Mapping[str, tuple[Event, ...]] | None` **收敛为** `Mapping[str, Event] | None`。这是 `path2/__init__` 出口的**冻结公开 API 变更**,采**硬切换、无 shim**。

## 1. 动机(为什么这是消除过度设计,不只是口味)

四个标准 PatternDetector(Chain/Dag/Kof/Neg)**结构性地每标签恰好绑定一个成员**:

- Chain/Dag:每个标签 = 图中一个节点 = 一个被赋值事件。
- Kof:`_kof_dfs` 返回 `assign = {标签: 单个 Event}`(n 标签全在场、每标签一个);k-of-n 松弛的是"满足的*边*数",**不是**"一个标签多个事件"。
- Neg:否定标签 N 结构性不进 role_index;正向标签同 Dag。
- 四者共用唯一产出点 `_emit`(`_advance.py:134`):`role_index={lab: (assign[lab],) for lab in assign}` —— 恒长度 1。

因此 `tuple` 包装在所有现行路径上**零信息量**,却让每个消费点永久付 `[0]` 解包税,并向读者泄漏"一个标签可能对应多个"的虚假一般性。

**关键事实(已查证)**:#3 设计稿 L69 给 tuple 的权威理由是"**Kof 一标签多命中**"。该理由被 #3 自身实现(`_kof_dfs` / `_emit` 每标签单成员)**证伪** —— 与 `path2_spec.md` §9 偏差①(frozen 自检为死代码,设计假设被实现轮推翻)**同类**。故本次收敛不仅是奥卡姆优化,更是消除一处理由已失效的过度设计;并据此须对 #3 设计稿做写回(§5)。

`children: tuple[Event, ...]` **保持不变** —— children 是真多元(全体成员集),只有 role_index 是真单元;二者基数本就不同,不应强行同型。

## 2. 类型与产出契约变更

**`path2/stdlib/pattern_match.py`**
- `role_index: Mapping[str, tuple[Event, ...]] | None = None` → `role_index: Mapping[str, Event] | None = None`
- 字段注释由"标签 → 命中实例(恒 tuple)"改为"标签 → 该标签命中的唯一 `Event`"
- `children: tuple[Event, ...]` 不变

**`path2/stdlib/_advance.py:134`(`_emit`,Chain/Dag/Kof/Neg 全部产出的单一汇聚点)**
- `role_index={lab: (assign[lab],) for lab in assign}` → `role_index={lab: assign[lab] for lab in assign}`

**新契约**:`PatternMatch.role_index[label]` 直接是该标签命中的那个 `Event`,访问不再需要 `[0]`。改 `_emit` 一处即覆盖四个 Detector。

## 3. `__post_init__` 不变式重写(策略 A)

| 当前校验 | 处置 | 理由 |
|---|---|---|
| 每个 `role_index[label]` tuple 按 `start_idx` 升序 | **删除** | 单 `Event` 无内部顺序,恒真空 |
| `children` 按 `start_idx` 升序 | **保留不变** | children 仍真多元 |
| `role_index` 扁平化集合 == `children` 集合 | **保留,改写为值集合等价** | 仍有判别力,防未来误构造 |

改写后(语义不变,适配单值;受 `config.RUNTIME_CHECKS` 门控,提前返回逻辑不动):

```python
ri = self.role_index or {}
# children 必须按 start_idx 升序(§3.3)
if list(self.children) != sorted(self.children, key=lambda e: e.start_idx):
    raise ValueError("children 未按 start_idx 升序")
# role_index 值集合 == children 集合(两视图不漂移)
if {id(e) for e in ri.values()} != {id(e) for e in self.children}:
    raise ValueError("role_index 值集合 != children 集合")
```

错误文案由"扁平化集合"改为"值集合"。Neg 的 N 仍由结构性保证不进 role_index/children,该不变式对 Neg 同样成立。

## 4. 调用点 + 测试改造

### 4.1 生产调用点(`path2/`)

`advance_neg` 是唯一读取 role_index 取值处:
- `_advance.py:522`(实代码)`e_anchor = m.role_index[anchor_label][0]` → `m.role_index[anchor_label]`
- `_advance.py:485` / `:482`(docstring 内伪代码)同步去 `[0]`
- `:520` 键判定 `if anchor_label not in m.role_index` 不变
- `detectors.py:189` / `_advance.py:493` "N 不进 children/role_index" 注释语义不变,不动

### 4.2 测试改造(`tests/path2/stdlib/`,7 文件)

1. **键集合断言不受影响,不改**:`test_dag.py`、`test_neg.py`(键/`"N" not in`)、`test_integration.py:109`、`test_kof.py:45/110/168`。
2. **取值断言机械去 `[0]` / tuple→Event**:
   - `test_kof.py:46-47` `== (ev(0,0),)` → `== ev(0,0)`
   - `test_advance_dag.py:45` `["A"][0].start_idx` → `["A"].start_idx`
   - `test_integration.py:66` `["L1"][0].pattern_label` → `["L1"].pattern_label`
   - `test_labels.py:96` 构造 `role_index={"A": (child,)}` → `{"A": child}`
   - `test_neg.py` 扁平化断言(`ichain.from_iterable(m.role_index.values())`、`for tup in m.role_index.values()`)→ `set(m.role_index.values())` 直接比对
   - `test_kof.py:144`、`test_advance_dag.py:339-341` 同类扁平化 → 同改
3. **`test_pattern_match.py` 专项不变式测试**:
   - `test_construct_ok_and_role_index_tuple`、`test_role_index_flatten_must_equal_children` → 重写为单 `Event` 等价版(构造 `{"A": a1, "B": a2}`,断言取值 + 等价不变式负路径触发 `ValueError`)
   - "tuple 内逆序"用例(`role_index={"A": (a2, a1)}`)→ **删除**(无内序可违,对应不变式已删)

## 5. 文档写回

- **`docs/path2/path2_stdlib_guide.md`**:`:181` 字段表行类型/语义、`:184` 不变式句、`:74`/`:188` 示例去 `[0]`;`:168` 不动。
- **#3 设计稿 `docs/superpowers/specs/2026-05-16-path2-stdlib-pattern-detectors-design.md`(L63-74,权威)**:加**写回横幅**(原文保留、横幅在上方,不重写历史),记:① L69 "Kof 一标签多命中"理由经 #3 实现证伪(同 spec §9 偏差①);② `role_index` 收敛为 `Mapping[str, Event]`,L73 不变式相应改;③ L69 的 `single(label)` 糖随之作废。
- **`.claude/docs/modules/path2.md:51`**:不在本次改,按 #1/#3/#4 惯例留 **post-merge `update-ai-context`** 统一刷新。
- **`path2_spec.md`**:无 `role_index`(协议层不含 stdlib),无需改。

## 6. 验收标准

- `uv run pytest tests/path2/ -q` 全绿;改写断言确实反映"取值即 `Event`、无 `[0]`、等价不变式仍触发"。
- `grep -rn "role_index.*\[0\]" path2/ tests/ docs/path2/` 零残留。
- `grep -rn "tuple\[Event" path2/stdlib/pattern_match.py` 零残留。
- 等价不变式负路径测试:`role_index` 值与 `children` 不一致 → `ValueError`。

## 7. 非目标(YAGNI)

- 不加任何 shim / 弃用期 / `single(label)` 糖(硬切换;糖随理由失效作废)。
- 不动 `children` 类型(真多元,保持 tuple)。
- 不改 `path2_spec.md` / 协议层(本次纯 stdlib 产出类)。
- 不在本分支改 `.claude/docs/`(post-merge update-ai-context 统一做)。
- 不重写 #3 设计稿历史(仅加写回横幅)。
