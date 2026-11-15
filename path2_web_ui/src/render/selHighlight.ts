/**
 * 选中后图上怎么画(纯函数,类型无关):从选中路径与 World 算出「跟它有关的是哪些」,渲染层只照这一份施加画法。
 *
 * 规律:粗框只框选中的那一个;它外面那几层(显示栏 `in` 的各节)各在自己下面画一道外层底线;跟它有关的照常
 * (并变高、方块加细边),那一边其余的画淡。图上深色的只有三种:选中的、外层的、有关的。
 * - 有关的:
 *   - 选中那一个的组成:一次 hit → 它绑定的 event 及子事件;event → 子事件(沿 child_refs 到底);
 *     样本 → 成员框;其余没有组成。
 *   - 它牵出的 hit(选中卡 `hits` 行数到的那几次),同一天叠着几次时只算一次:从选中的那一个走进那一天时
 *     ↓ 落的第一个(render/selWorld.ts 的 members 排在第一的那次;样本、框就是配对那次,从 event、反馈走进来时
 *     用到它 / 收进它的排前面,其余按族内先后)。event 被不同日子的几次 hit 用到时,每个买点日各一次。
 *   - 这些 hit 的组成。
 * - 同一层(← / → 与 ↑ / ↓ 换来换去的那些)不另外照常:它们和选中的那一个在同一行、同一条轨上,位置已经说明是同一层;
 *   是有关的才照常,否则和别的一样画淡。
 * - 画淡按边算:app 那边(hits 行、band、主图价格区 node)与用户那边(特征轨的框、▲ 与样本跨度、反馈记号)。
 *   一边里有组成或牵出的,那一边其余的才画淡;一边里一个都没有,这一边原样不动。选中的、外层的永不画淡;
 *   什么都没选中时什么都不淡;K 线与轨名不属任何一边。
 * - 合并记号(一格里并着几个)有一个照常就照常。
 *
 * 只读 hit 的 hit_id / start_idx、event 的 instance_id / child_refs 与 World 给的顺序,不认具体事件类型。
 */
import { HIT_FAMILY_PREFIX, familyKeyOf } from './fold'
import { mergedHit, type Item, type Sel, type SelPath, type World } from './select'
import { bandCells, type WorldCtx } from './selWorld'
import { BAND_MARKER_H, MARK_GROW } from './subGeometry'
import { darken } from './colors'

/** 画淡的不透明度(只此一处;用户在真页面上看过再定,待验证):app 那边、用户那边(沿用原来点样本时不相干的框)。 */
export const DIM_APP_OPACITY = 0.5
export const DIM_USER_OPACITY = 0.28

/** 画淡施加的唯一入口:这一边、这个记号淡不淡 → 不透明度(1 为照常)。 */
export function dimOpacity(side: 'app' | 'user', dim: boolean): number {
  return dim ? (side === 'app' ? DIM_APP_OPACITY : DIM_USER_OPACITY) : 1
}

/** hits 行上的一个格位:一族 × 一天(▼ 所在那一列)。 */
export interface HitSlot { familyKey: string; day: number }

export function slotKey(familyKey: string, day: number): string { return `${familyKey}|${day}` }

/** 外层底线画在谁下面(按种类分开放;买点日是它那一族那一天的格位)。 */
export interface Underlines {
  families: ReadonlySet<string>
  slots: readonly HitSlot[]
  events: ReadonlySet<string>
  feedbacks: ReadonlySet<string>
  samples: ReadonlySet<string>
  boxes: ReadonlySet<string>
}

export interface Highlight {
  /** 选中的那一个(只有一次 hit 的买点日按那次 hit);没选中为 null */
  focus: Sel | null
  /** 外层各节,由外到内 */
  outer: readonly Sel[]
  /** 选中的是买点日 / 一次 hit 时,粗框框的那个格位(一次 hit 在当前日竖线那一天) */
  focusSlot: HitSlot | null
  /** 选中的那一个由哪几次 hit 组成(侧栏 hits 列表的黑粗边):一次 hit → 自己;买点日 → 那个 ▼ 上的几次;一族 → 全族 */
  frameHits: ReadonlySet<string>
  /** 牵出、图上照常的 hit(同一天只算 ↓ 第一个;侧栏 hits 列表的左蓝条;hits 行并着它的那一格变高、加细边) */
  ledHits: ReadonlySet<string>
  /** app 那边照常的 event:组成、选中与外层的 event */
  appEvents: ReadonlySet<string>
  /** app 那边「有关的」event:选中的那一个(是 event 时)、它的组成、牵出的 hit 的组成(不含外层本身);
   *  记号(三角、格、条、主图价格点)在这些上竖直放大(只在 in_hit 档),格、条加细边 */
  appRelated: ReadonlySet<string>
  /** app 那边照常的 hit:牵出的、选中的 */
  appHits: ReadonlySet<string>
  /** hits 行底线照常的族:选中、外层的一族(行里的格与 ▼ 另按牵出的 hit、选中与外层的买点日算) */
  appFamilies: ReadonlySet<string>
  /** hits 行照常的格位(slotKey):选中、外层的买点日 */
  appSlots: ReadonlySet<string>
  /** 用户那边照常的框、样本、反馈:组成(成员框)、选中与外层的 */
  userBoxes: ReadonlySet<string>
  userSamples: ReadonlySet<string>
  userFeedbacks: ReadonlySet<string>
  /** 这一边其余的画不画淡 */
  dimApp: boolean
  dimUser: boolean
  under: Underlines
  /** 选中的 event 在当前档位、显隐下画不出来时它所在的 band(轨名旁挂 hidden 并框住);否则 null */
  hiddenBand: string | null
}

const EMPTY: ReadonlySet<string> = new Set()

export const NO_HIGHLIGHT: Highlight = {
  focus: null, outer: [], focusSlot: null, frameHits: EMPTY, ledHits: EMPTY,
  appEvents: EMPTY, appRelated: EMPTY, appHits: EMPTY, appFamilies: EMPTY, appSlots: EMPTY,
  userBoxes: EMPTY, userSamples: EMPTY, userFeedbacks: EMPTY, dimApp: false, dimUser: false,
  under: { families: EMPTY, slots: [], events: EMPTY, feedbacks: EMPTY, samples: EMPTY, boxes: EMPTY },
  hiddenBand: null,
}

export interface HighlightCtx {
  world: World
  wctx: Pick<WorldCtx, 'hits' | 'hitsById' | 'byId' | 'bound' | 'bandOf' | 'bandFamilies'>
  /** 样本的成员框(编号);不给时样本没有组成 */
  memberBoxes?: (sampleId: string) => readonly string[]
}

const hitIdOf = (it: Item | undefined): string | null => (it && it.sel.kind === 'hit' ? it.sel.hitId : null)

export function highlightOf(path: SelPath, c: HighlightCtx): Highlight {
  if (path.length === 0) return NO_HIGHLIGHT
  const { world, wctx } = c
  const merged = mergedHit(path, world)
  const focus: Sel = merged ? merged.sel : path[path.length - 1]
  const outer: Sel[] = merged ? [...path] : path.slice(0, -1)

  const famOfHit = (hitId: string | null): string | null => {
    const m = hitId ? wctx.hitsById.get(hitId) : undefined
    return m ? familyKeyOf(HIT_FAMILY_PREFIX, m.start_idx) : null
  }
  /** 一个买点日的格位:那个 ▼ 是 ↓ 第一个那次所在的那一族 */
  const slotOfBuy = (parent: SelPath, buy: Sel): HitSlot | null => {
    if (buy.kind !== 'buy') return null
    const fam = famOfHit(hitIdOf(world.members([...parent, buy])[0]))
    return fam ? { familyKey: fam, day: buy.day } : null
  }

  // ── 组成(只往下找) ──
  const appComp = new Set<string>()
  const userComp = new Set<string>()
  const descend = (id: string, out: Set<string>): void => {
    const stack = [...childIds(id)]
    while (stack.length) {
      const x = stack.pop()!
      if (out.has(x)) continue
      out.add(x)
      stack.push(...childIds(x))
    }
  }
  function childIds(id: string): string[] {
    const out: string[] = []
    for (const ids of Object.values(wctx.byId.get(id)?.child_refs ?? {})) if (Array.isArray(ids)) out.push(...ids)
    return out
  }
  const cellsCache = new Map<string, ReturnType<typeof bandCells>>()
  const cellsOf = (band: string) => {
    let cs = cellsCache.get(band)
    if (!cs) { cs = bandCells(wctx.bandFamilies(band)); cellsCache.set(band, cs) }
    return cs
  }
  if (focus.kind === 'hit') for (const id of wctx.bound(focus.hitId)) appComp.add(id)
  else if (focus.kind === 'event') descend(focus.instanceId, appComp)
  else if (focus.kind === 'sample') for (const id of c.memberBoxes?.(focus.sampleId) ?? []) userComp.add(id)

  // ── 牵出的 hit:同一天只算 ↓ 第一个 ──
  const led: string[] = []
  if (focus.kind === 'hit') led.push(focus.hitId)
  else if (focus.kind === 'buy' || focus.kind === 'sample' || focus.kind === 'box') {
    const id = hitIdOf(world.members(path)[0])
    if (id) led.push(id)
  } else if (focus.kind === 'hit_family' || focus.kind === 'event' || focus.kind === 'feedback') {
    for (const b of world.inside(path, 'day')) {
      const id = hitIdOf(world.members([...path, b.sel])[0])
      if (id && !led.includes(id)) led.push(id)
    }
  }
  const ledHits = new Set(led)
  for (const id of led) for (const e of wctx.bound(id)) appComp.add(e)

  // ── 选中的那一个由哪几次 hit 组成(侧栏黑粗边) ──
  const frameHits = new Set<string>()
  if (focus.kind === 'hit') frameHits.add(focus.hitId)
  else if (focus.kind === 'buy') for (const it of world.members(path)) { const id = hitIdOf(it); if (id) frameHits.add(id) }
  else if (focus.kind === 'hit_family') {
    const st = Number(focus.familyKey.slice(focus.familyKey.lastIndexOf('@') + 1))
    for (const m of wctx.hits) if (m.start_idx === st) frameHits.add(m.hit_id)
  }

  const focusSlot: HitSlot | null = focus.kind === 'hit'
    ? (() => { const fam = famOfHit(focus.hitId); return fam ? { familyKey: fam, day: focus.day } : null })()
    : focus.kind === 'buy' ? slotOfBuy(path.slice(0, -1), focus) : null

  const appRelated = new Set<string>(appComp)
  if (focus.kind === 'event') appRelated.add(focus.instanceId)

  // ── 选中与外层:照常,只亮记号本身(同一层不另外照常,是有关的才照常) ──
  const appEvents = new Set<string>(appComp)
  const appHits = new Set<string>(ledHits)
  const appFamilies = new Set<string>()
  const appSlots = new Set<string>()
  const userBoxes = new Set<string>(userComp)
  const userSamples = new Set<string>()
  const userFeedbacks = new Set<string>()
  const mark = (s: Sel, parent: SelPath): void => {
    switch (s.kind) {
      case 'hit_family': appFamilies.add(s.familyKey); break
      case 'buy': { const sl = slotOfBuy(parent, s); if (sl) appSlots.add(slotKey(sl.familyKey, sl.day)); break }
      case 'hit': appHits.add(s.hitId); break
      case 'event': appEvents.add(s.instanceId); break
      case 'feedback': userFeedbacks.add(s.id); break
      case 'sample': userSamples.add(s.sampleId); break
      case 'box': userBoxes.add(s.boxId); break
    }
  }
  for (let i = 0; i < path.length; i++) mark(path[i], path.slice(0, i))
  if (merged) mark(merged.sel, path)
  if (focusSlot) appSlots.add(slotKey(focusSlot.familyKey, focusSlot.day))

  // ── 外层底线 ──
  const under = {
    families: new Set<string>(), slots: [] as HitSlot[], events: new Set<string>(),
    feedbacks: new Set<string>(), samples: new Set<string>(), boxes: new Set<string>(),
  }
  outer.forEach((s, i) => {
    switch (s.kind) {
      case 'hit_family': under.families.add(s.familyKey); break
      case 'buy': { const sl = slotOfBuy(outer.slice(0, i), s); if (sl) under.slots.push(sl); break }
      case 'event': under.events.add(s.instanceId); break
      case 'feedback': under.feedbacks.add(s.id); break
      case 'sample': under.samples.add(s.sampleId); break
      case 'box': under.boxes.add(s.boxId); break
      case 'hit': break   // 一次 hit 不会在外层
    }
  })

  let hiddenBand: string | null = null
  if (focus.kind === 'event') {
    const ev = wctx.byId.get(focus.instanceId)
    if (ev) {
      const band = wctx.bandOf(ev)
      if (!cellsOf(band).some(x => x.members.some(m => m.id === focus.instanceId))) hiddenBand = band
    }
  }

  return {
    focus, outer, focusSlot, frameHits, ledHits,
    appEvents, appRelated, appHits, appFamilies, appSlots, userBoxes, userSamples, userFeedbacks,
    dimApp: ledHits.size > 0 || appComp.size > 0,
    dimUser: userComp.size > 0,
    under, hiddenBand,
  }
}

// ── 渲染层问的几句(每个记号淡不淡) ──

/**
 * hits 行的一格、一个 ▼:并着这几次 hit;days 是它借来照常的格位(▼ 给自己那天;格给同一列、
 * 并着同一次 hit 的 ▼ 那天,没有就不给)。一族选中或在外层时,照常的是它那一行的底线(familyLineDim),
 * 行里的格与 ▼ 仍按牵出的 hit 与选中、外层的买点日算(别的买点日是同一层,不另外照常)。
 */
export function hitMarkDim(h: Highlight, familyKey: string, hitIds: readonly string[], days: readonly number[] = []): boolean {
  if (!h.dimApp) return false
  if (hitIds.some(id => h.appHits.has(id))) return false
  return !days.some(d => h.appSlots.has(slotKey(familyKey, d)))
}

/** hits 行一族的底线(并着全族):这一族选中或在外层时照常,否则同 hitMarkDim。 */
export function familyLineDim(h: Highlight, familyKey: string, hitIds: readonly string[], days: readonly number[] = []): boolean {
  if (!h.dimApp || h.appFamilies.has(familyKey)) return false
  return hitMarkDim(h, familyKey, hitIds, days)
}

/** band 上的一个记号(格、整条、点)、一族的底线、主图价格区的一个 node 记号:并着这几个 event。 */
export function eventMarkDim(h: Highlight, memberIds: readonly string[]): boolean {
  return h.dimApp && !memberIds.some(id => h.appEvents.has(id))
}

/** 点记号(band 上的三角、主图价格点)竖直放大的倍数:只放大高、不放大宽(窄格下不和相邻的挤在一起;会话默认,待验证) */
export const POINT_ENLARGE_Y = 1.4
/** 格、条竖直放大的倍数(格高 BAND_MARKER_H 加上 render/subGeometry.ts 的 MARK_GROW) */
export const MARK_ENLARGE_Y = (BAND_MARKER_H + MARK_GROW) / BAND_MARKER_H

/**
 * 一个记号(并着这几个 event)竖直放大几倍:有一个是「有关的」就放大,否则 1。
 * 只在 in_hit 档放大:两个灰档里格高、三角大小表示档位,有关的再放大会和别的档位一样高。
 */
export function markScaleY(h: Highlight, memberIds: readonly string[], shape: 'point' | 'mark', level: string): number {
  if (level !== 'in_hit' || !memberIds.some(id => h.appRelated.has(id))) return 1
  return shape === 'point' ? POINT_ENLARGE_Y : MARK_ENLARGE_Y
}

/**
 * hits 行的一格、一个 ▼、格上的个数(并着这几次 hit):并着牵出的 hit(含选中的那一次)就变高。
 * hits 行不表示档位,所以任何档都变高(band 上的只在 in_hit 档,见 markScaleY)。
 */
export function hitMarkGrows(h: Highlight, hitIds: readonly string[]): boolean {
  return hitIds.some(id => h.ledHits.has(id))
}

/** band 上的格、条(并着这几个 event)是不是有关的方块:有一个是有关的就是(加细边;任何档都加)。 */
export function isRelatedMark(h: Highlight, memberIds: readonly string[]): boolean {
  return memberIds.some(id => h.appRelated.has(id))
}

/**
 * 有关的方块的细边:1px、向里贴着方块画(不外扩;粗框外扩、隔一道缝,一个贴边一个隔开,形状不同),
 * 颜色是方块本色深一档(不用粗框的近黑色,近黑色只留给选中);方块窄于 RELATED_EDGE_MIN_W 时不画
 * (左右两道边会把格子吃掉)。宽度门槛与深浅是会话默认,待验证。
 */
export const RELATED_EDGE_W = 1
export const RELATED_EDGE_MIN_W = 6
export const RELATED_EDGE_DARKEN = 0.35
export function relatedEdgeColor(fill: string): string {
  return darken(fill, RELATED_EDGE_DARKEN)
}

/**
 * 一个方块(x、y、宽、高,像素)加不加细边:加时把方块往里收半个边宽、描 1px 边,外沿仍是原来的范围。
 * 返回 rect 的 shape 与要并进 style 的描边;不加时原样返回、不描边。
 */
export function relatedEdgeRect(shape: { x: number; y: number; width: number; height: number }, fill: unknown, on: boolean):
    { shape: { x: number; y: number; width: number; height: number }; stroke: Record<string, unknown> } {
  if (!on || typeof fill !== 'string' || shape.width < RELATED_EDGE_MIN_W) return { shape, stroke: {} }
  const half = RELATED_EDGE_W / 2
  return {
    shape: { x: shape.x + half, y: shape.y + half, width: shape.width - RELATED_EDGE_W, height: shape.height - RELATED_EDGE_W },
    stroke: { stroke: relatedEdgeColor(fill), lineWidth: RELATED_EDGE_W },
  }
}

/** 用户那边的一个框、样本(▲ 与跨度)、反馈记号。 */
export function userMarkDim(h: Highlight, kind: 'box' | 'sample' | 'feedback', id: string): boolean {
  if (!h.dimUser) return false
  const set = kind === 'box' ? h.userBoxes : kind === 'sample' ? h.userSamples : h.userFeedbacks
  return !set.has(id)
}

/** 选中的那一个是不是这一样东西(粗框画在它身上)。 */
export function isFocus(h: Highlight, kind: Sel['kind'], id: string): boolean {
  const f = h.focus
  if (!f || f.kind !== kind) return false
  switch (f.kind) {
    case 'hit_family': return f.familyKey === id
    case 'event': return f.instanceId === id
    case 'feedback': return f.id === id
    case 'sample': return f.sampleId === id
    case 'box': return f.boxId === id
    case 'hit': return f.hitId === id
    case 'buy': return String(f.day) === id
  }
}
