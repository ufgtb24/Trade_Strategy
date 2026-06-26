// 几何分流 + greedy lane packing(spec §8.2.4 / §8.3)。
import type { EventDict, MatchDict } from '../types'

interface Span { start_idx: number; end_idx: number }

export function splitGeometry(events: EventDict[]): { points: EventDict[]; intervals: EventDict[] } {
  const points: EventDict[] = []
  const intervals: EventDict[] = []
  for (const e of events) (e.start_idx === e.end_idx ? points : intervals).push(e)
  return { points, intervals }
}

/**
 * greedy lane packing:按 start 升序,贪心放入第一个"末端 < 本 start"的 lane,否则开新 lane。
 * 返回原对象浅拷贝 + lane 字段。稳定(同 start 按输入序)。
 */
export function packLanes<T extends Span>(items: T[]): (T & { lane: number })[] {
  const sorted = items.map((it, i) => ({ it, i }))
    .sort((a, b) => a.it.start_idx - b.it.start_idx || a.i - b.i)
  const laneEnds: number[] = []
  const out: (T & { lane: number })[] = []
  for (const { it } of sorted) {
    let lane = laneEnds.findIndex((end) => end < it.start_idx)
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(it.end_idx) }
    else laneEnds[lane] = it.end_idx
    out.push({ ...it, lane })
  }
  return out
}

export type BandedItem<T> = T & { lane: number; band: number; nBands: number }

/** 每 band 独立 packLanes:按 bandOrder 序,各 band 内部 lane 从 0 重置。空 band 不产出。 */
export function packByBand<T extends { start_idx: number; end_idx: number }>(
  items: T[], bandOrder: string[], bandKeyOf: (it: T) => string,
): BandedItem<T>[] {
  const out: BandedItem<T>[] = []
  bandOrder.forEach((tag, band) => {
    const inBand = items.filter(it => bandKeyOf(it) === tag)
    for (const packed of packLanes(inBand))
      out.push({ ...packed, band, nBands: bandOrder.length })
  })
  return out
}

/** 归属带:match.span lane packing + 1-based 序号(按 start 升序)。 */
export function packBrackets(matches: MatchDict[]): (MatchDict & { lane: number; ordinal: number })[] {
  const ordered = [...matches].sort((a, b) => a.start_idx - b.start_idx)
  const withOrdinal = ordered.map((m, i) => ({ ...m, ordinal: i + 1 }))
  return packLanes(withOrdinal)
}
