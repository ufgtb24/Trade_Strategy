# 差 tag 不看属性：属性对不上时仍显示 =

Type: task (HITL)
Status: open

## Question

### Purpose

差 tag 是用户在 pattern 页判断「我的标注和 mapping 哪里对不上」的依据；这张票让属性一级的对不上也算进 差 tag，使 pattern 能对回用户的标注、标注里画在属性上的理由也看得出有没有被 mapping 接住。

**现状算法**（`docs/research/2026-10-28_annotation-web-loop/repro/backend_contract.md`「差」一节；原型 `mock_v4.html` 的 `diffOf`）：一个 sample 的成员框和 mapping 比，只比特征名——缺了必须有的特征名记 `−X`，成员里有 must_not 的特征名记 `+Y`，必须有齐但先后不同记 `order`，三者都没有就是 `=`，悬停「标注和 mapping 一致」。positive sample 和 negative sample 用同一种算法。属性完全不参与。

**漏洞**：mapping 里属性也有级（演示 mapping 中「放量」「突破过好几个峰」是挂在放量突破上的 must 属性），但 差 tag 看不到它们，两个方向都会出错：

- **positive sample**：必须有的属性判成 false，差 tag 仍是 `=`。原型演示数据里就有一例：WHLRP 2024-03-21 那个 positive sample，放量突破框上「突破过好几个峰」= false，mapping 定它 must，差 tag 却显示 `=`、悬停说「一致」；同一页 features 区该属性写着 `2/3`，两处说法相反。原型里它也不算作和 mapping 对不上的 positive sample。
- **negative sample**：不买的理由画成属性（如回踩框上「前一天放量长阴」= true），会话把这条属性定成 must_not 后，app 能用 where 把它排除，match tag 是琥珀色的 unmatched；差 tag 却仍是 `=`、悬停「一致」，用户看不出这条理由已经被 mapping 接住。

**建议的默认（待用户确认）**：

- 属性行的级也参与 差 tag：must 属性为 false 记 `−属性名`，must_not 属性为 true 记 `+属性名`；可有可无、excluded、unmapped 的属性不影响，和特征名同一规则。防的是：差 tag 说「一致」、features 区说「有一个没有」，同一页两处打架；画在属性上的理由看不出有没有被接住。
- 属性为 null（没看过）不算差。防的是：把「没看过」当成「没有」，后加的属性让旧图平白多出差（结构化标注那张票已定「没看过 ≠ 没有」）。
- 连带后果，需用户一并确认：属性对不上的 positive sample 从此也算作和 mapping 对不上，会进会话单子的三选一（补上 / 真没有就挪走或改成 negative sample / 留着）。
- 差 tag 里属性要不要带上所属特征名（只写「−突破过好几个峰」，还是标明它是放量突破的属性），解决时再定。

**批准后要改的**：`mock_v4.html` 的 差 tag 算法与悬停、`backend_contract.md`「差」一节；答案并入票「结构化标注：存什么、界面和主视图怎么合」里关于对照的规则。

相关：票「只在 negative sample 上出现的特征：定级时别被一半门槛吞掉」。
