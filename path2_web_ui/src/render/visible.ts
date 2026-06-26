// 可见集辅助函数(band/tier/tag/tooltip)。level 门控由 chart 层消费,此处仅提供纯函数原语。
import type { EventDict, MatchDict, TopoNode, Topology, AttrRow, Diagnostics, Tier, ClauseWitness } from '../types'

/** 所有匹配内实例 event_id 的并集。
 *  若提供 events,沿事件 dict 的 `members`(event_id 数组)和 `anchor_bo_id`(单个 event_id)
 *  字段递归展开:matched 的 composite event(如 burst)其 constituent bo 也进入 matched 集,
 *  让 K线主图的 bo/pk geometry 与 matched 状态自然继承(schema-driven,非 class_id 分支)。 */
export function matchedIds(matches: MatchDict[], events?: EventDict[]): Set<string> {
  const s = new Set<string>()
  for (const m of matches) for (const c of m.children) s.add(c)
  if (!events || s.size === 0) return s
  const byId = new Map(events.map(e => [e.event_id, e]))
  const queue: string[] = [...s]
  while (queue.length) {
    const id = queue.pop()!
    const ev = byId.get(id)
    if (!ev) continue
    const members = (ev as Record<string, unknown>).members
    if (Array.isArray(members)) {
      for (const mid of members) {
        if (typeof mid === 'string' && !s.has(mid)) { s.add(mid); queue.push(mid) }
      }
    }
    const anchor = (ev as Record<string, unknown>).anchor_bo_id
    if (typeof anchor === 'string' && !s.has(anchor)) { s.add(anchor); queue.push(anchor) }
  }
  return s
}

// ─── §3 band/tier 纯函数族 ─────────────────────────────────────────────────

/** 拓扑中没有任何边连接的孤立 node_id 集合。 */
export function isolatedNodeIds(topology: Topology): Set<string> {
  const inEdge = new Set<string>()
  for (const e of topology.edges) { inEdge.add(e.src); inEdge.add(e.dst) }
  return new Set(topology.nodes.map(n => n.node_id).filter(id => !inEdge.has(id)))
}

/** 按 source_tag 分组 nodes;返回 tagToNodes 映射与插入顺序 tagList。 */
export function deriveTagMap(nodes: TopoNode[]): { tagToNodes: Record<string, string[]>; tagList: string[] } {
  const tagToNodes: Record<string, string[]> = {}
  const tagList: string[] = []
  for (const n of nodes) {
    if (!(n.source_tag in tagToNodes)) { tagToNodes[n.source_tag] = []; tagList.push(n.source_tag) }
    tagToNodes[n.source_tag].push(n.node_id)
  }
  return { tagToNodes, tagList }
}

/** event 归哪个 band key:优先 source_tag,其次前缀匹配 tagList,最后降级为 class_id。 */
export function bandKeyOf(e: EventDict, tagList: string[]): string {
  const st = e.source_tag as string | undefined
  if (st) return st                                   // 首选:后端直给
  const m = tagList.filter(t => e.event_id.startsWith(t + '_')).sort((a, b) => b.length - a.length)[0]
  return m ?? e.class_id                               // 末级防御
}

/** AttrRow 是否 qualified:全部 clause satisfied(空 clauses vacuous 真)。 */
export function isQualifiedRow(row: AttrRow): boolean {
  return Object.values(row.clauses).every(c => c.satisfied)
}

/** ⋃_role { e ∈ diag.roles[nid].attr : isQualifiedRow }。返回 qualified event_id 集。 */
export function qualifiedIdsOf(diag: Diagnostics | null): Set<string> {
  const out = new Set<string>()
  if (!diag) return out
  for (const role of Object.values(diag.roles))
    for (const row of role.attr) if (isQualifiedRow(row)) out.add(row.event_id)
  return out
}

/** event 处于哪一档:matched > qualified > detected。 */
export function eventTierOf(e: EventDict, matched: Set<string>, qualified: Set<string>): Tier {
  if (matched.has(e.event_id)) return 'matched'
  if (qualified.has(e.event_id)) return 'qualified'
  return 'detected'
}

/** event 归哪个 band 的 node(1:1 下 tag→单 node)。 */
export function roleOfEventByBand(e: EventDict, tagToNodes: Record<string, string[]>, tagList: string[]): string | null {
  const nodesForTag = tagToNodes[bandKeyOf(e, tagList)]
  return nodesForTag && nodesForTag.length ? nodesForTag[0] : null
}

/** tooltip 数据组装(纯):从 diag 取该 event 的 clause witnesses(跨 role 找 event_id 匹配行),
 *  raw = event dict 去掉固定四字段 + source_tag + members 后的子类属性平铺。 */
export function resolveTooltipData(
  eventId: string, diag: Diagnostics | null, events: EventDict[],
): { clauses: Record<string, { measured: unknown; op: string | null; threshold: unknown; satisfied: boolean }>; raw: Record<string, unknown> } {
  const clauses: Record<string, { measured: unknown; op: string | null; threshold: unknown; satisfied: boolean }> = {}
  if (diag) {
    for (const role of Object.values(diag.roles)) {
      const row = role.attr.find((r) => r.event_id === eventId)
      if (row) for (const [cid, w] of Object.entries(row.clauses))
        clauses[cid] = { measured: (w as ClauseWitness).measured, op: (w as ClauseWitness).op, threshold: (w as ClauseWitness).threshold, satisfied: (w as ClauseWitness).satisfied }
    }
  }
  const ev = events.find((e) => e.event_id === eventId)
  const raw: Record<string, unknown> = {}
  const SKIP = new Set(['class_id', 'event_id', 'start_idx', 'end_idx', 'source_tag', 'members'])
  if (ev) for (const [k, v] of Object.entries(ev)) if (!SKIP.has(k)) raw[k] = v
  return { clauses, raw }
}

/** band 可见性判定(纯函数):band 的所有 nodeId 中有任一 roleVisible!==false 则可见。
 *  roleVisible 未传(undefined)或 tagToNodes 无该 band 条目时默认可见。 */
export function isBandVisible(
  bandKey: string,
  roleVisible: Record<string, boolean> | undefined,
  tagToNodes: Record<string, string[]> | undefined,
): boolean {
  if (!roleVisible) return true
  const nodeIds = tagToNodes?.[bandKey] ?? []
  if (nodeIds.length === 0) return true
  return nodeIds.some((nid) => roleVisible[nid] !== false)
}

// ─── label(N 日前瞻收益)/ 缓冲窗辅助 ─────────────────────────────────────────

/** 结果文件的实际渲染窗口:缓冲扫描用 win_*,旧文件回退 start/end(对齐铁律:与扫描同窗)。 */
export function windowOf(scan: { start_date: string; end_date: string; win_start?: string; win_end?: string }): { start: string; end: string } {
  return { start: scan.win_start ?? scan.start_date, end: scan.win_end ?? scan.end_date }
}

/** forward_return 显示格式:null → '—';数值 → 带符号一位小数百分比。 */
export function formatForwardReturn(v: number | null): string {
  if (v === null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
}

/** event 主 marker 渲染轴反查:source_tag → TopoNode.render_grid;
 *  缺省 / 找不到 → 'time' (守序保守, 与后端 NodeSpec.render_grid 默认值对齐)。 */
export function renderGridOf(
  e: EventDict,
  topology: Topology,
  bandKey: (e: EventDict) => string,
): 'price' | 'time' {
  const tag = bandKey(e)
  const node = topology.nodes.find((n) => n.source_tag === tag)
  return node?.render_grid ?? 'time'
}
