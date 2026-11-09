/**
 * compare 下用户轨与 app 轨的对应(纯函数)。副图分两区,中间一道分界线:
 * - 上区(用户):特征轨照 annotate 的顺序在上,样本跨度那一行(user)在这一区最后一行;
 * - 下区(app):hits 在第一行,band 照主视图的顺序在下(和主视图那张副图一模一样)。
 * 两区不穿插,所以这里不排轨序,只算两区之间怎么对上:
 * - laneNode:map 了的特征轨 → 它对的 node(轨标题写 `⇣ node`);
 * - unmapped:没 map 的特征轨(标题挂 unmapped);unnamed 轨不算;
 * - appOnly:所在的组(以「没有 produced_by 的 node」为根,根及 produced_by 链落到它的子 node)里
 *   没有任何 node 被 map 的 band(表头挂 app_only);
 * - linkedBands:选中一条特征轨的框时,要跟着加粗表头的 band = 它对的 node 及其子孙 node 的 band。
 * mapping 指向的 node 不在 bands 里(主图上的 node):轨照常写它对的 node,不连任何 band;拓扑里没有的,当作没 map。
 * 只用标注的轨、mapping(特征编号 → node_id)、拓扑的 produced_by,不认任何具体事件类型。
 */
import type { Lane } from '../annotate/model'
import type { Topology } from '../types'

export interface CompareLinks {
  /** 轨(lanes 下标)→ 它对的 node */
  laneNode: Map<number, string>
  /** 没 map 的特征轨(lanes 下标) */
  unmapped: Set<number>
  /** 所在组里没有任何 node 被 map 的 band(bands 下标) */
  appOnly: Set<number>
  /** 轨(lanes 下标)→ 它对的 node 及其子孙 node 的 band(bands 下标,按 bands 里的先后) */
  linkedBands: Map<number, number[]>
}

export function compareLinks(
  lanes: readonly Lane[], bands: readonly string[], topology: Topology,
  features: Readonly<Record<string, string>>, known: (fid: string) => boolean,
): CompareLinks {
  const nodes = new Map(topology.nodes.map(n => [n.node_id, n]))
  const parentOf = (id: string): string | null => {
    const p = nodes.get(id)?.produced_by
    return p && p !== id && nodes.has(p) ? p : null
  }
  const rootOf = (id: string): string => {
    let cur = id
    for (let guard = 0; guard < 64; guard++) {
      const p = parentOf(cur)
      if (!p) return cur
      cur = p
    }
    return cur
  }
  const isUnder = (id: string, anc: string): boolean => {
    let cur: string | null = id
    for (let guard = 0; cur && guard < 64; guard++) {
      if (cur === anc) return true
      cur = parentOf(cur)
    }
    return false
  }

  const laneNode = new Map<number, string>()
  const unmapped = new Set<number>()
  lanes.forEach((l, i) => {
    if (l.key === null) return
    const node = known(l.key) ? features[l.key] : undefined
    if (node && nodes.has(node)) laneNode.set(i, node)
    else unmapped.add(i)
  })

  const linkedBands = new Map<number, number[]>()
  const mappedRoots = new Set<string>()
  for (const [i, node] of laneNode) {
    const linked = bands.flatMap((b, bi) => (isUnder(b, node) ? [bi] : []))
    if (!linked.length) continue
    linkedBands.set(i, linked)
    mappedRoots.add(rootOf(node))
  }
  const appOnly = new Set<number>()
  bands.forEach((b, bi) => { if (!mappedRoots.has(rootOf(b))) appOnly.add(bi) })
  return { laneNode, unmapped, appOnly, linkedBands }
}
