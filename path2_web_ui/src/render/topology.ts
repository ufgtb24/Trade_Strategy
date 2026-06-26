// 拓扑图布局:从 nodes+edges 自动做 left→right 最长路径分层,
// 输出节点盒子(左上角坐标)+ 边曲线 SVG path + 标签锚点。
// 类型无关——只消费 TopoNode/TopoEdge 通用字段,不对具体 node_id / class_id 特判。
import type { TopoNode, TopoEdge } from '../types'

export interface NodeBox { node: TopoNode; x: number; y: number; w: number; h: number }
export interface EdgePath { edge: TopoEdge; d: string; label: { x: number; y: number } }
export interface TopoLayout { nodes: NodeBox[]; edges: EdgePath[]; width: number; height: number }

const NODE_H = 30
const HPAD = 12      // 节点左右内边距
const CH_W = 14      // 单字符估计宽(中文 @13px)
const COL_GAP = 96   // 层间水平间距下限(per-gap 自适应会按需上调)
const ROW_GAP = 30   // 层内垂直间距
const PAD_X = 14
const PAD_Y = 14
const LABEL_PAD = 24   // 边标签两端留白(避免贴节点/箭头)
const LBL_CJK = 12     // 边标签 CJK 字符估宽(rule @11px)
const LBL_ASCII = 7    // 边标签 ASCII 字符估宽

function estWidth(n: TopoNode): number {
  const chars = [...(n.label || n.node_id)].length   // 按 Unicode 码点,中文每字算 1
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

  // 1) 最长路径分层:无入边 → 0;否则 max(前驱 layer)+1
  const preds: Record<string, string[]> = {}
  for (const n of nodes) preds[n.node_id] = []
  for (const e of validEdges) preds[e.dst].push(e.src)

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
  for (const n of nodes) computeLayer(n.node_id, new Set())

  // 2) 分组(层内保持 nodes 出现序)
  const numLayers = nodes.length ? Math.max(...nodes.map((n) => layer[n.node_id])) + 1 : 0
  const byLayer: TopoNode[][] = Array.from({ length: numLayers }, () => [])
  for (const n of nodes) byLayer[layer[n.node_id]].push(n)

  // 3) 列宽 + per-gap 自适应层间距 + 列左缘 x
  const colW = byLayer.map((col) => Math.max(0, ...col.map(estWidth)))
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

  // 4) 层内垂直居中
  const stackH = byLayer.map((c) => c.length * NODE_H + Math.max(0, c.length - 1) * ROW_GAP)
  const contentH = Math.max(0, ...stackH)

  const boxById: Record<string, NodeBox> = {}
  const boxes: NodeBox[] = []
  for (let L = 0; L < numLayers; L++) {
    const startY = PAD_Y + (contentH - stackH[L]) / 2
    byLayer[L].forEach((n, i) => {
      const box: NodeBox = {
        node: n, x: colX[L], y: startY + i * (NODE_H + ROW_GAP), w: estWidth(n), h: NODE_H,
      }
      boxById[n.node_id] = box
      boxes.push(box)
    })
  }

  // 5) 边曲线 + 标签锚点
  const edgePaths: EdgePath[] = validEdges.map((e) => {
    const s = boxById[e.src], t = boxById[e.dst]
    const sx = s.x + s.w, sy = s.y + NODE_H / 2     // src 右缘中点
    const dx = t.x, dy = t.y + NODE_H / 2           // dst 左缘中点
    const k = Math.max(28, (dx - sx) * 0.5)         // 水平外推控制点
    const d = `M ${sx},${sy} C ${sx + k},${sy} ${dx - k},${dy} ${dx},${dy}`
    // 标签锚在路径中点。假设相邻层边(中点落在被撑宽的那段间隙内);
    // 若将来引入 skip-edge(span>1),中点可能压到中间节点列,届时需改锚定策略。
    let lx = (sx + dx) / 2, ly = (sy + dy) / 2
    if (Math.abs(sy - dy) < NODE_H) ly -= NODE_H / 2 + 8   // 近水平边把标签抬到线上方
    return { edge: e, d, label: { x: lx, y: ly } }
  })

  const width = PAD_X * 2 + colW.reduce((a, b) => a + b, 0) + gaps.reduce((a, b) => a + b, 0)
  const height = PAD_Y * 2 + contentH
  return { nodes: boxes, edges: edgePaths, width, height }
}
