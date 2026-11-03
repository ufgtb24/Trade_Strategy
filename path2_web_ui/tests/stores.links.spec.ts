// 跟着直达链接走(stores/links.ts):股票 + 日期打开那只股票、图窗停在那天附近、落在 annotate;样本编号等标注读完
// 再找,打开它所在的图并选中;编号不存在、写法认不出时记下原因;跟完把 # 部分从地址里去掉。
// 后端换成假实现:标注读结果由测试给,读的时机由测试放行。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnRead, AnnState } from '../src/annotate/model'

const fake = vi.hoisted(() => ({ read: null as any, gate: null as Promise<void> | null }))

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof import('../src/api')>('../src/api')
  return {
    ...actual,
    getAnnotations: async () => {
      if (fake.gate) await fake.gate
      return structuredClone(fake.read)
    },
  }
})

import { useAnnotationStore } from '../src/stores/annotation'
import { useLinkStore } from '../src/stores/links'
import { useViewStore } from '../src/stores/view'

function read(state: Partial<AnnState> = {}): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {} }, next_seq: 1, ignored_files: [],
    membership: { gap: 20, near: 40 },
  }
}

const WITH_SAMPLE = read({
  patterns: [{ name: 'W底' }],
  charts: [{
    symbol: 'MSFT',
    boxes: [{ id: 'b-pc-1', feature: null, start: '2024-01-02', end: '2024-01-20' }],
    samples: [{ id: 's-pc-2', date: '2024-02-08', pattern: 'W底', judgment: 'pos', members: ['b-pc-1'] }],
  }],
})

beforeEach(() => {
  setActivePinia(createPinia())
  fake.read = read()
  fake.gate = null
  localStorage.clear()
  history.replaceState(null, '', '/')
})

describe('股票 + 日期', () => {
  it('打开那只股票,图窗停在那天附近,落在 annotate;# 部分从地址里去掉', async () => {
    const view = useViewStore()
    view.mode = 'app'
    history.replaceState(null, '', '/#symbol=aapl&date=2024-05-10')
    await useLinkStore().follow(location.hash)
    expect(view.mode).toBe('annotate')
    expect(view.symbol).toBe('AAPL')
    expect(view.viewWindow).toEqual({ start: '2023-11-12', end: '2024-07-09' })
    expect(location.hash).toBe('')
    expect(useLinkStore().problem).toBeNull()
  })
  it('晚于训练段末日的日期:图窗按 2025-12-31 取', async () => {
    const view = useViewStore()
    await useLinkStore().follow('#symbol=AAPL&date=2026-03-01')
    expect(view.viewWindow).toEqual({ start: '2025-07-04', end: '2026-03-01' })
  })
})

describe('样本编号', () => {
  it('等标注读完再找:打开样本所在的图(图窗停在样本的跨度上)并选中它,侧栏翻到 selection', async () => {
    fake.read = WITH_SAMPLE
    let open!: () => void
    fake.gate = new Promise(r => { open = r })
    const ann = useAnnotationStore()
    const loading = ann.load()
    ann.tab = 'pattern'
    const view = useViewStore()
    const followed = useLinkStore().follow('#sample=s-pc-2')
    await Promise.resolve()
    expect(view.symbol).toBeNull()                       // 标注还没读完,先不动
    open()
    await loading
    await followed
    expect(view.symbol).toBe('MSFT')
    expect(view.viewWindow).toEqual({ start: '2023-11-03', end: '2024-04-08' })
    expect(ann.selectedSampleId).toBe('s-pc-2')
    expect(ann.currentSampleId).toBe('s-pc-2')
    expect(ann.tab).toBe('selection')
    expect(useLinkStore().problem).toBeNull()
  })
  it('编号不存在:不换图,记下 not_found 和编号,落在 annotate', async () => {
    fake.read = WITH_SAMPLE
    await useAnnotationStore().load()
    const view = useViewStore()
    view.mode = 'app'
    await useLinkStore().follow('#sample=s-pc-99')
    expect(view.symbol).toBeNull()
    expect(view.mode).toBe('annotate')
    expect(useLinkStore().problem).toEqual({ code: 'not_found', sample: 's-pc-99' })
  })
  it('标注读不到:不记 not_found(提示条已经写了标注的状态)', async () => {
    const ann = useAnnotationStore()
    fake.gate = Promise.reject(Object.assign(new Error('x'), { status: 503 }))
    fake.gate.catch(() => {})
    await ann.load()
    expect(ann.status).toBe('unavailable')
    await useLinkStore().follow('#sample=s-pc-2')
    expect(useLinkStore().problem).toBeNull()
  })
  it('样本卡也走这一处:keepTab 时侧栏留在当前页', async () => {
    fake.read = WITH_SAMPLE
    const ann = useAnnotationStore()
    await ann.load()
    ann.tab = 'pattern'
    expect(await useLinkStore().openSample('s-pc-2', { keepTab: true })).toBe(true)
    expect(ann.selectedSampleId).toBe('s-pc-2')
    expect(ann.tab).toBe('pattern')
    expect(await useLinkStore().openSample('nope')).toBe(false)
  })
})

describe('认不出的写法', () => {
  it('记下 bad_link 和原文;下一个跟成的链接清掉它', async () => {
    const links = useLinkStore()
    await links.follow('#symbol=AAPL')
    expect(links.problem).toEqual({ code: 'bad_link', raw: 'symbol=AAPL' })
    await links.follow('#symbol=AAPL&date=2024-05-10')
    expect(links.problem).toBeNull()
  })
  it('没有 # 部分:什么都不做', async () => {
    await useLinkStore().follow('')
    expect(useViewStore().symbol).toBeNull()
    expect(useLinkStore().problem).toBeNull()
  })
})
