export const meta = {
  name: 'wl-runtime-probe-4',
  description: 'web-loop 重构探针 4：workflow 子代理能否找到并复制本 run 的 journal.jsonl',
  phases: [{ title: 'Probe', detail: '1 个低开销 agent' }],
}
phase('Probe')
const OUT = '/home/yu/PycharmProjects/Trade_Strategy/.claude/worktrees/annotation-web-loop/docs/research/2026-10-29_web-loop-overhaul/repro/probe4_copy'
const r = await agent(
  `这是运行环境探针，严格只做下面几步。\n` +
  `1. 用一次 Bash 调用执行：find ~/.claude/projects -path '*subagents/workflows/*/journal.jsonl' -mmin -10 2>/dev/null | xargs -r grep -l 'journal-copy-probe-x7q' 2>/dev/null，把输出原样记下（这是本 run 自己的 journal 路径；你的 label 已经先于你写进了它）。\n` +
  `2. 若第 1 步找到且只有一个文件，用一次 Bash 调用执行：mkdir -p ${OUT} && cp "<该路径>" ${OUT}/journal.jsonl && wc -l ${OUT}/journal.jsonl，把输出原样记下。\n` +
  `3. 交回：找到的路径、复制是否成功、wc 输出；任一步出错把错误原文交回。不要做别的事，不要发消息。`,
  { label: 'journal-copy-probe-x7q', model: 'sonnet', effort: 'low', schema: { type: 'object', required: ['found', 'copied'], properties: { found: { type: 'string' }, copied: { type: 'boolean' }, wc: { type: 'string' }, error: { type: 'string' } } } })
return r
