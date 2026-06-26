import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// finalize 引用 pausedReason
assertContains(src, 'pausedReason', 'finalize 引用 pausedReason');

// SUMMARY 顶部 PAUSED 节
assertMatches(src, /##\s*⚠?\s*PAUSED|PAUSED\s*·\s*触发判据/, 'finalize prompt 含 PAUSED 节');

// 续修指引
assertMatches(src, /续修指引|续修协议|续修/, 'finalize PAUSED 节含续修指引');
assertContains(src, 'human-hint-r', 'finalize 提 human-hint-r{N+1}.md 写入');
assertContains(src, 'resumeFromRunId', 'finalize 提 resumeFromRunId');

ok('test-finalize-paused');
