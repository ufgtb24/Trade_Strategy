# 票 04 独立审查：Spec 轴

固定点 3e2637a，审查时的分支尖 d50f62f。子代理看不到执行过程。下面是它的报告原文，「处理」节是执行者写的。

**总体**：改名忠实，无阻塞项。我剥掉允许项后重新 grep，没有旧义残留；`hits`、`hit_id`、`hit_fp_counts`、`summary.hits`、`has_hit` 与实际代码一致；description 已改，译法表没有旧义。

**(a) 缺失或只做了一部分**
1. 边界第 4 条要求跑全套，「失败清单必须一样」。`evidence/04/logs` 只有 skill 与 web-loop。其他测试不引用这些 skill，风险低，但需补跑或写明。
2. 票要求「统计配对和「一致」两类单独列出条数」。`tune-gates-v3/tests/test_scoring.py` 的 :112、:321 属「一致」，被归入统计配对，计数差 2。

**(b) 范围蔓延**：没有。

**(c) 实现得不对**
1. `tune-gates/multivar_core.py` :446-447 写「至多属于一个 hit(387 股实测零命中)。命中说明拓扑变了」。这里的命中指查重断言触发，会读成零 hit。总览要求「会读混时才改」，此处该改。
2. authoring-path2-app 有 9 处「匹配」改成了「求解」，边界第 12 条写的是「命中」。求解语义更准，但总览要求「在完成记录里写旧名、新名和理由」。

**另记（非本票引入）**：diagnose-event 的 `reference.md`、`detectors/throwback.md` 叫人看 scan 的 `dropped_hits`，后端不产这个键，冒烟也打印 False。

## 处理

- (a)1 写明：只改了 `.claude/skills/`，`tests/`、`scripts/`、`path2*` 没有代码引用这个目录（只有两处注释提到路径）；`tests/` 里那批真实行情测试读 `datasets/pkls`，本票按调度约定不读。理由写进完成记录。
- (a)2 已修：`gen_allow.py` 的 `scoring.py` 规则收窄到 `scripts/scoring.py`，两行回到「一致」。
- (c)1 已修：这处和同一机制的另外两处（:487、:492）一起改成「触发 / 出现」。
- (c)2 写进完成记录。
- 另记：已按 Standards (a)1 修。
