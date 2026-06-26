import { readTemplate, assertMatches, ok } from './_helpers.mjs';
const src = readTemplate();

// 4 新字段都在 REVIEWER_SCHEMA.issues.items 内
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*issues:\s*\{[\s\S]*items:\s*\{[\s\S]*rootCauseHypothesis/, 'REVIEWER_SCHEMA.issues.items 含 rootCauseHypothesis');
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*items:\s*\{[\s\S]*affectedFiles/, 'REVIEWER_SCHEMA.issues.items 含 affectedFiles');
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*items:\s*\{[\s\S]*suggestedFix/, 'REVIEWER_SCHEMA.issues.items 含 suggestedFix');
assertMatches(src, /REVIEWER_SCHEMA[\s\S]*items:\s*\{[\s\S]*nextStepPlan/, 'REVIEWER_SCHEMA.issues.items 含 nextStepPlan');

// affectedFiles 必须是 array of string
assertMatches(src, /affectedFiles:\s*\{\s*type:\s*"array",\s*items:\s*\{\s*type:\s*"string"\s*\}\s*\}/, 'affectedFiles=array<string>');

// rootCauseHypothesis / suggestedFix / nextStepPlan 允许 null(非 code lens 可空)
assertMatches(src, /rootCauseHypothesis:\s*\{\s*type:\s*\[\s*"string"\s*,\s*"null"\s*\]\s*\}/, 'rootCauseHypothesis 允许 null');
assertMatches(src, /suggestedFix:\s*\{\s*type:\s*\[\s*"string"\s*,\s*"null"\s*\]\s*\}/, 'suggestedFix 允许 null');
assertMatches(src, /nextStepPlan:\s*\{\s*type:\s*\[\s*"string"\s*,\s*"null"\s*\]\s*\}/, 'nextStepPlan 允许 null');

ok('test-reviewer-schema-rootcause');
