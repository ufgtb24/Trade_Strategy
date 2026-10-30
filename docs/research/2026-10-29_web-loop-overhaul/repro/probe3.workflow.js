export const meta = {
  name: 'wl-runtime-probe-3',
  description: 'web-loop 重构探针 3：agent 起的后台进程在 agent 结束后是否存活；单条 4 分钟命令会不会被判卡住',
  phases: [{ title: 'Probe', detail: '2 个低开销 agent 并行' }],
}
phase('Probe')
const P = '/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy--claude-worktrees-annotation-web-loop/12e80ef3-98f9-4aa7-9260-f973584d71c2/scratchpad/p3'
const [bg, slow] = await parallel([
  () => agent(
    `这是运行环境探针，严格只做下面三步，然后交回。\n` +
    `1. 用一次 Bash 调用（不要设 run_in_background）执行：cd ${P} && nohup python3 -m http.server 8796 > ${P}/s8796.log 2>&1 & echo $! > ${P}/pid8796\n` +
    `2. 用一次 Bash 调用（不要设 run_in_background）执行：cd ${P} && setsid nohup python3 -m http.server 8797 > ${P}/s8797.log 2>&1 < /dev/null & echo $! > ${P}/pid8797\n` +
    `3. 用一次 Bash 调用，并把 run_in_background 设为 true，执行：cd ${P} && echo $$ > ${P}/pid8798 && exec python3 -m http.server 8798 > ${P}/s8798.log 2>&1\n` +
    `然后用一次 Bash 调用执行 sleep 2; for p in 8796 8797 8798; do curl -s -o /dev/null -w "$p:%{http_code} " http://localhost:$p/; done，把输出原样交回。不要杀任何进程，不要发消息。`,
    { label: 'detached-probe', model: 'sonnet', effort: 'low', schema: { type: 'object', required: ['curl'], properties: { curl: { type: 'string' }, note: { type: 'string' } } } }),
  () => agent(
    `这是运行环境探针，模拟一条要跑 4 分钟的数据刷新命令。用一次前台 Bash 调用（不要 run_in_background），把 timeout 参数设为 300000，执行：python3 -c "import time; t=time.time(); time.sleep(240); print('ran', round(time.time()-t))"。命令结束后把输出原样交回。如果被拦或超时，把错误原文交回。不要做别的事，不要发消息。`,
    { label: 'long-cmd-probe', model: 'sonnet', effort: 'low', schema: { type: 'object', required: ['out'], properties: { out: { type: 'string' } } } }),
])
return { bg, slow }
