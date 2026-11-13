// 副图上方的显示栏:九格位置和写法永远不变——kind / node / date / name / diff / in、← / → 与 ↑ / ↓ 两个键槽、Esc。
// 不适用的格照占位置、写 `—`(键帽画灰);进行到一半的 Shift 配对另占一格 pair 1/2;
// compare 下最右的 feedback 按钮(三态 on / off / open,不给就没有;点了只通知父组件,开关由图表组件接)。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import WalkStatusBar from '../src/components/WalkStatusBar.vue'
import type { EventDict, HitDict, MultiScanResultFile } from '../src/types'

vi.mock('../src/api', async (orig) => {
  const m: Record<string, unknown> = await orig()
  return Object.fromEntries(Object.entries(m).map(([k, v]) =>
    [k, typeof v === 'function' ? vi.fn(() => new Promise(() => {})) : v]))
})
vi.mock('../src/stores/config', () => ({ useConfigStore: vi.fn(() => ({ config: null, saveLastPattern: vi.fn() })) }))

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// 旧平台 O 被全部 hit 共用;两种阶跃切法 S10(一根)、S11(两根);13、14 两天各有两种切法,15 只有一根那种
const O = ev('old_plat', 0, 9)
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15)
const kids = (s: EventDict, t: EventDict) => ({ old: [O.instance_id], step: [s.instance_id], today: [t.instance_id] })
const P13a = ev('plateau', 0, 13, 0, kids(S10, T13)), P13b = ev('plateau', 0, 13, 1, kids(S11, T13))
const P14a = ev('plateau', 0, 14, 0, kids(S10, T14)), P14b = ev('plateau', 0, 14, 1, kids(S11, T14))
const P15a = ev('plateau', 0, 15, 0, kids(S10, T15))
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})
const HITS = [hit('a13', P13a), hit('b13', P13b), hit('a14', P14a), hit('b14', P14b), hit('a15', P15a)]
const DATES = Array.from({ length: 20 }, (_, i) => `2024-11-${String(i + 1).padStart(2, '0')}`)

function makeFixture(): MultiScanResultFile {
  return {
    pattern_ids: ['p1'],
    per_pattern: { p1: {
      end_node: 'plateau.today',
      pattern_spec: {
        pattern_id: 'p1',
        topology: {
          nodes: [
            { node_id: 'plateau', render_grid: 'time', where_rules: [] },
            { node_id: 'old_plat', render_grid: 'time', where_rules: [], solve: false },
            { node_id: 'step', render_grid: 'time', where_rules: [], solve: false },
            { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true },
          ],
          edges: [],
        },
        event_styles: {},
      },
    } },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [O, S10, S11, T13, T14, T15, P13a, P13b, P14a, P14b, P15a], hits: HITS,
    }, summary: { hits: 5 } } } }],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 },
  } as any
}

type W = ReturnType<typeof mount>
const CELLS = ['sel-kind', 'sel-node', 'sel-date', 'sel-name', 'sel-diff', 'sel-in', 'sel-day', 'sel-stack'] as const
const cell = (w: W, id: string) => w.get(`[data-testid="${id}"]`)
/** 一格里的值(标签 / 键帽后面那一段) */
const val = (w: W, id: string) => (cell(w, id).element.lastElementChild as HTMLElement).textContent!.trim()
/** 一格里的标签或键帽(前面那一段) */
const cap = (w: W, id: string) => (cell(w, id).element.firstElementChild as HTMLElement).textContent!.trim()
/** 八格的值,顺序同显示栏(Esc 那格只有键帽,另验) */
const vals = (w: W) => CELLS.map(id => val(w, id))
const keyOff = (w: W, id: string) => cell(w, id).get('kbd').classes().includes('off')

describe('WalkStatusBar', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  function setup() {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('detected')
    view.setBarDates(DATES)
    return { view, w: mount(WalkStatusBar) }
  }

  it('什么都没选中:九格都在、顺序固定,每格写 —,三个键帽都是灰的', () => {
    const { w } = setup()
    expect(w.find('[data-testid="walk-bar"]').exists()).toBe(true)
    const ids = w.findAll('.cell').map(c => c.attributes('data-testid'))
    expect(ids).toEqual([...CELLS, 'sel-esc'])
    expect(vals(w)).toEqual(['—', '—', '—', '—', '—', '—', '—', '—'])
    expect(CELLS.slice(0, 6).map(id => cap(w, id))).toEqual(['kind', 'node', 'date', 'name', 'diff', 'in'])
    expect([cap(w, 'sel-day'), cap(w, 'sel-stack'), cell(w, 'sel-esc').text()]).toEqual(['←/→', '↑/↓', 'Esc'])
    expect([keyOff(w, 'sel-day'), keyOff(w, 'sel-stack'), keyOff(w, 'sel-esc')]).toEqual([true, true, true])
    expect(cell(w, 'sel-esc').attributes('title')).toBe('Esc: nothing to go back from')
    expect(w.find('[data-testid="walk-pair"]').exists()).toBe(false)
  })

  it('hit 的一族:只有 kind 与起点日期;← / → 会进到它的买点日,↑ / ↓ 不适用;Esc 这一下清空', async () => {
    const { view, w } = setup()
    view.clickFamilyLine('hits@0')
    await nextTick()
    expect(vals(w)).toEqual(['hit_family', '—', '2024-11-01', '—', '—', '—', 'into buys ×3', '—'])
    expect([keyOff(w, 'sel-day'), keyOff(w, 'sel-stack'), keyOff(w, 'sel-esc')]).toEqual([false, true, false])
    expect(cell(w, 'sel-esc').attributes('title')).toBe('Esc: clear')
    expect(cell(w, 'sel-day').attributes('title')).toContain('goes into them (buys ×3)')
    expect(cell(w, 'sel-stack').attributes('title')).toContain('nothing to go to')
  })

  it('点 ▼(这天两次):kind 写 buy、in 写它那一族;← / → 是第几个买点日,↑ / ↓ 会进到这天的几次', async () => {
    const { view, w } = setup()
    view.clickBuyDay('hits@0', 13)
    await nextTick()
    expect(vals(w)).toEqual(['buy', '—', '2024-11-14', '—', '—', 'hit_family 2024-11-01', 'buys 1/3', 'into hits ×2'])
    expect(cell(w, 'sel-esc').attributes('title')).toBe('Esc: up: hit_family 2024-11-01')
    view.stepPos(1)
    await nextTick()
    expect([val(w, 'sel-date'), val(w, 'sel-day')]).toEqual(['2024-11-15', 'buys 2/3'])
  })

  it('进到这天的一次 hit:写起止与它和另一次的区别,in 由外到内写一族 › 这一天', async () => {
    const { view, w } = setup()
    view.clickBuyDay('hits@0', 13)
    view.stepStack(1); view.stepStack(1)
    await nextTick()
    expect(vals(w)).toEqual(['hit', '—', '2024-11-01→2024-11-14', '—', 'step→2024-11-12',
                             'hit_family 2024-11-01 › buy 2024-11-14', 'buys 1/3', 'hits 2/2'])
    expect(cell(w, 'sel-esc').attributes('title')).toBe('Esc: up: buy 2024-11-14')
  })

  it('点 ▼ 而这天只有一次:就是那次 hit——kind 写 hit,那一天进 in,↑ / ↓ 不适用', async () => {
    const { view, w } = setup()
    view.clickBuyDay('hits@0', 15)
    await nextTick()
    expect(vals(w)).toEqual(['hit', '—', '2024-11-01→2024-11-16', '—', '—',
                             'hit_family 2024-11-01 › buy 2024-11-16', 'buys 3/3', '—'])
    expect(cell(w, 'sel-esc').attributes('title')).toBe('Esc: up: hit_family 2024-11-01')
  })

  it('event:写它的 node 与起止,in 写它那条 band;牵出几个买点日时 ← / → 会进去', async () => {
    const { view, w } = setup()
    view.focusMark([S10.instance_id])
    await nextTick()
    expect(vals(w)).toEqual(['event', 'step', '2024-11-11', '—', '—', 'node step', 'into buys ×3', '—'])
    view.focusMark([P13a.instance_id, P13b.instance_id])    // 同一格叠着两个:diff 写区别,↑ / ↓ 在这一格里换
    await nextTick()
    expect(vals(w)).toEqual(['event', 'plateau', '2024-11-01→2024-11-14', '—', 'step→2024-11-11',
                             'node plateau', 'events 1/3', 'events 1/2'])
  })

  it('node:name 写它对到的特征名(用户起的名字,按用户内容的样子写);没对到特征时写 —', async () => {
    const { view, w } = setup()
    view.setSelSources({ featureOfBand: band => (band === 'step' ? '阶跃' : null) })
    view.selectNode('step')
    await nextTick()
    expect(vals(w)).toEqual(['node', 'step', '—', '阶跃', '—', '—', 'into events ×2', '—'])
    expect((cell(w, 'sel-name').element.lastElementChild as HTMLElement).classList.contains('user')).toBe(true)
    view.selectNode('today')
    await nextTick()
    expect(val(w, 'sel-name')).toBe('—')
  })

  it('样本:date 写样本日,name 写字母与判断(程序固定词);← / → 换样本,↑ / ↓ 会进到在场的几次', async () => {
    const { view, w } = setup()
    view.setSelSources({
      samples: () => [{ id: 's1', day: 13, hitIds: ['b13', 'a13'], pairedHitId: 'b13' }, { id: 's2', day: 15, hitIds: ['a15'], pairedHitId: 'a15' }],
      sampleOf: id => (id === 's1' ? { letter: 'a', judgment: 'pos', date: '2024-11-14' } : null),
    })
    view.setPath([{ kind: 'sample', sampleId: 's1' }])
    await nextTick()
    expect(vals(w)).toEqual(['sample', '—', '2024-11-14', 'a pos', '—', '—', 'samples 1/2', 'into hits ×2'])
    expect((cell(w, 'sel-name').element.lastElementChild as HTMLElement).classList.contains('user')).toBe(false)
    view.stepStack(1)                                        // 进到配对的那次:in 写这个样本
    await nextTick()
    expect(vals(w)).toEqual(['hit', '—', '2024-11-01→2024-11-14', '—', 'step→2024-11-12',
                             'sample 2024-11-14 a pos', 'samples 1/2', 'hits 1/2'])
  })

  it('框:name 写它的特征名(用户起的名字,按用户内容的样子写);没起名的写 none——程序固定词,黑字、不套用户内容的样子', async () => {
    const { view, w } = setup()
    const boxes: Record<string, { feature: string | null; start: string; end: string; node: string | null }> = {
      x1: { feature: '阶跃', start: '2024-11-11', end: '2024-11-12', node: 'step' },
      x2: { feature: null, start: '2024-11-11', end: '2024-11-14', node: null },
    }
    view.setSelSources({
      boxes: () => [{ id: 'x1', day: 11, hitIds: [], pairedHitId: null }, { id: 'x2', day: 13, hitIds: [], pairedHitId: null }],
      boxOf: id => boxes[id] ?? null,
    })
    const nameCls = () => (cell(w, 'sel-name').element.lastElementChild as HTMLElement).classList
    view.setPath([{ kind: 'box', boxId: 'x1' }])
    await nextTick()
    expect(vals(w)).toEqual(['box', 'step', '2024-11-11→2024-11-12', '阶跃', '—', '—', 'boxes 1/2', '—'])
    expect([nameCls().contains('user'), nameCls().contains('na')]).toEqual([true, false])
    view.setPath([{ kind: 'box', boxId: 'x2' }])
    await nextTick()
    expect(vals(w)).toEqual(['box', '—', '2024-11-11→2024-11-14', 'none', '—', '—', 'boxes 2/2', '—'])
    expect([nameCls().contains('user'), nameCls().contains('na')]).toEqual([false, false])
  })

  it('反馈:node 写它点的 node(没点 node 的写 none),date 写起止;段里 app 不买时两组键都不适用', async () => {
    const { view, w } = setup()
    const fbs = [{ id: 'f1', start: '2024-11-14', end: '2024-11-15', nodes: ['step'] },
                 { id: 'f2', start: '2024-11-19', end: '2024-11-19', nodes: [] as string[] }]
    view.setSelSources({
      feedbacks: () => fbs.slice(0, 1),
      feedbackOf: id => { const f = fbs.find(x => x.id === id); return f ? { ...f, familyStart: null } : null },
    })
    view.clickFeedback({ id: 'f1' })
    await nextTick()
    expect(vals(w)).toEqual(['feedback', 'step', '2024-11-14→2024-11-15', '—', '—', '—', 'into buys ×2', '—'])
    view.setSelSources({ feedbacks: () => fbs.slice(1) })
    view.clickFeedback({ id: 'f2' })
    await nextTick()
    expect(vals(w)).toEqual(['feedback', 'none', '2024-11-19', '—', '—', '—', '—', '—'])
    // none 是一个取值(黑字),不是「不适用」的灰 —
    expect((cell(w, 'sel-node').element.lastElementChild as HTMLElement).classList.contains('na')).toBe(false)
  })

  it('Shift 配对进行到一半:另占一格 pair 1/2,和选中的那一个同时写;Esc 悬停说下一下退掉配对', async () => {
    const { view, w } = setup()
    view.clickBuyDay('hits@0', 13)
    view.setShiftSelectedEvents([{ instance_id: 'x#0', node_id: 'x', source: 'sub' }])
    await nextTick()
    expect(cell(w, 'walk-pair').text()).toBe('pair 1/2')
    expect(val(w, 'sel-kind')).toBe('buy')
    expect(cell(w, 'sel-esc').attributes('title')).toMatch(/cancel the pair/)
    // 配对那格夹在 ↑ / ↓ 键槽与 Esc 之间,九格的位置不动
    expect(w.findAll('.cell').map(c => c.attributes('data-testid'))).toEqual([...CELLS, 'walk-pair', 'sel-esc'])
  })

  it('什么都没选中时配对进行到一半:九格仍写 —,Esc 键帽亮着', async () => {
    const { view, w } = setup()
    view.setShiftSelectedEvents([{ instance_id: 'x#0', node_id: 'x', source: 'sub' }])
    await nextTick()
    expect(vals(w)).toEqual(['—', '—', '—', '—', '—', '—', '—', '—'])
    expect(keyOff(w, 'sel-esc')).toBe(false)
  })

  describe('feedback 按钮', () => {
    const btn = (w: W) => w.find('[data-testid="sel-feedback"]')

    it('不给 feedback(app 模式):没有这个按钮', () => {
      const { w } = setup()
      expect(btn(w).exists()).toBe(false)
    })

    it('on:能点、不灰、不按下;点了 emit feedback;按下不夺焦点;带 data-feedback-opener', async () => {
      setup()
      const w = mount(WalkStatusBar, { props: { feedback: 'on' } })
      const b = btn(w)
      expect(b.exists()).toBe(true)
      expect(b.text()).toBe('feedback')
      expect(b.element.tagName).toBe('BUTTON')
      expect(b.attributes('disabled')).toBeUndefined()
      expect(b.classes()).not.toContain('off')
      expect(b.classes()).not.toContain('on')
      expect(b.attributes('aria-pressed')).toBe('false')
      expect(b.attributes('data-feedback-opener')).toBeDefined()
      expect(b.attributes('title')).toBe('give feedback on what is selected (Enter)')
      const md = new MouseEvent('mousedown', { bubbles: true, cancelable: true })
      b.element.dispatchEvent(md)
      expect(md.defaultPrevented).toBe(true)
      await b.trigger('click')
      expect(w.emitted('feedback')).toEqual([[]])
      // 在 Esc 那格之后,九格的位置不动
      expect(w.findAll('.cell').map(c => c.attributes('data-testid')).slice(0, 9)).toEqual([...CELLS, 'sel-esc'])
    })

    it('off:灰、disabled,点了不 emit;悬停写怎样才能作答', async () => {
      setup()
      const w = mount(WalkStatusBar, { props: { feedback: 'off' } })
      const b = btn(w)
      expect(b.attributes('disabled')).toBeDefined()
      expect(b.classes()).toContain('off')
      expect(b.attributes('title')).toMatch(/^select a buy day, a hit on it, a family of hits, or a feedback/)
      await b.trigger('click')
      expect(w.emitted('feedback')).toBeUndefined()
    })

    it('open(面板开着):按下的样子;点了 emit feedback(父组件拿它关面板)', async () => {
      setup()
      const w = mount(WalkStatusBar, { props: { feedback: 'open' } })
      const b = btn(w)
      expect(b.classes()).toContain('on')
      expect(b.attributes('aria-pressed')).toBe('true')
      expect(b.attributes('disabled')).toBeUndefined()
      expect(b.attributes('title')).toBe('close the feedback panel (Esc)')
      await b.trigger('click')
      expect(w.emitted('feedback')).toEqual([[]])
    })

    it('三态之间跟着 prop 换', async () => {
      setup()
      const w = mount(WalkStatusBar, { props: { feedback: 'off' } })
      await w.setProps({ feedback: 'on' })
      expect(btn(w).attributes('disabled')).toBeUndefined()
      await w.setProps({ feedback: 'open' })
      expect(btn(w).classes()).toContain('on')
      await w.setProps({ feedback: undefined })
      expect(btn(w).exists()).toBe(false)
    })
  })
})
