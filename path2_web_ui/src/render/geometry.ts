// greedy lane packing(spec §8.3)。点还是条不在这里分:按拓扑 node 的 is_point 声明,见 render/fold.ts。
interface Span { start_idx: number; end_idx: number }

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
