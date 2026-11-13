/**
 * 从分析结果现算「里面装着什么、同一层是谁」(render/select.ts 的 World;纯函数,类型无关)。
 *
 * 装着(只有这些):
 * - 跨天:一族 → 它的买点日;反馈 → 它收进来的 hit 的买点日;event → 用到它的 hit 的买点日;
 *   node → 它那条 band 上画出来的格(按终点日,一格可能并着几个 event)。
 * - 同一天:买点日 → 这天那个 ▼ 上的几次 hit(只有一次时这天就是那次 hit,算没有);样本、框 → 那天在场的几次 hit。
 * 一次 hit 绑定的 event 不算:它们散在不同的 band 上,不是一行里的一串。
 *
 * 同一层:路径上一节里面的同种东西;没有上一节就是整张图上的同种东西(族、反馈、样本、框)。
 * event 的同一层是它那条 band 上的格,每格取和它同一个起点的那个(没有取第一个);挂在样本下面的 event
 * (从样本的 diagnose 点进来)在样本里没有沿日子排开的邻居。
 *
 * 只读 hit 的 hit_id / start_idx / node_index、event 的 instance_id / start_idx / end_idx 与买入日,不认具体事件类型。
 */
import type { EventDict, HitDict } from '../types'
import { HIT_FAMILY_PREFIX, familyKeyOf, type Family } from './fold'
import { hitDays, landIndex } from './walk'
import type { Axis, Item, Sel, SelPath, World } from './select'

/**
 * 一个样本 / 框:day 是样本日 / 框终点;hitIds 是那天在场的几次 hit(配对的排第一,和 diagnose 的 hits 组同一顺序);
 * pairedHitId 是配对的那一次(配对的 event 没进 hit 为 null)。
 */
export interface AnchorRow { id: string; day: number; hitIds: readonly string[]; pairedHitId: string | null }

export interface WorldCtx {
  hits: readonly HitDict[]
  hitsById: ReadonlyMap<string, HitDict>
  byId: ReadonlyMap<string, EventDict>
  endNode: string | null | undefined
  /** hit 的先后(render/walk.ts 的 hitOrderOf) */
  hitOrder: ReadonlyMap<string, number>
  /** 一个 event 被哪些 hit 用到(render/walk.ts 的 usingIndex) */
  using: (instanceId: string) => HitDict[]
  /** 一次 hit 绑定的全部 event(落点比「像不像」用) */
  bound: (hitId: string) => ReadonlySet<string>
  /** event 画在哪条 band 上 */
  bandOf: (e: EventDict) => string
  /** 一条 band 上画出来的族(已过显隐、档位筛选),按起点升序 */
  bandFamilies: (band: string) => readonly Family[]
  /** 这张图上的反馈(已排好序)与各自收进来的 hit */
  feedbacks: readonly { id: string; hitIds: readonly string[] }[]
  /** 这张图上当前 pattern 的样本(按样本日) */
  samples: readonly AnchorRow[]
  /** 这张图上的框(按终点) */
  boxes: readonly AnchorRow[]
  /** 当前日竖线 */
  lineDay: number | null
}

/** band 上的一格:终点日,和落在这一天的成员(跨族;按族起点、族内顺序)。 */
export interface BandCell { day: number; members: { id: string; start: number }[] }

/** 一条 band 上有 event 结束的日子,一天一格(几族在同一天结束的并在一格里)。 */
export function bandCells(families: readonly Family[]): BandCell[] {
  const byDay = new Map<number, { id: string; start: number }[]>()
  for (const f of families) {
    for (const mk of f.marks) {
      const day = mk.kind === 'point' ? mk.start : mk.end
      const g = byDay.get(day) ?? []
      for (const id of mk.memberIds) g.push({ id, start: f.start })
      byDay.set(day, g)
    }
  }
  return [...byDay.keys()].sort((a, b) => a - b).map(day => ({ day, members: byDay.get(day)! }))
}

/** hit 的一族的键 → 起点下标。 */
function familyStart(familyKey: string): number {
  return Number(familyKey.slice(familyKey.lastIndexOf('@') + 1))
}

export function makeWorld(ctx: WorldCtx): World {
  const rank = (m: HitDict) => ctx.hitOrder.get(m.hit_id) ?? Number.MAX_SAFE_INTEGER
  const byOrder = (ms: HitDict[]) => [...ms].sort((a, b) => rank(a) - rank(b))
  const daysOf = (m: HitDict) => hitDays(m, ctx.byId, ctx.endNode)
  const pick = (ids: readonly string[]) => ids.map(id => ctx.hitsById.get(id)).filter((m): m is HitDict => !!m)

  /** 这一节自己牵出的 hit(只有族、反馈、event 有);别的为 null。 */
  function ownHits(s: Sel): HitDict[] | null {
    if (s.kind === 'hit_family') { const st = familyStart(s.familyKey); return ctx.hits.filter(m => m.start_idx === st) }
    if (s.kind === 'feedback') return pick(ctx.feedbacks.find(f => f.id === s.id)?.hitIds ?? [])
    if (s.kind === 'event') return ctx.using(s.instanceId)
    return null
  }

  /** 买点日所在的那一串来自哪一节(往外找最近的族、反馈或 event)。 */
  function scopeOf(path: SelPath): { sel: Sel; hits: HitDict[] } | null {
    for (let i = path.length - 1; i >= 0; i--) {
      const ms = ownHits(path[i])
      if (ms) return { sel: path[i], hits: ms }
    }
    return null
  }

  function buyItems(ms: readonly HitDict[]): Item[] {
    const days = new Set<number>()
    for (const m of ms) for (const d of daysOf(m)) days.add(d)
    return [...days].sort((a, b) => a - b).map(day => ({ sel: { kind: 'buy', day }, day }))
  }

  function cellsOf(band: string): BandCell[] { return bandCells(ctx.bandFamilies(band)) }

  function dayOf(s: Sel): number | null {
    if (s.kind === 'buy' || s.kind === 'hit') return s.day
    if (s.kind === 'event') return ctx.byId.get(s.instanceId)?.end_idx ?? null
    if (s.kind === 'sample') return ctx.samples.find(x => x.id === s.sampleId)?.day ?? null
    if (s.kind === 'box') return ctx.boxes.find(x => x.id === s.boxId)?.day ?? null
    return null
  }
  const self = (s: Sel): Item => ({ sel: s, day: dayOf(s) })

  function members(path: SelPath): Item[] {
    const last = path[path.length - 1]
    if (!last) return []
    if (last.kind === 'buy') {
      const scope = scopeOf(path.slice(0, -1))
      if (!scope) return []
      const here = byOrder(scope.hits.filter(m => daysOf(m).includes(last.day)))
      if (here.length === 0) return []
      // 那个 ▼ = 一族 × 这一天:从反馈、event 走进来时取它们的第一次所在的那一族,它们自己的排前面
      const fam = here[0].start_idx
      const mine = here.filter(m => m.start_idx === fam)
      const ids = new Set(mine.map(m => m.hit_id))
      const rest = scope.sel.kind === 'hit_family' ? []
        : byOrder(ctx.hits.filter(m => m.start_idx === fam && !ids.has(m.hit_id) && daysOf(m).includes(last.day)))
      return [...mine, ...rest].map(m => ({ sel: { kind: 'hit', hitId: m.hit_id, day: last.day }, day: last.day }))
    }
    if (last.kind === 'sample' || last.kind === 'box') {
      const row = last.kind === 'sample' ? ctx.samples.find(x => x.id === last.sampleId)
        : ctx.boxes.find(x => x.id === last.boxId)
      if (!row) return []
      return pick(row.hitIds).map(m => ({ sel: { kind: 'hit', hitId: m.hit_id, day: row.day }, day: row.day }))
    }
    return []
  }

  function inside(path: SelPath, axis: Axis): Item[] {
    const last = path[path.length - 1]
    if (!last) return []
    if (axis === 'stack') {
      const ms = members(path)
      // 只有一次 hit 的买点日和那次 hit 是同一样东西,不算「装着一个」
      return last.kind === 'buy' && ms.length < 2 ? [] : ms
    }
    const own = ownHits(last)
    if (own) return buyItems(own)
    if (last.kind === 'node') {
      return cellsOf(last.band).map(c => ({ sel: { kind: 'event', instanceId: c.members[0].id }, day: c.day }))
    }
    return []
  }

  function peers(path: SelPath, axis: Axis): Item[] {
    const last = path[path.length - 1]
    if (!last) return []
    const parent = path.length >= 2 ? path[path.length - 2] : null
    if (last.kind === 'event') {
      const ev = ctx.byId.get(last.instanceId)
      if (!ev || (parent && parent.kind !== 'node')) return [self(last)]
      const cells = cellsOf(ctx.bandOf(ev))
      const mine = cells.find(c => c.members.some(m => m.id === last.instanceId))
      if (!mine) return [self(last)]
      if (axis === 'stack') return mine.members.map(m => ({ sel: { kind: 'event', instanceId: m.id }, day: mine.day }))
      return cells.map(c => {
        const id = c === mine ? last.instanceId : (c.members.find(m => m.start === ev.start_idx) ?? c.members[0]).id
        return { sel: { kind: 'event', instanceId: id }, day: c.day }
      })
    }
    if (axis === 'stack') return [self(last)]
    if (last.kind === 'buy') return parent ? inside(path.slice(0, -1), 'day') : [self(last)]
    if (last.kind === 'hit_family') {
      const starts = [...new Set(ctx.hits.map(m => m.start_idx))].sort((a, b) => a - b)
      return starts.map(st => ({ sel: { kind: 'hit_family', familyKey: familyKeyOf(HIT_FAMILY_PREFIX, st) }, day: null }))
    }
    if (last.kind === 'feedback') return ctx.feedbacks.map(f => ({ sel: { kind: 'feedback', id: f.id }, day: null }))
    if (last.kind === 'sample') return ctx.samples.map(x => ({ sel: { kind: 'sample', sampleId: x.id }, day: x.day }))
    if (last.kind === 'box') return ctx.boxes.map(x => ({ sel: { kind: 'box', boxId: x.id }, day: x.day }))
    return [self(last)]
  }

  function similar(cands: readonly Item[], cur: Sel): number {
    if (cur.kind !== 'hit') return 0
    const entries = cands.map(c => ({ hitId: c.sel.kind === 'hit' ? c.sel.hitId : null, instanceId: null }))
    return landIndex(entries, { hitId: cur.hitId, instanceId: null }, ctx.bound)
  }

  return { inside, members, peers, similar, lineDay: () => ctx.lineDay }
}

/** 这一节的当前日竖线该落在哪根 K 线上;族、反馈、node 不带日子(竖线不动)为 null。 */
export function lineDayOf(s: Sel, ctx: Pick<WorldCtx, 'byId' | 'samples' | 'boxes'>): number | null {
  if (s.kind === 'buy' || s.kind === 'hit') return s.day
  if (s.kind === 'event') return ctx.byId.get(s.instanceId)?.end_idx ?? null
  if (s.kind === 'sample') return ctx.samples.find(x => x.id === s.sampleId)?.day ?? null
  if (s.kind === 'box') return ctx.boxes.find(x => x.id === s.boxId)?.day ?? null
  return null
}
