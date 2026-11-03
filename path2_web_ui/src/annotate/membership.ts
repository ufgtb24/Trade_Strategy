/**
 * 框套框的前端实现:同一张图上的框,算出每个框属于哪个框;另给「能不能手动挂上」的判断。
 *
 * 规则与后端参照实现 path2_web/annotation/membership.py 的 parents 相同,逐例通过同一份带答案的例子
 * tests/path2_web/fixtures/membership_examples.json 里的 parents 例子(tests/annotate.membership.spec.ts 读它)。
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

/** b 和 o 交叠且 o 比 b 长:o 是 b 可以手动挂上(attach)的框。 */
export function canAttach(b: NestBox, o: NestBox, days: readonly string[]): boolean {
  if (b.id === o.id) return false
  const p = pool([{ ...b, detach: false, attach: null }, { ...o, detach: false, attach: null }], days)
  const rb = p.get(b.id)!, ro = p.get(o.id)!
  return len(ro) > len(rb) && overlaps(ro, rb)
}
