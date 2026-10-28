import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// META_AGENT_SCHEMA 顶部声明(物理禁双源真理:无 issues / verified / rootCauseHypothesis 字段)
assertContains(src, 'META_AGENT_SCHEMA', 'META_AGENT_SCHEMA 顶部声明');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,800}forbiddenApproaches/, 'schema 含 forbiddenApproaches');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,800}prioritizedMustIds/, 'schema 含 prioritizedMustIds');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,800}escapeRequest/, 'schema 含 escapeRequest');
assertMatches(src, /META_AGENT_SCHEMA[\s\S]{0,1000}required:\s*\[\s*"forbiddenApproaches"/, 'schema required = forbiddenApproaches');

// 4 类 escapeRequest type
assertContains(src, 'missing_state', 'escapeRequest type missing_state');
assertContains(src, 'rubric_too_strict', 'escapeRequest type rubric_too_strict');
assertContains(src, 'goal_unrealistic', 'escapeRequest type goal_unrealistic');
assertContains(src, 'reviewer_disagreement', 'escapeRequest type reviewer_disagreement');

// 触发判据 P1_TRIGGER_STREAK = max(1, STALE_ROUNDS - 1)
assertContains(src, 'P1_TRIGGER_STREAK', 'P1_TRIGGER_STREAK 变量');
assertMatches(src, /P1_TRIGGER_STREAK\s*=\s*Math\.max\(\s*1\s*,\s*STALE_ROUNDS\s*-\s*1\s*\)/, 'P1_TRIGGER_STREAK = max(1, STALE_ROUNDS-1)');

// 三条触发判据
assertContains(src, 'coveredSubgoalsUnchangedRounds', 'P1 触发 coveredSubgoalsUnchangedRounds');
assertContains(src, 'gitDiffSmallRounds', 'P1 触发 gitDiffSmallRounds');
assertContains(src, 'p1Triggered', 'p1Triggered 变量');

// meta-agent 调用 label + model opus
assertMatches(src, /label:\s*`?meta-agent-?[\s\S]{0,200}model:\s*"opus"/, 'meta-agent 调用 model=opus');
assertMatches(src, /label:\s*`?meta-agent[\s\S]{0,200}phase:\s*"iterate"/, 'meta-agent 调用 phase=iterate');

// schema 强约束 prompt 字样
assertContains(src, '不质疑、不修改、不复判', 'meta-agent prompt 强约束');
assertContains(src, '台账真相', 'meta-agent prompt 「reviewer 的 issues/verified 是台账真相」');

// 落 decision_log.json append-only
assertContains(src, 'decision_log.json', '落 decision_log.json');

// escapeRequest 触发 paused
assertMatches(src, /escapeRequest[\s\S]{0,500}pausedReason\s*=\s*['"]escapeRequest|pausedReason\s*=\s*['"]escapeRequest/, 'escapeRequest 非 null → pausedReason=escapeRequest');

ok('test-p1-meta-agent');
