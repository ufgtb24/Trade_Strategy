# 记账

第 8 步读。账本是 `path2_apps/<app>/mapping.yaml` 顶层的 `session`，只有 `snapshot` / `conditions` / `tags` 三样；形状规则在 `path2_web/mapping.py` 开头的说明里。不加新的键。它随 app 进 git，页面读它给红着的反馈挂原因标签，下一轮的摘要也读它。

## `conditions`：每条条件一行

每个处理过的 issue（或样本）推出的条件记一行 `{where, from, state}`：

- `where`：改动落在 app 的哪里——`node.where 名`、边；detector 或拓扑层面的改动写 node 名；没进 app 的候选条件写拟用的名字。
- `from`：这个 issue **各处的反馈编号**（摘要里每一处行尾括号里的 `f-…`；由样本推出的写样本编号 `s-…`），不是 issue 标题上的那个名字。写成 issue 名不报错，但下一轮摘要里这个 issue 会显示「还没有条件」，等于没记。
- `state`：以下面六个词之一开头，后面跟日期和一句理由。整句用双引号括起来（里面有冒号、逗号时不括会把这一行写坏）。

  | 开头词 | 意思 | 条件在不在 app 里 |
  |---|---|---|
  | `from_definition` | 照用户定义里已有的话改的 | 在 |
  | `unmeasured` | 用户同意新加的条件，还没量；写明用户哪天同意 | 在 |
  | `declined` | 用户说不加 | 不在 |
  | `for_tuning` | 条件已有，只差门槛，留给调参 | 在 |
  | `not_worth` | 量过，不值得加 | 不在 |
  | `pending` | 两轮之间用户定下、待下一轮实施（[between-rounds.md](between-rounds.md)）；这一轮实施了就把开头词改成现在的去向，接着写「第 N 轮实施」 | 不在 |

  例：`- {where: plateau.not_stale, from: [f-pc-9, f-pc-10], state: "unmeasured 2026-11-10 用户同意新加"}`

连条件都翻不出来的（纯「当天看不出」）不记行，只挂标签，理由已在改版报告里。

出局核对（[checklist.md](checklist.md)「出局核对」）里用户选了 invalidation 或 setback 的，也记一行：`where` 写那条 where（detector 的截断写 node 名加一个自起的短名，如 `plateau.fall_back_end`，同一 node 的几处截断各写各的），`from` 写空数组 `[]`（这一处是你查出来的，没有反馈编号；空数组合法），`state` 以 `from_definition` 开头（用户在题里的选择就是他的定义，定为 setback 的也一样），接日期、「出局核对：用户定为 invalidation / setback」和改法。下一轮核对见到这一行就照它办，不再问。选了「先放着」的不记行。

  例：`- {where: plateau.new_hold, from: [], state: "from_definition 2026-11-20 出局核对：用户定为 invalidation"}`

切法题（[checklist.md](checklist.md)「先怀疑切法」）用户选了「改切法」或「现在的切法对」的，同样记一行：`where` 写切出那一段的 node 名加短名 `cut`（如 `plateau.cut`），`from` 写引出它的反馈编号（全由样本引出时写 `[]`），`state` 以 `from_definition` 开头，接日期、「切法题：用户定为改切法 / 现在的切法对」和涉及的那几次形状（股票 + 日期）。和出局核对不同，这一行不免问：同一次形状上又出现新的、不同的较劲时照样再问。选了「先放着」的不记行。

## `tags`：还红着的每一处一个原因标签

按**改完之后**的状态：各处现在的状态 = 摘要里那一处的状态，改版报告 ① 逐条列出「变了」的以报告为准。只给用户自己挑的反馈挂（摘要 issue 一节里的那些编号）。

- 还在买（`matched`）的每一处反馈都要有标签；基准 node 对不上的看你在报告里怎么交代的——交代为「认法变了」、原来的毛病还在的，按原因挂；交代为「改好了」的不挂。标签取值：

  | 标签 | 用在 |
  |---|---|
  | `for_tuning` | 条件已有，只差门槛 |
  | `not_worth` | 量过不值得加 |
  | `hindsight` | 当天看不出（事后才看得出） |
  | `accepted` | 用户说过这种可以买 |
  | `redefined` | 用户改过定义，这条不再作数（挂了它的不再算红） |
  | `unhandled` | 还没处理，含用户选了「先放着」的、这一版改了但还在买的 |

- 已经不买的处去掉它的标签（`redefined` 除外：它说的是定义，不随 app 变）。

## 写法

只动 `session` 下的 `conditions` 和 `tags`；`snapshot` 是第 1 步写的，不改。完整的一段长这样：

```yaml
session:
  snapshot:
    seen: {pc: 171}
    samples: [s-pc-3, s-pc-9]
    at: '2026-11-10'
  conditions:
    - {where: plateau.not_stale, from: [f-pc-9, f-pc-10], state: "unmeasured 2026-11-10 用户同意新加"}
    - {where: no_gap_up, from: [f-pc-12], state: "declined 2026-11-10 用户说这种可以买"}
    - {where: plateau.cut, from: [], state: "pending 2026-11-12 两轮之间用户定：「冲高那根也算阶跃」；图：QBTS 2024-11-25；待下一轮实施；2026-11-12 已写进定义"}
  tags:
    f-pc-10: for_tuning
    f-pc-12: accepted
```

- `conditions` 每行恰好 `where`、`from`、`state` 三个键，多一个少一个整段都读不出；`from` 是编号的数组，`state` 是一个字符串。
- **三种笔误会让整份 `mapping.yaml` 读不出**（不只是会话段坏，`compare` 也跟着用不了），引用户原话时最容易犯：
  - `state` 没加引号，里面又有半角冒号——`state` 整句一律用半角双引号括起来；
  - 双引号里又套了半角双引号——引用户原话用「」括，不用 `"`；
  - `tags` 下面的行缩进和别的行没对齐——每行前面的空格数照上面的例子。
- 同一条条件只占一行：动笔前先看现有的行，这一轮已经记过的（中断后接着做时会遇到）只补缺、不重记。
- 上一轮留下的行不删：条件的去向变了（量过了、用户改主意了）就在那一行的 `state` 后面接着写，开头词换成现在的。
- `tags` 的值只能是上表六个词之一。

## 写完核对

```bash
uv run python .claude/skills/annotation-round/scripts/round_state.py <R>
```

`round_state.py <R>` 打印「快照已写进会话段: True」，且「mapping 问题」「会话段问题」都是 None。三样缺一不可：文件被写坏到整份读不出时，「会话段问题」那一格什么也不会报，只有「快照已写进会话段」会变成 False。没过就照输出里的提示修 `mapping.yaml`，再跑一遍。
