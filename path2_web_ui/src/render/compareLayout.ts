/**
 * compare 下副图的轨序(纯函数):用户的特征轨照 annotate 的顺序,map 了的轨下面紧跟它对的那个 node 的 band 组
 * (这个 node 及其子 node 的 band,按拓扑里的父子关系),没 map 的轨留在原位,没被任何轨拉走的 band 接在最后,
 * unnamed 轨永远最后。只用标注的轨、mapping(特征编号 → node_id)、拓扑的 produced_by,不认任何具体事件类型。
 *
 * - 组:以「没有 produced_by 的 node」为根,根的 band 在前,其后是 produced_by 链最终落到这个根的子 node 的 band,
 *   按 bands 里的先后;
 * - 一条轨 map 到根:轨在前、整组在后;几条轨 map 到同一组:这几条轨按原序叠在组的上方,组只出现一次,
 *   位置在其中第一条轨那里;
 * - 一条轨 map 到子 node:它插在组里那条子 band 正前面;这一组若没有别的轨拉走,由它把整组拉到它的位置;
 * - mapping 指向的 node 不在 bands 里(主图上的 node、拓扑里没有的 node):轨照常留在原位,不拉任何 band,
 *   表头仍写它对的 node(在拓扑里时);拓扑里没有的,当作没 map。
 */
import type { Lane } from '../annotate/model'
import type { Topology } from '../types'

export type Slot = { kind: 'lane'; lane: number } | { kind: 'band'; band: number }

export interface CompareLayout {
  /** 自上而下的轨与 band。lane、band 分别是 lanes、bands 里的下标 */
  slots: Slot[]
  /** 每一组在 slots 里的首尾(含两端)与组的根 node:左边那道竖线画在这一段 */
  groups: { from: number; to: number; node: string }[]
  /** 轨 → 它对的 node(表头写 `⇣ node`) */
  laneNode: Map<number, string>
  /** 没 map 的特征轨(表头挂 unmapped);unnamed 轨不算 */
  unmapped: Set<number>
  /** 没被任何轨拉走、也不是被拉走的组里的 band(表头挂 app_only) */
  appOnly: Set<number>
}

export function compareSlots(
  lanes: readonly Lane[], bands: readonly string[], topology: Topology,
  features: Readonly<Record<string, string>>, known: (fid: string) => boolean,
): CompareLayout {
  const nodes = new Map(topology.nodes.map(n => [n.node_id, n]))
  const rootOf = (id: string): string => {
    let cur = id
    for (let guard = 0; guard < 64; guard++) {
      const p = nodes.get(cur)?.produced_by
      if (!p || !nodes.has(p)) return cur
      cur = p
    }
    return cur
  }
  const bandIdx = new Map(bands.map((b, i) => [b, i]))
  const groupBands = new Map<string, number[]>()           // 根 → 组里 band 的下标(根在前)
  bands.forEach((b, i) => {
    const r = rootOf(b)
    if (!groupBands.has(r)) groupBands.set(r, [])
    groupBands.get(r)!.push(i)
  })
  for (const [r, list] of groupBands) {
    const ri = bandIdx.get(r)
    if (ri !== undefined) groupBands.set(r, [ri, ...list.filter(i => i !== ri)])
  }

  const laneNode = new Map<number, string>()
  const unmapped = new Set<number>()
  lanes.forEach((l, i) => {
    if (l.key === null) return
    const node = known(l.key) ? features[l.key] : undefined
    if (node && nodes.has(node)) laneNode.set(i, node)
    else unmapped.add(i)
  })

  // 每一组被哪些轨拉走(按轨序);组出现在第一条拉它的轨那里
  const pullers = new Map<string, number[]>()
  for (const [i, node] of laneNode) {
    if (!bandIdx.has(node)) continue
    const r = rootOf(node)
    if (!pullers.has(r)) pullers.set(r, [])
    pullers.get(r)!.push(i)
  }
  const firstPuller = new Map<number, string>()            // 轨 → 它负责放出的组
  for (const [r, ls] of pullers) firstPuller.set(Math.min(...ls), r)
  const pulledLanes = new Set([...pullers.values()].flat())

  const slots: Slot[] = []
  const groups: CompareLayout['groups'] = []
  const unnamed: number[] = []
  lanes.forEach((l, i) => {
    if (l.key === null) { unnamed.push(i); return }
    if (pulledLanes.has(i) && !firstPuller.has(i)) return  // 跟着它的组一起放
    if (!firstPuller.has(i)) { slots.push({ kind: 'lane', lane: i }); return }
    const r = firstPuller.get(i)!
    const ls = pullers.get(r)!
    const gb = groupBands.get(r) ?? []
    const from = slots.length
    // map 到根(或拓扑里不在本组 band 上)的轨叠在组上方;map 到子 node 的轨插在那条子 band 前
    const atBand = new Map<number, number[]>()
    for (const li of ls) {
      const b = bandIdx.get(laneNode.get(li)!)!
      const key = b === gb[0] ? -1 : b
      if (!atBand.has(key)) atBand.set(key, [])
      atBand.get(key)!.push(li)
    }
    for (const li of atBand.get(-1) ?? []) slots.push({ kind: 'lane', lane: li })
    for (const b of gb) {
      if (b !== gb[0]) for (const li of atBand.get(b) ?? []) slots.push({ kind: 'lane', lane: li })
      slots.push({ kind: 'band', band: b })
    }
    groups.push({ from, to: slots.length - 1, node: r })
  })
  const pulledBands = new Set([...pullers.keys()].flatMap(r => groupBands.get(r) ?? []))
  const appOnly = new Set<number>()
  bands.forEach((_, b) => {
    if (pulledBands.has(b)) return
    appOnly.add(b)
    slots.push({ kind: 'band', band: b })
  })
  for (const i of unnamed) slots.push({ kind: 'lane', lane: i })
  return { slots, groups, laneNode, unmapped, appOnly }
}
