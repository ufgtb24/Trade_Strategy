// 验 implementer agent 调用带 schema,强制包含 reviewer_stuck 三字段
// P0-1 part (ii) 的 TDD RED test
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATE = resolve(__dirname, '..', 'workflow-template.js');
const src = readFileSync(TEMPLATE, 'utf8');

// 抓 implementer agent 调用块(label:implLabel 起到下一个 agent 调用为止)
const implCallMatch = src.match(
  /label:\s*implLabel[\s\S]+?\}\s*\)\s*;/);
assert(implCallMatch, 'implementer agent 调用未找到');
const implCall = implCallMatch[0];

// 必须含 schema: 字段(P0-1 part ii 新增)
assert(/schema\s*:/.test(implCall),
  'implementer agent 缺 schema 字段');

// schema 必须含 reviewer_stuck + planRepetition + mdSnippet + kind
const SCHEMA_FIELDS = ['reviewer_stuck', 'planRepetition', 'mdSnippet', 'kind'];
for (const f of SCHEMA_FIELDS) {
  assert(implCall.includes(f),
    `implementer schema 缺字段 ${f}`);
}

// reviewer_stuck 必须是 boolean
assert(/reviewer_stuck\s*:\s*\{\s*type\s*:\s*"boolean"/.test(implCall),
  'reviewer_stuck 字段类型应是 boolean');

// kind 必须是 enum frontend|backend|data|none
assert(/kind\s*:\s*\{\s*enum\s*:\s*\[\s*"frontend"\s*,\s*"backend"\s*,\s*"data"\s*,\s*"none"\s*\]/.test(implCall),
  'kind 字段应是 enum [frontend,backend,data,none]');

console.log('PASS · test-implementer-schema-reviewerstuck');
