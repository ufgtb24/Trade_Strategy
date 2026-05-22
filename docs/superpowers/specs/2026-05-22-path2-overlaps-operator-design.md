# Path 2 协议层:`Overlaps` 多 mode 区间关系算子 — 设计稿

> 日期:2026-05-22
> 状态:已通过用户分节审批,待用户审阅本稿 → 转 writing-plans
> 上游:`path2/operators.py`、`path2/__init__.py`、`docs/research/path2_spec.md` §2、`tests/path2/test_operators.py`
> 约束:走 superpowers 管线;brainstorm 逐问确认(部分问题派 tom)

## 0. 目标

在协议层新增一个**多 mode 区间关系存在性算子** `Overlaps`:给定锚点 `Event` 与一条事件流,判定流中是否存在与锚点成**指定区间关系**的事件。"overlap" 取**宽泛义 = 任意相交**,5 个 mode 描述相交的形状(包含 / 属于 / 前重叠 / 后重叠 / 相等)。纯函数返 `bool`,与 `Before`/`At`/`After`/`Over`/`Any` 并列,经 `path2/__init__` 出口。

## 1. 动机与设计取向

### 1.1 起点与演化

起点是补全 `Before`/`During`/`After` 三元对称中缺失的"锚点内部区间"算子(`During`)。brainstorm 中用户将需求**扩展**为一族区间-区间关系(A 包含 B / B 包含 A / 前重叠 / 后重叠 / 相等),并采宽泛义"相交=overlap",故收敛为单个多 mode 算子 `Overlaps`,**替代**单语义 `During`。

### 1.2 用户指定 vs YAGNI 留痕(诚实记录)

tom 曾从第一性原理裁定:单语义 `During`(`A.start ≤ e.end_idx ≤ A.end`,与 Before/After 的 end_idx 单坐标惯例一致)为最小充分,**不**囊括 Allen 多关系(理由:真实事件多为点事件,多关系退化为同一种;多关系需双坐标偏离惯例;为空集需求泛化属 YAGNI 违规)。

**本设计的多 mode 是用户明确指定的设计选择,有意覆盖该 tom 裁定。** 留此痕供未来读者理解:`Overlaps` 的丰富度来自用户需求,非 YAGNI-最小推导。tom 裁定记录见其 agent-memory `project_path2_during_ruling.md`。

### 1.3 涵盖原 `During` 用例

**不再单设 `During`**。原动机"ABC 期间不发生 D"(D 多为点事件)由 `not Overlaps(m, "contains", stream=d)` 覆盖——点事件下 `"contains"` 即 `A.start ≤ d ≤ A.end`,正是"d 在 ABC 期间"。

## 2. 签名与 API

**`path2/operators.py` 新增**:

```python
def Overlaps(anchor: Event,
             mode,                                  # str 或 Iterable[str]
             predicate: Optional[Callable] = None,
             *, stream: Iterable[Event]) -> bool:
```

- `mode`:单个 mode 字符串,或一组(set/list/tuple)。传一组 → **任一命中即 True**(any-of)。
- `predicate`:可选(`Optional[Callable]=None`),沿用既有可选化惯例;给出则与关系判定 AND。
- `stream`:**必填 keyword-only**(无默认)。
- 返回 `bool`。**无 `window`**(窗即两区间关系本身)。**无 `stream=None` 索引形态**(区间-区间关系对裸 bar 索引退化无意义)。

## 3. mode 语义(A = anchor,B = stream 事件;闭区间 `[start_idx, end_idx]`,`start ≤ end`)

| `mode` | 含义 | 判据 |
|---|---|---|
| `"contains"` | A 包含 B | `A.start_idx ≤ B.start_idx ∧ B.end_idx ≤ A.end_idx` |
| `"within"` | A 属于 B | `B.start_idx ≤ A.start_idx ∧ A.end_idx ≤ B.end_idx` |
| `"overlapped_front"` | A 前端被叠(B 从前方探入) | `B.start_idx < A.start_idx ∧ A.start_idx < B.end_idx < A.end_idx` |
| `"overlapped_back"` | A 后端被叠(B 从 A 内延伸到后方) | `A.start_idx < B.start_idx < A.end_idx ∧ A.end_idx < B.end_idx` |
| `"equals"` | A 与 B 同段 | `B.start_idx == A.start_idx ∧ B.end_idx == A.end_idx` |

### 3.1 边界规则(已锁)

- **包含类用 `≤`(闭)**:共享端点归包含;`A==B` 同时满足 `"contains"` 与 `"within"`。
- **重叠类要真交叠**:单点相接(meets,如 `B.end == A.start`)**不命中**任何 mode(被严格不等式排除)。
- **`"equals"`** 是 `"contains" ∩ "within"` 的退化角,单列以便显式表达精确同段;点事件下 `contains ≡ within ≡ equals`(同刻共现)。
- 性质:除 `A==B`(命中 contains + within + equals)与"`"equals"` ⊂ contains/within"外,5 mode 在各自专属区互斥;`"contains"∪"within"∪"overlapped_front"∪"overlapped_back"∪"equals"`(+meets 退化点)穷尽两区间**非空相交**的所有形状。
- 与 `Before`/`After`(纯前/纯后,end_idx 不交)**互补**:`Overlaps` 是相交族。

## 4. mode 集合与谓词组合

- `mode` 规整:str → `{mode}`;Iterable → `set(mode)`。
- **未知 mode** → `ValueError`(消息列出 5 个合法值;沿用 `Over` 未知 `op` 的拦截风格)。
- **空 mode 集合** → `ValueError`("mode 不能为空";绝不静默退化为恒 False)。
- 存在性求值:`return any( _matches(anchor, e, modes) and (predicate is None or predicate(e)) for e in stream )`,其中 `_matches` = 任一所给 mode 的关系成立。

## 5. 错误与边界

- `stream` 缺失 → Python `TypeError`(必填 keyword-only;清晰且无需自检)。
- 空 `stream` → `any(...)` 为 `False`(无相交,合理)。
- 无 `predicate=None`+`stream=None` 的 ValueError 分支(`stream` 必填,该退化不存在)。
- `Event` 不变式保证 `start_idx ≤ end_idx`,锚点/事件区间恒非空,无空窗退化。

## 6. 调用例

```python
not Overlaps(m, "contains", stream=d_events)            # ABC 期间无 D(D 多为点事件)
Overlaps(m, {"overlapped_front", "overlapped_back"}, stream=d)  # D 与 m 部分穿插(任一向)
Overlaps(a, "equals", stream=b_events)                   # 存在与 a 精确同段/同刻的 b
Overlaps(m, "contains", lambda e: e.ratio >= 2.0, stream=d)  # 叠加额外判据
```

## 7. 放置与导出

- 定义于 `path2/operators.py`(纯函数,与 Before/At/After/Over/Any 同文件)。
- `path2/__init__.py` 出口新增 `Overlaps`(加入 `from path2.operators import ...` 与 `__all__`)。
- `Optional`/`Callable`/`Iterable` 已在 `operators.py:5` 导入,无需新增 import。

## 8. 测试(`tests/path2/test_operators.py` 新增段,现有用例不改)

- 5 mode 各正/负路径(区间事件,精确卡边界值)。
- 边界:`A==B` 命中 contains/within/equals;meets(`B.end==A.start` / `B.start==A.end`)**不**命中任何 overlap;共享端点归包含不归重叠。
- 点事件:`contains`/`within`/`equals` 三者等价 = 同 idx 共现;overlapped_front/back 点事件下永不命中。
- `mode` 传一组 → any-of(命中其一即 True;均不命中 False)。
- `predicate` 过滤:关系成立但 predicate 否决 → 不计。
- 空 `stream` → False。
- 未知 mode → `ValueError`;空 mode 集合 → `ValueError`。
- 否定用例:`not Overlaps(m, "contains", stream=d)` 表达"期间无 D"。

## 9. 文档写回

- **`docs/research/path2_spec.md` §2(权威)**:新增 `Overlaps` 节(签名、5 mode 判据表、边界规则、any-of、stream 必填无索引形态、宽泛义 overlap 说明);记一行"多 mode 为用户指定设计选择"。
- **`docs/path2/path2_api_reference.md`**:关系算子表新增 `Overlaps` 行 + 用法示例(含 `not Overlaps` 否定、mode 组、equals 共现)。
- **`docs/path2/path2_tutorial.md`**:补 `Overlaps` 用法(择一处展示"期间无 D"与点事件共现)。
- **`.claude/docs/modules/path2.md`**:本分支不改,留 post-merge `update-ai-context` 统一刷新(与既有惯例一致)。

## 10. 验收标准

- `uv run pytest tests/path2/ -q` 全绿;现有 `test_operators.py` 用例未改仍通过(零破坏)。
- 5 mode 判据与 §3 表逐字一致;边界(meets 不命中、共享端点归包含、A==B 三命中)有用例钉死。
- `grep -n "def Overlaps" path2/operators.py` 签名为 `(anchor, mode, predicate=None, *, stream)`。
- `Overlaps` 在 `path2/__init__.py` `__all__` 中。
- 未知 mode / 空 mode 集合均触发 `ValueError`。

## 11. 非目标(YAGNI)

- 不提供 `stream=None` 索引形态(区间关系对裸 bar 索引无意义)。
- 不实现 Allen 全 13 关系(只做这 5;meets/met-by 等留给调用方,或待真实需求倒逼)。
- 不做 events × stream 多对多批量化(已由 `docs/research/path2_batch_relops_analysis.md` 裁定"不做";`Overlaps` 仍是 1-对-多,外层遍历调用方自管)。
- 不保留单独的 `During` 别名(`Overlaps(.., "contains", ..)` 已涵盖)。
- 不动 `Before`/`At`/`After`/`Over`/`Any` 签名或语义。
- 不在本分支改 `.claude/docs/`(post-merge update-ai-context 统一做)。
