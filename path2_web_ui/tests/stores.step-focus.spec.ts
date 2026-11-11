// 当前日、当家行与 ←/→ 步进:bracket 族内逐次 hit、band 族内逐个成员、待选时在候选间走、外部行自带步进。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useViewStore } from '../src/stores/view'
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

describe('view store · 当前日、当家行与 ←/→', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  function setup() {
    const view = useViewStore()
    view.loadScanFile(makeFixture())
    view.setLevel('detected')
    return view
  }

  it('focusHit:当前日缺省取第一个买入日,当家行缺省是它所在的 bracket 族', () => {
    const view = setup()
    view.focusHit('h2')
    expect(view.currentDay).toBe(14)
    expect(view.activeFamilyKey).toBe('hits@0')
  })

  it('sameDayHits:选中的 hit 和别的几次买在同一天时给出这几次与当前第几次;只有一次、没选中时为 null', () => {
    const view = setup()
    expect(view.sameDayHits).toBeNull()
    view.focusHit('h0')
    expect(view.sameDayHits).toEqual({ ids: ['h0', 'h1'], index: 0 })
    view.stepFocus(1)
    expect(view.sameDayHits).toEqual({ ids: ['h0', 'h1'], index: 1 })
    view.stepFocus(1)                                    // h2 那天只有它一次
    expect(view.focusedHitId).toBe('h2')
    expect(view.sameDayHits).toBeNull()
  })

  it('bracket 族内按终点走(同终点按原顺序),到头停住', () => {
    const view = setup()
    view.focusHit('h0')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h1')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h2')
    expect(view.currentDay).toBe(14)
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h2')
    view.stepFocus(-1)
    expect(view.focusedHitId).toBe('h1')
    expect(view.activeFamilyKey).toBe('hits@0')
  })

  it('band 族内按成员顺序走(含同一天两个成员),走到没成 hit 的成员只选它;档位筛掉的不走', () => {
    const view = setup()
    view.focusEvent(P0.instance_id)
    expect(view.focusedHitId).toBe('h0')
    expect(view.activeFamilyKey).toBe('plateau@0')
    expect(view.currentDay).toBe(13)
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h1')                 // 同一天的另一个成员
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h2')
    view.stepFocus(1)
    expect(view.focusedHitId).toBeNull()
    expect(view.selectedInstanceId).toBe(P3.instance_id)
    expect(view.currentDay).toBe(15)
    view.stepFocus(1)
    expect(view.selectedInstanceId).toBe(P3.instance_id)  // 到头停住
    expect(view.activeFamilyKey).toBe('plateau@0')

    view.focusEvent(P2.instance_id)
    view.setLevel('in_hit')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h2')                 // P3 只到 detected,in_hit 档下不在这一族里
  })

  it('点被几次 hit 共用的子段:待选、当前日为空、当家行在 bracket;←/→ 在候选间走,选中后仍在候选间走', () => {
    const view = setup()
    view.focusEvent(S10.instance_id, { family: 'step@10' })
    expect([...view.candidateHitIds].sort()).toEqual(['h0', 'h2'])
    expect(view.currentDay).toBeNull()
    expect(view.activeFamilyKey).toBe('hits@0')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h0')
    expect(view.currentDay).toBe(13)
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h2')                 // 跳过不在候选里的 h1
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h2')
    view.stepFocus(-1)
    expect(view.focusedHitId).toBe('h0')
    expect(view.activeFamilyKey).toBe('hits@0')
  })

  it('聚焦一个低于当前档位的 event 不改档位:只选中它、当前日落在它的终点', () => {
    const view = setup()
    view.setLevel('in_hit')
    view.focusEvent(P3.instance_id)                                 // P3 只到 detected
    expect(view.level).toBe('in_hit')
    expect(view.selectedInstanceId).toBe(P3.instance_id)
    expect(view.currentDay).toBe(15)
  })

  it('待选时 ← 从最后一个候选开始', () => {
    const view = setup()
    view.focusEvent(S10.instance_id)
    view.stepFocus(-1)
    expect(view.focusedHitId).toBe('h2')
  })

  it('点击统一规则 · band 格:成员的 hit 合起来;同一天的两次 hit 直选第一次(深档、原顺序),→ 换同一天的下一次', () => {
    const view = setup()
    view.focusMark([P0.instance_id, P1.instance_id], { day: 13, family: 'plateau@0' })
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.focusedHitId).toBe('h0')
    expect(view.focusedInstanceId).toBe(P0.instance_id)
    expect(view.currentDay).toBe(13)
    expect(view.activeFamilyKey).toBe('plateau@0')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h1')
  })

  it('点击统一规则 · 一个成员被同一天两次 hit 共用(today):直选第一次,当家行仍是这一行,→ 在这两次间走', () => {
    const view = setup()
    view.focusEvent(T13.instance_id, { day: 13, family: 'today@13' })
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.focusedHitId).toBe('h0')
    expect(view.currentDay).toBe(13)
    expect(view.activeFamilyKey).toBe('today@13')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h1')
    expect(view.activeFamilyKey).toBe('today@13')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h1')                 // 到头停住
    view.stepFocus(-1)
    expect(view.focusedHitId).toBe('h0')
  })

  it('点击统一规则 · ▼ 与 bracket 格:买入日完全一样直选第一次,不一样进待选', () => {
    const view = setup()
    view.focusBuyDay(13, ['h0', 'h1'], 'hits@0')
    expect(view.candidateHitIds.size).toBe(0)
    expect(view.focusedHitId).toBe('h0')
    expect(view.currentDay).toBe(13)
    expect(view.activeFamilyKey).toBe('hits@0')
    view.stepFocus(1)
    expect(view.focusedHitId).toBe('h1')
    view.focusBuyDay(14, ['h2'], 'hits@0')
    expect(view.focusedHitId).toBe('h2')
    expect(view.currentDay).toBe(14)
    view.focusHits(['h0', 'h2'], { family: 'hits@0' })
    expect([...view.candidateHitIds].sort()).toEqual(['h0', 'h2'])
    expect(view.focusedHitId).toBeNull()
    expect(view.currentDay).toBeNull()
  })

  it('外部行:←/→ 调它自己的 step;待选时调用方带的外部行不被 bracket 顶掉', () => {
    const view = setup()
    const step = vi.fn()
    view.focusEvent(S10.instance_id, { family: { kind: 'external', key: 'samples', step } })
    expect(view.candidateHitIds.size).toBe(2)
    expect(view.activeFamilyKey).toBe('samples')
    view.stepFocus(1)
    expect(step).toHaveBeenCalledWith(1)
    view.setActiveFamily(null)
    view.setCurrentDay(7)
    expect(view.currentDay).toBe(7)
  })

  it('clearFocus 清当前日与当家行', () => {
    const view = setup()
    view.focusHit('h0')
    view.clearFocus()
    expect(view.currentDay).toBeNull()
    expect(view.activeFamily).toBeNull()
    view.stepFocus(1)                                     // 没有当家行:什么都不做
    expect(view.focusedHitId).toBeNull()
  })
})
