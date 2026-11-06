/**
 * 副图的折叠(纯函数,类型无关):同一条 band 里起点相同的 event 折成一族,画成一行。
 *
 * 只读 event 的 node / start_idx / end_idx / child_refs、拓扑 node 的 is_point 与 edges 上的 anchor_field、
 * 档位和事件数组原顺序,不认任何具体事件类型。
 *
 * 规则:
 * - 认族:键 = 序列化下来的 start_idx 原值,只在同一条 band 内比;起点不同一律不折。
 * - 档位筛选在先:按显示档位筛成员,筛空的族丢掉;solve=false 的 node 免疫。族的右端 = 剩下成员的最大终点。
 *   之后的一切(梳子还是整条、分行)只看筛剩的成员,低档位的 event 不影响高档位的样子。
 * - 梳子还是整条:筛剩的成员数 ≥ 2(multi)就画成「每个成员一格 + 一根中性底线」,否则画一根整条
 *   (一个 event 和它的整段跨度)。所以切档位时同一族可能在梳子与整条之间变样,这是如实反映。
 * - 族内成员顺序:(end_idx, 档位深 → 浅, 输入顺序);每个不同终点一个格,格的档位 = 成员里最深的。
 * - 声明为点的 node(is_point)每族只有一个点记号(成员都在同一根上)。
 *
 * 「同起点折」的前提:同一个 node 里起点相同的实例,是同一个对象逐天长出来(或同一处的几种收段)。
 * 这个前提在三种情形下会失效,折出来的一行里混了本不相干的东西(不做自动检查,写 app 时留意):
 * - 起点由 detector 自适应往回找(左端随当天而变):同一个对象的实例起点各不相同,一个对象被拆成好几行;
 * - 起点锚在几个对象共享的更早一点(如都从同一次突破算起):不同的对象被折进同一行;
 * - 起点被数据起点或视窗截断:截断后的起点相同、真实起点不同——所以认族只用序列化下来的 start_idx 原值,
 *   不用画图时裁到视窗里的值。
 */
import type { EventDict, HitDict, Level, Tier } from '../types'

export const TIER_RANK: Record<Tier, number> = { detected: 0, qualified: 1, in_hit: 2 }

/** 一行里的一个记号:整条(单成员族)、格(多成员族的一个终点)或点。 */
export interface FoldMark {
  kind: 'bar' | 'cell' | 'point'
  start: number
  end: number
  memberIds: string[]   // 落在这个记号上的成员,已按族内顺序排好
  tier: Tier            // 成员里最深的档位
}

/** 一族:同 band、同起点的一串事件。 */
export interface Family {
  key: string           // `${band}@${start}`
  band: string
  start: number
  end: number           // 档位筛选后剩下成员的最大终点
  multi: boolean        // 档位筛选后成员数 ≥ 2
  isPoint: boolean
  memberIds: string[]   // 档位筛选后剩下的成员,族内顺序(即 ←/→ 的步进顺序)
  marks: FoldMark[]
}

export function familyKeyOf(band: string, start: number): string {
  return `${band}@${start}`
}

export interface FoldBandOptions {
  band: string
  isPoint: boolean
  tierOf: (e: EventDict) => Tier
  level: Level
  /** 不参与求解、只显示的 node:不受显示档位筛选 */
  levelImmune?: boolean
}

/** 一条 band 的事件 → 族(按起点升序)。events 必须已是这条 band 的、且已过 node 显隐筛选。 */
export function foldBand(events: readonly EventDict[], opts: FoldBandOptions): Family[] {
  const groups = new Map<number, { e: EventDict; i: number }[]>()
  events.forEach((e, i) => {
    const g = groups.get(e.start_idx)
    if (g) g.push({ e, i })
    else groups.set(e.start_idx, [{ e, i }])
  })
  const minRank = TIER_RANK[opts.level]
  const out: Family[] = []
  for (const start of [...groups.keys()].sort((a, b) => a - b)) {
    const kept = groups.get(start)!
      .map((x) => ({ ...x, tier: opts.tierOf(x.e) }))
      .filter((x) => opts.levelImmune || TIER_RANK[x.tier] >= minRank)
    if (kept.length === 0) continue
    const multi = kept.length >= 2
    kept.sort((a, b) => a.e.end_idx - b.e.end_idx || TIER_RANK[b.tier] - TIER_RANK[a.tier] || a.i - b.i)
    const end = kept.reduce((m, x) => Math.max(m, x.e.end_idx), start)
    const memberIds = kept.map((x) => x.e.instance_id)
    let marks: FoldMark[]
    if (opts.isPoint) {
      marks = [{ kind: 'point', start, end: start, memberIds, tier: deepest(kept.map((x) => x.tier)) }]
    } else if (!multi) {
      marks = [{ kind: 'bar', start, end: kept[0].e.end_idx, memberIds, tier: kept[0].tier }]
    } else {
      marks = []
      for (const x of kept) {
        const last = marks[marks.length - 1]
        if (last && last.end === x.e.end_idx) {
          last.memberIds.push(x.e.instance_id)
          if (TIER_RANK[x.tier] > TIER_RANK[last.tier]) last.tier = x.tier
        } else {
          marks.push({ kind: 'cell', start: x.e.end_idx, end: x.e.end_idx, memberIds: [x.e.instance_id], tier: x.tier })
        }
      }
    }
    out.push({ key: familyKeyOf(opts.band, start), band: opts.band, start, end, multi, isPoint: opts.isPoint,
               memberIds, marks })
  }
  return out
}

function deepest(tiers: Tier[]): Tier {
  return tiers.reduce<Tier>((m, t) => (TIER_RANK[t] > TIER_RANK[m] ? t : m), 'detected')
}

/** ←/→ 的步进顺序 = 族内成员顺序。 */
export function familyMembers(family: Family): string[] {
  return [...family.memberIds]
}

// ── bracket 轨:hit 按同一规则折(hit 没有档位,不做档位筛选) ──────────────────────

export const HIT_FAMILY_PREFIX = 'hits'

export interface HitMark {
  kind: 'bar' | 'cell'
  start: number
  end: number
  hitIds: string[]
}

export interface HitFamily {
  key: string           // `hits@${start}`
  start: number
  end: number
  multi: boolean
  hitIds: string[]      // 族内顺序:(end_idx, 输入顺序)
  marks: HitMark[]
  buys: { day: number; hitIds: string[] }[]   // 买入日(升序),每天带买在这天的 hit
}

/**
 * 一次 hit 里 app 的买入日(K 线下标,升序去重),和后端评估取买点日的口径一致:
 * endNode 是 app 的 eval_meta 声明的买点 node——'node' 取 hit 里这个 node 的 event;'node.slot' 取这个 node 的 event
 * 在 slot 里的 child event;每个 event 跨度里的每一根都是买入日。没有 endNode、或在这次 hit 里解析不到,为空。
 */
export function buyDaysOf(m: HitDict, byId: ReadonlyMap<string, EventDict>, endNode: string | null | undefined): number[] {
  if (!endNode) return []
  const [nodeId, slot] = endNode.split('.')
  const own = m.node_index?.[nodeId]
  const parent = own ? byId.get(own) : undefined
  if (!parent) return []
  const evs = slot ? (parent.child_refs?.[slot] ?? []).map(id => byId.get(id)).filter((e): e is EventDict => !!e) : [parent]
  const days = new Set<number>()
  for (const e of evs) for (let i = e.start_idx; i <= e.end_idx; i++) days.add(i)
  return [...days].sort((a, b) => a - b)
}

/** hit → 族(按起点升序)。 */
export function foldHits(hits: readonly HitDict[], events: readonly EventDict[],
                         endNode: string | null | undefined): HitFamily[] {
  const byId = new Map(events.map((e) => [e.instance_id, e]))
  const groups = new Map<number, { m: HitDict; i: number }[]>()
  hits.forEach((m, i) => {
    const g = groups.get(m.start_idx)
    if (g) g.push({ m, i })
    else groups.set(m.start_idx, [{ m, i }])
  })
  const out: HitFamily[] = []
  for (const start of [...groups.keys()].sort((a, b) => a - b)) {
    const all = groups.get(start)!.sort((a, b) => a.m.end_idx - b.m.end_idx || a.i - b.i)
    const multi = all.length >= 2
    const end = all.reduce((x, y) => Math.max(x, y.m.end_idx), start)
    // bracket 一律画梳子(只有一次 hit 也是):每个终点一格,族的跨度只靠底线。hit 的跨度只是上下文(从旧平台
    // 起点到当天),整条琥珀条会被读成「整段都能买」;选中时空心框照样给出 [族起点, hit 终点]。band 的单成员整条不变。
    const marks: HitMark[] = []
    for (const { m } of all) {
      const last = marks[marks.length - 1]
      if (last && last.end === m.end_idx) last.hitIds.push(m.hit_id)
      else marks.push({ kind: 'cell', start: m.end_idx, end: m.end_idx, hitIds: [m.hit_id] })
    }
    const buyMap = new Map<number, string[]>()
    for (const { m } of all) {
      for (const d of buyDaysOf(m, byId, endNode)) {
        const g = buyMap.get(d)
        if (g) g.push(m.hit_id)
        else buyMap.set(d, [m.hit_id])
      }
    }
    const buys = [...buyMap.keys()].sort((a, b) => a - b).map((day) => ({ day, hitIds: buyMap.get(day)! }))
    out.push({ key: familyKeyOf(HIT_FAMILY_PREFIX, start), start, end, multi,
               hitIds: all.map((x) => x.m.hit_id), marks, buys })
  }
  return out
}

// ── 同一格几个成员的区分标签 ─────────────────────────────────────────────────

/** via:区分它的那个子段槽名、anchor 字段名,或 'instance_id';ref_id:它在那里引用的事件;idx:显示用的下标。 */
export interface MemberLabel { via: string; ref_id: string | null; idx: number | null }

/**
 * 一格里几个成员(同 node、跨度相同)各自的区分标签,band 的格、bracket 的 ▼ 悬停与 compare 的诊断共用。
 * ① 按第一个成员 child_refs 的键顺序逐个槽看,把每个成员这个槽里的子事件合成 [最小起点, 最大终点];
 *    成员之间不全相同就用这个槽,idx 取各自的终点;
 * ② 没有这样的槽:逐个看 anchor 字段(拓扑 edges 上的 anchor_field),值不全相同就用它,idx 取被锚事件的起点;
 * ③ 还分不开:用 instance_id 本身。
 */
export function memberLabels(memberIds: readonly string[], byId: ReadonlyMap<string, EventDict>,
                             anchorFields: readonly string[]): MemberLabel[] {
  const fallback = (): MemberLabel[] => memberIds.map((id) => ({ via: 'instance_id', ref_id: id, idx: null }))
  const evs = memberIds.map((id) => byId.get(id))
  if (memberIds.length < 2 || evs.some((e) => !e)) return fallback()
  const es = evs as EventDict[]
  for (const slot of Object.keys(es[0].child_refs ?? {})) {
    const spans = es.map((e) => {
      const kids = (e.child_refs?.[slot] ?? []).map((id) => byId.get(id)).filter((k): k is EventDict => !!k)
      if (kids.length === 0) return null
      let last = kids[0]
      for (const k of kids) if (k.end_idx > last.end_idx) last = k
      return { s: Math.min(...kids.map((k) => k.start_idx)), e: last.end_idx, ref: last.instance_id }
    })
    const sig = spans.map((x) => (x ? `${x.s}:${x.e}` : '-'))
    if (new Set(sig).size > 1) {
      return spans.map((x) => ({ via: slot, ref_id: x?.ref ?? null, idx: x?.e ?? null }))
    }
  }
  for (const f of anchorFields) {
    const vals = es.map((e) => anchorRef(e[f]))
    if (vals.every((v) => v === null)) continue
    if (new Set(vals.map((v) => v ?? '-')).size > 1) {
      return vals.map((v) => ({ via: f, ref_id: v, idx: v ? byId.get(v)?.start_idx ?? null : null }))
    }
  }
  return fallback()
}

function anchorRef(v: unknown): string | null {
  if (typeof v === 'string') return v
  if (Array.isArray(v) && typeof v[0] === 'string') return v[0]
  return null
}

/**
 * 一个 ▼(或一格 hit)背后的几次 hit 的区分标签:按拓扑 node 顺序找第一个「这几次 hit 绑定的实例不全相同」的 node,
 * 对那几个实例调 memberLabels。找不到就用 hit_id。
 */
export function hitLabels(hitIds: readonly string[], hitsById: ReadonlyMap<string, HitDict>,
                          byId: ReadonlyMap<string, EventDict>, nodeOrder: readonly string[],
                          anchorFields: readonly string[]): MemberLabel[] {
  const hs = hitIds.map((id) => hitsById.get(id))
  if (hitIds.length >= 2 && hs.every((h) => !!h)) {
    for (const node of nodeOrder) {
      const insts = hs.map((h) => h!.node_index?.[node] ?? '')
      if (insts.some((x) => !x)) continue
      if (new Set(insts).size > 1) return memberLabels(insts, byId, anchorFields)
    }
  }
  return hitIds.map((id) => ({ via: 'hit_id', ref_id: id, idx: null }))
}

/** 标签的显示文字:`step → 2024-11-22`;拿不到下标时退回引用的 id。 */
export function formatMemberLabel(l: MemberLabel, dates: readonly string[]): string {
  if (l.idx != null) return `${l.via} → ${dates[l.idx] ?? l.idx}`
  return `${l.via}: ${l.ref_id ?? '—'}`
}
