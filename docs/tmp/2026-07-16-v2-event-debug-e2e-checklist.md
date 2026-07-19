# path2_web Event Debug 手动 e2e Checklist

> **文件起源说明(Task 5 补记 · 2026-07-16)**:v3 role-gated debug 的 spec(`docs/superpowers/specs/2026-07-16-path2-role-gated-debug-design.md` §6.5)与 plan(`docs/superpowers/plans/2026-07-16-path2-role-gated-debug.md` Task 5)都假设本文件已存在、内含 v2 的「场景 A-I」,Task 5 只需在文件末尾追加 v3「场景 J」。经核实(`git log --all` 全历史 + 全仓 grep),这份假设不成立——仓库里从未存在过一份带 A-I 编号的独立 checklist 文件。v2 的手动验证内容(`docs/superpowers/plans/2026-07-14-path2-web-debug-breakpoints.md` 文末「End-to-end manual verification」节)只是 3 条未编号步骤,内联在 plan 文档里,从未被抽成独立 checklist 文件。
>
> 因此本文件由 Task 5 首次创建,直接从「场景 J」开始。下文 J1/J2/J3 内容(逐字照抄 plan 原文,未改动)里对「场景 A-C」/「场景 A/B/C」的引用目前是悬空的——人工执行时请改为参照上面提到的 v2 plan 文档那 3 条步骤,或凭 v2 落地时的记忆复现,而非期待本文件里有对应的 A-I 章节。

---

## 场景 J · v3 anchor_kind-gated 隔离(2026-07-16 补 · spec `2026-07-16-path2-role-gated-debug-design.md`)

### 前置
- 与场景 A-C 相同(PyCharm 以 Debug 方式跑 `path2_web.main` · DEBUG_MODE=1 · 前端 `VITE_API_BASE=http://localhost:8010 npm run dev -- --port 5174 --strictPort`)
- 打开一只有 tb match 的股票(如 TSLA · 2025-01-01 ~ 2026-01-01)

### J1 · 入口 A(brush 框选)anchor_kind 隔离

**目的**:验证 v3 修复 · 入口 A 只 pause 在 gate 失败点 · 不再被 v2 entry/trough/end 埋点污染。

**步骤**:
1. 主图工具栏点「框选」进入 brush 模式
2. 在 K 线主图上框选一段跨越多个 bo 的区间(≥ 50 bar)
3. 观察 PyCharm Debug 面板 · 记录 pause 位置

**判据**:
- ✅ pause 只出现在 `throwback.py:105`(`_emit_tb_gate` 内 · L104 debug_break 后一行)
- ✅ **不再**出现 pause 在 `throwback.py:248`(L247 entry 后)/ `throwback.py:164`(L163 trough 后)/ `throwback.py:217/222`(L216/L221 end 后)
- ✅ 每次 pause · Frame 显示 `_emit_tb_gate` 或 `evaluate_throwback` · 变量含 `gate_idx` / `gate_name` / `measured` / `threshold`
- ⚠ 若框选区间内有多个 bo 走到 gate 失败 · 依然会多次 pause 在 L105 · 但每次都是 gate 语义 · 无其他 anchor_kind noise · Resume 逐个看

### J2 · 入口 D(marker 右键)anchor_kind 精准

**目的**:验证 marker 右键选 anchor 时 · 只 pause 在对应 anchor_kind 埋点。

**步骤**:
1. 选一个 tb marker · 右键弹菜单
2. 分别选 `Debug tb entry` / `Debug tb trough` / `Debug tb end` 三次(每次做完 Resume 到底再做下一个)

**判据**:
- ✅ 选 entry → pause 只在 `throwback.py:248`(L247 entry 后)· 不 pause 在 164/217/222
- ✅ 选 trough → pause 只在 `throwback.py:164`(L163 trough 后)· 不 pause 在 248/217/222
- ✅ 选 end → pause 只在 `throwback.py:217` 或 `throwback.py:222`(L216/L221 end 后 · 取决于 rise vs timeout)· 不 pause 在 248/164
- ✅ 三次调试独立 · 前次 anchor_kind 不污染后次(DEBUG_ANCHOR_KIND env 每次 handler finally 都 pop)

### J3 · v1 兼容 · curl 不带 anchor_kind

**目的**:验证 v3 前端不改的 v1 API 用户 · 依然 fire 全 anchor_kind(与 v2 e2e 场景 A/B/C 兜底覆盖)。

**步骤**:
1. 前端不操作 · 直接在终端手工 curl:
   ```bash
   curl -o /tmp/r.json 'http://localhost:8010/diagnose?pattern_id=bottom_burst&symbol=TSLA&start=2025-01-01&end=2026-01-01&scope=time&start_bar=0&end_bar=250&event_class=tb'
   ```
   (**注**:URL 不含 `&anchor_kind=...` · 模拟 v1 API 用户)
2. 观察 PyCharm Debug 面板

**判据**:
- ✅ pause 依然会命中(证明 v1 兼容 fallback 生效)
- ✅ pause 出现在多个位置(L104/L163/L216/L221/L247 · 全 anchor_kind fire · 与 v2 pre-anchor_kind-gate 行为等价)
- ✅ 与 v2 e2e checklist 场景 A/B/C 用同一路径 · 判定 v3 未破坏 v1 行为
