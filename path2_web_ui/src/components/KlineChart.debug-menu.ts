/**
 * Task 3 · KlineChart 右键菜单分流 pure helper
 *
 * 把 ECharts 无关的分流逻辑抽出 module · 便于 vitest 单测。
 * KlineChart.vue 里 chartMain.on('contextmenu') handler 调此函数决定弹哪种菜单。
 *
 * 分流规则(v2 D5):
 *   1. 生产 env(VITE_API_BASE 未设 或 = http://localhost:8000)→ 一律 driver(生产隔离 debug)
 *   2. debug env + eventId 在 DEBUG_ENABLED_CLASSES → menu=debug + anchors
 *   3. debug env + eventId 不在 whitelist(或 eventId=null)→ menu=driver 降级
 */
import type { useViewStore } from '../stores/view'
import { anchorsOf, DEBUG_ENABLED_CLASSES, type DebugAnchor } from '../stores/view'

export type MenuDispatch = {
  menu: 'debug' | 'driver'
  anchors?: DebugAnchor[]
}

export type DispatchInput = {
  eventId: string | null   // null = 空白 K 线右键
}

export function isDebugFrontend(): boolean {
  const base = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000'
  return base !== 'http://localhost:8000' && base !== ''
}

export function dispatchDebugMenu(
  input: DispatchInput,
  store: ReturnType<typeof useViewStore>,
  // 【相对 brief 原版新增第 3 参,默认走真实 isDebugFrontend】实测坐实(2 独立 probe):
  // vitest 2.1.9 + vite 6.4.3 组合下 vi.stubEnv 不生效于 import.meta.env 读取(连内置 MODE
  // key 都读不到 stub 后的新值,而非仅 VITE_API_BASE 未声明的问题)—— 与 vitest 官方文档承诺
  // 的跨模块传播行为不符。改走依赖注入使 whitelist 分流单测不依赖不可靠的 env mock 层;
  // 真实调用点(KlineChart.vue)不传第 3 参,行为与生产环境完全一致。
  isDebugCheck: () => boolean = isDebugFrontend,
): MenuDispatch {
  // 生产前端: 一律 driver(v-if 生产隔离)
  if (!isDebugCheck()) return { menu: 'driver' }

  // 空白 K 线右键
  if (!input.eventId) return { menu: 'driver' }

  // 查 event · whitelist 分流
  const events = (store as any).effectiveAnalysis?.events
    ?? (store as any).preview?.analysis?.events
    ?? []
  const event = events.find((e: any) => e.event_id === input.eventId)
  if (!event) return { menu: 'driver' }
  if (!DEBUG_ENABLED_CLASSES.includes(event.class_id)) return { menu: 'driver' }

  // debug menu · 3 anchors(上一行 whitelist 检查已保证 event.class_id ∈ anchorsOf key,故直取)
  const anchorFn = anchorsOf[event.class_id]
  const anchors = anchorFn(event, events)
  return { menu: 'debug', anchors }
}
