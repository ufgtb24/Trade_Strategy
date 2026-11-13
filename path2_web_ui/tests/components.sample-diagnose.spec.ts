// selection 页的 diagnose 块:按进没进 hit 分两组,组头带个数;hits 组一块一次 hit、不写档位,先后照 compare store 的
// stackCards(和 ↑ / ↓ 走的先后同一份);同一个 event 被几次 hit 共用时写 × k;not_in_hit 组写档位与没过的 where,
// 非配对的 detected 折起来。
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import SampleDiagnose from '../src/components/SampleDiagnose.vue'

const row = (instanceId: string, level: string, o: Record<string, unknown> = {}) =>
  ({ instanceId, start: 0, member: null, level, failed: [], paired: false, ...o })

const view = reactive({
  barDates: ['2024-01-01', '2024-01-02', '2024-01-03'], level: 'in_hit', selectedHitId: null as string | null,
  focusedInstanceRef: null as string | null,
  effectiveAnalysis: { hits: [
    { hit_id: 'h_b', node_index: { plateau: 'P_b' } },      // 先后:P_b 在前
    { hit_id: 'h_a1', node_index: { plateau: 'P_a' } },
    { hit_id: 'h_a2', node_index: { plateau: 'P_a' } },     // P_a 被两次 hit 共用
  ] },
})
// 块的先后由 compare store 给(stackCards);这里直接给定
let cards = [{ instanceId: 'P_a', hitIds: ['h_a1', 'h_a2'] }, { instanceId: 'P_b', hitIds: ['h_b'] }]
const pickCard = vi.fn()
const cmp = reactive({
  pairNode: 'plateau', notes: { 'plateau.vol_ok': '放量' } as Record<string, string>,
  stackCards: () => cards, pickCard,
  diagnose: { read: { id: 's1', day: 2, judgment: 'pos', mark: '✓', match: { state: 'matched', offset: 0 }, pairing: {} },
    rows: [
      row('P_a', 'in_hit', { paired: true, member: 'step → 2024-01-02' }),
      row('P_b', 'in_hit', { member: 'step → 2024-01-03' }),
      row('P_q', 'qualified'),
      row('P_d', 'detected', { failed: ['vol_ok'] }),
    ] },
})
vi.mock('../src/stores/view', () => ({ useViewStore: () => view }))
vi.mock('../src/stores/compare', () => ({ useCompareStore: () => cmp }))
vi.mock('../src/stores/annotation', () => ({ useAnnotationStore: () => ({ match: { pos: 3, neg: 1 } }) }))

describe('SampleDiagnose · hits / not_in_hit 两组', () => {
  it('组头个数、块的归组与顺序、× k、档位只在 not_in_hit、detected 折叠后点开', async () => {
    const w = mount(SampleDiagnose)
    const count = (g: string) => w.find(`[data-testid="diagnose-group-${g}"] [data-testid="diagnose-count"]`).text()
    expect(count('hits')).toBe('3')                      // 数的是 hit:P_a 两次 + P_b 一次
    expect(count('not_in_hit')).toBe('2')
    expect(w.find('[data-testid="diagnose-group-not_in_hit"]').text()).toMatch(/qualified 1.*detected 1/)
    expect(w.find('[data-testid="diagnose-group-hits"]').text()).not.toContain('in_hit')

    const rows = () => w.findAll('[data-testid="diagnose-row"]').map(r => `${r.attributes('data-group')}:${r.attributes('data-instance')}`)
    expect(rows()).toEqual(['hits:P_a', 'hits:P_b', 'not_in_hit:P_q'])   // 配对的在最前;detected 折着
    const [a, b, q] = w.findAll('[data-testid="diagnose-row"]')
    expect(a.find('[data-testid="diagnose-shared"]').text()).toBe('× 2')
    expect(b.find('[data-testid="diagnose-shared"]').exists()).toBe(false)
    expect(a.find('[data-testid="diagnose-level"]').exists()).toBe(false)
    expect(q.find('[data-testid="diagnose-level"]').text()).toBe('qualified')
    expect(q.find('[data-testid="diagnose-hidden"]').exists()).toBe(true)   // 当前档位 in_hit,qualified 画不出来

    await w.find('[data-testid="diagnose-more"]').trigger('click')
    expect(rows()).toEqual(['hits:P_a', 'hits:P_b', 'not_in_hit:P_q', 'not_in_hit:P_d'])
    const d = w.findAll('[data-testid="diagnose-row"]')[3]
    expect(d.find('[data-testid="diagnose-failed"]').text()).toBe('vol_ok')
    expect(d.find('[data-testid="diagnose-note"]').text()).toBe('放量')
  })

  it('hits 组的先后照 stackCards;选中的那块描黑边;点一块交给 compare store(选中的仍在这个样本下面)', async () => {
    cmp.diagnose.rows = [
      row('P_a', 'in_hit'), row('P_b', 'in_hit'),          // 都不是配对:P_b 的 hit 在前
    ]
    cards = [{ instanceId: 'P_b', hitIds: ['h_b'] }, { instanceId: 'P_a', hitIds: ['h_a1', 'h_a2'] }]
    view.selectedHitId = 'h_a1'
    const w = mount(SampleDiagnose)
    const rows = w.findAll('[data-testid="diagnose-row"]')
    expect(rows.map(r => r.attributes('data-instance'))).toEqual(['P_b', 'P_a'])
    expect(rows.map(r => r.classes('cur'))).toEqual([false, true])
    await rows[0].trigger('click')
    expect(pickCard).toHaveBeenCalledWith('s1', 'P_b')
  })
})
