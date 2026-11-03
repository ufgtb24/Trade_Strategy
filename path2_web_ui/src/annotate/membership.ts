/**
 * 框套框的前端实现:同一张图上的框,算出每个框属于哪个框、成员框排成的树、骨架与 dup。
 *
 * 规则与后端参照实现 path2_web/annotation/membership.py 相同,两边逐例通过同一份带答案的例子
 * tests/path2_web/fixtures/membership_examples.json(tests/annotate.membership.spec.ts 读它)。
 *
 * - 一个日期的序号 = days 里比它早的交易日有几个;先后、包住、交叠、长短都按序号比(「隔几根」是 K 线根数)。
 * - 框的长度 = 终点序号 − 起点序号;框的先后:起点早的在前,同起点长的在前,再按编号(字符串比)。
 * - 框套框(parents):
 *   1. 有 detach:不属于任何框;
 *   2. 有 attach,且那个框在这组里、比它长、和它交叠:属于那个框(否则这条 attach 不算数,照第 3 条);
 *   3. 否则属于包住它的框里最短的那个;一样短取起点早的,再一样取编号小的。
 *   「o 包住 b」= b 的起止都落在 o 里且 o 更长;detach 和 attach 同时出现报 attach_and_detach。
 */

export interface NestBox {
  id: string
  feature: string | null
  start: string
  end: string
  detach?: boolean
  attach?: string | null
}

export class MembershipInputError extends Error {
  constructor(readonly code: string, message: string) { super(message) }
}

interface Ranked {
  id: string
  feature: string | null
  start: string
  end: string
  s: number
  e: number
  attach: string | null
  detach: boolean
}

/** 日期的序号:days(升序)里比它早的交易日有几个。 */
export function rankOf(days: readonly string[], date: string): number {
  let lo = 0, hi = days.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (days[mid] < date) lo = mid + 1
    else hi = mid
  }
  return lo
}

const len = (b: Ranked) => b.e - b.s
const overlaps = (a: Ranked, b: Ranked) => a.s <= b.e && b.s <= a.e
const contains = (o: Ranked, b: Ranked) => o.s <= b.s && b.e <= o.e && len(o) > len(b)

function byOrder(a: Ranked, b: Ranked): number {
  return a.s - b.s || b.e - a.e || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
}

function pool(boxes: readonly NestBox[], days: readonly string[]): Map<string, Ranked> {
  const out = new Map<string, Ranked>()
  for (const b of boxes) {
    if (b.detach && b.attach != null) {
      throw new MembershipInputError('attach_and_detach', `box ${b.id}: detach and attach are exclusive`)
    }
    out.set(b.id, {
      id: b.id, feature: b.feature, start: b.start, end: b.end,
      s: rankOf(days, b.start), e: rankOf(days, b.end),
      attach: b.attach ?? null, detach: !!b.detach,
    })
  }
  return out
}

function parentIn(b: Ranked, p: Map<string, Ranked>): string | null {
  if (b.detach) return null
  const o = b.attach != null ? p.get(b.attach) : undefined
  if (o && len(o) > len(b) && overlaps(o, b)) return o.id
  let best: Ranked | null = null
  for (const c of p.values()) {
    if (!contains(c, b)) continue
    if (!best || len(c) < len(best) || (len(c) === len(best) && (c.s < best.s || (c.s === best.s && c.id < best.id)))) best = c
  }
  return best ? best.id : null
}

/** 框套框:每个框属于这组框里的哪个框(框编号 → 所属框编号,不属于任何框为 null)。 */
export function parents(boxes: readonly NestBox[], days: readonly string[]): Record<string, string | null> {
  const p = pool(boxes, days)
  const out: Record<string, string | null> = {}
  for (const [id, b] of p) out[id] = parentIn(b, p)
  return out
}

/** 框按先后排好的编号(起点早的在前,同起点长的在前,再按编号)。 */
export function orderedIds(boxes: readonly NestBox[], days: readonly string[]): string[] {
  return [...pool(boxes, days).values()].sort(byOrder).map(b => b.id)
}

/** b 和 o 交叠且 o 比 b 长:o 是 b 可以手动挂上(attach)的框。 */
export function canAttach(b: NestBox, o: NestBox, days: readonly string[]): boolean {
  if (b.id === o.id) return false
  const p = pool([{ ...b, detach: false, attach: null }, { ...o, detach: false, attach: null }], days)
  const rb = p.get(b.id)!, ro = p.get(o.id)!
  return len(ro) > len(rb) && overlaps(ro, rb)
}

export interface TreeNode { box: string; kids: TreeNode[] }

/** 成员框按框套框排成树,顶层和每层子框都按框的先后排;归属只在这组框之间找。 */
export function memberTree(members: Iterable<string>, boxes: readonly NestBox[], days: readonly string[]): TreeNode[] {
  const wanted = new Set(members)
  const p = pool(boxes.filter(b => wanted.has(b.id)), days)
  const kids = new Map<string | null, Ranked[]>()
  for (const b of [...p.values()].sort(byOrder)) {
    const k = parentIn(b, p)
    if (!kids.has(k)) kids.set(k, [])
    kids.get(k)!.push(b)
  }
  const node = (b: Ranked): TreeNode => ({ box: b.id, kids: (kids.get(b.id) ?? []).map(node) })
  return (kids.get(null) ?? []).map(node)
}

/** 骨架:树顶层框的特征编号按先后排(还没标特征的为 null)。 */
export function skeleton(members: Iterable<string>, boxes: readonly NestBox[], days: readonly string[]): (string | null)[] {
  const feature = new Map(boxes.map(b => [b.id, b.feature]))
  return memberTree(members, boxes, days).map(n => feature.get(n.box) ?? null)
}

/** 树顶层出现两次以上的特征编号,按第一次出现的先后排;还没标特征的不算。 */
export function dupFeatures(members: Iterable<string>, boxes: readonly NestBox[], days: readonly string[]): string[] {
  const tops = skeleton(members, boxes, days)
  return tops.filter((f, i): f is string =>
    f !== null && tops.indexOf(f) === i && tops.filter(x => x === f).length > 1)
}
