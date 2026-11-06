// 跟着直达链接走(stores/directLinks.ts)与按编号打开样本(标注 store 的 openSample):
// 股票 + 日期先对股票列表核代码,在就打开、图窗停在那天附近、落在 annotate,不在就记下 not_found、不动当前的图;
// 样本编号等标注读完再找,打开它所在的图并选中,不换当前 pattern;编号不存在、写法认不出时记下原因并落在 annotate;
// 跟完把 # 部分从地址里去掉。后端换成假实现:标注读结果、股票列表由测试给,标注读的时机由测试放行。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { AnnRead, AnnState } from '../src/annotate/model'

const fake = vi.hoisted(() => ({
  read: null as any, gate: null as Promise<void> | null, symbols: null as string[] | null,
}))

vi.mock('../src/api', async () => {
  const actual = await vi.importActual<typeof import('../src/api')>('../src/api')
  return {
    ...actual,
    getAnnotations: async () => {
      if (fake.gate) await fake.gate
      return structuredClone(fake.read)
    },
    getSymbols: async () => {
      if (!fake.symbols) throw new Error('symbols unavailable')
      return [...fake.symbols]
    },
  }
})

import { useAnnotationStore } from '../src/stores/annotation'
import { useDirectLinkStore } from '../src/stores/directLinks'
import { useViewStore } from '../src/stores/view'

function read(state: Partial<AnnState> = {}): AnnRead {
  return {
    state: { machine: 'pc', data_fingerprint: null, features: [], patterns: [], charts: [], ...state },
    conflicts: [], unsynced: [], violations: [],
    fingerprint: { local: 'fp', local_error: null, recorded: [], consistent: true }, merges: [],
    revs: { feature: {}, pattern: {}, box: {}, sample: {} }, next_seq: 1, ignored_files: [],
    membership: { gap: 20, near: 40 },
    match: { pos: 3, neg: 1, sub: 2 },
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
  fake.symbols = ['AAPL', 'MSFT']
  localStorage.clear()
  history.replaceState(null, '', '/')
})

describe('股票 + 日期', () => {
  it('打开那只股票,图窗停在那天附近,落在 annotate;# 部分从地址里去掉', async () => {
    const view = useViewStore()
    view.mode = 'app'
    history.replaceState(null, '', '/#symbol=aapl&date=2024-05-10')
    await useDirectLinkStore().follow(location.hash)
    expect(view.mode).toBe('annotate')
    expect(view.symbol).toBe('AAPL')
    expect(view.viewWindow).toEqual({ start: '2023-11-12', end: '2024-07-09' })
    expect(location.hash).toBe('')
    expect(useDirectLinkStore().problem).toBeNull()
  })
  it('晚于训练段末日的日期:图窗按 2025-12-31 取', async () => {
    await useDirectLinkStore().follow('#symbol=AAPL&date=2026-03-01')
    expect(useViewStore().viewWindow).toEqual({ start: '2025-07-04', end: '2026-03-01' })
  })
  it('代码不在股票列表里:不动当前的图,记下 not_found,落在 annotate', async () => {
    const view = useViewStore()
    await useDirectLinkStore().follow('#symbol=MSFT&date=2024-05-10')
    view.mode = 'app'
    await useDirectLinkStore().follow('#symbol=ZZZZ&date=2024-05-10')
    expect(view.symbol).toBe('MSFT')
    expect(view.viewWindow).toEqual({ start: '2023-11-12', end: '2024-07-09' })
    expect(view.mode).toBe('annotate')
    expect(useDirectLinkStore().problem).toEqual({ code: 'not_found', kind: 'symbol', id: 'ZZZZ' })
  })
  it('股票列表拿不到:不拦,交给后端判', async () => {
    fake.symbols = null
    await useDirectLinkStore().follow('#symbol=ZZZZ&date=2024-05-10')
    expect(useViewStore().symbol).toBe('ZZZZ')
    expect(useDirectLinkStore().problem).toBeNull()
  })
})

describe('样本编号', () => {
  it('等标注读完再找:打开样本所在的图(图窗停在样本的跨度上)并选中它,侧栏翻到 selection,不换当前 pattern', async () => {
    fake.read = WITH_SAMPLE
    let open!: () => void
    fake.gate = new Promise(r => { open = r })
    const ann = useAnnotationStore()
    const loading = ann.load()
    ann.tab = 'pattern'
    const view = useViewStore()
    const followed = useDirectLinkStore().follow('#sample=s-pc-2')
    await Promise.resolve()
    expect(view.symbol).toBeNull()                       // 标注还没读完,先不动
    open()
    await loading
    await followed
    expect(view.symbol).toBe('MSFT')
    expect(view.mode).toBe('annotate')
    expect(view.viewWindow).toEqual({ start: '2023-11-03', end: '2024-04-08' })
    expect(ann.selectedSampleId).toBe('s-pc-2')
    expect(ann.currentSampleId).toBe('s-pc-2')
    expect(ann.tab).toBe('selection')
    expect(ann.currentPattern).toBeNull()
    expect(useDirectLinkStore().problem).toBeNull()
  })
  it('编号不存在:不换图,记下 not_found 和编号,落在 annotate', async () => {
    fake.read = WITH_SAMPLE
    await useAnnotationStore().load()
    const view = useViewStore()
    view.mode = 'app'
    await useDirectLinkStore().follow('#sample=s-pc-99')
    expect(view.symbol).toBeNull()
    expect(view.mode).toBe('annotate')
    expect(useDirectLinkStore().problem).toEqual({ code: 'not_found', kind: 'sample', id: 's-pc-99' })
  })
  it('标注读不到:不记 not_found(提示条已经写了标注的状态),落在 annotate', async () => {
    const ann = useAnnotationStore()
    fake.gate = Promise.reject(Object.assign(new Error('x'), { status: 503 }))
    fake.gate.catch(() => {})
    await ann.load()
    expect(ann.status).toBe('unavailable')
    useViewStore().mode = 'app'
    await useDirectLinkStore().follow('#sample=s-pc-2')
    expect(useDirectLinkStore().problem).toBeNull()
    expect(useViewStore().mode).toBe('annotate')
  })
  it('样本卡也走 openSample:keepTab 时侧栏留在当前页;编号不存在返回 false', async () => {
    fake.read = WITH_SAMPLE
    const ann = useAnnotationStore()
    await ann.load()
    ann.tab = 'pattern'
    expect(await ann.openSample('s-pc-2', { keepTab: true })).toBe(true)
    expect(useViewStore().symbol).toBe('MSFT')
    expect(ann.selectedSampleId).toBe('s-pc-2')
    expect(ann.tab).toBe('pattern')
    expect(await ann.openSample('nope')).toBe(false)
  })
})

describe('认不出的写法', () => {
  it('记下 bad_url 和原文;下一个跟成的链接清掉它', async () => {
    const links = useDirectLinkStore()
    await links.follow('#symbol=AAPL')
    expect(links.problem).toEqual({ code: 'bad_url', raw: 'symbol=AAPL' })
    await links.follow('#symbol=AAPL&date=2024-05-10')
    expect(links.problem).toBeNull()
  })
  it('没有 # 部分:什么都不做', async () => {
    useViewStore().mode = 'app'
    await useDirectLinkStore().follow('')
    expect(useViewStore().symbol).toBeNull()
    expect(useViewStore().mode).toBe('app')
    expect(useDirectLinkStore().problem).toBeNull()
  })
})
