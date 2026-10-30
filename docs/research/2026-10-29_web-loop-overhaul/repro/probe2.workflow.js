export const meta = {
  name: 'wl-runtime-probe-2',
  description: 'web-loop 重构探针 2：从仓库内文件 scriptPath 启动、model/effort 覆盖是否生效',
  phases: [{ title: 'Probe', detail: '1 个低开销 agent' }],
}
phase('Probe')
const r = await agent('这是一次运行环境探针。只回答一个字：好。不要调用任何工具。', { label: 'model-effort-probe', model: 'sonnet', effort: 'low' })
return { got: r, argsType: typeof args }
