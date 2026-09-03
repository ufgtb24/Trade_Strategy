# 待办：多流引擎的真实 app 践行（pk 应用层）

> 2026-09-01 用户指示「按推荐方向，把真实 app 践行记为独立待办」。状态：**pending**（不在多流引擎 spec/plan 范围内，独立跟进）。

## 目标

让多流能力的第一个**真实消费者**落地：一个生产 app 使用「同一 detector 产多条命名流」的能力，端到端验证它在真实业务中有用（而非只被测试 fixture 消费）。

## 方向（已定：改 bb_v1 多流化）

**让 `BODetector` 产 bo + pk 两条流**——把内部本就计算的峰（`_active_peaks`）yield 成 `PeakEvent` 流，作为 bb_v1 的 pk 节点。理由：

- 贴合度最高：`BODetector` 内部本来就检测峰，多流化是顺理成章的产出，无重复逻辑
- **对 bo 是纯增量**：多流下峰与突破同趟共享 `_active_peaks`，bo 流逐字不变，matches/eval 不受影响（这正是方案③相对①的决定性优势）
- 用户原本接受「重新创建语义等价的新 app」的成本，改 bb_v1 比新建更省

（备选：新建独立 app 承载 pk——仅当 bb_v1 多流化遇到不可接受的耦合时再考虑，默认不改。）

## 前置依赖（必须全部满足）

1. **多流引擎 + ref_slots + solve 落地**（`docs/superpowers/plans/2026-09-01-multistream-engine-and-refs.md` 实施完成）
2. **A9 tune-gates 同步**——已延期（另一 worktree 优化 tune-gates，避免错乱）。**开始本待办前必须先补 A9**，否则多流 app 无法调参/静默口径分裂

## 本待办内的待拍事项（来自 pk-display 研究，届时逐一拍板）

- **`PeakEvent` 几何三选一**：撒谎 `confirm` 7~14 根 / 主 marker 落在真峰右侧 / 做 E1（span × price）——三方案同等
- **`bo_only` 上 eaten 恒为空集**怎么处理（定理 T1：`breakout ⪰ peak` 且 `exceed < supersede` 时 supersede 永不触发）——建议接受只显示 broken/alive 两态
- **大阴线 kind**（`bear_drop=0.05` / `bear_min_rh=0.20`）是否随 pk 应用层一并做
- pk 节点 `solve=False`（零边 pattern `bo_only` 的硬阻断，依赖 solve 已落地）

## 参考

- 多流引擎 spec：`docs/superpowers/specs/2026-09-01-multistream-engine-and-refs-design.md`
- 三态显示设计（待办触发源）：`docs/research/2026-08-31_pk-display-three-approaches/final_report.md`
- 用户对方案③的倾向记录：本目录 `final_report.md`
