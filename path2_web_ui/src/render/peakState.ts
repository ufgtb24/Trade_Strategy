// pk 三态合成(契约 C4)+ pk_id 反查索引(契约 C5 消费者)。
// bo/pk 特有语义(槽名 broken/superseded、字段 peak_idx/pk_id)在本渲染层的唯一落点
// (契约 C7 类型无关红线);chart.ts 只调这两个纯函数,不直接解释这些语义。
import type { EventDict } from '../types'

export type PkState = 'alive' | 'broken' | 'eaten'

/**
 * pk 三态合成:按本股全部 events(level / nodeVisible 过滤之前)合成。
 * 某 pk 的 instance_id 出现在任一事件 ref_ids.broken 里 → broken;
 * 否则出现在任一事件 ref_ids.superseded 里 → eaten;否则 alive。
 * 与被删的 PeakEvent.state 三条突变规则逐条等价(broken 优先于 eaten)。
 * pk 事件的判别子 = 带 peak_idx(number);非 pk 事件不进结果。
 */
export function derivePeakStates(events: EventDict[]): Map<string, PkState> {
  const states = new Map<string, PkState>()
  for (const e of events) {
    if (typeof e.peak_idx === 'number') states.set(e.instance_id, 'alive')
  }
  const eaten = new Set<string>()
  for (const e of events) {
    for (const id of e.ref_ids?.superseded ?? []) eaten.add(id)
  }
  for (const id of eaten) {
    if (states.has(id)) states.set(id, 'eaten')
  }
  const broken = new Set<string>()
  for (const e of events) {
    for (const id of e.ref_ids?.broken ?? []) broken.add(id)
  }
  for (const id of broken) {
    if (states.has(id)) states.set(id, 'broken')
  }
  return states
}

/** instance_id → pk_id,只收 pk 事件(带 peak_idx 的事件)。 */
export function peakIdIndex(events: EventDict[]): Map<string, number> {
  const idx = new Map<string, number>()
  for (const e of events) {
    if (typeof e.peak_idx === 'number' && typeof e.pk_id === 'number') {
      idx.set(e.instance_id, e.pk_id)
    }
  }
  return idx
}
