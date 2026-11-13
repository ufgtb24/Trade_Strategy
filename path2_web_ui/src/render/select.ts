/**
 * 选中与按键走动(纯函数,类型无关)。
 *
 * 选中的是一条路径:最外一节 → 当前那一节(`SelPath`)。最后一节是「选中的那一个」,前面几节是它属于谁
 * (也就是 Esc 一层层退到的地方)。能被选中的只有八种东西:hit 的一族、买点日、一次 hit、event、node、反馈、样本、框。
 *
 * 两根轴、一个判断:
 * - 跨天(`day`,← / →,当前日竖线会动);同一天(`stack`,↑ / ↓,竖线不动)。
 * - 每根轴只看两个数——选中的东西在这根轴上「里面装着几个」、「同一层有几个(含自己)」:
 *     里面 ≥2            → 进去,在它们之间走;
 *     否则同一层 ≥2      → 留在本层,换到旁边那个(到头停);
 *     否则里面恰有 1 个  → 进那一个;
 *     都没有             → 不响应。
 * `step`、`slot` 只按这两个数分支,从不看最后一节是哪一种;「里面装着什么」「同一层是谁」由 `World` 回答
 * (render/selWorld.ts 从分析结果现算)。
 *
 * 叠在某一天里的一个(一次 hit:它在上一节的 `members` 里)跨天走时,同一层取上一节的同一层:带着它换到旁边
 * 那一天,落在那里最像的一个;那边没有可落的,就落在那一天(样本、框)本身。
 */

export type Axis = 'day' | 'stack'

/** 路径上的一节。day 都是 K 线下标。 */
export type Sel =
  | { kind: 'hit_family'; familyKey: string }
  | { kind: 'buy'; day: number }
  | { kind: 'hit'; hitId: string; day: number }
  | { kind: 'event'; instanceId: string }
  | { kind: 'node'; band: string }
  | { kind: 'feedback'; id: string }
  | { kind: 'sample'; sampleId: string }
  | { kind: 'box'; boxId: string }

export type SelKind = Sel['kind']
export type SelPath = readonly Sel[]

/** 一个可以走到的东西:那一节,和当前日竖线该落的那根 K 线(不带日子的为 null:族、反馈、node)。 */
export interface Item { sel: Sel; day: number | null }

/**
 * 「里面装着什么、同一层是谁」的回答者。都以路径的最后一节为准,前面几节给出它属于谁。
 * - inside:在这根轴上里面装着的一串,已排好序。只有一次 hit 的买点日和那次 hit 是同一样东西,
 *   所以它在 `stack` 轴上回答空(不是「装着一个」)。
 * - members:叠在最后一节那一天里的全部(买点日 → 这天的几次 hit;样本、框 → 那天在场的几次);别的为空。
 *   和 inside(…,'stack') 的差别只在「只有一次的买点日」:这里照实给出那一次。
 * - peers:这根轴上同一层的同种东西,含最后一节自己,已排好序;已替调用方在每个位置挑好
 *   「和当前最像的那个」(event 沿 band 换时每格取同起点的)。叠着的成员的同一层由 step 用 members 处理,这里不管。
 * - similar:cands 里和 cur 最像的那个的下标(一次 hit 换天时落同一种切法)。
 * - lineDay:当前日竖线在哪根 K 线上;没有为 null。
 */
export interface World {
  inside(path: SelPath, axis: Axis): Item[]
  members(path: SelPath): Item[]
  peers(path: SelPath, axis: Axis): Item[]
  similar(cands: readonly Item[], cur: Sel): number
  lineDay(): number | null
}

/** 键槽里被走的那一组的名字(复数名词)。界面名集中在这里,改名只改这一处。 */
export const SLOT_NOUN: Record<SelKind, string> = {
  hit_family: 'hit_families', buy: 'buys', hit: 'hits', event: 'events', node: 'nodes',
  feedback: 'feedbacks', sample: 'samples', box: 'boxes',
}

export function selKey(s: Sel): string {
  switch (s.kind) {
    case 'hit_family': return `hit_family:${s.familyKey}`
    case 'buy': return `buy:${s.day}`
    case 'hit': return `hit:${s.hitId}@${s.day}`
    case 'event': return `event:${s.instanceId}`
    case 'node': return `node:${s.band}`
    case 'feedback': return `feedback:${s.id}`
    case 'sample': return `sample:${s.sampleId}`
    case 'box': return `box:${s.boxId}`
  }
}

export function sameSel(a: Sel | null | undefined, b: Sel | null | undefined): boolean {
  return !!a && !!b && selKey(a) === selKey(b)
}

export function samePath(a: SelPath, b: SelPath): boolean {
  return a.length === b.length && a.every((s, i) => sameSel(s, b[i]))
}

/** 一次 hit 不带日子比(同一次 hit 停在不同买点日上算同一个成员)。 */
function sameMember(a: Sel, b: Sel): boolean {
  if (a.kind === 'hit' && b.kind === 'hit') return a.hitId === b.hitId
  return sameSel(a, b)
}

/** 这一节在这根轴上的同一层:items 含它自己,index 是它排第几;lifted 时 items 是上一节的同一层。 */
interface Level { items: Item[]; index: number; lifted: boolean }

function levelOf(path: SelPath, axis: Axis, world: World): Level {
  const cur = path[path.length - 1]
  const parentPath = path.slice(0, -1)
  const sibs = parentPath.length ? world.members(parentPath) : []
  const stacked = sibs.findIndex(it => sameMember(it.sel, cur))
  if (stacked >= 0) {
    if (axis === 'stack') return { items: sibs, index: stacked, lifted: false }
    const up = levelOf(parentPath, 'day', world)
    return { items: up.items, index: up.index, lifted: true }
  }
  const items = world.peers(path, axis)
  return { items, index: items.findIndex(it => sameSel(it.sel, cur)), lifted: false }
}

/** 进去落哪一个:同一天 → 第一个 / 最后一个;跨天 → 竖线那天本身有就落它,否则按键方向最近的,那边没有取另一边最近的。 */
function enterIndex(ins: readonly Item[], axis: Axis, dir: -1 | 1, line: number | null): number {
  if (axis === 'stack' || line === null) return dir > 0 ? 0 : ins.length - 1
  const exact = ins.findIndex(it => it.day === line)
  if (exact >= 0) return exact
  const right = ins.findIndex(it => it.day !== null && it.day > line)
  let left = -1
  for (let i = ins.length - 1; i >= 0; i--) { const d = ins[i].day; if (d !== null && d < line) { left = i; break } }
  if (dir > 0) return right >= 0 ? right : (left >= 0 ? left : 0)
  return left >= 0 ? left : (right >= 0 ? right : ins.length - 1)
}

export type StepAction = 'into' | 'move' | 'none'

export interface StepResult {
  /** 走完之后的路径(没动时就是原来那条) */
  path: SelPath
  /** 这一下属于哪一种;到头没动也算 'move' */
  action: StepAction
  /** 路径变没变 */
  moved: boolean
}

/** 按一下键:axis 是哪根轴,dir 是往前(-1)还是往后(+1)。没有选中时不响应。 */
export function step(path: SelPath, axis: Axis, dir: -1 | 1, world: World): StepResult {
  if (path.length === 0) return { path, action: 'none', moved: false }
  const ins = world.inside(path, axis)
  const enter = (): StepResult => {
    const pick = ins[enterIndex(ins, axis, dir, world.lineDay())]
    return { path: [...path, pick.sel], action: 'into', moved: true }
  }
  if (ins.length >= 2) return enter()
  const lv = levelOf(path, axis, world)
  if (lv.items.length >= 2 && lv.index >= 0) {
    const ti = lv.index + dir
    if (ti < 0 || ti >= lv.items.length) return { path, action: 'move', moved: false }
    const target = lv.items[ti]
    if (!lv.lifted) return { path: [...path.slice(0, -1), target.sel], action: 'move', moved: true }
    const parentPath = [...path.slice(0, -2), target.sel]
    const cands = world.members(parentPath)
    if (cands.length === 0) return { path: parentPath, action: 'move', moved: true }
    const pick = cands[Math.max(0, world.similar(cands, path[path.length - 1]))]
    return { path: [...parentPath, pick.sel], action: 'move', moved: true }
  }
  if (ins.length === 1) return enter()
  return { path, action: 'none', moved: false }
}

/** 键槽上写什么:会进去(into,×n)、在同一层的第几个(pos,k/n)、还是不适用(none)。和 step 同一份判断。 */
export interface Slot {
  mode: 'into' | 'pos' | 'none'
  /** 被走的那一组的名字(SLOT_NOUN);none 时为空串 */
  noun: string
  k: number | null
  n: number
}

export function slot(path: SelPath, axis: Axis, world: World): Slot {
  const none: Slot = { mode: 'none', noun: '', k: null, n: 0 }
  if (path.length === 0) return none
  const ins = world.inside(path, axis)
  const into = (): Slot => ({ mode: 'into', noun: SLOT_NOUN[ins[0].sel.kind], k: null, n: ins.length })
  if (ins.length >= 2) return into()
  const lv = levelOf(path, axis, world)
  if (lv.items.length >= 2 && lv.index >= 0) {
    return { mode: 'pos', noun: SLOT_NOUN[lv.items[lv.index].sel.kind], k: lv.index + 1, n: lv.items.length }
  }
  if (ins.length === 1) return into()
  return none
}

/** 最后一节是只有一次 hit 的买点日时,那一次(显示、复制都按这次 hit 写);否则 null。 */
export function mergedHit(path: SelPath, world: World): Item | null {
  if (path.length === 0 || path[path.length - 1].kind !== 'buy') return null
  const ms = world.members(path)
  return ms.length === 1 ? ms[0] : null
}

/**
 * Esc 退一层:弹掉最后一节。露出来的是只有一次 hit 的买点日、而刚弹掉的正是那一次时,那一天和它是同一样东西,
 * 再弹一层(否则这一下看起来什么都没变)。
 */
export function up(path: SelPath, world: World): SelPath {
  if (path.length === 0) return path
  const popped = path[path.length - 1]
  const rest = path.slice(0, -1)
  const m = mergedHit(rest, world)
  if (m && sameMember(m.sel, popped)) return rest.slice(0, -1)
  return rest
}
