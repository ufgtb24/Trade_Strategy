// 拓扑图布局:业务边做 left→right 最长路径分层(水平轴),父子关系(parent_refs)
// 垂直挂靠(垂直轴)——两轴正交:业务流水平读、结构包含垂直读。
// 输出节点盒子(左上角坐标)+ 边曲线 SVG path + 标签锚点。
// 类型无关——只消费 TopoNode/TopoEdge 通用字段,不对具体 node_id 特判。
import type { TopoNode, TopoEdge } from '../types'

export interface NodeBox { node: TopoNode; x: number; y: number; w: number; h: number }
export interface EdgePath { edge: TopoEdge; d: string; label: { x: number; y: number } }
// 父子虚线边:被引用 node(child)指向物化来源父(parent),label 显示槽名。
// 挂靠形态垂直(子顶→父底)、回退形态水平(子左缘→父右缘)。
export interface ParentEdgePath { child: TopoNode; parent_id: string; slot: string; d: string; label: { x: number; y: number } }
export interface TopoLayout {
  nodes: NodeBox[]; edges: EdgePath[]; parentEdges: ParentEdgePath[]
  width: number; height: number
}

const NODE_H = 30
const HPAD = 12      // 节点左右内边距
const CH_W = 14      // 单字符估计宽(中文 @13px)
const COL_GAP = 96   // 层间水平间距下限(per-gap 自适应会按需上调)
const ROW_GAP = 30   // 层内垂直间距
const VBEND = 24     // 回退水平虚线垂直弯曲:控制点上移,绕开业务边走廊(防"双向箭头"误读)
export const SUB_GAP = 30  // 父层栈底与首个挂靠子顶间距(= ROW_GAP,竖向节奏统一)
const PAD_X = 14
const PAD_Y = 14
const LABEL_PAD = 24   // 边标签两端留白(避免贴节点/箭头)
const LBL_CJK = 12     // 边标签 CJK 字符估宽(rule @11px)
const LBL_ASCII = 7    // 边标签 ASCII 字符估宽

function estWidth(n: TopoNode): number {
  const chars = [...n.node_id].length   // 按 Unicode 码点,中文每字算 1
  return 2 * HPAD + chars * CH_W
}

// 边标签文字估宽:区分 CJK/ASCII,取 kind(去 Edge 后缀)与 rule 较宽者。类型无关。
function estLabelWidth(e: TopoEdge): number {
  const textW = (s: string) => {
    let w = 0
    for (const ch of s) w += /[　-鿿＀-￯]/.test(ch) ? LBL_CJK : LBL_ASCII
    return w
  }
  return Math.max(textW(e.kind.replace('Edge', '')), textW(e.rule))
}

export function layoutTopology(nodes: TopoNode[], edges: TopoEdge[]): TopoLayout {
  const ids = new Set(nodes.map((n) => n.node_id))
  const validEdges = edges.filter((e) => ids.has(e.src) && ids.has(e.dst))
  // 业务边端点:被引用但也是端点 → 回退(不挂靠,留水平流,虚线水平画法)
  const businessEndpoints = new Set(validEdges.flatMap((e) => [e.src, e.dst]))

  // ── 0/1) 挂靠两遍分类:满足条件且父不是挂靠节点才挂靠;其余进水平流(flowNodes) ──
  // 第一遍:基本条件(parent_refs 恰一父、父在图中、非自引用、非业务边端点)
  const candidates = new Set<string>()
  for (const n of nodes) {
    const refs = n.parent_refs ?? []
    if (refs.length === 1
        && ids.has(refs[0][0])
        && refs[0][0] !== n.node_id
        && !businessEndpoints.has(n.node_id)) {
      candidates.add(n.node_id)
    }
  }
  // 第二遍:父 ∈ 候选集 → 嵌套挂靠防护,剔除(自动回退水平流;零实例,YAGNI)
  const anchorByChild = new Map<string, { parentId: string; slot: string }>()
  for (const n of nodes) {
    const refs = n.parent_refs ?? []
    if (candidates.has(n.node_id) && !candidates.has(refs[0][0])) {
      anchorByChild.set(n.node_id, { parentId: refs[0][0], slot: refs[0][1] })
    }
  }
  const flowNodes = nodes.filter((n) => !anchorByChild.has(n.node_id))
  const flowIds = new Set(flowNodes.map((n) => n.node_id))

  // ── 2/3) 最长路径分层(只跑水平流)+ byLayer 分组 ──
  // 无入边 → 0;否则 max(前驱 layer)+1。回退节点的 parent_refs 父仍作伪前驱 → 落父后列。
  const preds: Record<string, string[]> = {}
  for (const n of flowNodes) preds[n.node_id] = []
  for (const e of validEdges) preds[e.dst].push(e.src)
  for (const n of flowNodes) {
    for (const pid of (n.parent_refs ?? []).map((r) => r[0])) {
      if (flowIds.has(pid)) preds[n.node_id].push(pid)
    }
  }

  const layer: Record<string, number> = {}
  function computeLayer(id: string, stack: Set<string>): number {
    if (layer[id] !== undefined) return layer[id]
    if (stack.has(id)) return 0                       // 环保护(DAG 理论上不触发)
    stack.add(id)
    const ps = preds[id]
    const l = ps.length === 0 ? 0 : Math.max(...ps.map((p) => computeLayer(p, stack) + 1))
    stack.delete(id)
    layer[id] = l
    return l
  }
  for (const n of flowNodes) computeLayer(n.node_id, new Set())

  // ── 4) 降级守卫:父非其层末位 → 挂靠组会穿兄弟节点 → 降级回水平流 ──
  let numLayers = flowNodes.length ? Math.max(...flowNodes.map((n) => layer[n.node_id])) + 1 : 0
  const byLayer: TopoNode[][] = Array.from({ length: numLayers }, () => [])
  for (const n of flowNodes) byLayer[layer[n.node_id]].push(n)
  for (const [childId, { parentId }] of [...anchorByChild]) {
    const parentLayer = byLayer[layer[parentId]] ?? []
    if (parentLayer[parentLayer.length - 1]?.node_id !== parentId) {
      // 降级:层 = max(flow 父层)+1,追加该层末尾(父都在 flow,层已就绪)
      layer[childId] = Math.max(...flowNodes.map((n) => layer[n.node_id] + 1))
      if (layer[childId] >= numLayers) numLayers = layer[childId] + 1   // 可能加层
      byLayer[layer[childId]] = byLayer[layer[childId]] ?? []
      byLayer[layer[childId]].push(nodes.find((n) => n.node_id === childId)!)
      anchorByChild.delete(childId)
    }
  }

  // ── 5) 列宽:并入父在层 L 的挂靠子宽;gaps/colX 不变(挂靠子无边无标签) ──
  const colW = byLayer.map((col, L) => Math.max(0, ...col.map(estWidth),
    ...nodes.filter((n) => anchorByChild.has(n.node_id)
      && layer[anchorByChild.get(n.node_id)!.parentId] === L).map(estWidth)))
  // 每个间隙 gaps[i](col i ↔ i+1)初始为 COL_GAP 下限;按跨越它的边标签宽度上调
  const gaps: number[] = new Array(Math.max(0, numLayers - 1)).fill(COL_GAP)
  for (const e of validEdges) {
    const sL = layer[e.src], dL = layer[e.dst]
    const span = dL - sL
    if (span <= 0) continue                              // 同层/非前向:不参与列距
    const need = (estLabelWidth(e) + LABEL_PAD) / span   // 多层边:标签宽均摊到跨越的各间隙
    for (let i = sL; i < dL; i++) gaps[i] = Math.max(gaps[i], need)
  }
  const colX: number[] = []
  let acc = PAD_X
  for (let L = 0; L < numLayers; L++) {
    colX[L] = acc
    acc += colW[L] + (L < numLayers - 1 ? gaps[L] : 0)
  }

  // ── 6) 垂直布局(闭式解,无迭代):挂靠组放层栈之下 ──
  // 挂靠组底 ≤ contentH ⟺ effectiveStackH[L] ≤ contentH → contentH = max(effectiveStackH)
  const numAnchored: number[] = byLayer.map((_, L) =>
    nodes.filter((n) => anchorByChild.has(n.node_id)
      && layer[anchorByChild.get(n.node_id)!.parentId] === L).length)
  const anchoredStackH = numAnchored.map((k) => k * NODE_H + Math.max(0, k - 1) * ROW_GAP)
  const stackH = byLayer.map((c) => c.length * NODE_H + Math.max(0, c.length - 1) * ROW_GAP)
  const effectiveStackH = byLayer.map((_, L) =>
    stackH[L] + (numAnchored[L] ? SUB_GAP + anchoredStackH[L] : 0))
  const contentH = Math.max(0, ...effectiveStackH)

  const boxById: Record<string, NodeBox> = {}
  const boxes: NodeBox[] = []
  for (let L = 0; L < numLayers; L++) {
    const startY = PAD_Y + (contentH - effectiveStackH[L]) / 2
    byLayer[L].forEach((n, i) => {
      const box: NodeBox = {
        node: n, x: colX[L], y: startY + i * (NODE_H + ROW_GAP), w: estWidth(n), h: NODE_H,
      }
      boxById[n.node_id] = box
      boxes.push(box)
    })
    // 挂靠子:父层栈之下(父必为层末位 ⟹ 父底 = startY + stackH),多子竖排
    let j = 0
    for (const n of nodes) {
      if (!anchorByChild.has(n.node_id)) continue
      if (layer[anchorByChild.get(n.node_id)!.parentId] !== L) continue
      const box: NodeBox = {
        node: n, x: colX[L], y: startY + stackH[L] + SUB_GAP + j * (NODE_H + ROW_GAP),
        w: estWidth(n), h: NODE_H,
      }
      boxById[n.node_id] = box
      boxes.push(box)
      j++
    }
  }

  // ── 7) 业务边曲线 + 标签锚点(原样) ──
  const edgePaths: EdgePath[] = validEdges.map((e) => {
    const s = boxById[e.src], t = boxById[e.dst]
    const sx = s.x + s.w, sy = s.y + NODE_H / 2     // src 右缘中点
    const dx = t.x, dy = t.y + NODE_H / 2           // dst 左缘中点
    const k = Math.max(28, (dx - sx) * 0.5)         // 水平外推控制点
    const d = `M ${sx},${sy} C ${sx + k},${sy} ${dx - k},${dy} ${dx},${dy}`
    let lx = (sx + dx) / 2, ly = (sy + dy) / 2
    if (Math.abs(sy - dy) < NODE_H) ly -= NODE_H / 2 + 8   // 近水平边把标签抬到线上方
    return { edge: e, d, label: { x: lx, y: ly } }
  })

  // ── 8) 父子虚线:挂靠 → 垂直(子顶 → 父底);回退 → 水平(子左缘 → 父右缘,现状保留) ──
  const parentEdges: ParentEdgePath[] = []
  for (const n of nodes) {
    for (const [pid, slot] of n.parent_refs ?? []) {
      const child = boxById[n.node_id], parent = boxById[pid]
      if (!child || !parent) continue
      if (anchorByChild.has(n.node_id)) {
        // 垂直直线:子顶缘中点 → 父底缘(同一 x,方向 child → parent,箭头扎进父底)。
        // 直线终点切线 = 直线方向(向上),marker orient="auto" 自动指父;
        // 槽名 label 放虚线右侧(+8),避免白底文字盖住虚线。
        const cx = child.x + child.w / 2, cy = child.y                 // 子顶缘中点(起点)
        const py = parent.y + parent.h                                 // 父底缘(终点)
        const d = `M ${cx},${cy} L ${cx},${py}`
        parentEdges.push({ child: n, parent_id: pid, slot,
                           d, label: { x: cx + 8, y: (cy + py) / 2 } })
      } else {
        // 回退水平虚线:子左缘 → 父右缘 + VBEND 上弯(现状逐字节保留)
        const cx = child.x, cy = child.y + NODE_H / 2                  // 子左缘中点
        const px = parent.x + parent.w, py = parent.y + NODE_H / 2     // 父右缘中点
        const k = Math.max(28, (cx - px) * 0.5)                        // 向左外推控制点
        const d = `M ${cx},${cy} C ${cx - k},${cy - VBEND} ${px + k},${py - VBEND} ${px},${py}`
        let lx = (cx + px) / 2, ly = (cy + py) / 2
        if (Math.abs(cy - py) < NODE_H) ly -= NODE_H / 2 + 8           // 近水平边把标签抬到线上方
        parentEdges.push({ child: n, parent_id: pid, slot, d, label: { x: lx, y: ly } })
      }
    }
  }

  const width = PAD_X * 2 + colW.reduce((a, b) => a + b, 0) + gaps.reduce((a, b) => a + b, 0)
  const height = PAD_Y * 2 + contentH
  return { nodes: boxes, edges: edgePaths, parentEdges, width, height }
}
