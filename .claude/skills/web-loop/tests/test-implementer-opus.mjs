import { readTemplate, assertMatches, assertNotContains, ok } from './_helpers.mjs';
const src = readTemplate();

// implementer agent options 内 model:"opus"
assertMatches(src, /label:\s*implLabel[\s\S]{0,400}model:\s*"opus"/, 'implementer agent 用 opus');
assertMatches(src, /label:\s*implLabel[\s\S]{0,400}phase:\s*"iterate"/, 'implementer agent phase=iterate(契约不变)');

// 旧 sonnet 在 implementer 调用块内消失(其他 sonnet agent 保留)
// 用上下文锁定 implementer 块:label:implLabel 段内不应再有 model:"sonnet"
const implBlock = src.match(/label:implLabel[\s\S]{0,400}?model:[^,}]+/);
if (!implBlock || /model:\s*"sonnet"/.test(implBlock[0])) {
  console.error(`FAIL implementer model: 仍含 sonnet — ${implBlock?.[0]||'未找到 label:implLabel 块'}`);
  process.exit(1);
}

ok('test-implementer-opus');
