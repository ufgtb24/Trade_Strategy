# 票 11 独立审查:Spec

审的是 `impl/11-app-and-compare-overlay` 从 be297de(与 annotation-path2 的分叉点)到 a40549b 的 diff,对照票 11、拆分总览「各票共用的执行边界」、spec 4.1/4.3/4.4/5.2/5.7/5.8/6.1/第 7 节 V-S1、用户故事 24、决策票 01 Answer 第 3 节。由 code-review skill 派出的子代理做,看不到实现过程。下面是它的报告原文。

---

这次改动的主体大致合格：mapping 小文件、`compare` 叠画、数据墙测试和两条 e2e 都已落地。但有两处偏离 spec 字面，第 1 条最该改，或者至少报给用户裁定。

**(c) 看似做了、但做法有问题**

1. **`compare` 下换图的规则被架空了**（`path2_web_ui/src/stores/view.ts:703-704`，`SampleCard.vue`）
   - 现在 `compare` 下只有 pattern 页、unsorted 页的样本卡换图会留在 `compare`。顶栏代码输入、`rally`、`random` 和两种链接一律退回 `annotate`，e2e 第二条也照这个断言。
   - spec 5.2 原话是「用 `symbol` 换图时，不退出 `compare`」。同节说明了 `symbol` 指什么：「`symbol`：代码输入框，回车打开；另有 `rally`、`random` 两个入口」。票的 Inherited Direction 也写「用 `symbol` 换图时不退出 `compare`（决策票 01）」。现状是 `symbol` 本身恰恰会退出 `compare`，留在 `compare` 的反而是 spec 没提到的样本卡。
   - 决策票 01 的理由也指向不关：「换图不自动关，因为训练段上看着 app 标是用户的自由」。
   - 更顺的读法是：「从 rally、random、代码输入和链接进来时，落在 `annotate`」管的是从非 `compare` 状态进来时的默认落点（比如扫描结果的 `app`、刚打开页面），链接属于从外部带进来的场景，也落在 `annotate`；已经在 `compare` 里时，用 `symbol` 那组（代码输入、`rally`、`random`）换图就留在 `compare`。样本卡留在 `compare` 可以保留。
   - 就算坚持现在的读法，这也是 spec 自相矛盾时做的一次取舍，应该在完成记录里写明、交用户过目。目前提交说明和模块文档都没提。

2. **显示了 mapping**（`TopBar.vue:42`、`:135` 的 `mappingTitle`）
   - `compare` / `app` 下，app 名的悬停提示会逐行列出「特征名 → node」。spec 5.8 和票都写明「不挂第二段的对照 tag……也不显示 mapping」。
   - 次要的一处：`compare` 下 event 的悬停写着 node 名（`annotateLanes.ts` 的 `tip`），再加上它画在哪条特征轨上，等于把这一行 mapping 也露出来了，建议一起去掉。

**(b) spec 没要求的行为**

3. **没有 app 时 `app` 按钮也变灰**（`TopBar.vue:39`）。spec 5.2 只说「当前 pattern 还没有 app 时，`compare` 变灰」。没有 app 可跑时让 `app` 变灰说得通，但这是对 spec 的扩展，应在完成记录里注明。
4. **会另起特征轨**（`compareOverlay.ts:63`）。这张图上没有某个特征的框、却有 event 时，会为这个特征新开一条轨。spec 5.2 写的是「app 的 event 画在用户框所在的同一条轨上」。这样做有用（能看出 app 认出了用户没框的段），但超出了字面要求，属于新增的界面行为，应列给用户。

**(a) 缺失或不完整**

5. 截图只在 e2e 的测试结果里，`evidence/11/` 还没建。票要求「拍截图自查（共用执行边界第 5、6 条）」；按执行边界第 9 条，证据要在合回前放进去。新起的界面名（`linked-app`、`loading` / `load_failed`）也要在完成记录里列给用户（执行边界第 6 条、spec 4.3）。这两项目前都还没做，属于收尾项。

**核对过、符合要求的**
- **mapping 文件**：放在 `path2_apps/<app>/mapping.yaml`，随 app 进 git；有没有这个文件就决定当前 pattern 有没有 app；格式写在 `path2_web/mapping.py` 的模块文档里。
- **只叠画、不做对照**：event 档位画到 detected，用档位色、不套琥珀；hit 画在 `bracket` 轨上，用琥珀底、实线边；e2e 核对过没有任何对照 tag。
- **`tiers` 开关**：只管 band 上的 `qualified_only` / `detected_only`，默认开。
- **跑 app 和数据墙**：走 `/preview`，窗口终点截到 2025-12-31；数据墙测试带了对照组，证明这组数据测得出泄漏。
- **参照层**：`peaks` 在 `compare` 下可用，切到 `app` 自动关。
