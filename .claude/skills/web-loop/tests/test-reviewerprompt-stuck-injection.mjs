// 验 reviewerPrompt 接受新 stuckSignal 参数,程序化注入到 prompt,
// 不再让 reviewer 自己 bash cat ${WORKDIR}/rounds/.../impl.md
// P0-1 part (iii) 的 TDD RED test
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATE = resolve(__dirname, '..', 'workflow-template.js');
const src = readFileSync(TEMPLATE, 'utf8');

// 抓 reviewerPrompt 函数源码
const fnMatch = src.match(/function reviewerPrompt[\s\S]+?\n\}/);
assert(fnMatch, 'reviewerPrompt 函数未找到');
const fn = fnMatch[0];

// (a) 函数签名必须含 stuckSignal 参数
// 注:stuckSignal 在解构参数 {…,stuckSignal} 内,用 \([^)]*stuckSignal 匹配参数列表
assert(fn.match(/function reviewerPrompt\([^)]*stuckSignal/),
  'reviewerPrompt 签名应含 stuckSignal 参数');

// (b) reflectBlock(或其取代者)不得再含 "bash: cat ${WORKDIR}" 指令
//     reviewer 不应被指示读 impl.md
assert(!/bash:\s*cat\s+\$\{WORKDIR\}\/rounds/.test(fn),
  'reviewer prompt 不应含 "bash: cat ${WORKDIR}/rounds/.../impl.md" 指令(P0-1 part iii)');

// (c) 函数体应当通过 stuckSignal 内插已解析的 reviewer_stuck 字段
//     检查方式:函数体内含 ${stuckSignal} 或 stuckSignal 拼接
assert(/\$\{stuckSignal\}|stuckSignal\s*[?:|]|\+\s*stuckSignal/.test(fn),
  '函数体应内插 stuckSignal');

// 调用方:第一轮(round=1)调用时 stuckSignal 应是空串(无上轮)
// 第二轮 stuckSignal 应来自 read implementer agent 的结构化输出
// 这条约束由调用点 grep 验证
// 注:实际 call site 在 parallel(REVIEW_LENSES.map(lens=>()=>agent(reviewerPrompt(...),...)))
const callSite = src.match(/agent\s*\(\s*\n?\s*reviewerPrompt\([\s\S]+?\}\)\s*,[\s\S]+?REVIEWER_SCHEMA/);
assert(callSite, 'reviewerPrompt 的 agent 调用点未找到');
assert(callSite[0].includes('stuckSignal'),
  '调用点应传 stuckSignal 参数');

console.log('PASS · test-reviewerprompt-stuck-injection');
