// 当前日与选中的边角:档位筛掉的成员不在 band 上、低于当前档位的 event、样本(由 compare 登记进来)、clearFocus。
// 主路径(▼、格、band、step、today、族底线、反馈)见 stores.walk.spec.ts。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
import { slotText } from '../src/render/selSnapshot'
import type { Sel } from '../src/render/select'
import type { EventDict, HitDict, MultiScanResultFile } from '../src/types'

const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })

// new_step 式:plateau 容器引用 step / today;同一个阶跃前缀被几天的 plateau 共用
const S10 = ev('step', 10, 10), S11 = ev('step', 10, 11)
const T13 = ev('today', 13, 13), T14 = ev('today', 14, 14), T15 = ev('today', 15, 15)
const P0 = ev('plateau', 0, 13, 0, { step: [S10.instance_id], today: [T13.instance_id] })
const P1 = ev('plateau', 0, 13, 1, { step: [S11.instance_id], today: [T13.instance_id] })
const P2 = ev('plateau', 0, 14, 0, { step: [S10.instance_id], today: [T14.instance_id] })
const P3 = ev('plateau', 0, 15, 0, { step: [S10.instance_id], today: [T15.instance_id] })   // 没成 hit
const hit = (id: string, p: EventDict): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id },
  children: [p.instance_id, ...Object.values(p.child_refs ?? {}).flat()],
})

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
            { node_id: 'step', render_grid: 'time', where_rules: [], solve: false },
            { node_id: 'today', render_grid: 'time', where_rules: [], solve: false, is_point: true },
          ],
          edges: [],
        },
        event_styles: {},
      },
    } },
    results: [{ symbol: 'AAA', per_pattern: { p1: { analysis: {
      events: [S10, S11, T13, T14, T15, P0, P1, P2, P3],
      hits: [hit('h0', P0), hit('h1', P1), hit('h2', P2)],
    }, summary: { hits: 3 } } } }],
    scan: { win_start: '2020-01-01', win_end: '2020-12-31', label_horizon: 20 },
  } as any
}

const node = (band: string): Sel => ({ kind: 'node', band })
const e = (x: EventDict): Sel => ({ kind: 'event', instanceId: x.instance_id })
const sample = (id: string): Sel => ({ kind: 'sample', sampleId: id })

describe('view store · 当前日与选中的边角', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  function setup() {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('detected')
    return view
  }
  const slots = (view: ReturnType<typeof useViewStore>) =>
    [slotText(view.selInfo!.day), slotText(view.selInfo!.stack)]

  it('沿 band 按格走:选中的一直是 event,走到没成 hit 的成员照样选它;档位筛掉的成员不在这条 band 上', () => {
    const view = setup()
    view.focusEvent(P0.instance_id)
    // 点 band 上的东西只选中这个 event,不替用户选中用到它的那次 hit
    expect(view.selPath).toEqual([node('plateau'), e(P0)])
    expect([view.focusedHitId, view.selectedInstanceId, view.currentDay]).toEqual([null, P0.instance_id, 13])
    view.stepStack(1)
    expect(view.selectedInstanceId).toBe(P1.instance_id)  // 同一格的另一个成员
    view.stepPos(1)
    expect(view.selectedInstanceId).toBe(P2.instance_id)
    view.stepPos(1)
    expect([view.focusedHitId, view.selectedInstanceId, view.currentDay]).toEqual([null, P3.instance_id, 15])
    view.stepPos(1)
    expect(view.selectedInstanceId).toBe(P3.instance_id)  // 到头停住

    view.focusEvent(P2.instance_id)
    view.setLevel('in_hit')
    view.stepPos(1)
    expect(view.selectedInstanceId).toBe(P2.instance_id)  // P3 只到 detected,in_hit 档下不在这条 band 上
  })

  it('聚焦一个低于当前档位的 event 不改档位:只选中它、当前日落在它的终点;它在图上画不出来,两组键都没有可去的地方', () => {
    const view = setup()
    view.setLevel('in_hit')
    view.focusEvent(P3.instance_id)                                 // P3 只到 detected
    expect(view.level).toBe('in_hit')
    expect(view.selectedInstanceId).toBe(P3.instance_id)
    expect(view.currentDay).toBe(15)
    expect(slots(view)).toEqual([null, null])
  })

  it('样本(由 compare 登记进来):选中样本只是样本,竖线落样本日;↓ 进到在场的几次,← / → 带着这一次换到旁边的样本并通知登记方', () => {
    const view = setup()
    const onAnchor = vi.fn()
    view.setSelSources({
      samples: () => [{ id: 'a', day: 13, hitIds: ['h0', 'h1'], pairedHitId: 'h0' }, { id: 'b', day: 14, hitIds: ['h2'], pairedHitId: 'h2' }],
      onAnchor,
    })
    view.setPath([sample('a')])
    // 在场的哪一次都不算选中,要按 ↓ 进去才是
    expect([view.focusedHitId, view.currentDay, view.activeFamilyKey]).toEqual([null, 13, 'samples'])
    expect(slots(view)).toEqual(['samples 1/2', 'into hits ×2'])
    view.stepStack(1)
    expect(view.focusedHitId).toBe('h0')
    view.stepStack(1)
    expect([view.focusedHitId, view.currentDay]).toEqual(['h1', 13])
    expect(onAnchor).not.toHaveBeenCalled()              // 还在同一个样本里
    view.stepPos(1)
    expect(view.selPath).toEqual([sample('b'), { kind: 'hit', hitId: 'h2', day: 14 }])
    expect([view.focusedHitId, view.currentDay]).toEqual(['h2', 14])
    expect(onAnchor).toHaveBeenCalledWith(sample('b'))
    // 挂在样本下面的 event(从样本的 diagnose 点进来):只选中它,没有可走的邻居
    view.setPath([sample('a'), e(P3)])
    expect([view.focusedHitId, view.selectedInstanceId, view.activeFamilyKey]).toEqual([null, P3.instance_id, 'samples'])
    expect(slots(view)).toEqual([null, null])
  })

  it('换档位:显示栏的 events k/n 跟着当前档位画出来的格数走,→ 只走画出来的格', () => {
    const view = setup()                                            // detected 档:plateau 那条 band 上三格(13、14、15)
    view.focusEvent(P0.instance_id)
    expect(slotText(view.selInfo!.day)).toBe('events 1/3')
    view.setLevel('in_hit')                                         // 第 15 天那格只有没成 hit 的 P3:这一档不画
    expect(view.selectedInstanceId).toBe(P0.instance_id)
    expect(slotText(view.selInfo!.day)).toBe('events 1/2')
    view.stepPos(1)
    expect([view.selectedInstanceId, slotText(view.selInfo!.day)]).toEqual([P2.instance_id, 'events 2/2'])
    view.stepPos(1)                                                 // 画出来的最后一格:到头,不会走到没画的 P3
    expect([view.selectedInstanceId, view.currentDay]).toEqual([P2.instance_id, 14])
    view.setLevel('detected')                                       // 换回来:三格都在,→ 又能走到 P3
    expect(slotText(view.selInfo!.day)).toBe('events 2/3')
    view.stepPos(1)
    expect(view.selectedInstanceId).toBe(P3.instance_id)
  })

  it('样本 / 框的细框与亮起的组成只跟配对的那一次:没有配对时那天在场别的 hit 也不画细框、不亮组成,↓ 仍能进去', () => {
    const view = setup()
    const present = ['h0', 'h1']                                    // 第 13 天在场的两次
    let paired: string | null = null
    view.setSelSources({
      samples: () => [{ id: 'a', day: 13, hitIds: present, pairedHitId: paired }],
      boxes: () => [{ id: 'x', day: 13, hitIds: present, pairedHitId: paired }],
    })
    for (const sel of [sample('a'), { kind: 'box', boxId: 'x' } as Sel]) {
      view.setPath([sel])
      expect([view.candidateHitIds.size, view.highlightedEventIds.size]).toEqual([0, 0])
      expect(slotText(view.selInfo!.stack)).toBe('into hits ×2')
      view.stepStack(1)
      expect(view.selPath).toEqual([sel, { kind: 'hit', hitId: 'h0', day: 13 }])
    }
    paired = 'h1'
    view.setSelSources({
      samples: () => [{ id: 'a', day: 13, hitIds: present, pairedHitId: paired }],
      boxes: () => [{ id: 'x', day: 13, hitIds: present, pairedHitId: paired }],
    })
    for (const sel of [sample('a'), { kind: 'box', boxId: 'x' } as Sel]) {
      view.setPath([sel])
      expect([...view.candidateHitIds]).toEqual(['h1'])
      expect([...view.highlightedEventIds].sort()).toEqual([P1.instance_id, S11.instance_id, T13.instance_id].sort())
    }
  })

  it('clearFocus 清当前日与选中;之后按键不接', () => {
    const view = setup()
    view.focusHit('h0')
    view.clearFocus()
    expect(view.currentDay).toBeNull()
    expect(view.selPath).toEqual([])
    expect(view.selInfo).toBeNull()
    expect(view.stepPos(1)).toBe(false)
    expect(view.focusedHitId).toBeNull()
    view.setCurrentDay(7)
    expect(view.currentDay).toBe(7)
  })
})
