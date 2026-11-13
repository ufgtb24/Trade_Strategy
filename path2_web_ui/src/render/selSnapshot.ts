/**
 * 选中的那一个 → 显示栏、选中卡、复制行要写的字(纯函数;三处只读这一份,所以写法处处一致)。
 *
 * 统一写法:一天 `YYYY-MM-DD`;起止 `起→止`(同一天只写一天);一组日子 `首…尾 ×n`(只有一天 `那天 ×1`);
 * 第几个 `k/n`;个数 `×n`;身份 = `kind node date name`(不适用的跳过);路径由外到内用 ` › ` 连。
 * 不适用的维度为 null(界面写灰 `—`);适用但是空的写 `none`(黑字,是一个取值)。
 *
 * 只有一次 hit 的买点日和那次 hit 是同一样东西:这里按那次 hit 写(kind 是 hit),那一天进 `in`。
 */
import type { EventDict, HitDict } from '../types'
import { boundEvents, familiesOf, hitDays, stackLabelTexts, type WalkEntry } from './walk'
import { mergedHit, slot, up, type Sel, type SelKind, type SelPath, type Slot, type World } from './select'
import type { WorldCtx } from './selWorld'

/** 界面上的固定词集中在这里(改名只改这一处)。 */
export const SEL_NA = '—'
export const SEL_NONE = 'none'
export const BAR_LABELS = { kind: 'kind', node: 'node', date: 'date', name: 'name', diff: 'diff', in: 'in' } as const
export const CARD_ROWS = ['buys', 'hits', 'nodes', 'family', 'feedback', 'sample', 'paired', 'level', 'failed', 'id', 'copy'] as const
export const PATH_SEP = ' › '

export interface SnapCtx {
  dates: readonly string[]
  wctx: WorldCtx
  world: World
  /** 拓扑里 node 的先后、边上的锚点字段(区别标签用) */
  nodeOrder: readonly string[]
  anchorFields: readonly string[]
  /** 一条 band 对到的用户特征名;没有为 null */
  featureOfBand: (band: string) => string | null
  feedbackOf: (id: string) => { start: string; end: string; nodes: readonly string[]; familyStart: string | null } | null
  sampleOf: (id: string) => { letter: string | null; judgment: string; date: string } | null
  boxOf: (id: string) => { feature: string | null; start: string; end: string; node: string | null } | null
}

/** 一样东西的身份:种类、对应的 node、日期、叫法(不适用为 null)。 */
export interface Identity { kind: SelKind; node: string | null; date: string | null; name: string | null }

export interface Snapshot extends Identity {
  /** 同一天叠着两个以上时,它和另几个的区别;否则 null */
  diff: string | null
  /** 路径上外面几节的身份,由外到内;最后一个就是 Esc 退到的地方 */
  in: string[]
  /** ← / → 与 ↑ / ↓ 两个键槽 */
  day: Slot
  stack: Slot
  /** Esc 这一下:`clear`,或 `up: <退到的那一节的身份>` */
  esc: string
  /** 牵出的买点日 `首…尾 ×n` */
  buys: string | null
  /** 牵出的 hit:head 是 `×n`(跨两族以上接 `families ×k`),lines 是逐个的区别 */
  hits: { head: string; lines: string[] } | null
  /** 一次 hit 的组成:每个 node 一行 `node 起→止` */
  nodes: string[] | null
  /** 结构上的那一族(起点日期) */
  family: string | null
  /** 内部编号 */
  id: string | null
  /** 复制行里股票、pattern 之后的部分 */
  copyTail: string
  /** 这一下选中的那次 hit / 那个 event(卡片的其它行按它取数);没有为 null */
  hitId: string | null
  instanceId: string | null
}

/** 拼身份串、复制行:不适用的(null)和空的(none)都跳过 */
const join = (...parts: (string | null | undefined | false)[]): string =>
  parts.filter(x => !!x && x !== SEL_NONE).join(' ')

export function identityText(i: Identity): string {
  return join(i.kind, i.node, i.date, i.name)
}

/** 键槽上的字:`into buys ×11`、`buys 1/11`;不适用为 null。 */
export function slotText(s: Slot): string | null {
  if (s.mode === 'into') return `into ${s.noun} ×${s.n}`
  if (s.mode === 'pos') return `${s.noun} ${s.k}/${s.n}`
  return null
}

export function snapshotOf(path: SelPath, c: SnapCtx): Snapshot | null {
  if (path.length === 0) return null
  const { wctx, world, dates } = c
  const d = (i: number): string => dates[i] ?? String(i)
  const span = (a: number, b: number): string => (a === b ? d(a) : `${d(a)}→${d(b)}`)
  const hitOf = (id: string): HitDict | undefined => wctx.hitsById.get(id)
  const evOf = (id: string): EventDict | undefined => wctx.byId.get(id)

  const identity = (s: Sel): Identity => {
    const base: Identity = { kind: s.kind, node: null, date: null, name: null }
    if (s.kind === 'hit_family') return { ...base, date: d(Number(s.familyKey.slice(s.familyKey.lastIndexOf('@') + 1))) }
    if (s.kind === 'buy') return { ...base, date: d(s.day) }
    if (s.kind === 'hit') { const m = hitOf(s.hitId); return { ...base, date: m ? span(m.start_idx, m.end_idx) : null } }
    if (s.kind === 'event') {
      const e = evOf(s.instanceId)
      return { ...base, node: e?.node_id ?? null, date: e ? span(e.start_idx, e.end_idx) : null }
    }
    if (s.kind === 'node') return { ...base, node: s.band, name: c.featureOfBand(s.band) }
    if (s.kind === 'feedback') {
      const f = c.feedbackOf(s.id)
      return { ...base, node: f ? (f.nodes.length ? f.nodes.join(',') : SEL_NONE) : null,
               date: f ? (f.start === f.end ? f.start : `${f.start}→${f.end}`) : null }
    }
    if (s.kind === 'sample') {
      const x = c.sampleOf(s.sampleId)
      return { ...base, date: x?.date ?? null, name: x ? join(x.letter, x.judgment) : null }
    }
    const b = c.boxOf(s.boxId)
    return { ...base, node: b?.node ?? null, date: b ? (b.start === b.end ? b.start : `${b.start}→${b.end}`) : null,
             name: b ? b.feature ?? SEL_NONE : null }
  }

  const last = path[path.length - 1]
  const merged = mergedHit(path, world)
  /** 按哪一节写:只有一次 hit 的买点日按那次 hit */
  const shown: Sel = merged ? merged.sel : last
  const outer = merged ? path : path.slice(0, -1)
  const me = identity(shown)

  const labelsOf = (entries: WalkEntry[]): string[] =>
    stackLabelTexts(entries, wctx.hitsById, wctx.byId, c.nodeOrder, c.anchorFields, dates)

  // 区别:同一天叠着的几个里它排第几
  let diff: string | null = null
  if (shown.kind === 'hit') {
    const sibs = world.members(outer)
    const i = sibs.findIndex(x => x.sel.kind === 'hit' && x.sel.hitId === shown.hitId)
    if (sibs.length >= 2 && i >= 0) {
      diff = labelsOf(sibs.map(x => ({ hitId: x.sel.kind === 'hit' ? x.sel.hitId : null, instanceId: null })))[i] || null
    }
  } else if (shown.kind === 'event') {
    const sibs = world.peers(path, 'stack')
    const i = sibs.findIndex(x => x.sel.kind === 'event' && x.sel.instanceId === shown.instanceId)
    if (sibs.length >= 2 && i >= 0) {
      diff = labelsOf(sibs.map(x => ({ hitId: null, instanceId: x.sel.kind === 'event' ? x.sel.instanceId : null })))[i] || null
      // 子段上分不出来、起点不一样时(同一天结束的几串),写它的起点
      const starts = sibs.map(x => (x.sel.kind === 'event' ? evOf(x.sel.instanceId)?.start_idx : undefined))
      const mine = starts[i]
      if (!diff && mine !== undefined && starts.some(v => v !== mine)) diff = `start→${d(mine)}`
    }
  }

  // 牵出的 hit 与买点日
  const pick = (ids: readonly string[]) => ids.map(hitOf).filter((m): m is HitDict => !!m)
  let own: HitDict[] | null = null
  if (shown.kind === 'hit_family') {
    const st = Number(shown.familyKey.slice(shown.familyKey.lastIndexOf('@') + 1))
    own = wctx.hits.filter(m => m.start_idx === st)
  } else if (shown.kind === 'feedback') own = pick(wctx.feedbacks.find(f => f.id === shown.id)?.hitIds ?? [])
  else if (shown.kind === 'event') own = wctx.using(shown.instanceId)
  else if (shown.kind === 'hit') { const m = hitOf(shown.hitId); own = m ? [m] : [] }

  let buys: string | null = null
  if (own) {
    const days = [...new Set(own.flatMap(m => hitDays(m, wctx.byId, wctx.endNode)))].sort((a, b) => a - b)
    buys = days.length === 0 ? SEL_NONE
      : days.length === 1 ? `${d(days[0])} ×1` : `${d(days[0])}…${d(days[days.length - 1])} ×${days.length}`
  }

  const countOf = (ms: readonly HitDict[]): string => {
    if (ms.length === 0) return SEL_NONE
    const fams = familiesOf(ms)
    return fams >= 2 ? `×${ms.length} families ×${fams}` : `×${ms.length}`
  }
  let hits: Snapshot['hits'] = null
  if (shown.kind === 'buy' || shown.kind === 'sample' || shown.kind === 'box') {
    const ms = world.members(path)
    const entries = ms.map(x => ({ hitId: x.sel.kind === 'hit' ? x.sel.hitId : null, instanceId: null }))
    hits = { head: countOf(pick(entries.map(x => x.hitId ?? ''))), lines: labelsOf(entries).filter(Boolean) }
  } else if (own && shown.kind !== 'hit') {
    hits = { head: countOf(own), lines: [] }
  }

  let nodes: string[] | null = null
  let family: string | null = null
  if (shown.kind === 'hit') {
    const m = hitOf(shown.hitId)
    if (m) {
      const rank = (e: EventDict) => { const i = c.nodeOrder.indexOf(e.node_id); return i < 0 ? c.nodeOrder.length : i }
      nodes = [...boundEvents(m, wctx.byId)].map(evOf).filter((e): e is EventDict => !!e)
        .sort((a, b) => rank(a) - rank(b) || a.start_idx - b.start_idx || a.end_idx - b.end_idx)
        .map(e => `${e.node_id} ${span(e.start_idx, e.end_idx)}`)
      family = d(m.start_idx)
    }
  } else if (shown.kind === 'buy') {
    const first = world.members(path)[0]
    const m = first && first.sel.kind === 'hit' ? hitOf(first.sel.hitId) : undefined
    family = m ? d(m.start_idx) : null
  } else if (shown.kind === 'feedback') family = c.feedbackOf(shown.id)?.familyStart ?? null

  const id = shown.kind === 'hit' ? shown.hitId : shown.kind === 'event' ? shown.instanceId
    : shown.kind === 'feedback' ? shown.id : shown.kind === 'sample' ? shown.sampleId
    : shown.kind === 'box' ? shown.boxId : null

  const upper = up(path, world)
  const copyTail = join(me.kind, me.node, me.date, me.name, diff,
    buys && buys !== SEL_NONE && `buys ${buys}`,
    hits && hits.head !== SEL_NONE && `hits ${hits.head}`,
    id && `[${id}]`)

  return {
    ...me, diff,
    in: outer.map(s => identityText(identity(s))),
    day: slot(path, 'day', world), stack: slot(path, 'stack', world),
    esc: upper.length ? `up: ${identityText(identity(upper[upper.length - 1]))}` : 'clear',
    buys, hits, nodes, family, id, copyTail,
    hitId: shown.kind === 'hit' ? shown.hitId : null,
    instanceId: shown.kind === 'event' ? shown.instanceId : null,
  }
}
