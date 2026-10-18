/** 启动脚本告诉前端的模式:环境变量 VITE_CHART_WORKFLOW_MODE,run_path2_web.py 给 formal,
 *  run_path2_web_debug.py 给 debug。手工 npm run dev 没给 → null,不和后端比对。
 *  单独成一个模块,测试里直接 vi.mock 它(本项目的 vitest 组合下 vi.stubEnv 改不到 import.meta.env)。 */
export type LaunchMode = 'formal' | 'debug'

export function launchMode(): LaunchMode | null {
  const v = (import.meta as any).env?.VITE_CHART_WORKFLOW_MODE
  return v === 'formal' || v === 'debug' ? v : null
}
