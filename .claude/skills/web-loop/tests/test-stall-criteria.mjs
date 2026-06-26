import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 判据 1: oscillating(regressionCount >= 2 + status open/regressed)
assertContains(src, 'oscillating', '判据 1 变量 oscillating 存在');
assertMatches(src, /regressionCount[\s\S]{0,200}>=\s*2/, '判据 1 算法 regressionCount >= 2');

// 判据 2: treadmill(REVIEW_LENSES 上同 lens 新 must 增速 ≥ 修复速持续 2 轮)
assertContains(src, 'treadmill', '判据 2 变量 treadmill 存在');
assertMatches(src, /REVIEW_LENSES\.some|REVIEW_LENSES\.some/, '判据 2 算法遍历 REVIEW_LENSES');

// 判据 3: missingStates(GOAL_SUBGOALS 上 unverifiable ≥2 轮 + requiredStates 重叠)
assertContains(src, 'missingStates', '判据 3 变量 missingStates 存在');
assertMatches(src, /GOAL_SUBGOALS[\s\S]{0,400}unverifiable/, '判据 3 引用 GOAL_SUBGOALS + unverifiable');
assertMatches(src, /requiredStates[\s\S]{0,300}重叠|重叠[\s\S]{0,200}requiredStates/, '判据 3 检测 requiredStates 重叠');

// 触发后写 paused.latest.md + 退出循环(P2-3 rename)
assertContains(src, 'paused.latest.md', 'paused.latest.md 协议文件');
assertMatches(src, /Write 工具[\s\S]{0,300}paused\.latest\.md|\$\{WORKDIR\}\/paused\.latest\.md[\s\S]{0,300}Write 工具/, '写 ${WORKDIR}/paused.latest.md(用 Write 工具)');
assertContains(src, 'pausedReason', 'pausedReason 字段记录触发判据');

// 触发判据描述
assertContains(src, '判据 1', 'paused.md 描述判据 1');
assertContains(src, '判据 2', 'paused.md 描述判据 2');
assertContains(src, '判据 3', 'paused.md 描述判据 3');

ok('test-stall-criteria');
