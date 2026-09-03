# tb v3 调试埋点完善 — 实施报告(2026-08-12)

分支 dag,HEAD 起点 ad5ed57。按 authoring-path2-detector skill §3 debug 菜单契约 + V2 容器先例(throwback.py:容器 tb 只挂 entry+gate,段 tb_seg 挂 confirm+end)实施。

## 改动说明

### 1. path2/atoms/throwback_v3.py — 埋点身份重挂 + gate helper 自建(纯埋点,行为/match 零变化)

- 段级 6 处 debug_break 的 class_id 从 `'tb_v3'` 改 `'tb_seg_v3'`:
  - `end` ×5:phase2_break 截断(bar=i-1)/ weak(bar=i-1)/ rise(bar=i-1)/ timeout(bar=i)/ 收尾强制闭合(bar=end)
  - `confirm` ×1:企稳确认(bar=i)
- 容器 1 处(L274 附近,bar=bo_idx)保持 `'tb_v3'`(entry)
- 自建 `_emit_tb_gate_v3`:从 throwback_v1._emit_tb_gate 逐字复制,唯一改动 = GateFailure.class_id 与 debug_break 的 class_id `'tb_v1'`→`'tb_v3'`;保留 `stop_at_frame=sys._getframe(1)`;新增 `import sys` 与 `from path2.debug import current_symbol`(逐字复制所需,任务书只提了 sys)
- 5 处调用点(L88/97/108/153/179)`_emit_tb_gate` → `_emit_tb_gate_v3`;L38 import 行移除 `_emit_tb_gate`(只留 `_atr_at, _has_stop_signal`)
- throwback_v1.py / throwback.py 零改动

**与任务书的偏差(一处笔误,已按代码事实执行)**:任务书 joint Counter 写 `('end','tb_seg_v3'):4`,但段级 end 埋点实际 5 处(L94/114/122/130/175 全部是 end 语义)——「总数 8」自洽的分布是 1(gate)+1(entry)+1(confirm)+5(end)= 8;end×4 则总数 7 对不上。任务书正文「confirm×1 + end×4」同样应为「confirm×1 + end×5」(6 处段级 = 1 confirm + 5 end)。

### 2. tests/path2/atoms/test_throwback_v3_debug_anchor_kinds.py(新增,6 测试)

照 V2 版 test_throwback_debug_anchor_kinds.py 的 ast 静态模式:
- 全模块(含 _emit_tb_gate_v3 内部)debug_break 总数 == 8
- 每处 anchor_kind/class_id 均为 str literal
- (anchor_kind, class_id) joint Counter 严格 == `{('gate','tb_v3'):1, ('entry','tb_v3'):1, ('confirm','tb_seg_v3'):1, ('end','tb_seg_v3'):5}`
- `_emit_tb_gate_v3` hook 行为测试(照 test_throwback_debug_hook.py 模式):on_gate=None 早退不调 debug_break;on_gate 非 None 时 debug_break 收到 gate_idx(非 bo_idx)、GateFailure.class_id=='tb_v3'、on_gate 仍被调用

TDD 流程:先写测试跑出 RED(4 failed:总数 7≠8、joint 分布不匹配、`_emit_tb_gate_v3` 不存在),实现后全绿。

### 3. path2_web_ui/src/stores/view.ts — anchorsOf 新增两条目(不动现有任何条目)

- `tb_v3`(V3 容器):entry 一条,bar=findBoBar(e.anchor_bo_ids,events) fallback e.start_idx,含 disabled/disabledReason(照 tb 条目);hint 写 v3 语境(ThrowbackDetectorV3.detect per-bo 入口)
- `tb_seg_v3`(V3 段):confirm(bar=e.start_idx)+ end(bar=e.end_idx)两条(照 tb_seg 条目);hint 写 v3 语境(confirm=企稳确认根开段 / end=段出口根,weak/rise/timeout/break)

## 测试命令与输出摘要

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/path2/atoms/test_throwback_v3.py tests/path2/atoms/test_throwback_v3_debug_anchor_kinds.py -v` | **15 passed**(原 9 + 新 6,test_throwback_v3.py 零改动) |
| `uv run pytest tests/path2/atoms/test_throwback.py tests/path2/atoms/test_throwback_unified.py tests/path2/atoms/test_throwback_debug_hook.py tests/path2/atoms/test_tb_e2e_outcomes.py -q` | **39 passed**(V1/V2 零回归) |
| `uv run pytest tests/path2/atoms/test_throwback_debug_anchor_kinds.py tests/path2/atoms/test_tb_on_gate.py -q` | **4 failed / 7 passed** —— 预存失败(V2 版测试 baseline 还是旧的「2 处」,throwback.py 实际 9 处;与本次无关,按任务书记录不修;test_tb_on_gate.py 实际全过) |
| `cd path2_web_ui && npx vue-tsc --noEmit` | **零错** |

## 前后端对拍表

后端 debug_break 分布(throwback_v3.py 全模块 8 处)↔ 前端 anchorsOf:

| class_id | anchor_kind | 后端 bar | 前端 key / bar | 对齐 |
|---|---|---|---|---|
| tb_v3 | entry ×1 | bo_idx(= last_bo.end_idx) | tb_v3 / entry · findBoBar(anchor_bo_ids) = bo.end_idx(fallback e.start_idx,disabled 阻塞) | ✓ 严格相等 |
| tb_v3 | gate ×1 | gate_idx | 不进 anchorsOf(gate 走入口 A failedAttempts 卡片路径,与 V2 tb 的 gate 同先例) | ✓ 项数守恒(UI ≤ 后端) |
| tb_seg_v3 | confirm ×1 | i(= 企稳确认根 = 段 start_idx) | tb_seg_v3 / confirm · e.start_idx | ✓ 严格相等 |
| tb_seg_v3 | end ×5 | phase2_break(i-1)/ weak(i-1)/ rise(i-1)/ timeout(i)/ 收尾闭合(end),均为段 exit 根 | tb_seg_v3 / end · e.end_idx | ✓ 严格相等(5 处后端合并为 1 个 UI 菜单项,契约允许) |

要求核对:`tb_v3={entry, gate}`, `tb_seg_v3={confirm, end}` —— 满足。DEBUG_ENABLED_CLASSES 由 anchorsOf keys 自动派生,含 tb_v3/tb_seg_v3 无额外改动。

## Commit

- `git log --oneline -2` 后补:
  1. `fix: tb v3 调试埋点按容器模式重挂(confirm/end→tb_seg_v3,gate 身份 tb_v1→tb_v3)`(throwback_v3.py + 新测试)
  2. `feat: 前端 anchorsOf 补 tb_v3/tb_seg_v3 调试锚点(前后端同 PR 契约)`(view.ts)

## Concerns

1. 任务书 joint Counter 的 `end:4` 是笔误,实际 end:5(见改动说明 §1)——已在测试 baseline 与文档注释中写明依据,如与任务书有出入以此报告与测试为准。
2. 任务书说「6 个调用点」,实际 `_emit_tb_gate` 调用点 5 处(L88/97/108/153/179);任务书列出的行号本身即是这 5 处,「6」为笔误。已全部改 `_emit_tb_gate_v3`。
3. V2 版 test_throwback_debug_anchor_kinds.py 4 failed 为预存状态(埋点数 9≠2 旧 baseline),与本次改动无关,未修。
4. 未 push / 未开 PR / 未 merge(按任务书)。
