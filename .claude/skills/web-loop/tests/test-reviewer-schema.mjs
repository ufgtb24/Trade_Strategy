import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// REVIEWER_SCHEMA 块内含新字段
assertMatches(src, /REVIEWER_SCHEMA\s*=\s*\{[\s\S]*goalEcho/, 'REVIEWER_SCHEMA 含 goalEcho');
assertMatches(src, /REVIEWER_SCHEMA\s*=\s*\{[\s\S]*coveredSubgoalIds/, 'REVIEWER_SCHEMA 含 coveredSubgoalIds');

// verified 子 schema 含 coveredSubgoals 必填
assertMatches(src, /verified[\s\S]{0,400}required:\s*\[[^\]]*coveredSubgoals/, 'verified 子 schema coveredSubgoals 必填');
assertMatches(src, /verified[\s\S]{0,500}coveredSubgoals:\s*\{[^}]*type:\s*"array"/, 'verified.coveredSubgoals type=array');

// 注释保留(非收敛依据)
assertContains(src, '注意力归位仪式', 'goalEcho 注释 "注意力归位仪式"');
assertContains(src, '不进收敛判据', 'goalEcho 注释 "不进收敛判据"');

ok('test-reviewer-schema');
