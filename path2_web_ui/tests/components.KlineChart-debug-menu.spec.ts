/**
 * Task 3 · KlineChart marker 右键 3 项 debug 菜单 + whitelist 分流 + 生产 v-if 隔离
 *
 * 由于 ECharts 实例在 jsdom 里难以真跑,本 test focus 在 store 层的分流函数上:
 * 组件 export 一个 pure function `dispatchDebugMenu({ instanceId }, store, isDebugCheck?)`,
 * 返回 { menu: 'debug' | 'driver', anchors?: DebugAnchor[] } 让菜单模板消费。
 *
 * 【相对 brief 原版修正 · env 分流测试机制】brief 原版直接改写
 * `(import.meta as any).env = {...}` 来 stub env;实测(2 独立 probe,含改用官方
 * vi.stubEnv/vi.unstubAllEnvs 的修正尝试)坐实:vitest 2.1.9 + vite 6.4.3 这套组合下,
 * import.meta.env 的运行时读取不受两种 stub 方式影响(连内置 MODE key 都读不到 stub 后
 * 的新值),与 vitest 官方文档承诺的跨模块传播行为不符 —— 实测优先于文档。
 * 改为给 dispatchDebugMenu 加第 3 参 isDebugCheck(默认 = 真实 isDebugFrontend)做依赖注入,
 * 单测直接传 () => true / () => false 确定性控制生产/debug 分支,不依赖不可靠的 env mock 层;
 * KlineChart.vue 真实调用点不传第 3 参,行为与生产环境完全一致。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { dispatchDebugMenu } from '../src/components/KlineChart.debug-menu'

beforeEach(() => setActivePinia(createPinia()))

function seedTb(store: ReturnType<typeof useViewStore>) {
  // 完整 seedStore 模式(参考 tests/stores.triggerEventDebug.spec.ts)· 补 previewEnabled/
  // pattern_spec/symbol/activePatternId/scanFile,让 _previewHits 命中、走 effectiveAnalysis
  // 主路径,而非 dispatchDebugMenu 的 store.preview.analysis.events fallback。
  // 【Task 9 修正】previewEnabled 由 ref 改 computed(isExploring 别名),直接赋值静默 no-op;
  // 改为直接注入 workingCopy 槽位(enabled=true),同 stores.triggerEventDebug.spec.ts 的修法。
  ;(store as any).workingCopy = { bottom_burst: { enabled: true, baseline: {}, currentDict: {} } }
  ;(store as any).preview = {
    symbol: 'AAPL',
    pattern_spec: { pattern_id: 'bottom_burst' },
    scan: { win_start: '2025-01-01', win_end: '2025-12-31' },
    analysis: {
      events: [
        { instance_id: 'bo_1#0', node_id: 'bo', start_idx: 30, end_idx: 33 },
        // 真实 node_id 契约:tb 容器/子段/V1 共用 node_id 'tb',靠 child_refs 区分——
        // tb_1#0(V2 容器)持有 segments 引用;tb_seg_1#0(子段)被其引用;tb_v1_1#0(V1 叶子)无人引用。
        { instance_id: 'tb_1#0', node_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1#0',
          child_refs: { segments: ['tb_seg_1#0'] } },
        { instance_id: 'tb_seg_1#0', node_id: 'tb', start_idx: 44, end_idx: 50, anchor_bo_id: 'bo_1#0',
          child_refs: {} },
        { instance_id: 'tb_v1_1#0', node_id: 'tb', start_idx: 42, end_idx: 55, anchor_bo_id: 'bo_1#0',
          child_refs: {} },
      ],
      matches: [], summary: {}, gate_failures: [],
    },
  }
  ;(store as any).symbol = 'AAPL'
  ;(store as any).activePatternId = 'bottom_burst'
  ;(store as any).scanFile = {
    scan: { win_start: '2025-01-01', win_end: '2025-12-31' },
    results: [],
  }
}

const DEBUG = () => true
const PROD = () => false

describe('dispatchDebugMenu · whitelist 分流', () => {
  it('marker + tb(v4 容器)→ menu=debug · 3 anchors(entry/start/end)', () => {
    const store = useViewStore()
    seedTb(store)
    const r = dispatchDebugMenu({ instanceId: 'tb_1#0' }, store, DEBUG)
    expect(r.menu).toBe('debug')
    expect(r.anchors).toHaveLength(3)
  })

  it('marker + tb_seg(V2 段)→ menu=debug · 2 anchors(confirm/end)', () => {
    const store = useViewStore()
    seedTb(store)
    const r = dispatchDebugMenu({ instanceId: 'tb_seg_1#0' }, store, DEBUG)
    expect(r.menu).toBe('debug')
    expect(r.anchors).toHaveLength(2)
  })

  it('marker + tb_v1(V1)→ menu=debug · 3 anchors(entry/confirm/end)', () => {
    const store = useViewStore()
    seedTb(store)
    const r = dispatchDebugMenu({ instanceId: 'tb_v1_1#0' }, store, DEBUG)
    expect(r.menu).toBe('debug')
    expect(r.anchors).toHaveLength(3)
  })

  it('marker + bo(不在 whitelist)→ menu=driver 降级', () => {
    const store = useViewStore()
    seedTb(store)
    const r = dispatchDebugMenu({ instanceId: 'bo_1#0' }, store, DEBUG)
    expect(r.menu).toBe('driver')
    expect(r.anchors).toBeUndefined()
  })

  it('空白 K 线(无 instanceId)→ menu=driver', () => {
    const store = useViewStore()
    seedTb(store)
    const r = dispatchDebugMenu({ instanceId: null }, store, DEBUG)
    expect(r.menu).toBe('driver')
  })

  it('生产 env(isDebugFrontend=false)→ menu=driver(隔离 debug)', () => {
    const store = useViewStore()
    seedTb(store)
    const r = dispatchDebugMenu({ instanceId: 'tb_1#0' }, store, PROD)
    expect(r.menu).toBe('driver')  // 生产不出 debug 菜单
  })

  it('debug env(isDebugFrontend=true)→ menu=debug', () => {
    const store = useViewStore()
    seedTb(store)
    const r = dispatchDebugMenu({ instanceId: 'tb_1#0' }, store, DEBUG)
    expect(r.menu).toBe('debug')
  })
})
