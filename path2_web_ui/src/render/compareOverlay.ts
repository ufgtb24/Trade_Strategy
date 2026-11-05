/**
 * compare 下把当前 pattern 的 app 在这张图上的输出叠到用户的标注上(spec 5.8:只叠画,不挂对照 tag,不显示 mapping)。
 * 本模块只算放在哪条轨、哪一行,画法见 render/annotateLanes.ts 的 buildAnnotateSubOption。
 *
 * - event:mapping(stores/appLink.ts)里对到某个特征的 node,它的 event 画在这个特征的轨上,档位一直画到
 *   detected。几个特征对同一个 node 时,这个 node 的 event 在每条轨上各画一份。这张图上没有这个特征的框、
 *   却有 event 时,另起一条这个特征的轨(排在已有的特征轨之后、unnamed 轨之前),在上面照样能画框。
 *   没进 mapping 的 node、特征编号不在词表里的行都不画。
 * - 一条轨里 event 自己分行(交叠的不同行,同主视图副图的分行),这几行作为一块竖直居中在轨里、和用户的框叠在一起;
 *   轨的行数取「框的行数」与「event 块要的行数」中大的那个。
 * - hit:画在 bracket 轨上,排在样本跨度的那几行下面,自己分行;条里用 ▼ 标出 app 的每个买入日(buyDaysOf),
 *   和样本的三角在同一条轨上比。
 * event、hit 的起止都是 K 线下标:app 跑的区间是这只股票截到训练段末日的全部 K 线,和图上的 K 线逐根对齐
 * (stores/appLink.ts;后端测试 tests/path2_web/test_data_wall.py 核对)。
 */
import type { EventDict, HitDict, Tier } from '../types'
import type { Lane } from '../annotate/model'
import { packLanes } from './geometry'
import { APP_ROW_H, LANE_ROW_H } from './annotateLanes'

/** 叠到轨上的一个 event:它在 event 块里第几行、档位;tiered = 它的 node 分档(只显示、不进求解的 node 不分档,不挂 tier tag)。 */
export interface OverlayEvent { id: string; node: string; start: number; end: number; tier: Tier; tiered: boolean; row: number }
/** 一条轨上叠的 event(按轨的下标与 lanes 对齐);rows 是 event 块的行数。 */
export interface OverlayLane { events: OverlayEvent[]; rows: number }
/** bracket 轨上的一个 hit,row 从 0 起(画的时候排在样本的那几行下面);buys:app 在这次 hit 里的买入日(K 线下标,升序)。 */
export interface OverlayHit { id: string; start: number; end: number; row: number; buys: number[] }

/** event 块要占轨里几行(按轨的行高折算)。 */
export function laneRowsFor(appRows: number): number {
  return appRows ? Math.ceil((appRows * APP_ROW_H) / LANE_ROW_H) : 0
}

/**
 * compare 下的特征轨:在 annotate 的轨(computeLanes 的结果)上叠 event,必要时另起特征轨、加高轨。
 * features:特征编号 → node_id(mapping);known:特征编号在不在词表里;tierOf:event 的档位;
 * untiered:只显示、不进求解的 node(serialize 的 solve=false),它们的 event 不分档。
 */
export function compareLanes(base: readonly Lane[], features: Readonly<Record<string, string>>,
                             events: readonly EventDict[], tierOf: (e: EventDict) => Tier,
                             known: (fid: string) => boolean,
                             untiered: ReadonlySet<string> = new Set()): { lanes: Lane[]; app: OverlayLane[] } {
  const byNode = new Map<string, EventDict[]>()
  for (const e of events) {
    if (!byNode.has(e.node_id)) byNode.set(e.node_id, [])
    byNode.get(e.node_id)!.push(e)
  }
  const eventsOf = (fid: string | null): EventDict[] => {
    const node = fid !== null && known(fid) ? features[fid] : undefined
    return node ? byNode.get(node) ?? [] : []
  }
  const have = new Set(base.map(l => l.key))
  const firstStart = (fid: string) => Math.min(...eventsOf(fid).map(e => e.start_idx))
  const extra = Object.keys(features)
    .filter(fid => !have.has(fid) && eventsOf(fid).length > 0)
    .sort((a, b) => firstStart(a) - firstStart(b) || (a < b ? -1 : 1))
    .map((fid): Lane => ({ key: fid, parent: null, rows: 0, boxes: [] }))
  const unnamed = base.findIndex(l => l.key === null)
  const all = unnamed < 0 ? [...base, ...extra] : [...base.slice(0, unnamed), ...extra, ...base.slice(unnamed)]
  const app: OverlayLane[] = []
  const lanes = all.map(l => {
    const placed = packLanes(eventsOf(l.key)).map((e): OverlayEvent => ({
      id: e.instance_id, node: e.node_id, start: e.start_idx, end: e.end_idx, tier: tierOf(e),
      tiered: !untiered.has(e.node_id), row: e.lane,
    }))
    const rows = placed.reduce((n, e) => Math.max(n, e.row + 1), 0)
    app.push({ events: placed, rows })
    return { ...l, rows: Math.max(l.rows, laneRowsFor(rows), 1) }
  })
  return { lanes, app }
}

/**
 * 一次 hit 里 app 的买入日(K 线下标,升序去重),和后端评估取买点日的口径一致(path2/eval.py 的 _resolve_end_events):
 * endNode 是 app 的 eval_meta 声明的买点 node——'node' 取 hit 里这个 node 的 event;'node.slot' 取这个 node 的 event
 * 在 slot 里的 child event;每个 event 跨度里的每一根都是买入日(path2/core.py 的 Event.sample_bar_indices)。
 * 没有 endNode、或在这次 hit 里解析不到,为空。
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

/** bracket 轨上的 hit:各自分行(行号从 0 起);events、endNode 给了就带上每个 hit 的买入日(见 buyDaysOf)。 */
export function packHits(hits: readonly HitDict[], events: readonly EventDict[] = [],
                         endNode: string | null = null): { rows: number; placed: OverlayHit[] } {
  const byId = new Map(events.map(e => [e.instance_id, e]))
  const placed = packLanes([...hits]).map(m => ({ id: m.hit_id, start: m.start_idx, end: m.end_idx, row: m.lane,
                                                      buys: buyDaysOf(m, byId, endNode) }))
  return { rows: placed.reduce((n, h) => Math.max(n, h.row + 1), 0), placed }
}
