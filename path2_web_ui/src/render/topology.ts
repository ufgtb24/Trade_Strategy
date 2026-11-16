// 拓扑图布局:业务边做 left→right 最长路径分层(水平轴),父子关系(parent_refs)画成父下面的
// 缩进树(├ └,同副图轨名的写法)——两轴正交:业务流水平读、结构包含往下读。
// 输出节点盒子(左上角坐标)+ 边曲线 SVG path + 标签锚点。
// 类型无关——只消费 TopoNode/TopoEdge 通用字段,不对具体 node_id 特判。
import type { TopoNode, TopoEdge } from '../types'

export interface NodeBox { node: TopoNode; x: number; y: number; w: number; h: number }
export interface EdgePath { edge: TopoEdge; d: string; label: { x: number; y: number } }
// 父子虚线边:被引用 node(child)与物化来源父(parent),label 是子在父里的位置名(槽名)。
// 挂靠形态是缩进树的一段(tree:主干 + 树杈,不带箭头,位置名写在树杈上);
// 回退形态水平(子左缘→父右缘,带箭头指向父)。
export interface ParentEdgePath {
  child: TopoNode; parent_id: string; slot: string; d: string; tree: boolean; label: { x: number; y: number }
}
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
// 缩进树(待验证):主干离父左缘 TRUNK_DX;树杈先引 BRANCH_LEAD 再写位置名,名后留 BRANCH_TAIL 接子左缘;
// 树里上下两行隔 TREE_ROW_GAP(位置名写在树杈上,行间不用再给标签留地方)
export const TRUNK_DX = 14
export const BRANCH_LEAD = 6
export const BRANCH_TAIL = 8
export const TREE_ROW_GAP = 10
const SLOT_CH = 6.2    // 位置名等宽 10px 字的单字宽(估)
const SLOT_PAD = 8     // 位置名左右内边距之和(同 .pelabel 的 padding)
const PAD_X = 14
const PAD_Y = 14
const LABEL_PAD = 24   // 边标签两端留白(避免贴节点/箭头)
const LBL_CJK = 12     // 边标签 CJK 字符估宽(rule @11px)
const LBL_ASCII = 7    // 边标签 ASCII 字符估宽

function estWidth(n: TopoNode): number {
  const chars = [...n.node_id].length   // 按 Unicode 码点,中文每字算 1
  return 2 * HPAD + chars * CH_W
}

/** 树杈上位置名的宽(估) */
export function slotWidth(slot: string): number {
  return [...slot].length * SLOT_CH + SLOT_PAD
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

  // ── 0/1) 挂靠分类:恰一父、父在图中、非自引用、非业务边端点 → 挂靠(画成父下面的缩进树);其余进水平流 ──
  // 子的子同样挂靠(树往里再缩一级);沿父链往上走回到自己(环)的,整条环退回水平流
  const candidates = new Map<string, { parentId: string; slot: string }>()
  for (const n of nodes) {
    const refs = n.parent_refs ?? []
    if (refs.length === 1
        && ids.has(refs[0][0])
        && refs[0][0] !== n.node_id
        && !businessEndpoints.has(n.node_id)) {
      candidates.set(n.node_id, { parentId: refs[0][0], slot: refs[0][1] })
    }
  }
  const anchorByChild = new Map<string, { parentId: string; slot: string }>()
  for (const [id, ref] of candidates) {
    const seen = new Set<string>([id])
    let up = ref.parentId
    let cyclic = false
    while (candidates.has(up)) {
      if (seen.has(up)) { cyclic = true; break }
      seen.add(up)
      up = candidates.get(up)!.parentId
    }
    if (!cyclic) anchorByChild.set(id, ref)
  }
  const flowNodes = nodes.filter((n) => !anchorByChild.has(n.node_id))
  const flowIds = new Set(flowNodes.map((n) => n.node_id))
  // 每个 node 的挂靠子,按 nodes 的先后(与副图轨名同序)
  const kidsOf = (id: string): TopoNode[] => nodes.filter((n) => anchorByChild.get(n.node_id)?.parentId === id)

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

  const numLayers = flowNodes.length ? Math.max(...flowNodes.map((n) => layer[n.node_id])) + 1 : 0
  const byLayer: TopoNode[][] = Array.from({ length: numLayers }, () => [])
  for (const n of flowNodes) byLayer[layer[n.node_id]].push(n)

  // ── 4/5) 块:一个水平流 node 连同它下面的缩进树;列宽取各块最宽,gaps/colX 按业务边标签 ──
  // 子 node 的左缘 = 父左缘 + 树杈缩进(主干 + 引线 + 位置名 + 尾段)
  const branchW = (slot: string): number => TRUNK_DX + BRANCH_LEAD + slotWidth(slot) + BRANCH_TAIL
  const blockW = (n: TopoNode): number =>
    Math.max(estWidth(n), ...kidsOf(n.node_id).map((k) => branchW(anchorByChild.get(k.node_id)!.slot) + blockW(k)))
  const blockH = (n: TopoNode): number =>
    NODE_H + kidsOf(n.node_id).reduce((h, k) => h + TREE_ROW_GAP + blockH(k), 0)
  const colW = byLayer.map((col) => Math.max(0, ...col.map(blockW)))
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

  // ── 6) 垂直布局(闭式解,无迭代):每层的块自上而下堆叠、整列竖直居中;块里的树按先序往下排 ──
  const colH = byLayer.map((col) => col.reduce((h, n) => h + blockH(n), 0) + Math.max(0, col.length - 1) * ROW_GAP)
  const contentH = Math.max(0, ...colH)

  const boxById: Record<string, NodeBox> = {}
  const boxes: NodeBox[] = []
  /** 把 n 放在 (x, y),它的子树接着往下排;返回这一块的底 */
  const place = (n: TopoNode, x: number, y: number): number => {
    const box: NodeBox = { node: n, x, y, w: estWidth(n), h: NODE_H }
    boxById[n.node_id] = box
    boxes.push(box)
    let bottom = y + NODE_H
    for (const k of kidsOf(n.node_id)) {
      bottom = place(k, x + branchW(anchorByChild.get(k.node_id)!.slot), bottom + TREE_ROW_GAP)
    }
    return bottom
  }
  for (let L = 0; L < numLayers; L++) {
    let y = PAD_Y + (contentH - colH[L]) / 2
    for (const n of byLayer[L]) y = place(n, colX[L], y) + ROW_GAP
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

  // ── 8) 父子关系:挂靠 → 缩进树(主干从父底往下,树杈横到子左缘,位置名写在树杈上);回退 → 水平虚线(现状保留) ──
  const parentEdges: ParentEdgePath[] = []
  for (const n of nodes) {
    for (const [pid, slot] of n.parent_refs ?? []) {
      const child = boxById[n.node_id], parent = boxById[pid]
      if (!child || !parent) continue
      if (anchorByChild.has(n.node_id)) {
        // 主干:父左缘 + TRUNK_DX 处竖直往下,接到这个子的中线;接上一个兄弟的中线(第一个子接父底),
        // 几段连起来就是 ├ … └。树杈:从主干横到子左缘。不带箭头(方向看缩进)
        const tx = parent.x + TRUNK_DX
        const cy = child.y + NODE_H / 2
        const sibs = kidsOf(pid)
        const i = sibs.findIndex((k) => k.node_id === n.node_id)
        const prevY = i > 0 ? boxById[sibs[i - 1].node_id].y + NODE_H / 2 : parent.y + NODE_H
        const d = `M ${tx},${prevY} L ${tx},${cy} L ${child.x},${cy}`
        parentEdges.push({ child: n, parent_id: pid, slot, d, tree: true, label: { x: tx + BRANCH_LEAD, y: cy } })
      } else {
        // 回退水平虚线:子左缘 → 父右缘 + VBEND 上弯(现状逐字节保留)
        const cx = child.x, cy = child.y + NODE_H / 2                  // 子左缘中点
        const px = parent.x + parent.w, py = parent.y + NODE_H / 2     // 父右缘中点
        const k = Math.max(28, (cx - px) * 0.5)                        // 向左外推控制点
        const d = `M ${cx},${cy} C ${cx - k},${cy - VBEND} ${px + k},${py - VBEND} ${px},${py}`
        let lx = (cx + px) / 2, ly = (cy + py) / 2
        if (Math.abs(cy - py) < NODE_H) ly -= NODE_H / 2 + 8           // 近水平边把标签抬到线上方
        parentEdges.push({ child: n, parent_id: pid, slot, d, tree: false, label: { x: lx, y: ly } })
      }
    }
  }

  const width = PAD_X * 2 + colW.reduce((a, b) => a + b, 0) + gaps.reduce((a, b) => a + b, 0)
  const height = PAD_Y * 2 + contentH
  return { nodes: boxes, edges: edgePaths, parentEdges, width, height }
}
