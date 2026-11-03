/**
 * compare 下把当前 pattern 的 app 在这张图上的输出叠到用户的标注上(spec 5.8;第一段只叠画,不挂对照 tag,
 * 不显示 mapping)。本模块只算放在哪条轨、哪一行,画法见 render/annotateLanes.ts 的 buildAnnotateSubOption。
 *
 * - event:mapping(stores/appLink.ts)里对到某个特征的 node,它的 event 画在这个特征的轨上,档位一直画到
 *   detected。几个特征对同一个 node 时,这个 node 的 event 在每条轨上各画一份。这张图上没有这个特征的框、
 *   却有 event 时,另起一条这个特征的轨(排在已有的特征轨之后、unnamed 轨之前),在上面照样能画框。
 *   没进 mapping 的 node、特征编号不在词表里的行都不画。
 * - 一条轨里 event 自己分行(交叠的不同行),这几行作为一块竖直居中在轨里、和用户的框叠在一起;
 *   轨的行数取「框的行数」与「event 块要的行数」中大的那个。
 * - hit:画在 bracket 轨上,排在样本跨度的那几行下面,自己分行。
 * event、hit 的起止都是 K 线下标:app 跑的区间是这只股票截到训练段末日的全部 K 线,和图上的 K 线逐根对齐
 * (stores/appLink.ts;后端测试 tests/path2_web/test_data_wall.py 核对)。
 */
import type { EventDict, MatchDict, Tier } from '../types'
import type { Lane } from '../annotate/model'
import { APP_ROW_H, LANE_ROW_H } from './annotateLanes'

/** 叠到轨上的一个 event:它在 event 块里第几行、档位。 */
export interface CmpEvent { id: string; node: string; start: number; end: number; tier: Tier; row: number }
/** 一条轨上叠的 event(按轨的下标与 lanes 对齐);rows 是 event 块的行数。 */
export interface CmpLane { events: CmpEvent[]; rows: number }
/** bracket 轨上的一个 hit,row 从 0 起(画的时候排在样本的那几行下面)。 */
export interface CmpHit { id: string; start: number; end: number; row: number }

/** 按起点排,一行里不交叠(按 K 线下标比);返回每项的行号与行数。 */
function packRows<T extends { start: number; end: number }>(items: readonly T[]): { rows: number; placed: (T & { row: number })[] } {
  const sorted = [...items].sort((a, b) => a.start - b.start || b.end - a.end)
  const ends: number[] = []
  const placed = sorted.map(it => {
    let row = ends.findIndex(e => e < it.start)
    if (row < 0) { row = ends.length; ends.push(0) }
    ends[row] = it.end
    return { ...it, row }
  })
  return { rows: ends.length, placed }
}

/** event 块要占轨里几行(按轨的行高折算)。 */
export function laneRowsFor(appRows: number): number {
  return appRows ? Math.ceil((appRows * APP_ROW_H) / LANE_ROW_H) : 0
}

/**
 * compare 下的特征轨:在 annotate 的轨(computeLanes 的结果)上叠 event,必要时另起特征轨、加高轨。
 * features:特征编号 → node_id(mapping);known:特征编号在不在词表里;tierOf:event 的档位。
 */
export function compareLanes(base: readonly Lane[], features: Readonly<Record<string, string>>,
                             events: readonly EventDict[], tierOf: (e: EventDict) => Tier,
                             known: (fid: string) => boolean): { lanes: Lane[]; app: CmpLane[] } {
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
  const extra = Object.keys(features)
    .filter(fid => !have.has(fid) && eventsOf(fid).length > 0)
    .sort((a, b) => Math.min(...eventsOf(a).map(e => e.start_idx)) - Math.min(...eventsOf(b).map(e => e.start_idx)) || (a < b ? -1 : 1))
    .map((fid): Lane => ({ key: fid, parent: null, rows: 0, boxes: [] }))
  const unnamed = base.findIndex(l => l.key === null)
  const all = unnamed < 0 ? [...base, ...extra] : [...base.slice(0, unnamed), ...extra, ...base.slice(unnamed)]
  const app: CmpLane[] = []
  const lanes = all.map(l => {
    const { rows, placed } = packRows(eventsOf(l.key).map(e => ({
      id: e.instance_id, node: e.node_id, start: e.start_idx, end: e.end_idx, tier: tierOf(e),
    })))
    app.push({ events: placed, rows })
    return { ...l, rows: Math.max(l.rows, laneRowsFor(rows), 1) }
  })
  return { lanes, app }
}

/** bracket 轨上的 hit:各自分行(行号从 0 起)。 */
export function packHits(matches: readonly MatchDict[]): { rows: number; placed: CmpHit[] } {
  return packRows(matches.map(m => ({ id: m.match_id, start: m.start_idx, end: m.end_idx })))
}
