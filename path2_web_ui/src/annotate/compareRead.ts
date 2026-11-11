/**
 * compare 的读数(纯函数):样本日 / 框终点那天,app 在某个 node 上怎么看。只读 app 的 event、hit、诊断数据与标注,
 * 不从 K 线现算任何东西,不认具体事件类型(path2_web 的「纯投影」红线)。
 *
 * - 那天在场的 event:这个 node 里跨度盖住那天、且到那天已经确认(确认根 ≤ 那天)的 event。复合事件每天产一个
 *   「截到当天」的实例,这条就是「终点等于那天」的那些;跨度型的买点 node 则是盖住那天的那一段;
 * - 配对(一天几个 event 时挑哪个,和主视图「点样本的默认选中」同一条):
 *   1. 给了子框(用户在框里画的、mapping 对到这个 node 的某个子 node 的框):取那个子段和子框对上的 event
 *      (子段终点离子框终点不超过 tol 根;tol 同样由调用方传 GET /annotations 带出的 match.sub);一个都对不上时
 *      当没给子框,照第 2、3 条在全部在场的 event 里挑;
 *   2. 那天有 hit:取那次 hit 绑定的 event;一天几个 hit 时按 hit 在结果里的先后取第一个;
 *   3. 没有 hit:取档位最深的,同档取起点最晚的(最近那一族),再同取结果里在前的;
 *   4. 一个都没有:null(样本的 diagnose 里 events 写 0)。
 * - match(spec 6.2):正样本:有一次 hit 的买点日离样本日不超过 tol.pos 根;负样本不超过 tol.neg 根。容差不在
 *   这里设:调用方传 GET /annotations 带出的 match(后端 path2_web/annotation/match.py 唯一设定,spec 第 10 节)。
 *   买点日按 eval_meta 的买点 node 取(buyDaysOf),所以「样本日落在买点 node 那段事件里」已包含在内。
 *   样本 match 有两份实现:这里(画图用)和后端 path2_web/annotation/match.py 的 sample_match(给会话的改版报告用),
 *   两份逐例通过同一份例子文件 tests/path2_web/fixtures/match_examples.json,改判法时两边连同例子一起改。
 *   反馈(feedback)的状态不在这里算:唯一实现在 match.py,界面照后端状态接口给的结果画。
 * - diagnose 的行只给类别:档位、没过的 where 名,不给实测值与门槛(spec 1.4)。
 */
import type { Diagnostics, EventDict, HitDict, Tier } from '../types'
import type { MatchTolerance } from './model'

const RANK: Record<Tier, number> = { in_hit: 2, qualified: 1, detected: 0 }

/** 那天在场的 event:跨度盖住那天,且确认根(没有就取终点)不晚于那天。 */
export function dayEvents(events: readonly EventDict[], node: string, day: number): EventDict[] {
  return events.filter(e => e.node_id === node && e.start_idx <= day && day <= e.end_idx
                            && (e.confirm_idx ?? e.end_idx) <= day)
}

/** 子框:它的起止(K 线下标)、它对的子 node 在父 children 里的槽名。 */
export interface SubBox { start: number; end: number; slot: string }

export interface Pairing {
  day: number
  /** 配对的那个 event;那天一个都没有为 null */
  event: EventDict | null
  /** 配对 event 所在的那次 hit(第 2 条成立时) */
  hitId: string | null
  /** 那天在场的全部 event(含配对的那个) */
  present: EventDict[]
}

/** 子段和子框对不对得上:交叠,且子段终点落在子框终点前后 tol 根内(同上一轮的整体判法,起点不看)。 */
function childMatches(child: EventDict | undefined, box: SubBox, tol: number): boolean {
  if (!child) return false
  return child.start_idx <= box.end && child.end_idx >= box.start && Math.abs(child.end_idx - box.end) <= tol
}

export function pairOn(
  day: number, node: string, events: readonly EventDict[], hits: readonly HitDict[],
  tierOf: (e: EventDict) => Tier, opts: { subBox?: { box: SubBox; tol: number } | null } = {},
): Pairing {
  const present = dayEvents(events, node, day)
  const none: Pairing = { day, event: null, hitId: null, present }
  if (!present.length) return none
  const byId = new Map(events.map(e => [e.instance_id, e]))
  const ids = new Set(present.map(e => e.instance_id))
  const sb = opts.subBox
  let pool = present
  if (sb) {
    const { box, tol } = sb
    const hitsSub = present.filter(e => (e.child_refs?.[box.slot] ?? []).some(id => childMatches(byId.get(id), box, tol)))
    if (hitsSub.length) pool = hitsSub
  }
  const poolIds = new Set(pool.map(e => e.instance_id))
  const hit = hits.find(h => { const id = h.node_index?.[node]; return !!id && ids.has(id) && poolIds.has(id) })
  if (hit) return { day, event: byId.get(hit.node_index[node]) ?? null, hitId: hit.hit_id, present }
  const best = [...pool].sort((a, b) => RANK[tierOf(b)] - RANK[tierOf(a)] || b.start_idx - a.start_idx)[0]
  return { day, event: best ?? null, hitId: null, present }
}

export interface MatchResult {
  state: 'matched' | 'unmatched'
  /** 让它成立的那次 hit(离样本日最近的买点) */
  hitId: string | null
  /** 那个买点日减样本日(根);unmatched 为 null */
  offset: number | null
}

export function matchOf(
  day: number, judgment: 'pos' | 'neg', hits: readonly HitDict[], buyDaysOf: (h: HitDict) => readonly number[],
  tol: MatchTolerance,
): MatchResult {
  const lim = judgment === 'pos' ? tol.pos : tol.neg
  let best: { hitId: string; offset: number } | null = null
  for (const h of hits) {
    for (const d of buyDaysOf(h)) {
      const off = d - day
      if (Math.abs(off) > lim) continue
      if (!best || Math.abs(off) < Math.abs(best.offset)) best = { hitId: h.hit_id, offset: off }
    }
  }
  return best ? { state: 'matched', hitId: best.hitId, offset: best.offset } : { state: 'unmatched', hitId: null, offset: null }
}

/**
 * ▲ 字母后的记号:app 和用户的判断一致(正样本 matched、负样本 unmatched)写 ✓,不一致写 ✗(画的时候加朱红底,
 * 同 spec 6.2「正样本 unmatched、负样本 matched 时用朱红」);matched / unmatched 这两个词放悬停。
 */
export function matchMark(judgment: 'pos' | 'neg', m: MatchResult): '✓' | '✗' {
  return (judgment === 'pos') === (m.state === 'matched') ? '✓' : '✗'
}

export interface DiagnoseRow {
  instanceId: string
  start: number
  /** 同族同格几个 event 时的消歧标签(memberLabels 给的),其余为 null */
  member: string | null
  level: Tier
  /** 没过的 where 名(只要名字) */
  failed: string[]
  paired: boolean
}

/**
 * diagnose 的行:配对的在最前,其余按档位深到浅、起点晚到早。memberLabel 由调用方给(render/fold.ts 的 memberLabels
 * 渲染成 `step → 11-22`);同起点、跨度完全相同的几个 event 才有标签。
 */
export function diagnoseRows(
  p: Pairing, diag: Diagnostics | null, tierOf: (e: EventDict) => Tier,
  memberLabel: (e: EventDict, sameCell: readonly EventDict[]) => string | null,
): DiagnoseRow[] {
  const failedOf = (e: EventDict): string[] => {
    const row = diag?.nodes?.[e.node_id]?.attr.find(r => r.instance_id === e.instance_id)
    return row ? Object.entries(row.clauses).filter(([, c]) => !c.satisfied).map(([k]) => k) : []
  }
  const rows = p.present.map(e => {
    const sameCell = p.present.filter(x => x.start_idx === e.start_idx && x.end_idx === e.end_idx)
    return {
      instanceId: e.instance_id, start: e.start_idx,
      member: sameCell.length > 1 ? memberLabel(e, sameCell) : null,
      level: tierOf(e), failed: failedOf(e), paired: e.instance_id === p.event?.instance_id,
    }
  })
  return rows.sort((a, b) => Number(b.paired) - Number(a.paired) || RANK[b.level] - RANK[a.level] || b.start - a.start)
}

/** ←/→ 在样本间走:这张图上当前 pattern 的样本,按样本日;到头不动。 */
export function stepSample(sampleIds: readonly { id: string; day: number }[], current: string | null, dir: -1 | 1): string | null {
  const sorted = [...sampleIds].sort((a, b) => a.day - b.day || (a.id < b.id ? -1 : 1))
  if (!sorted.length) return null
  const k = sorted.findIndex(s => s.id === current)
  if (k < 0) return sorted[dir > 0 ? 0 : sorted.length - 1].id
  return sorted[Math.min(sorted.length - 1, Math.max(0, k + dir))].id
}

/** 进 compare 时默认聚焦的样本:已有选中的就用它,否则取样本日离图窗中心最近的。 */
export function defaultFocus(samples: readonly { id: string; day: number }[], selected: string | null,
                             viewCenter: number): string | null {
  if (selected && samples.some(s => s.id === selected)) return selected
  let best: { id: string; d: number } | null = null
  for (const s of samples) {
    const d = Math.abs(s.day - viewCenter)
    if (!best || d < best.d) best = { id: s.id, d }
  }
  return best?.id ?? null
}
