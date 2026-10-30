# 外壳基线矩阵：现模板上的场景结果

外壳：`.claude/skills/web-loop/tests/dryrun.mjs`；场景：`.claude/skills/web-loop/tests/test-dryrun-scenarios.mjs`（单场景运行：`SCN='^T2' node ...`）。
跑法：`node .claude/skills/web-loop/tests/run-all.mjs`。结果取自 2026-10-29 现模板（未改动）：21 个场景，3 通过，18 失败。

外壳让 `agent()` 按 label 返回预设结果，只验证脚本自己的控制流；不证明真 agent 会照 prompt 做。回滚的文件层验证见 `rollback_fs.mjs`（临时 git 仓库，已实测：旧做法 `git checkout -- .` 把 A 退回 A0、X 的开跑前脏改动被冲、C 留着；快照做法三项全对）。

| 场景 | 清单条 | 构造 | 现模板结果 | 期望 |
|---|---|---|---|---|
| G0 | 0 | 缺省配置、全 pass | PASS | 语法可过（接受顶层 return），收敛 |
| G1 | 0 | args 字符串 vs 对象 | PASS | 两种形态调用序列一致 |
| T1 | 10 | 3 lens 各 1 条 must 原样不动 | PASS | 仍暂停（真停滞） |
| T2 | 10 | ux 报 5 条 must 每轮修 1 条，func/code 无 must | FAIL：判 treadmill 暂停 | 不暂停 |
| T3 | 10 | ux 每轮修 1 条新增 1 条，func 无 must | FAIL：误报 treadmill | 不因 func 误报 |
| T4 | 10 | 第 3 轮收敛，且 treadmill 恰好成立 | FAIL：finalize 带 `## ⚠ PAUSED` | 收敛不挂 PAUSED，不退 stalled |
| U1 | 12 | 唯一 must 标 unverifiable，子项全覆盖 | FAIL：stalled，1 must left | 收敛 |
| U2 | 12 | 评审自报 fail 但台账只有 nice | FAIL：stalled | 收敛（verdict 由台账推导） |
| S1 | 14 | issue 带 detail/evidence | FAIL：impl-r02 看不到 detail | 看得到，台账有 4 个字段 |
| S1b | 4 | persist 写 `round_1.md`，impl 读 `round_01.md` | FAIL：写入侧不补零 | 两侧一致、两位数 |
| S2b | 14 | 同子项连续 3 轮 unverifiable，requiredStates 相同 | FAIL：只有 treadmill，missingStates 不触发 | 触发 missingStates |
| S4 | 17 | matchesIssueId 笔误 | FAIL：新 must 被丢，台账无 B | 按新问题入账，不收敛 |
| S5 | 17 | rival 回填 lens=ux | FAIL：记在 ux 名下 | 记在 rival |
| S6 | 16 | lenses=[ux]，refresh 失败一次 | FAIL：stalled，剩 1 条 infra must | 脚本自己关闭，收敛 |
| S7 | 2 | 每轮 capture 失败 | FAIL：34 个 agent，5 轮跑满，不暂停，无 persist | 连续两轮跳过即暂停，有 persist |
| S7b | 2 | implementer 返回 null | FAIL：台账无 lens=workflow 条目（capture、评审照常） | 台账记 workflow 条目 |
| S8 | 13 | implementer 返回 kind/stuck | FAIL：仍派 read-impl-stuck | 不派；kind、stuck 直接用 |
| S8b | 13 | refresh 依赖 impl.md 时缺文件 | FAIL：整轮评审被跳过 | refresh 不依赖 impl.md |
| R1 | 1 | smoke-r02 红 | FAIL：回滚指令不指向 snapshots/r02 | 基于快照，不含裸 `git checkout -- .`；impl-r02 被要求先快照 |
| H1 | 3/15 | impl-r03 能否消费 `human-hint-r7.md` | FAIL：只认 `human-hint-r03.md` | prompt 按通配符消费所有未消费 hint |
| H2 | 3 | implementer prompt 约束 | FAIL：无 to-main，无禁 SendMessage | 有 |

## 外壳断言口径（给 architect 核对）

- 暂停：有 `paused-*` 的 agent 调用，或退出日志含 stalled/paused。
- 收敛：退出日志含 converged（现为 `web-iterate-review done: converged, N rounds, M must left`）。新设计若改成脚本返回值里的 `exitReason`，我改 `exitText()` 一处即可，场景不用动。
- 台账：从 persist prompt 里抠 `issues.json(覆写)=...`；第 4 条改成评审自己落盘、persist 只写增量后，我改 `issuesFromPersist()`（优先读 `reviews/round_NN/*.json` 对应的 respond 数据）。
- S4/S5/S1/S7b 要看台账内容，依赖设计是否保留「台账进某个 prompt」的出口；若不保留，请告知台账能从哪里观察到（脚本返回值？某个 agent 的 prompt？）。
