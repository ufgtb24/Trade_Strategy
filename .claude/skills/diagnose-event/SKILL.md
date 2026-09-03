---
name: diagnose-event
description: 诊断 path2 单个 event(为什么没生成/没 match/confirm 位置)。用户说"诊断 SYM 的 INSTANCE_ID"或"SYM 的 tb/bo/burst 为什么..."时调。自动探测环境(scan 锚定)+ 按 reference 分析。
---

# diagnose-event

诊断 path2 单个 event。用户给 symbol + instance_id(前端事件 id),自动探测环境(scan 锚定 4 参数),按 reference 分析。

## 何时调
用户说:"诊断 X 的 INSTANCE_ID"、"X 的 tb_257_258 为什么没 match"、"bo_182 生出的 tb 为什么远"等单 event 诊断。

## 步骤

### 1. 环境探测(调 skill 自带脚本,固定流程)
在 worktree root 写 /tmp 小脚本(import 调用,不改脚本本体;`${CLAUDE_SKILL_DIR}` 注入时展开为本 skill 目录绝对路径):
```python
import sys; sys.path.insert(0, "${CLAUDE_SKILL_DIR}")
from path2_diag_env import diagnose_env, format_declaration
env = diagnose_env("SYM", "INSTANCE_ID")  # 第二参收 instance_id(如 "tb_257_258#0");
                                          #  可选第三参 scan_path=绝对路径
print(format_declaration(env))
```
(或 `uv run python ${CLAUDE_SKILL_DIR}/path2_diag_env.py` 改顶部变量跑;测试 = 同目录 `test_path2_diag_env.py`,需显式路径跑,不进默认 pytest 收集)

### 2. 声明确认(硬性,不可省)
把声明贴给用户(scan_ts + provenance + 关键阈值 + 窗口),**等用户确认或一句纠正**才继续。
防默认错(曾因没声明、跑整个 pkl 误判"tb 不存在")。用户纠正如:"用主 repo 的 scan"、"用 p2.yaml"(非 scan 快照)。

### 3. 探索态检查
若声明的 provenance 含 `working_copy`(wc.json 存在且 pid 匹配)→ 已用 WC params(探索态真理),继续。
否则用 scan snapshot(浏览态)。用户说"我在探索"但 provenance 非 working_copy → 提示需 Write Copy 镜像(独立 plan)或 Save yaml。

### 4. 诊断分析(按 reference,本目录 reference.md)
读 reference.md,按问题选骨架:
- "tb 为什么没 match" → 骨架 A(读 scan analysis.events/matches,tb.anchor_bo_id→burst.last_bo→where 判定)
- "tb 企稳段为什么进不了 / 退出早 / 没生成 / 只有一段" → 骨架 B(切窗 df + 按
  detector 契约枚举——契约文件在 `detectors/` 目录,按 scan 的 pattern 对号:
  如 throwback.md(方案 C) / throwback_v3.md(V3 多段);无契约文件先读模块
  docstring + 源码)
- "event 完全没生成" → 骨架 C(切窗 + detector.detect)

诊断分析脚本临时写(/tmp),骨架 + API 签名在 reference.md。

## 红线(详见 reference.md)
必须切窗对齐 scan(勿整个 pkl)/ web 在 worktree(scan 在 worktree outputs)/ 先声明 / 目标 pattern = 非 bo_only。

## 详细参考
scan 结构 / API 签名 / 三类诊断骨架 / 典型机制速查 → 本目录 `reference.md`。
