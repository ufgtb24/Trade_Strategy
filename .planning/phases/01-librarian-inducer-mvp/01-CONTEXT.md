# Phase 1: Librarian + Inducer MVP - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning (gap-fix scope only — Phase 1 主体已 commit `3c6b933 finish Phase 1`)

<domain>
## Phase Boundary

**真实状态错位说明**:Phase 1 的 17 条 REQ(SPEC §6.1)与 §9 五条 acceptance 在仓库 `dig_more` 分支已基本落地(110 tests PASS,Phase 0 35 + Phase 1 75)。本次 `/gsd-discuss-phase 1` 不再讨论 Phase 1 的整体设计 — 那些决策已 commit、已测试。

本次 discuss 聚焦在用户使用 dev UI 后发现的**两组 UX/渲染 gap**:

1. **Picker 交互不严谨** — 当前 KeyboardPicker(`33d1327` 之后版本)对端点先后无约束,任意两根 K 线即触发渲染;用户实际需求是"严格强制第一次点 BO、第二次点 BO 之前任意 K 线",且整个交互过程应有明确的状态机提示。
2. **chart.png 渲染对 GLM-4V 不友好** — 当前实现把整个 `df_window`(默认 ~200 bar)整段渲染并在 pk/bo 位置加虚线 + legend + 注释;字体也偏大。新需求:窗口收窄到[左端点, BO]之间;视觉脱敏更彻底(去虚线 / 去注释 / 标题不带语义);Y 轴 pivot 改用 BO close 作锚点(跨样本可比)。

**本次 phase 的"交付边界"是**:
- 修订 `BreakoutStrategy/UI/charts/keyboard_picker.py`(状态机三态化 + 顺序约束)
- 修订 `BreakoutStrategy/UI/charts/canvas_manager.py`(供给 BO 集合 + 联动新状态机)
- 修订 `BreakoutStrategy/feature_library/sample_renderer.py`(渲染窗口 / 视觉脱敏 / pivot / 字号)
- 同步修订 `BreakoutStrategy/feature_library/prompts.py` 与 `inducer_prompts.py` 的 pivot 表述,使**图像通道与文本通道共用同一个 BO close 锚点**(避免 GLM-4V 看到两个不一致的零点)
- 补/改对应单元测试

**out of scope**(继续放在 deferred 给后续 Phase):
- Phase 1.5 的 `epoch_tag` / `superseded_by` 真正激活(schema 已就位,Phase 1 仍写 null)
- Phase 1 SPEC §9 #5 三道硬防线的正式 code review(`/gsd-secure-phase 1` 单独跑)
- Phase 1 SPEC §9 #1 端到端 smoke 在真 GLM-4V API 上的 once-through 验证(放在 `/gsd-verify-work 1` 阶段)

</domain>

<decisions>
## Implementation Decisions

### Picker 状态机(`KeyboardPicker`)

- **D-01: 状态机由两态升级到三态**
  - `IDLE → AWAITING_BO → AWAITING_LEFT → IDLE`
  - `IDLE`:无 sticky;按 P 进入 `AWAITING_BO`,sticky 显示 `[PICK 1/2] Hover the BO bar, press P`。
  - `AWAITING_BO`:按 P 时若 hover 在 detected BO 集合内 → 进入 `AWAITING_LEFT`,sticky 显示 `[PICK 2/2] Hover any K-line BEFORE BO, press P. ESC to cancel`;否则 toast(warn) `This bar is not a detected BO. Hover a BO and press P.`,**保持 AWAITING_BO 不重置**。
  - `AWAITING_LEFT`:按 P 时若 hover idx < bo_idx → 触发 `on_render(left_idx, right_idx)` 后回 `IDLE`;否则 toast(warn) `Pick a K-line BEFORE the BO bar.`,**保持 AWAITING_LEFT 不重置**。
  - 同根:仍 toast `Same bar, hover another` + 保持当前态。
  - Esc:`AWAITING_BO` / `AWAITING_LEFT` 消费(清状态 + toast `Picking cancelled`);`IDLE` 透传(让 canvas_manager 原有 `_on_close_window_key` 处理窗口关闭,保留 70b1c44 之前的设计)。

- **D-02: 第一次点击强制 ∈ detected BO 集合**
  - 该约束于 `33d1327 picker 摒弃 BO 约束` 中曾被取消,本次回归并升级语义:
    - 旧版本(1fe108c):"端点先后无关,sorted 后右端必须 ∈ BO" → 用户可先点左、再点右
    - 新版本(本次):"严格第一次必须 ∈ BO,第二次必须 idx < 第一次" → 顺序敏感
  - `KeyboardPicker.__init__` 需新增依赖注入:`get_bo_indices: Callable[[], frozenset[int]]`(canvas_manager 暴露当前已识别的 BO bar 全局 index 集)。

- **D-03: 错点行为统一为 stay + toast**
  - 不 reset、不前进;用户原话"强制"理解为"必须满足约束",而非"违反即作废"。该选择降低反复劳动,与 dev tool UX 习惯一致。

- **D-04: 回调签名不变**
  - `on_endpoints_picked(left_idx, right_idx)` 维持 `right_idx > left_idx` 的语义;新状态机已天然保证 `right_idx = bo_idx` 且 `left_idx < bo_idx`,无需改 `sample_picker_handler.py`。

### chart.png 渲染(`sample_renderer.py`)

- **D-05: 渲染窗口收窄**
  - 由 `df_window`(全长,~200 bar)改为 `df_window.iloc[left_idx : right_idx + 1]`(用户挑的左端点到 BO 的闭区间)。
  - `render_sample_chart` 的 `pk_index` 形参不再有"盘整起点"语义 — 改名为 `left_index`(或维持名字加 docstring 重定义);`bo_index` 仍为 BO 在传入 `df_window` 中的局部 index。
  - 注意:`sample_picker_handler.handle_endpoints_picked` 当前把 `local_pk = left_idx - window_start` 传给 `preprocess_sample` → `preprocess_sample` 再传给 `sample_renderer`;链路语义需要同步明确为"left_index = 用户挑的窗口左端,**不一定**是盘整 anchor"。`meta.yaml` 的 `consolidation` 字段是否仍按"left_idx 即 anchor"计算,**保持不动**(consolidation 是已锁定的 5 字段语义,Phase 1 不改),这意味着`left_idx` 在数据层兼任 anchor 与渲染左端两个角色,这是**有意识的耦合保留**(consolidation 字段的 anchor 与用户挑的左端是同一根 K 线)。

- **D-06: 视觉去标注**
  - 删除 price 面板的两条 axvline(pk 橙色虚线、bo 蓝色虚线)。
  - 删除 volume 面板的两条 axvline。
  - 删除 `ax_price.legend(loc="upper left")` 调用。
  - 标题维持通用文案 `Breakout sample (anonymized)`,**不**追加 `right edge = BO` 之类的语义后缀(依靠位置约定 + prompt 文本传递 BO 语义)。

- **D-07: Y 轴 pivot 改用 BO close = 0%**
  - 来源:`docs/research/feature_mining_chart_pivot_decision.md` 强推荐(BO 是这批样本的语义不变量,三重锚点重合,跨样本几何同构)。
  - `_build_figure_for_inspection` 中 `pivot_close = float(df_window.iloc[bo_index]["close"])`(原为 `pk_index`)。
  - `_pct_fmt` 公式不变,但因 pivot 改变,所有历史 bar 显示为非正值(BO 上涨 → 历史为负;BO 下跌 → 历史为正,符号自然反映方向)。
  - `ax_price.set_ylabel("Price (% from BO close)")`(原 "% vs pk")。

- **D-08: 文本通道同步切到 BO close pivot**
  - `prompts.py::build_user_message` 当前把 breakout_day OHLCV 表述为"相对盘整起点 +X.X%";改为以 BO close 为锚:`breakout_day(close 锚点 = 0%):open=ΔO%, high=ΔH%, low=ΔL%`(`Δ = (price - bo_close) / bo_close * 100`)。
  - `inducer_prompts.py::build_batch_user_message` 中 batch 每条样本的 breakout_day 行同步改写。
  - 这一改动是为了让**图像通道(Y 轴)与文本通道(prompt 数值)共用同一个零点**,避免 GLM-4V 在 cross-attention 时遇到两套不一致的相对参考系。

- **D-09: 字体压缩**
  - `_build_figure_for_inspection` 内对 fig 局部 set:
    - `rcParams.update({"font.size": 8})`(局部 context manager 或 fig 级别 mpl 参数,**不污染全局 rcParams** — 与 OO API 约束一致)
    - `ax_price.set_title(..., fontsize=10)`
    - `ax_*.set_xlabel/ylabel(..., fontsize=8)`
    - `ax_*.tick_params(labelsize=7)`
  - `figsize=(12, 8)`、`CHART_DPI=100` 不变,chart.png 仍输出 1200×800,K 线主体可视面积不损失。
  - 实现时优先用 `with mpl.rc_context({"font.size": 8}):` 包住整个 figure 构造,避免触碰 `mpl.rcParams` 全局表(防御 OO API 不污染原则)。

### canvas_manager 集成

- **D-10: 暴露 BO 集合到 KeyboardPicker**
  - `update_chart` 中已经把 `breakouts: list[Breakout]` 传给 `_attach_hover` 与端点 marker 系统;新增 `get_bo_indices` 闭包(读 `breakouts` 的 `idx` 字段,返回 `frozenset[int]`),作为 `KeyboardPicker.__init__` 的新参数。
  - `update_chart` 重建 picker 实例,沿用现有的 sticky / toast / marker_redraw 三个钩子。

- **D-11: 端点 marker 重绘行为微调**
  - 状态机进入 `AWAITING_LEFT` 后,canvas 上仍画一根 marker(BO 那根)指示用户已选定第一根;进入 `IDLE` 后清空。
  - 当前 `_redraw_endpoint_markers` 接受 `Iterable[int]`,新状态机在 `AWAITING_BO` 完成时传 `[bo_idx]`,渲染时传 `[]`(因为 chart.png 是另一进程产物,dev UI 上的 marker 与 chart.png 视觉脱敏互不影响)。

### Claude's Discretion

- 状态机 sticky 文案的英文措辞、toast 的具体词句:用户没逐字审过,Claude 可在保持语义不变的前提下微调。
- `_pct_fmt` 中"百分号位置 / 小数位"细节(当前 `"+%.1f%%"`)可微调,只要保证 OCR 友好。
- `prompts.py` 文本通道中 breakout_day 行的中文表述(如"相对突破日 close" vs "vs BO close"等),可在保持"零点 = BO close"语义不变前提下选定。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 项目顶层 / LOCKED 决策(MUST 通读)

- `.planning/PROJECT.md` — 21 条 LOCKED ADR + Phase 1 偏离记录 + 数学常量
- `.planning/REQUIREMENTS.md` — 17 条 v1 REQ + traceability
- `.planning/intel/decisions.md` — 21 条 ADR 详注
- `.planning/intel/SYNTHESIS.md` — ingest 结果总结
- `docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md` — Framework Design ADR(LOCKED,manifest precedence 0)
- `docs/superpowers/specs/2026-04-27-phase1-librarian-inducer-mvp.md` — Phase 1 SPEC §6.1 / §9 / §11 偏离

### 本次 discuss 的研究依据(MUST 通读)

- `docs/research/feature_mining_chart_pivot_decision.md` — **本次决策核心**:tom 第一性原理研究,论证 BO close 作 Y 轴 pivot 的最优性(强推荐 / 次推荐 / 反对,跨样本同构 + ChartLlama / FinChartQA 支撑)
- `docs/research/feature_mining_input_normalization.md` — 双通道脱敏研究(2026-04-28),奠定 chart.png 视觉脱敏 + prompt 文本脱敏的整体方案

### 本次需要修改的代码(MUST 阅读以理解当前状态)

- `BreakoutStrategy/UI/charts/keyboard_picker.py` — 当前两态机,改三态
- `BreakoutStrategy/UI/charts/canvas_manager.py` — `_attach_hover` / `_show_toast` / `_set_status_sticky` / `_redraw_endpoint_markers` / `update_chart` 集成点(grep `endpoint_marker_lines` / `_attach_hover` / `on_endpoints_picked`)
- `BreakoutStrategy/feature_library/sample_renderer.py` — `_build_figure_for_inspection` 与 `render_sample_chart`
- `BreakoutStrategy/feature_library/prompts.py` — `build_user_message`(单图 preprocess prompt)
- `BreakoutStrategy/feature_library/inducer_prompts.py` — `build_batch_user_message`(batch Inducer prompt)
- `BreakoutStrategy/dev/sample_picker_handler.py` — `handle_endpoints_picked` 链路(verify left_idx 角色不变)
- `BreakoutStrategy/feature_library/preprocess.py` — `preprocess_sample` pipeline(检查 pk/left 语义)
- `BreakoutStrategy/feature_library/sample_meta.py` — meta.yaml schema(consolidation 字段)

### 现有测试(MUST 复跑 + 补充)

- `BreakoutStrategy/UI/charts/tests/test_keyboard_picker.py` — 现有两态机断言,需重写为三态机
- `BreakoutStrategy/feature_library/tests/test_sample_renderer.py` — 含 `test_render_sample_chart_does_not_pollute_global_backend` / `test_render_sample_chart_anonymizes_title_and_normalizes_yaxis`
- `BreakoutStrategy/feature_library/tests/test_prompts.py` — 含 `test_build_user_message_anonymizes_ticker_date_and_absolute_price`
- `BreakoutStrategy/feature_library/tests/test_inducer_prompts.py` — batch user message 脱敏断言
- `BreakoutStrategy/dev/tests/test_sample_picker_handler.py` — 端点处理 handler 单测

### 历史参考(non-binding,理解上一轮设计意图)

- `docs/superpowers/plans/2026-04-28-phase1.1-chart-input-and-normalization.md` — 上一轮 Phase 1.1 plan(已实现并 commit;本次是其修订版)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`KeyboardPicker` 注入式回调结构**:`get_hovered_bar` / `on_render` / `on_toast` / `on_sticky` / `on_marker_redraw` 五钩子设计良好,本次只需 +1 钩子(`get_bo_indices`)。状态机扩展不影响外部接口。
- **`canvas_manager._show_toast` / `_set_status_sticky` / `_redraw_endpoint_markers`**:已就位,新状态机沿用,无需新建 UI 控件。
- **`_build_figure_for_inspection` 已是 OO API**:用 `Figure + FigureCanvasAgg` 不污染全局 backend,改 pivot / 字体只动函数内部。
- **`FuncFormatter`**:已用于 Y 轴百分比格式,改 pivot 只换一行。
- **fastembed 384-d L0 + cosine 0.85 合并** 与本次决策的关系:cross-sample candidate 文本若使用同一个零点世界(BO close),embedding 空间会更聚拢(`docs/research/feature_mining_chart_pivot_decision.md` §3 跨样本同构论证)。

### Established Patterns

- **OO API 不污染全局 backend / rcParams** — D-09 字号方案严守这一约束(用 `mpl.rc_context` 局部覆盖)。
- **三层钩子注入到 picker** — 解耦 UI / 状态机,单元测试时 mock 钩子而不需 Tk 主循环。
- **入口脚本无 argparse,参数声明在 `main()` 顶部** — 本次只改库代码与 dev UI,不改 `scripts/feature_mining_phase1.py`,无 argparse 风险。
- **测试位置约定** — `BreakoutStrategy/feature_library/tests/` 与 `BreakoutStrategy/UI/charts/tests/` 与 `BreakoutStrategy/dev/tests/` 三处对齐。
- **中文注释 / print / log,英文标识符与 UI 文本** — 本次新增 sticky/toast 文案沿用英文(画面交互),docstring 中文。

### Integration Points

- **picker → canvas_manager** 通过五(新六)钩子注入。
- **sample_renderer → preprocess_sample → handle_endpoints_picked → KeyboardPicker.on_render** 是 dev UI 触发链;本次 D-05 改窗口语义不影响链路签名。
- **prompts.py / inducer_prompts.py → meta.yaml → preprocess.py** 是 prompt 构造链;D-08 同步切 pivot 影响所有 prompt 构造点。
- **`get_bo_indices` 数据源**:`canvas_manager.update_chart` 接到的 `breakouts: list[Breakout]`;`Breakout` 类型见 `BreakoutStrategy/analysis/`(下游 planner 需读以确认 idx 字段名)。

</code_context>

<specifics>
## Specific Ideas

- 用户的体验主线诉求(原话):"只渲染两次点击 P 键所在 K 线及其之间的所有 K 线,而不是像现在这样将所有 K 线渲染并将两次 P 键位置标注为虚线。"
- 用户的语义澄清(原话):"两次 P 键其中一个代表 bo,但是另一个不一定是 pk。"
- 用户的状态机要求(原话):"两次 P 键的点击强制第一次必须点击 bo,第二次点击 bo 之前的任意 K 线。在 dev UI 的操作界面点击 P 时予以提示。请你设计提示状态机,保证交互流程得到提示。"
- 用户的字号反馈:对附图(`docs/research/.../sample-1.png` 类似的截图)字体过大不满,要求压缩。
- 用户对 Y 轴 pivot 的态度:在听完 tom 研究后明确选择 BO close 锚点,接受文本通道同步改造。
- **隐含的"left_idx 不再 = pk"语义重构**:`sample_renderer.render_sample_chart` 的 `pk_index` 形参语义在用户脑中已变成"窗口左端"。但 `meta.yaml` 的 `consolidation` 字段(`consolidation_anchor_close` 等)仍以这根 K 线为 anchor — 这种 dual-role 是有意保留的(用户挑的左端 ≡ consolidation anchor)。规划时要避免把 `pk_index` 重命名为完全 anchor-free 的名字,以免破坏 `consolidation_fields.py` 与 `sample_meta.py` 的字段命名一致性。

</specifics>

<deferred>
## Deferred Ideas

- **Phase 1 SPEC §9 #5 三道硬防线 code review**:`REQ-invariant-blind-inducer` / `REQ-invariant-cli-no-feature-content` 这两条要求"code review 验证",尚未走过 `/gsd-secure-phase 1`。本次 gap 范围不包含此审计,作为后续动作。
- **Phase 1 端到端 smoke 在真 GLM-4V API 上的 once-through 验证**:SPEC §9 #1 的 `uv run python scripts/feature_mining_phase1.py` × AAPL × 5 样本端到端 exit 0,本次不验证 — 走 `/gsd-verify-work 1`。
- **G0/G1/G2/G3 ablation**(`feature_mining_input_normalization.md` §8):四组对比未跑;若本次 BO-pivot 决策上线后想用数据复核,可单独立 phase。
- **Phase 1.5 `epoch_tag` / `superseded_by` 真正激活**:Phase 1 schema 已就位且写 null,激活属于 Phase 1.5 范围。
- **dev UI 提示发现性问题**:用户启动 dev UI 后是否要在某处默认提示"按 P 开始挑选样本"(全局 sticky / 顶部 status bar),本次未讨论 — 视下一轮 UAT 反馈再决定。

</deferred>

---

*Phase: 1-Librarian + Inducer MVP*
*Context gathered: 2026-04-29*
*Scope: gap-fix(picker UX + chart rendering)post-`finish Phase 1` commit*
