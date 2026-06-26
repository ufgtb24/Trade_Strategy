import { readSkillMd, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readSkillMd();

// args 表 staleRounds 行补 P1 耦合说明
assertMatches(src, /staleRounds[\s\S]{0,500}max\(1,?\s*staleRounds\s*-\s*1\)/, 'staleRounds 注 P1 耦合 = max(1, staleRounds-1)');

// 三条机检判据节
assertContains(src, '三条机检判据', '新节「三条机检判据」');
assertContains(src, 'oscillating', 'SKILL.md 提 oscillating');
assertContains(src, 'treadmill', 'SKILL.md 提 treadmill');
assertContains(src, 'missingStates', 'SKILL.md 提 missingStates');

// 续修协议节
assertContains(src, '续修协议', '新节「续修协议」');
assertContains(src, 'paused.latest.md', 'SKILL.md 提 paused.latest.md(P2-3 rename)');
assertContains(src, 'human-hint-r', 'SKILL.md 提 human-hint-r{N+1}.md');
assertContains(src, 'resumeFromRunId', 'SKILL.md 提 resumeFromRunId');

// implementer = opus 决策小节
assertContains(src, 'implementer = opus', '新小节「implementer = opus(本 skill 例外)」');
assertContains(src, '§5.1', 'SKILL.md 引用 final_report §5.1 决策记录');

ok('test-skill-doc-decision');
