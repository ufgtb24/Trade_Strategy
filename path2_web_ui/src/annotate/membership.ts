/**
 * 框套框、成员框、骨架、成员链空槽的前端实现:同一张图上的框和样本,算出框的归属、样本的成员框、
 * 成员框树与骨架、dup,以及成员链上的空槽。界面为了交互流畅在本地算,结果必须和会话读标注时用的参照实现一致。
 *
 * 规则与后端参照实现 path2_web/annotation/membership.py 相同,逐例通过同一份带答案的例子
 * tests/path2_web/fixtures/membership_examples.json 的全部例子(tests/annotate.membership.spec.ts 读它);
 * 规则的完整说明在参照实现的模块说明里,这里只列要点。
 *
 * - 一个日期的序号 = days 里比它早的交易日有几个;先后、包住、交叠、长短、gap、near 都按序号比
 *   (「隔几根」是 K 线根数);因果(框在样本日当天或之前结束)按日期字符串比 end <= date。
 * - 框的长度 = 终点序号 − 起点序号;框的先后:起点早的在前,同起点长的在前,再按编号(字符串比)。
 * - 框套框(parents):
 *   1. 有 detach:不属于任何框;
 *   2. 有 attach,且那个框在这组里、比它长、和它交叠:属于那个框(否则这条 attach 不算数,照第 3 条);
 *   3. 否则属于包住它的框里最短的那个;一样短取起点早的,再一样取编号小的。
 *   「o 包住 b」= b 的起止都落在 o 里且 o 更长;detach 和 attach 同时出现报 attach_and_detach。
 * - 成员框(sampleMembers):新放的样本 = 推断(候选只取样本日当天或之前结束的框,从样本日往前,终点离边界
 *   gap 根以内就并进来,边界更新为成员框里最早的起点,直到没有新增);已有成员框的样本,存下的就是冻结的那份,
 *   它是当前样本期间新画的框里推断会收的并进来(只加不踢);手动点进点出最后生效;最后只留在样本日当天或之前
 *   结束的框。
 * - 骨架(skeleton):成员框树顶层框的特征编号按先后排;dup:顶层出现两次以上的特征(没标特征的不算)。
 * - 空槽(emptySlots):特征在同一 pattern(unsorted 自成一组)的样本成员框里出现过、既不是这个样本也不是
 *   同图同 pattern 别的样本的成员框;在样本日当天或之前结束且终点离样本范围起点 near 根以内的是 unclaimed
 *   (画了没收),起点不晚于样本日、终点晚于样本日的是 crosses_sample_date(跨过样本日收不进)。
 *
 * gap、near 不在这里设默认值:调用方传入后端读路由带出的那一对(GET /annotations 的 membership),
 * 和参照实现读的是同一处设定。
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

// ── 成员框 ─────────────────────────────────────────────────────────────

export const UNCLAIMED = 'unclaimed'
export const CROSSES_SAMPLE_DATE = 'crosses_sample_date'
export type SlotReason = typeof UNCLAIMED | typeof CROSSES_SAMPLE_DATE

/** 算成员框用到的样本:样本日、pattern(null 为 unsorted)、存下的成员框。 */
export interface MemberSample { id: string; date: string; pattern: string | null; members: readonly string[] }
export interface MemberChart { symbol: string; boxes: readonly NestBox[]; samples: readonly MemberSample[] }

const byOrder = (a: Ranked, b: Ranked) => a.s - b.s || b.e - a.e || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
const ordered = (bs: Iterable<Ranked>) => [...bs].sort(byOrder)

/** 成员框推断:候选只取样本日当天或之前结束的框,从样本日往前,终点离边界 gap 根以内的并进来,直到没有新增。 */
function infer(date: string, p: Map<string, Ranked>, days: readonly string[], gap: number): Set<string> {
  const candidates = [...p.values()].filter(b => b.end <= date)
  const members = new Set<string>()
  let edge = rankOf(days, date)
  for (;;) {
    const joined = candidates.filter(b => !members.has(b.id) && b.e >= edge - gap)
    if (!joined.length) return members
    for (const b of joined) members.add(b.id)
    edge = Math.min(...candidates.filter(b => members.has(b.id)).map(b => b.s))
  }
}

export interface MemberOpts {
  /** 存下的成员框;null / 不给 = 新放的样本 */
  stored?: readonly string[] | null
  /** 它是当前样本期间新画的框 */
  newBoxes?: Iterable<string>
  /** 手动点进点出:框编号 → true 收进 / false 拿掉 */
  manual?: Record<string, boolean> | null
  gap: number
}

/** 一个样本现在的成员框编号,按框的先后排(规则见模块说明)。boxes 是这只股票上的全部框。 */
export function sampleMembers(date: string, boxes: readonly NestBox[], days: readonly string[], o: MemberOpts): string[] {
  const p = pool(boxes, days)
  const auto = infer(date, p, days, o.gap)
  const fresh = new Set(o.newBoxes ?? [])
  const chosen = o.stored == null ? new Set(auto)
    : new Set([...o.stored, ...[...auto].filter(id => fresh.has(id))])
  for (const [id, keep] of Object.entries(o.manual ?? {})) {
    if (keep) chosen.add(id)
    else chosen.delete(id)
  }
  return ordered(p.values()).filter(b => chosen.has(b.id) && b.end <= date).map(b => b.id)
}

export interface TreeNode { box: string; kids: TreeNode[] }

/** 成员框按框套框排成树,顶层和每层子框都按框的先后排;归属只在成员框之间找,不在 boxes 里的编号不计。 */
export function memberTree(members: Iterable<string>, boxes: readonly NestBox[], days: readonly string[]): TreeNode[] {
  const wanted = new Set(members)
  const p = pool(boxes.filter(b => wanted.has(b.id)), days)
  const kids = new Map<string | null, Ranked[]>()
  for (const b of ordered(p.values())) {
    const par = parentIn(b, p)
    if (!kids.has(par)) kids.set(par, [])
    kids.get(par)!.push(b)
  }
  const node = (b: Ranked): TreeNode => ({ box: b.id, kids: (kids.get(b.id) ?? []).map(node) })
  return (kids.get(null) ?? []).map(node)
}

/** 骨架:成员框树顶层框的特征编号按先后排(还没标特征的为 null);子框和属性不进骨架。 */
export function skeleton(members: Iterable<string>, boxes: readonly NestBox[], days: readonly string[]): (string | null)[] {
  const feature = new Map(boxes.map(b => [b.id, b.feature]))
  return memberTree(members, boxes, days).map(n => feature.get(n.box) ?? null)
}

/** 成员框树顶层出现两次以上的特征编号,按第一次出现的先后排;还没标特征的不算。 */
export function dupFeatures(members: Iterable<string>, boxes: readonly NestBox[], days: readonly string[]): string[] {
  const tops = skeleton(members, boxes, days)
  return tops.filter((f, i): f is string => f !== null && tops.indexOf(f) === i && tops.lastIndexOf(f) !== i)
}

/** 样本存下的成员框里,还在这张图上、且在样本日当天或之前结束的那些框。 */
export function currentMemberBoxes<B extends NestBox>(sample: MemberSample, boxes: readonly B[]): B[] {
  const byId = new Map(boxes.map(b => [b.id, b]))
  const out: B[] = []
  for (const m of sample.members) {
    const b = byId.get(m)
    if (b && b.end <= sample.date) out.push(b)
  }
  return out
}

export interface Slot { box: string; feature: string | null; reason: SlotReason }

/**
 * 一个样本成员链上的空槽,按框的先后排(规则见模块说明)。charts:状态里的全部图(要看全部图,才知道特征在
 * 这个 pattern 里出现过没有);symbol、sampleId:哪张图的哪个样本;days:这张图的交易日。
 * 找不到这张图或这个样本 → MembershipInputError(unknown_chart / unknown_sample)。
 */
export function emptySlots(charts: readonly MemberChart[], symbol: string, sampleId: string,
                           days: readonly string[], near: number): Slot[] {
  const chart = charts.find(c => c.symbol === symbol)
  if (!chart) throw new MembershipInputError('unknown_chart', `no chart ${symbol}`)
  const sample = chart.samples.find(s => s.id === sampleId)
  if (!sample) throw new MembershipInputError('unknown_sample', `no sample ${sampleId} on ${symbol}`)
  const { pattern, date } = sample
  const used = new Set<string>()
  for (const c of charts) for (const s of c.samples) if (s.pattern === pattern) {
    for (const b of currentMemberBoxes(s, c.boxes)) if (b.feature != null) used.add(b.feature)
  }
  const others = new Set<string>()
  for (const s of chart.samples) if (s.id !== sampleId && s.pattern === pattern) {
    for (const b of currentMemberBoxes(s, chart.boxes)) others.add(b.id)
  }
  const mine = new Set(currentMemberBoxes(sample, chart.boxes).map(b => b.id))
  const p = pool(chart.boxes, days)
  const rangeStart = Math.min(rankOf(days, date), ...[...mine].map(id => p.get(id)!.s))
  const out: Slot[] = []
  for (const b of ordered(p.values())) {
    if (mine.has(b.id) || others.has(b.id) || b.feature == null || !used.has(b.feature)) continue
    let reason: SlotReason
    if (b.end > date) {
      if (b.start > date) continue
      reason = CROSSES_SAMPLE_DATE
    } else if (b.e >= rangeStart - near) reason = UNCLAIMED
    else continue
    out.push({ box: b.id, feature: b.feature, reason })
  }
  return out
}
