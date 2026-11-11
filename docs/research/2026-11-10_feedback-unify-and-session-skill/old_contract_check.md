# 前任 skill 成员派出的只读核对：旧文档里「怎么写 app 声明」的 20 条说法对着代码逐条判定

来源：会话重启前的对话记录，原文未改（2026-11-10 09:01～09:09 UTC）。只作来历与对照用，结论以现在的代码为准。

## 任务原文

在仓库 /home/yu/PycharmProjects/Trade_Strategy 里做一次只读核对（very thorough）。背景：我要把一份旧文档里关于「怎么写 path2 app 声明」的说法搬进新文档，搬之前每条都要对着**现在的代码**核实。请逐条给出判定：`成立` / `过时或不准`（写出现在代码的真实情况）/ `查不到`，每条附证据 `文件路径:行号` 和一两句原因。不要改任何文件；不要读 `datasets/`、`annotations/`、`docs/research/`。以代码为准，不要信任何 .md 文档里的说法。

要读的主要文件：`path2/dag/nodes.py`、`path2/dag/edges.py`、`path2/dag/where.py`、`path2/dag/spec.py`、`path2/dag/_solve.py`（只看 compile_plan 里决定哪些 node 参与求解的部分）、`path2/dag/engine.py`（run_streams 的去重）、`path2/stdlib/app.py`、`path2_apps/_params_base.py`、`path2_apps/new_step/`（`__init__.py`、`dag_spec.py`、`params.py`、`params.yaml`，plateau.py 只看事件类的 child / child_slots）、`path2_apps/bottom_burst/dag_spec.py`、`path2_web/discovery.py`、`path2_web/eval_runner.py`（只看 run_healthcheck 签名）、`path2_web/serialize.py`（只查 node_index[end_node] 相关）。

待核对的说法：

1. NodeSpec 的字段清单与默认值：node_id、detector、where、event_cls、children、produces_stream、consumes_stream、solve（默认 True）、render_grid（默认 'time'）、produced_by。请列出现在真实的字段全集、类型、默认值。
2. where 的形状是 `(clause_id, 谓词)` 的序列；顶层各条之间恒为 AND。
3. 子结构 node（没有 detector 的 node）：detector 必须为 None、必须显式写 event_cls。**重点核对**：子结构 node 能不能挂 where？旧文档有两种互相矛盾的说法——(a)「where 是死字段，写了构造期报错」；(b)「where 可选，是诊断层判定，只影响显示的档位，不进求解」。现在代码是哪种？`path2_apps/new_step/dag_spec.py` 里 step / today 子结构 node 是否真的挂了 where？consumes_stream / produces_stream / render_grid 在子结构 node 上是不是写了非默认值就报错（哪个校验函数）？
4. children 是「slot 名 → 子 node_id」；produced_by 由它逆推回填（孤儿报错、多父报错）；运行期有「声明与实际物化一致」的核对（旧文档叫 C1/C2/C3：声明⊆实例、实例⊆声明、slot 元素类型核对），改了事件的 child_slots() 忘改 children 声明会报错。请指出运行期核对在哪个文件哪个函数。
5. 哪些 node 参与求解（旧文档叫 bound_ids）：= 边端点并集（整个 pattern 一条边都没有时为全部 node）∩ detector 非空 ∩ solve 为 True，并排除否定边的 dst。请给出现在的确切判据。
6. 零边 pattern 里，每个参与求解的 node 的每个通过 where 的事件各自成为一个 hit；这时加一个只用于显示的 node 必须 solve=False，否则它也产 hit，而序列化对每个 hit 取 `node_index[end_node]` 会 KeyError。
7. 多流 detector：node 用 `produces_stream="流名"` 认领一条流；detector 声明的每条流都必须被某个 node 认领，否则 PatternSpec 构造期报错（哪个校验函数）；同一条流被两个及以上 node 绑定是否报错、在哪报。
8. 同一个 detector 实例被两个 node 共用（同一条流）时，run_streams 按对象身份去重，第二个 node 的身份会塌缩；同一 detector 家族要扮演两个角色时应各配独立的 detector 实例。
9. 边类型及参数：`TemporalEdge(min_gap, max_gap, strict=…)`（gap 闭区间、锚 src.end_idx → dst.start_idx、max_gap 默认无穷、strict 是 keyword-only）、`ContainmentEdge`、`StartContainmentEdge`、`OverlapEdge`、`EqualsEdge`（作为 src 的 node 会被关掉某项剪枝）、`NegationEdge(min_gap, max_gap, inner_predicate=None)`（dst 不进 hit 的 node_index）。请列出现在 edges.py 里真实存在的边类与构造参数。
10. 边上的 `anchor_field=<dst 字段>`：要求 dst 事件的这个字段等于 src 端事件的 instance_id；`Child(node_id, key)` 可以替代字符串端点，指向复合事件内部的某个子事件，要求外层事件实现 `child(key)`；边的 __post_init__ 把它归一化成 src_selector / dst_selector。
11. where 组合子：`W.attr(name, op, thr)`（字段为 None 时判不满足）、`W.child(key, inner)`、`W.children(key, agg)`、`W.all`、`W.any`、`W.not_`；裸 lambda 也被接受但没有可显示的实测值。请列出现在 where.py 对外提供的全部构造函数与签名。
12. `path2/stdlib/app.py` 的 `make_app`：由 build_pattern + Params 装配出 analyze / has_hit / PATTERN_DAG 三件。请给出它的确切签名、返回值、以及 new_step 的 dag_spec.py 里是怎么调用的（贴出那几行）。
13. `path2_apps/_params_base.py` 的 `ParamsBase`：提供 default / from_yaml / to_dict / from_dict；Params 容器的字段是若干子 dataclass（每个是一个 section）；from_yaml 对未知的 section 名和 section 内未知字段报错。**重点核对**：section 名是不是固定的 bo / burst / tb / edges 四个？new_step 的 params.py / params.yaml 实际有哪些 section？一个新 app 的 params.py 最少要写什么（贴 new_step 的 params.py 骨架：类定义、*_kwargs 函数、load_params、DEFAULT_YAML_PATH）。
14. `eval_meta(params=None)` 必须返回含 `end_node: str` 与 `head_buffer_trading_days: int` 的字典，否则 discovery 跳过这个 app；end_node 可以写成 `"父node.slot名"` 的路径形式；head_buffer 应从参数推导而不是写死。贴出 new_step 的 eval_meta 实现。
15. app 包的导出约定：`__init__.py` 导出什么；dag_spec.py 是否需要 re-export `Params, load_params, DEFAULT_YAML_PATH`（旧文档说 web 的注册表注册的是 `.dag_spec` 子模块，所以 dag_spec 也要 re-export）。discovery 实际 import 的是哪个模块、注册表的键是包名还是 PATTERN_DAG.pattern_id。
16. node_id / pattern_id 直接被前端当显示名；NodeSpec / PatternSpec 没有 display_name / label 字段（写了会报 unknown keyword）。
17. PatternSpec 构造期有哪些校验（列出 spec.py 里全部 `_validate_*` 函数名和各自一句话管什么）。
18. `run_healthcheck` 在 eval_runner 里是否存在、签名、data_dir 的默认值。
19. new_step 有没有专门的测试文件（在 tests/ 下 grep new_step / plateau），路径与大致覆盖什么；跑它们的命令形式。
20. 事件类的约定：`path2/core.py` 里 Event 是不是 frozen dataclass、容器字段是否必须 tuple；事件上 `child(name)` / `child_slots()` 的协议签名。

最后另起一段：列出你在核对中发现的、上面没问到但「写 app 声明的人很容易踩」的现行约束（最多 8 条，每条带 文件:行号）。

## 结论原文

核对完了，20 条全部有结论。依据是现在的代码，加上两轮只用内存、不落盘的 Python 探针（`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -`），没有改动或新建任何文件。下文路径都相对 `/home/yu/PycharmProjects/Trade_Strategy/`。

最要紧的三处：

- **第 3 条**：现行的是说法 (b)。子结构 node 可以挂 where，只影响诊断显示，不参与求解；说法 (a) 已过时。`path2/dag/nodes.py:38-40` 的注释还写着「死字段」，这条注释本身也过时了。
- **第 9 条**：边的 `min_gap/max_gap` 必须用关键字传。按位置写 `TemporalEdge("a","b",1,20)` 不会报错，1 和 20 会悄悄落进 `src_selector/dst_selector`，gap 仍是 [0, inf)。
- **第 13 条**：section 名不是固定的四个，由各 app 自己的 Params 字段决定。new_step 实际只有 `plateau` 和 `edges` 两个。

---

**1. NodeSpec 字段清单** — 成立（字段全集就是这 10 个），另有两处要补
- 证据：`path2/dag/nodes.py:23-60`，`@dataclass(frozen=True)`。按位置参数的顺序列出：
  - `node_id: str`（必填）
  - `detector: Optional[object]=None`
  - `event_cls: Optional[type]=None`
  - `produced_by: Optional[str]=None`
  - `children: Mapping[str,str]=dict`
  - `where: Tuple[Tuple[str, WherePredicate],...]=()`
  - `consumes_stream: Optional[str]=None`
  - `produces_stream: Optional[str]=None`
  - `render_grid: str="time"`
  - `solve: bool=True`
- 补充一：有 detector 的 node，`event_cls` 会被无条件改写为 detector 流的类型（`nodes.py:72`）。作者自己写的值会被静默覆盖，不会报错；探针里写 `event_cls=Q`，结果变成了 `P`。
- 补充二：`detector` 和 `produced_by` 互斥（`nodes.py:73-74`）。

**2. where 形状与 AND** — 成立
- `nodes.py:56` 定义了 where 的形状。求解时是 `all(fn(e) for _, fn in node.where)`（`path2/dag/_solve.py:234-235`），而且发生在候选生成处、早于 C1 塌缩。
- 同一 node 内 clause_id 必须唯一（`path2/dag/spec.py:189-198`）；不同 node 之间可以重名。

**3. 子结构 node** — 现行是 (b)；说法 (a) 过时
- detector 必须为 None。只要 node 被父 node 的 children 引用并且没有 detector，就会被当作子结构。`event_cls` 必须显式写，否则报错（`nodes.py:80-83`）。
- where 允许挂：`_validate_substructure`（`spec.py:112-125`）只拒绝 `consumes_stream` 和非默认的 `render_grid`，不检查 where。
- where 只被诊断用：`path2/dag/diagnose.py:53-60` 从父容器的槽里取出事件做判定。它不进求解，因为 bound_ids 要求 detector 非空（`_solve.py:107`）。序列化会照常输出它的 where_rules（`path2_web/serialize.py:317`）。
- new_step 确实挂了：step 有 `step_big / vs_left / step_vol`，today 有 `bull_close`（`path2_apps/new_step/dag_spec.py:74-78`），而且和父 where 共用同一个谓词对象（`tests/path2_apps/new_step/test_dag_spec.py:78-94`）。
- 写了非默认值会报错的字段，以及各自由哪个函数拦：
  - `consumes_stream`、`render_grid`：由 `_validate_substructure` 拦（`spec.py:120-125`）
  - `produces_stream`：由 `NodeSpec.__post_init__` 拦（`nodes.py:76-79`），不在 `_validate_substructure` 里
  - `solve`：不校验（对子结构没有意义）
  - 子结构 node 也不能作为边的端点（`spec.py:148-151`），`consumes_stream` 也不能指向它（`spec.py:184-187`）

**4. children / produced_by / 运行期核对** — 成立，补几处精确信息
- produced_by 回填在 `spec.py:61-99`，以下情况报错：
  - children 引用不存在的 node（`:72-74`）
  - 子结构 node 被多个父引用（`:76-79`）；独立 node 允许多父，比如 `burst.members→bo`
  - 孤儿（`:81-85`）
  - 显式写的 produced_by 和推导结果不一致（`:96-99`）
- 运行期核对函数是 `path2/dag/engine.py:117-154` 的 `_check_children_declarations`，三项分别是 C1（`:136-139`）、C2（`:141-144`）、C3 的 isinstance 检查（`:145-154`）。它在 `run_streams` 出口调用（`engine.py:243`）。
- 这一检查受 `config.RUNTIME_CHECKS` 门控（`path2/config.py:8`）：设置环境变量 `PATH2_RUNTIME_CHECKS` 关闭时就跳过。
- 不受门控的另一道检查：`annotate_stream`（`engine.py:57-62`）遇到「槽名不在 children 声明里」会直接抛 ValueError。所以「事件新增了槽、声明没跟上」实际先在这里报错。只有预置流才会走到出口的 C2。
- 构造期还有 `_validate_children_declared`（`spec.py:127-137`）：重写了 child_slots 的容器 node 至少要声明 children。
- 局限：这些检查都是逐事件做的。某只股票的流为空时，什么也不查。

**5. 参与求解的 node（bound_ids）** — 成立
- 判据在 `_solve.py:102-108`：`(not edges or nid in edge_endpoints) and nid not in neg_dst and detector is not None and solve`。
- 要注意两点：edge_endpoints 包括 NegationEdge 的端点；只要有一条 NegationEdge，pattern 就不算零边。
- bound_ids 再按正向边分成弱连通分量（WCC），每个分量单独求解、各自产出 hit（`_solve.py:110-117`；`path2/dag/_graph.py:64-89`）。

**6. 零边 pattern 与只用于显示的 node** — 成立，补报错位置
- 探针结果：零边、显示用 node 设 `solve=True` 时，hit 的 node_index 键集是 `{('disp',),('main',)}`；设 `solve=False` 后只剩 `('main',)`。
- KeyError 实际最先在 `path2/eval.py:105/110` 的 `_resolve_end_events` 抛出，调用方是 `serialize.py:417`，早于 `serialize.py:430`。
- 评估端走同一条路径（`path2_web/eval_runner.py:108/128`），但每只股票的异常会被捕获、计入 errors（`eval_runner.py:148`），不会让评估崩掉。
- 有边的 pattern 里，不是边端点的 node 无论 solve 设什么都不参与求解（探针 D）。

**7. 多流 detector** — 认领与构造期报错成立；「同一条流被多个 node 绑定」不报错
- 多流 node 必须写 `produces_stream`：写成 None 时，因为 None 不在声明的流里，`nodes.py:68-71` 会报错。
- 流没被认领时由 `_validate_streams_bound`（`spec.py:257-280`）报错，按 `(id(detector), consumes_stream)` 分组。
- 同一条流被两个及以上 node 绑定：没有任何校验，`engine.py:161-163` 还把它明文写成合法。

**8. 同一 detector 实例共用** — 成立
- 去重键是 `(id(detector), consumes_stream)`（`engine.py:193-194, 227-233`）。标注时先到先得（`engine.py:41-42`）。
- 探针结果：`streams['n2'] is streams['n1']`，n2 的事件 `node_id='n1'`；n2 的 hit 键名是 `'n2'`，但 instance_id 是 `n1_*`。
- `res.events` 按列表身份去重（`engine.py:263-268`），所以 n2 没有自己的事件可显示。
- 换成独立实例后，键不同，就会分别 detect、分别标注，所以「各配独立实例」的建议成立。

**9. 边类与构造参数** — 部分不准（位置参数写法会出错）
- `path2/dag/edges.py` 里实际存在的类：
  - 端点选择器 `Child(node, key)`（`:21-32`，不是边）
  - 抽象基类 `DependencyEdge`（`:34-104`）
  - `TemporalEdge`（`:107`）、`ContainmentEdge`（`:134`）、`OverlapEdge`（`:151`）、`EqualsEdge`（`:167`）、`StartContainmentEdge`（`:185`）、`NegationEdge`（`:214`）
- 基类的字段顺序：`src, dst, src_selector=None, dst_selector=None, anchor_field=None, anchor_src_field=None`（`:50-58`，`anchor_src_field` 已退役）。
- 各子类追加的参数：
  - `TemporalEdge`：`min_gap=0, max_gap=inf, strict=False`，其中 strict 是 keyword-only（`:114-116`）
  - `NegationEdge`：`min_gap=0, max_gap=inf, inner_predicate=None`（`:220-222`）
  - 其余四个边类没有额外参数
- 由于 dataclass 继承，第 3 个位置参数是 `src_selector`，所以 `min_gap/max_gap` 必须用关键字传（探针确认）。`test_edges.py:44` 只断言了 strict 不会被误填，没有检查 gap。
- 成立的部分：
  - gap 是闭区间，锚在 `src.end_idx → dst.start_idx`（`:123-128`）
  - 只有 TemporalEdge 校验 gap（`:118-121`），NegationEdge 不校验（探针 `min=5,max=2` 照样通过）
  - EqualsEdge 的 src 会被关闭 C1（`_solve.py:86,95`），但生产路径用的是 `collapse=False`（`_solve.py:270`，`engine.py:261`），实际没有效果
  - NegationEdge 的 dst 被排除在求解之外，不进 node_index（`_solve.py:106`），也不能作为正向边的端点（`spec.py:152-154`）
- 各边的判定条件：
  - Containment：`src.s<=dst.s ∧ dst.e<=src.e`
  - StartContainment：`src.s<=dst.s<=src.e`
  - Overlap：`src.s<dst.s<src.e<dst.e`
  - Equals：起止都相等

**10. anchor_field / Child** — 成立
- `_anchor_ok`（`edges.py:92-104`）：dst 字段等于 src 端（经 Child 投影后）事件的 instance_id；如果 dst 字段是集合，就按「包含」判定。
- 构造期只校验这个字段在 dst 的 event_cls 上存在（`spec.py:200-219`）。
- Child 的归一化在 `edges.py:60-71`；选择器不参与边的相等比较（`:53-54`）。
- Child 的 key 构造期不做检查。外层事件没实现 `child(key)` 时，要到 analyze 才抛 KeyError（`path2/core.py:137-139`，探针 K）。

**11. where 组合子** — 成立
- `path2/dag/where.py` 对外提供的函数：
  - `attr(name, op, thr)`（`:62`）
  - `all(*fns)`（`:77`）、`any(*fns)`（`:86`）、`not_(fn)`（`:96`）
  - `child(key, inner)`（`:113`）、`children(key, agg)`（`:123`）
  - 另有 `witness_of(fn, target)`（`:105`），是诊断工具，不是构造函数
- 可用的 op 只有 `>= > <= < == !=`（`:15`），写错 op 在构造时就报错。
- None 判为不满足（`:23-26`）；`not_` 会把这种情况翻成 True（`:97`）。
- 裸 lambda 会被包装成不透明谓词，实测值为 None（`:70-74, 105-110`）。
- `W.children` 要求外层事件实现 `children(name)`。PlateauEvent 没有实现它（`path2_apps/new_step/plateau.py:141-153`）。
- `W.distinct/W.count` 已归档（`:127-128`）。

**12. make_app** — 成立
- 签名（`path2/stdlib/app.py:18-22`）：`make_app(*, default_params: Callable[[], object], build_pattern: Callable[[object], PatternSpec])`，返回 `(analyze, has_hit, pattern_dag)`（`:49`）。
- 其中 `analyze(df, params=None)` 每次调用都重新 build；`pattern_dag` 在 import 时用 `default_params()` 预先算好（`:40-47`）。
- new_step 里的调用（`path2_apps/new_step/dag_spec.py:42, 83`）：
```python
from path2.stdlib.app import make_app
analyze, has_hit, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)
```

**13. ParamsBase / section 名** — 「固定四个 section」过时，其余成立
- section 由 Params 的 dataclass 字段推导（`path2_apps/_params_base.py:33-36`），不是固定的 bo/burst/tb/edges。
- new_step 只有 `plateau` 和 `edges`（`path2_apps/new_step/params.py:58-59`；`params.yaml:3,20`）；bo_only 只有 `bo`（`path2_apps/bo_only/params.py:30-33`）。
- ParamsBase 提供的方法：
  - `default`（`:50-53`）
  - `to_dict`（`:55-60`）
  - `from_yaml`（`:62-91`）：未知顶层 section、section 内未知字段都抛 ValueError；缺失的 section 或字段用默认值
  - `from_dict(d, strict=False)`（`:93-115`）
  - 额外还有 `key_order`（`:38-48`）和 `RUNTIME_FIELDS`（`:30`）
- new_step `params.py` 的骨架：
```python
from path2_apps._params_base import ParamsBase
DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"

@dataclass(frozen=True)
class PlateauParams:
    old_window: int = 15
    ...   # 共 13 个字段:4 个 detector 构造参数 + 9 个 where 阈值
@dataclass(frozen=True)
class EdgesParams:
    pass
@dataclass(frozen=True)
class Params(ParamsBase):
    plateau: PlateauParams = field(default_factory=PlateauParams)
    edges: EdgesParams = field(default_factory=EdgesParams)
    def plateau_kwargs(self) -> dict:
        return {'old_window': self.plateau.old_window, 'strong_k': self.plateau.strong_k,
                'max_step_bars': self.plateau.max_step_bars, 'max_days': self.plateau.max_days}

def load_params() -> Params:
    return Params.from_yaml(DEFAULT_YAML_PATH)
```
- 一个新 app 最少要写：`DEFAULT_YAML_PATH`、section dataclass、`Params(ParamsBase)`（frozen）、`load_params`。`*_kwargs` 是可选的业务映射；`edges` 也不是必需的 section。

**14. eval_meta** — 成立
- 校验在 `path2_web/discovery.py:20-37`：
  - 模块上有 `load_params` 时调 `eval_meta(load_params())`，否则调 `eval_meta()`
  - 不合规就记进 errors 并跳过这个 app
- end_node 路径最多一级，比如 `"父.slot"`（`path2/eval.py:95-116`）。
- `eval_runner._resolve_meta` 同样会传 `load_params()`（`eval_runner.py:290-299`）。
- head_buffer 从参数推导，测试钉住了这一点（`tests/path2_apps/new_step/test_eval_meta.py:17-28`）。
- new_step 的实现（`dag_spec.py:86-95`）：
```python
def eval_meta(params: Optional[Params] = None) -> dict:
    p = (params or Params.default()).plateau
    return {
        "end_node": "plateau.today",
        "head_buffer_trading_days": p.max_days + p.max_step_bars + p.old_window + 1,
    }
```

**15. 导出约定** — 成立
- `__init__.py` 导出 8 个名字：`build_pattern, PATTERN_DAG, analyze, has_hit, eval_meta, Params, load_params, DEFAULT_YAML_PATH`（`path2_apps/new_step/__init__.py:15-19`）。
- discovery import 的是 `path2_apps.<子包>.dag_spec`（`discovery.py:51`）；注册表的键是 `PATTERN_DAG.pattern_id`，不是包名（`discovery.py:60`）。
- web 端直接在 dag_spec 模块上取这些名字：`mod.Params / load_params / build_pattern / analyze / PATTERN_DAG / eval_meta / DEFAULT_YAML_PATH`。出处：`eval_runner.py:59,296`、`path2_web/api.py:400-737`、`path2_web/scan.py:118-122`、`path2_web/app_version.py:22-23`。
- 所以 dag_spec 必须 re-export `Params, load_params, DEFAULT_YAML_PATH`（`dag_spec.py:46`），测试钉住了（`test_dag_spec.py:102-106`）。

**16. 显示名** — 成立
- 探针：`NodeSpec(..., display_name=...)` 和 `PatternSpec(..., label=...)` 都报 `TypeError unexpected keyword`。字段定义见 `nodes.py:51-60` 与 `spec.py:41-45`。
- `serialize_pattern` 只输出 node_id 和 pattern_id（`serialize.py:315, 348`）。
- 前端直接渲染 `{{ box.node.node_id }}`（`path2_web_ui/src/components/TopologyControl.vue:44`）和 `{{ p.pattern_id }}`（`path2_web_ui/src/components/ScanConfigDialog.vue:63`）。

**17. PatternSpec 构造期校验**（调用顺序见 `spec.py:47-58`）
- `_normalize_produced_by`（不是 `_validate_*`，`:61`）：回填 produced_by；处理孤儿、多父、不一致、引用不存在的 node。
- `_validate_node_ids`（`:104`）：node_id 全局唯一。
- `_validate_substructure`（`:112`）：子结构 node 的 consumes_stream 必须为 None，render_grid 必须是 'time'。
- `_validate_dag`（`:139`）：边端点必须已声明；子结构不能做端点；否定边的 dst 不能出现在正向边上；不能有环。
- `_validate_detector_dag`（`:176`）：consumes_stream 必须指向已声明的非子结构 node。
- `_validate_where_clauses`（`:189`）：同一 node 内 clause_id 唯一。
- `_validate_anchor`（`:200`）：anchor_field 必须是 dst event_cls 的字段。
- `_validate_render_grid`（`:221`）：`'price'` 要求 `is_point=True`。
- `_validate_no_self_feed`（`:242`）：consumes_stream 不能指向共享同一 detector 的 node。
- `_validate_streams_bound`（`:257`）：多流的每条流都必须被认领。
- `_validate_children_declared`（`:127`）：容器 node 必须声明 children。

**18. run_healthcheck** — 成立
- 位置在 `eval_runner.py:389-394`，参数全部是关键字参数：
```python
run_healthcheck(*, module_path, start, end, target_ticker=None, min_tickers=1, max_tickers=500,
                horizons=(5,), end_node=None, head_buffer_trading_days=None, param_overrides=None,
                data_dir="datasets/pkls", workers=26, ticker_regex=None, out_path=None,
                executor_factory=None, on_progress=lambda *a: None) -> dict
```
- `data_dir` 的默认值是相对当前工作目录的 `"datasets/pkls"`。

**19. new_step 测试** — 有
- `tests/path2_apps/new_step/` 下五个文件：
  - `test_dag_spec.py`：node 与 children、零边、父 where 的名字与阈值、子结构 where 共用谓词、re-export、mapping
  - `test_eval_meta.py`：默认值为 `plateau.today`/61、head_buffer 跟随参数变化
  - `test_has_hit.py`：合成 K 线的正例与反例
  - `test_params.py`：默认值、frozen、kwargs 与 detector 签名一致、yaml 未知键报错
  - `test_plateau.py`：543 行，detector 单测
- 另有 `tests/path2_web/test_mapping.py:133-139` 和 `tests/path2_web/test_serialize.py:139-144, 249-254` 也覆盖 new_step。
- 命令形式：在仓库根目录运行 `uv run pytest tests/path2_apps/new_step -q`。这是推断的：仓库里没有 pytest 配置，`CLAUDE.md:90` 只说包管理用 uv。我没有运行。

**20. 事件约定** — 基本成立；「容器必须用 tuple」是约定，不是强制校验
- `@dataclass(frozen=True) class Event(ABC)` 见 `core.py:28-29`；子类必须是 frozen dataclass 见 `:31-33`。
- `__post_init__` 只检查 int、bool、区间、confirm 和 NaN（`:94-115`）。用 tuple 装容器的约定写在 `path2/atoms/__init__.py:10-11`。
- 不过引擎只把 tuple 当作一组子事件，其他类型都当成单个事件（`engine.py:64, 108, 150`）。所以 slot 的值写成 list 会出问题。
- 协议签名：
  - `child_slots(self) -> Mapping[str, Event | Tuple[Event,...]]`，默认 `{}`（`core.py:121-123`）
  - `child(self, name: str) -> Event`，默认抛 KeyError（`:137-139`）
  - `children(self, name) -> Tuple[Event,...]`，默认抛 KeyError（`:141-143`）
  - 另有 `ref_slots`（`:125`）和类属性 `is_point`（`:92`）
- `confirm_idx` 是 keyword-only 必填（`:90`）。

---

**另外发现的、写 app 声明时容易踩的现行约束**

1. **边参数一律用关键字传。** `TemporalEdge(src, dst, 1, 20)` 会静默把数字填进 `src_selector/dst_selector`，gap 仍是 [0, inf)（`path2/dag/edges.py:50-58, 114-116`）。现有 app 都用的关键字（`path2_apps/bottom_burst/dag_spec.py:63-69`）。
2. **NodeSpec 的第 3 个位置参数是 `event_cls`。** `NodeSpec("x", det, (("w", fn),))` 不报错，但 where 会被丢掉：这个元组先落进 event_cls，又被 detector 的类型覆盖（`path2/dag/nodes.py:53, 72`；探针 F）。where 必须写成 `where=`。
3. **`solve=False` 的 node 不能作为正向边的端点。** 构造能通过，但 analyze 时会在 `compile_plan → wccs` 抛 `KeyError`（`path2/dag/_graph.py:68-73`）。另外，有边 pattern 里的 bound node 不连通、形成多个 WCC 时，各分量会各自产 hit，node_index 里缺少其他分量的 node，取 end_node 就会 KeyError（`path2/dag/_solve.py:110`；探针 C）。
4. **否定边的 dst 上挂 where 不起作用。** 否定判定直接读原始流（`path2/dag/_solve.py:155-163`；探针 B2），要用 `inner_predicate`。`strict=True` 的「窗口内第一个」判断同样读原始 dst 流、无视 where（`_solve.py:147`）。NegationEdge 不校验 gap 区间。
5. **字段名和 key 写错，构造期都不报，到 analyze 才炸。** 包括 `W.attr` 的字段名、`W.child` 和 `Child` 的 key（`path2/dag/where.py:65`；`path2/core.py:137-139`；探针 G/K）。评估里这类错误会被逐股吞进 errors（`path2_web/eval_runner.py:148`），所以 healthcheck 要看 errors 数，不能只看命中。
6. **`PATTERN_DAG` 和不带参数的 `analyze(df)` 用的是 dataclass 默认值，不是 params.yaml**（`path2/stdlib/app.py:40-44`；`path2_apps/new_step/dag_spec.py:83`）。web 路径才走 `load_params()`。默认值也必须能在 import 时 build 成功，否则 discovery 会把这个 app 记成错误。
7. **pattern_id 必须全局唯一。** 注册表按它做键，撞名会静默覆盖（`path2_web/discovery.py:60`；`path2_apps/try_conplex_where/dag_spec.py:145-146` 的注释）。另外，import `dag_spec` 会先执行包的 `__init__.py`，`__init__` 出错同样让 discovery 跳过这个 app。
8. **代码里也有过时的注释，搬文档时不能当依据：**
   - `path2/dag/nodes.py:38-40` 还说子结构的 where 是死字段
   - `path2/dag/spec.py:5` 说只有「三类校验」
   - `path2_apps/bottom_burst/dag_spec.py:35` 说「残缺 hit 由 analyze 出口过滤」，但 analyze 已无出口过滤（`path2/dag/engine.py:257-258`），那个 bo node 根本不参与求解
   - `path2/dag/edges.py:111` 暗示位置参数是安全的，实际并不安全
