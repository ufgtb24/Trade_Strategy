/**
 * hit 与 event 之间的几样基本查询(纯函数,类型无关),选中模型(render/select.ts、selWorld.ts、selSnapshot.ts)、
 * 图上的悬停与侧栏共用:
 * - 一次 hit 的日子(买入日)、hit 的先后;
 * - 一个 event 被哪些 hit 用到(沿 child_refs 找父容器)、一次 hit 绑定的全部 event;
 * - 同一天叠着的几个各自的区别标签(显示栏的 diff 格、选中卡、悬停逐行同一写法);
 * - 落点:换到另一天时,那里叠着好几次 hit,落在和当前那次最像的一次。
 *
 * 只读 hit 的 hit_id / start_idx / end_idx / node_index、event 的 instance_id / child_refs 与买入日(fold.ts 的
 * buyDaysOf),不认任何具体事件类型。
 */
import type { EventDict, HitDict } from '../types'
import { buyDaysOf, formatMemberLabel, hitLabels, memberLabels } from './fold'

/** 同一天叠着的一个:一次 hit,或一个 event(band 上同一格里的成员)。 */
export interface WalkEntry { hitId: string | null; instanceId: string | null }

/** 一次 hit 的日子:买入日(升序);解析不到买入日(没有 endNode 等)时取终点。 */
export function hitDays(m: HitDict, byId: ReadonlyMap<string, EventDict>, endNode: string | null | undefined): number[] {
  const d = buyDaysOf(m, byId, endNode)
  return d.length ? d : [m.end_idx]
}

/** hit 的先后:(起点, 终点, 结果里的原顺序)——同一族里就是族内顺序,跨族时先按族起点。 */
export function hitOrderOf(hits: readonly HitDict[]): Map<string, number> {
  const out = new Map<string, number>()
  hits.map((m, i) => ({ m, i }))
    .sort((a, b) => a.m.start_idx - b.m.start_idx || a.m.end_idx - b.m.end_idx || a.i - b.i)
    .forEach((x, k) => out.set(x.m.hit_id, k))
  return out
}

/**
 * 「一个实例被哪些 hit 用到」的查表:先看 hit.node_index 的精确引用;没有就沿 child_refs 爬到父容器再看
 * (子 node 的 event 不在 node_index 里,经容器 child_refs 挂靠;多父时汇总)。按结果里的原顺序。
 * 选中一个 event 时它牵出的 hit、悬停里的 `hits ×n` 都是这个数。
 */
export function usingIndex(hits: readonly HitDict[], events: readonly EventDict[]): (instanceId: string) => HitDict[] {
  const direct = new Map<string, number[]>()
  hits.forEach((m, i) => {
    for (const id of new Set(Object.values(m.node_index ?? {}))) {
      const g = direct.get(id)
      if (g) g.push(i)
      else direct.set(id, [i])
    }
  })
  const parents = new Map<string, string[]>()
  for (const e of events) {
    for (const ids of Object.values(e.child_refs ?? {})) {
      if (!Array.isArray(ids)) continue
      for (const c of ids) {
        const g = parents.get(c)
        if (g) { if (!g.includes(e.instance_id)) g.push(e.instance_id) } else parents.set(c, [e.instance_id])
      }
    }
  }
  return (instanceId) => {
    const own = direct.get(instanceId)
    if (own) return own.map(i => hits[i])
    const idx = new Set<number>()
    for (const p of parents.get(instanceId) ?? []) for (const i of direct.get(p) ?? []) idx.add(i)
    return [...idx].sort((a, b) => a - b).map(i => hits[i])
  }
}

/**
 * 叠着的几个各自的区别标签(显示栏的 diff 格、选中卡、悬停逐行、复制的行共用,写法一致):都是 hit 时用 hitLabels,
 * 否则用成员区分标签;退到内部编号的(分不出哪里不一样)写空串——界面上不给编号。只有一个时为空数组。
 */
export function stackLabelTexts(entries: readonly WalkEntry[], hitsById: ReadonlyMap<string, HitDict>,
                                byId: ReadonlyMap<string, EventDict>, nodeOrder: readonly string[],
                                anchorFields: readonly string[], dates: readonly string[]): string[] {
  if (entries.length < 2) return []
  const hitIds = entries.map(e => e.hitId)
  const ls = hitIds.every((h): h is string => !!h)
    ? hitLabels(hitIds, hitsById, byId, nodeOrder, anchorFields)
    : memberLabels(entries.map(e => e.instanceId ?? ''), byId, anchorFields)
  return ls.map(l => (l.via === 'hit_id' || l.via === 'instance_id'
    ? '' : formatMemberLabel(l, dates).replace(' → ', '→')))
}

/** 这几次 hit 跨了几族(起点不同算不同族)。 */
export function familiesOf(ms: readonly HitDict[]): number {
  return new Set(ms.map(m => m.start_idx)).size
}

/**
 * 一次 hit 绑定的全部 event:node_index 里的,再沿 child_refs 往下(子 node 的 event 不在 node_index 里,
 * 挂在容器的 child_refs 下;如 new_step 的阶跃切法只在 plateau 的 child_refs 里看得出)。
 */
export function boundEvents(m: HitDict, byId: ReadonlyMap<string, EventDict>): Set<string> {
  const out = new Set<string>()
  const stack = [...Object.values(m.node_index ?? {}), ...(m.children ?? [])]
  while (stack.length) {
    const id = stack.pop()!
    if (out.has(id)) continue
    out.add(id)
    for (const ids of Object.values(byId.get(id)?.child_refs ?? {})) if (Array.isArray(ids)) stack.push(...ids)
  }
  return out
}

function sameEntry(a: WalkEntry | null | undefined, b: WalkEntry): boolean {
  return !!a && a.hitId === b.hitId && a.instanceId === b.instanceId
}

/**
 * 落点:带着当前那一个换到另一天(或点了一格里的几次)时,那里叠着好几个,落在和当前那个最像的一个——
 * 同一个就是它;否则比两次 hit 绑定的 event(boundEvents)重合几个(切法跟着走),同一个成员也算像;平手取靠前的。
 * 没有当前那个时落第一个。待验证:「重合最多、平手靠前」是会话默认。
 */
export function landIndex(entries: readonly WalkEntry[], cur: WalkEntry | null | undefined,
                          bound: (hitId: string) => ReadonlySet<string>): number {
  if (!cur || entries.length === 0) return 0
  let best = 0, bestScore = -1
  entries.forEach((e, i) => {
    let s = 0
    if (sameEntry(cur, e)) s = 1e9
    else {
      if (cur.hitId && e.hitId) {
        if (cur.hitId === e.hitId) s += 1e6
        const mine = bound(cur.hitId)
        for (const v of bound(e.hitId)) if (mine.has(v)) s += 1
      }
      if (cur.instanceId && e.instanceId === cur.instanceId) s += 1000
    }
    if (s > bestScore) { bestScore = s; best = i }
  })
  return best
}
