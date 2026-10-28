import { readTemplate, assertContains, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 2 级优先级显式标定(P1-4 将 5 级改为 2 级:权威 · 必须遵循 / 参考补充)
assertContains(src, 'human-hint', 'implementer prompt 引用 human-hint');
assertMatches(src, /权威 · 必须遵循\(用户人工指令\)[\s\S]{0,300}human-hint|human-hint[\s\S]{0,200}权威 · 必须遵循/, '权威·必须遵循(用户人工指令) = human-hint');
assertMatches(src, /权威 · 必须遵循\(本轮 must[\s\S]{0,300}nextStepPlan|nextStepPlan[\s\S]{0,300}权威 · 必须遵循\(本轮 must/, '权威·必须遵循(本轮 must) = nextStepPlan');
assertContains(src, 'forbiddenApproaches', 'implementer prompt 引用 forbiddenApproaches(P1 占位)');
assertMatches(src, /权威 · 必须规避[\s\S]{0,300}forbidden|forbidden[\s\S]{0,200}权威 · 必须规避/, '权威·必须规避 = 跨轮 forbidden');
assertMatches(src, /参考补充\(历史 reviews[\s\S]{0,300}round_|round_[\s\S]{0,200}参考补充/, '参考补充(历史 reviews) = round_<N-1>.md');
assertMatches(src, /参考补充\(历史 impl\.md[\s\S]{0,300}反根因|反根因[\s\S]{0,200}参考补充\(历史 impl\.md/, '参考补充(历史 impl.md) = 反根因段');

// 透传 must 完整对象(含 nextStepPlan / rootCauseHypothesis / affectedFiles)
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}nextStepPlan/, 'implementer prompt 含 nextStepPlan');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}rootCauseHypothesis/, 'implementer prompt 含 rootCauseHypothesis');
assertMatches(src, /impl-\$\{rtag\}[\s\S]{0,5000}affectedFiles/, 'implementer prompt 含 affectedFiles');

// 强制 Read affectedFiles 实际代码 + Read 历史 + Read human-hint
assertMatches(src, /Read\s*[^\n]{0,80}affectedFiles/, 'implementer 强制 Read affectedFiles');
assertMatches(src, /Read[\s\S]{0,200}reviews\/round_/, 'implementer Read 历史 reviews');
assertMatches(src, /human-hint-r[\s\S]{0,200}Read|Read[\s\S]{0,200}human-hint-r/, 'implementer Read human-hint-r*.md');

// 强制判断题 + impl.md 首段固定结构
assertContains(src, 'reviewer_stuck', 'implementer prompt 强制写 reviewer_stuck 标');
assertContains(src, 'plan 重复分析', 'impl.md 首段含 plan 重复分析');
assertContains(src, '反根因', 'impl.md 首段含反根因段(若有)');
assertMatches(src, /首段[\s\S]{0,500}固定结构|固定结构[\s\S]{0,300}首段/, 'impl.md 首段固定结构');

// human-hint Read 完 mv 到 consumed
assertMatches(src, /mv[\s\S]{0,200}human-hint-r[\s\S]{0,80}\.consumed\.md/, 'human-hint 消费完 mv 到 .consumed.md');

ok('test-implementer-prompt-priority');
