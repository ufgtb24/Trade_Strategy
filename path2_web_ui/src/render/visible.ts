// 可见集辅助函数(band/tier/tag/tooltip)。level 门控由 chart 层消费,此处仅提供纯函数原语。
import type { EventDict, MatchDict, TopoNode, TopoEdge, Topology, AttrRow, Diagnostics, Tier, ClauseWitness, ScanMeta, Bar } from '../types'
import type { TooltipPayload, TooltipClauseRow } from './chart'

/** 所有匹配内实例 instance_id 的并集(schema-driven 协议驱动)。
 *  展开规则:
 *  - 初始集 = ⋃_match node_index 的【精确实例】引用(值已是 instance_id 字符串),
 *    match 引用谁就是谁;children 保留作显示投影,不再作初始集来源
 *  - 持有型引用:沿 ev.child_refs 所有 slot value(instance_id 列表)递归入队(直加字符串)
 *  - 弱引用(opts.expandAnchor!==false 时):从 edges 收集非空 anchor_field,遍历 ev 上
 *    对应字段(标量或集合;tb.anchor_bo_id 单值标量,未来多源可为数组)入队——anchor 字段值
 *    恒为 instance_id(后端交错标注后 detect 期写入),byId 直连命中即入集
 *  opts.expandAnchor=false 时只沿 child_refs 闭包、不反查 anchor——专用于按选中 match
 *  高亮(highlightedInstanceIds):anchor 是 leaf event 的元属性(记录触发源),不是链路结构,
 *  反查会在共享 leaf 场景把别的 match 的 bo 污染进高亮集。focusEvent 归属 / eventTier
 *  等用默认 expandAnchor=true(bo 经 anchor 归属 match)。matched 的 composite event
 *  (如 burst)其 constituent bo 通过 child_refs 自然进集。
 *  实例化契约:集合元素为 instance_id 字符串(恒含 #idx);引用协议全实例化,零身份展开。 */
export function matchedIds(
  matches: MatchDict[],
  events: EventDict[],
  edges: TopoEdge[],
  opts: { expandAnchor?: boolean } = {},
): Set<string> {
  const expandAnchor = opts.expandAnchor ?? true
  const s = new Set<string>()
  if (events.length === 0) return s
  // instance_id → 对象索引:queue 出队元素为 instance_id,直接查对象
  const byId = new Map(events.map(e => [e.instance_id, e]))
  const queue: string[] = []
  const enqueue = (id: string): void => {
    if (!s.has(id)) { s.add(id); queue.push(id) }
  }
  // anchor 直连(与 findBoBar 同款单路径):anchor 字段值恒为 instance_id(后端交错标注
  // 后 detect 期写入),byId 直连命中即入集;非 instance_id 形态(物化残漏)miss 无害。
  const resolveAnchor = (v: string): void => {
    if (byId.has(v)) enqueue(v)
  }
  // 实例化初始集:match.node_index 值 = instance_id 字符串,引用谁就是谁。
  for (const m of matches) {
    for (const ref of Object.values(m.node_index)) enqueue(ref)
  }
  if (s.size === 0) return s
  const anchorFields = expandAnchor
    ? new Set(edges.map(e => e.anchor_field).filter((x): x is string => !!x))
    : new Set<string>()
  while (queue.length) {
    const id = queue.pop()!
    const ev = byId.get(id)
    if (!ev) continue
    // 持有型:child_refs 所有 slot(值已是 instance_id 列表,直加)
    const refs = ev.child_refs
    if (refs) {
      for (const ids of Object.values(refs)) {
        for (const cid of ids) enqueue(cid)
      }
    }
    // 弱引用:anchor_field 反查(仅 expandAnchor=true;高亮场景关掉避免共享 leaf 污染)
    if (expandAnchor) {
      for (const af of anchorFields) {
        const v = (ev as Record<string, unknown>)[af]
        if (typeof v === 'string') {
          resolveAnchor(v)
        } else if (Array.isArray(v)) {
          for (const vid of v) {
            if (typeof vid === 'string') resolveAnchor(vid)
          }
        }
      }
    }
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

/** 按 node_id 分组 nodes;返回 nodeIdToNodes 映射与插入顺序 bandList(dag 内 node_id 唯一,
 *  故每个 band 恰含其自身)。函数名沿袭旧称(分组键已按 node_id)。 */
export function deriveTagMap(nodes: TopoNode[]): { tagToNodes: Record<string, string[]>; tagList: string[] } {
  const tagToNodes: Record<string, string[]> = {}
  const tagList: string[] = []
  for (const n of nodes) {
    if (!(n.node_id in tagToNodes)) { tagToNodes[n.node_id] = []; tagList.push(n.node_id) }
    tagToNodes[n.node_id].push(n.node_id)
  }
  return { tagToNodes, tagList }
}

/** event 归哪个 band key:实例化契约下按 node_id 分组(node 维度蕴含 class 维度)。
 * 段等子事件由引擎 children 声明命名表直标子结构 node_id(如 tb_seg),天然独立泳道。 */
export function bandKeyOf(e: EventDict): string {
  return e.node_id
}

/** AttrRow 是否 qualified:全部 clause satisfied(空 clauses vacuous 真)。 */
export function isQualifiedRow(row: AttrRow): boolean {
  return Object.values(row.clauses).every(c => c.satisfied)
}

/** ⋃_node { e ∈ diag.nodes[nid].attr : isQualifiedRow }。实例化:集合元素为 instance_id
 *  (attr 行恒带 instance_id)。 */
export function qualifiedIdsOf(diag: Diagnostics | null): Set<string> {
  const out = new Set<string>()
  if (!diag) return out
  for (const node of Object.values(diag.nodes))
    for (const row of node.attr)
      if (isQualifiedRow(row)) out.add(row.instance_id)
  return out
}

/** event 处于哪一档:matched > qualified > detected。两档均实例级判定
 *  (集合元素为 instance_id,同 node 多实例可不同档)。 */
export function eventTierOf(e: EventDict, matched: Set<string>, qualified: Set<string>): Tier {
  if (matched.has(e.instance_id)) return 'matched'
  if (qualified.has(e.instance_id)) return 'qualified'
  return 'detected'
}

/** event 归哪个 band 的 node(node_id 分组下 1:1 → 即 event.node_id)。 */
export function nodeOfEventByBand(e: EventDict, tagToNodes: Record<string, string[]>, tagList: string[]): string | null {
  const nodesForTag = tagToNodes[bandKeyOf(e)]
  return nodesForTag && nodesForTag.length ? nodesForTag[0] : null
}

/** ClauseWitness → TooltipClauseRow(单行)。组合子行 kind=label,叶子 kind=null。 */
function toClauseRow(cid: string, node: string, w: ClauseWitness,
                     depth: number, guide = ''): TooltipClauseRow {
  const kids = w.children ?? []
  return {
    cid, node,
    measured: w.measured, op: w.op, threshold: w.threshold,
    satisfied: w.satisfied,
    depth,
    kind: kids.length ? (w.label ?? null) : null,
    guide,
  }
}

/** 深度优先展开子树为线性行,同时算好【树线前缀】:
 *  末子用 └、其余用 ├;再往下递归时,末子这一路补空格、非末子补 │ 以延续竖线。
 *  子行 cid 用 witness.label(=字段名 / 组合子 kind)。 */
function flattenChildren(w: ClauseWitness, node: string, depth: number,
                         prefix: string, out: TooltipClauseRow[]): void {
  const kids = w.children ?? []
  kids.forEach((k, i) => {
    const last = i === kids.length - 1
    out.push(toClauseRow(k.label ?? '?', node, k, depth, prefix + (last ? '└ ' : '├ ')))
    flattenChildren(k, node, depth + 1, prefix + (last ? '  ' : '│ '), out)
  })
}

/** tooltip 数据组装（纯）：
 *  - identity：node 反查 diag.nodes（多 node 时各保留）；时间 = bars[idx].date，point 时 dateEnd=null；
 *              bars 越界 fallback 到 String(idx)
 *  - clauses：跨 node 累积为 ClauseRow[]，按 satisfied 排序（失败 ✗ 在前）
 *  - raw：event dict 平铺，去掉 SKIP 集 + clauses 已引用 cid
 *  实例化:attr 行与 identity 均按 instance_id 取【该实例】的判定/属性(悬停哪个实例
 *  展示哪个)。identity.eventId 字段名沿袭 chart 侧 TooltipPayload 契约,值=instanceId。
 *  spec 见 docs/superpowers/specs/2026-06-29-marker-tooltip-cleanup-design.md */
export function resolveTooltipData(
  instanceId: string,
  diag: Diagnostics | null,
  events: EventDict[],
  bars: Bar[],
): TooltipPayload {
  // ── clauses 累积（不覆盖；多 node 同 cid 各保留）─────────────────────────
  // 排序只作用于顶层(失败 ✗ 在前);子树紧跟父行、保持声明顺序(作者写 any 的
  // 分支顺序本身带主次语义,不重排)。
  const clauses: TooltipClauseRow[] = []
  const nodes: string[] = []
  if (diag) {
    const groups: { row: TooltipClauseRow; subtree: TooltipClauseRow[] }[] = []
    for (const [nodeId, node] of Object.entries(diag.nodes)) {
      // clauses:attr 行按 instance_id 取【该实例】的判定(多实例各判各的)
      const row = node.attr.find((r) => r.instance_id === instanceId)
      if (!row) continue
      nodes.push(nodeId)
      for (const [cid, w] of Object.entries(row.clauses)) {
        const witness = w as ClauseWitness
        const subtree: TooltipClauseRow[] = []
        flattenChildren(witness, nodeId, 1, '', subtree)
        groups.push({ row: toClauseRow(cid, nodeId, witness, 0), subtree })
      }
    }
    groups.sort((a, b) => Number(a.row.satisfied) - Number(b.row.satisfied))
    for (const g of groups) clauses.push(g.row, ...g.subtree)
  }

  // ── identity 组装 ──────────────────────────────────────────────────────
  // identity:实例级取该实例(悬停实例的属性,如 anchor_bo_id)
  const ev = events.find((e) => e.instance_id === instanceId)
  const startIdx = (ev?.start_idx as number | undefined) ?? -1
  const endIdx = (ev?.end_idx as number | undefined) ?? -1
  const dateStart = bars[startIdx]?.date ?? String(startIdx)
  const dateEnd = startIdx === endIdx ? null : (bars[endIdx]?.date ?? String(endIdx))

  // ── raw 平铺 + 去重 ─────────────────────────────────────────────────────
  const cidsInClauses = new Set(clauses.map((c) => c.cid))
  const SKIP = new Set(['instance_id', 'node_id', 'instance_idx', 'start_idx', 'end_idx',
                        'confirm_idx', 'child_refs', 'ref_ids'])
  const raw: Record<string, unknown> = {}
  if (ev) for (const [k, v] of Object.entries(ev)) {
    if (SKIP.has(k)) continue
    if (cidsInClauses.has(k)) continue
    raw[k] = v
  }

  return {
    identity: { nodes, dateStart, dateEnd, eventId: instanceId },
    clauses,
    raw,
  }
}

/** band 可见性判定(纯函数):band 的所有 nodeId 中有任一 nodeVisible!==false 则可见。
 *  nodeVisible 未传(undefined)或 tagToNodes 无该 band 条目时默认可见。 */
export function isBandVisible(
  bandKey: string,
  nodeVisible: Record<string, boolean> | undefined,
  tagToNodes: Record<string, string[]> | undefined,
): boolean {
  if (!nodeVisible) return true
  const nodeIds = tagToNodes?.[bandKey] ?? []
  if (nodeIds.length === 0) return true
  return nodeIds.some((nid) => nodeVisible[nid] !== false)
}

// ─── label(N 日前瞻收益)/ 缓冲窗辅助 ─────────────────────────────────────────

/** 结果文件的实际渲染窗口:铁律 eval_meta 后 win_start/win_end 永远非空;缺则 throw。 */
export function windowOf(scan: Pick<ScanMeta, 'win_start' | 'win_end' | 'start_date' | 'end_date'>):
  { start: string; end: string } {
  // 铁律 eval_meta 后 win_*/end_node/label_horizon 永远非 null;
  // 旧文件回退分支删除(spec §3.6)。
  if (!scan.win_start || !scan.win_end) {
    throw new Error('windowOf: scan.win_start/win_end required (eval_meta 铁律下应永远非空)')
  }
  return { start: scan.win_start, end: scan.win_end }
}

/** forward_return 显示格式:null → '—';数值 → 带符号一位小数百分比。 */
export function formatForwardReturn(v: number | null): string {
  if (v === null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
}

// ─── 样本消费窗右端拆段(tb v4 状态机 spec §10 UI 面)─────────────────────

/** bar 索引区间(两端含)。 */
export interface IntervalSpan {
  start: number
  end: number
}

/** 拆分后的一段:afterWindow=true 为 scanEnd 之后的机器轨迹段(渲染为非样本灰)。 */
export interface IntervalSpanPart extends IntervalSpan {
  afterWindow: boolean
}

/** 副图 band interval 在样本消费窗右端(scanEndIdx)处拆分:
 *  - 完全窗内(end <= scanEndIdx)→ [原区间](窗内)
 *  - 完全窗外(start > scanEndIdx)→ [原区间](窗后,整段灰)
 *  - 跨界 → [窗内段(…scanEndIdx), 窗后段(scanEndIdx+1…)](按时间序,窗内段在前)
 *  边界语义:scanEndIdx 本身归窗内(与主图 buildShadingMarkArea 从 endIdx+1 起灰
 *  同一口径)。 */
export function splitIntervalAtScanEnd(interval: IntervalSpan, scanEndIdx: number): IntervalSpanPart[] {
  if (interval.end <= scanEndIdx) return [{ ...interval, afterWindow: false }]
  if (interval.start > scanEndIdx) return [{ ...interval, afterWindow: true }]
  return [
    { start: interval.start, end: scanEndIdx, afterWindow: false },
    { start: scanEndIdx + 1, end: interval.end, afterWindow: true },
  ]
}

/** event 主 marker 渲染轴反查:node_id → TopoNode.render_grid;
 *  缺省 / 找不到 → 'time' (守序保守, 与后端 NodeSpec.render_grid 默认值对齐)。 */
export function renderGridOf(
  e: EventDict,
  topology: Topology,
  bandKey: (e: EventDict) => string,
): 'price' | 'time' {
  const nid = bandKey(e)
  const node = topology.nodes.find((n) => n.node_id === nid)
  return node?.render_grid ?? 'time'
}

/** 副图分轨 tag 列表:剔除 render_grid==='price' 的 tag(其 marker 钉主图,不占副图轨道)。
 *  node 查找规则与 renderGridOf 一致(按 node_id 查找,缺省 'time'),
 *  保证路由与分轨判定永远一致:timeAnchored event 的 tag 必在返回列表中。 */
export function subBandTagList(tagList: string[], topology: Topology): string[] {
  return tagList.filter((tag) =>
    (topology.nodes.find((n) => n.node_id === tag)?.render_grid ?? 'time') !== 'price')
}
