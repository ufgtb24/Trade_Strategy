// web-loop test helpers (zero deps, pure Node ESM).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const skillRoot = resolve(here, '..');

export function readTemplate() {
  return readFileSync(resolve(skillRoot, 'workflow-template.js'), 'utf8');
}
export function readSkillMd() {
  return readFileSync(resolve(skillRoot, 'SKILL.md'), 'utf8');
}
export function readExamplesPath2() {
  return readFileSync(resolve(skillRoot, 'examples/path2.md'), 'utf8');
}
export function assertContains(haystack, needle, label) {
  if (!haystack.includes(needle)) {
    console.error(`FAIL ${label}: expected to contain ${JSON.stringify(needle)}`);
    process.exit(1);
  }
}
export function assertNotContains(haystack, needle, label) {
  if (haystack.includes(needle)) {
    console.error(`FAIL ${label}: expected NOT to contain ${JSON.stringify(needle)}`);
    process.exit(1);
  }
}
export function assertMatches(haystack, regex, label) {
  if (!regex.test(haystack)) {
    console.error(`FAIL ${label}: expected to match ${regex}`);
    process.exit(1);
  }
}
export function ok(label) {
  console.log(`PASS ${label}`);
}
