# 归组与 pattern 页（unsorted、M9、计数）

Status: ready-for-agent
Progress: not-started
Blocked by: 06

## Purpose

用户先看特征、后定目标。本票让未归类的样本按骨架成行地挪进某个 pattern；还没有 app 时，用户也能从 pattern 页的计数里发现混进来的别的东西。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.2「淡化」；5.6 全节；用户故事 19～22。
- 决策：[界面显示的对称与统一](../annotation-path2/issues/15-display-consistency.md)的 Answer；说明书报告 M9。
- 前置交付：[06](06-samples-and-members.md)。

## Inherited Direction

- 共用执行边界。
- **计数照决策票 15**：
  - 一律数样本，写成 `pos k/N · neg m/M`；
  - 点开后就地分排，各排之和等于分母；
  - 是 0 也显示；
  - 凡是数样本的数都能点开。
  - 防的是：同一个数在不同地方意思不同，被读错。
- **负样本的「像」必须有对象**：挂在 `unsorted` 的负样本算没填完（说明书 ③；M9）。
- 同一样本收了几个同名框时，按「任一个」算（V-15-1 的默认，待验证）。
- 骨架用 03 的实现。

## What to build

- **unsorted 页**：
  - 按骨架分行；
  - 一整行可以 `move` 进已有 pattern，或者 `+ new`；
  - 负样本那一行加灰字 `pattern?`，带悬停提示；
  - 一行 `samples` 计数。
- **pattern 页**：
  - `definition` 输入框；
  - 页头计数；
  - features 区平铺，每块带 `in` 计数和属性的 `true` 计数，块之间画 `↓`，父子写成 `横盘 ⊃ 缩量`；
  - samples 表按 judgment 折行。
- **计数**：点开后就地分排。
- **淡化**：别的 pattern 的样本、它们的 bracket，以及只被它们收进的框，都画淡一些。
- **轨序**：`annotate` 的轨序改成按当前 pattern 里各段的先后。

## Blocked by

06

## Acceptance criteria

- 用一份固定的例子标注（存成 02 格式的批次文件）断言：各处计数正确，点开分排后各排之和等于分母，0 也显示。
- 骨架分行和 03 的例子一致。整行 `move` 以后样本的归属改变，刷新后还在。
- 挂在 unsorted 的负样本显示 `pattern?`。
- 拍截图自查（共用执行边界第 5、6 条）。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

## Validation responsibility

为 V-15-1 实现默认规则。V-15-1 不在票里收口，见[拆分总览](../ticket-breakdown.md)「验证责任」。
