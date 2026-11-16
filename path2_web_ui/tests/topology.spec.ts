import { describe, it, expect } from 'vitest'
import { BRANCH_LEAD, BRANCH_TAIL, TREE_ROW_GAP, TRUNK_DX, layoutTopology, slotWidth } from '../src/render/topology'
import type { TopoLayout } from '../src/render/topology'
import type { TopoNode, TopoEdge } from '../src/types'

function node(node_id: string, produced_by?: string, child_slot?: string,
              parent_refs?: [string, string][]): TopoNode {
  return { node_id, where_rules: [],
           produced_by: produced_by ?? null, child_slot: child_slot ?? null,
           // 兼容:给了 produced_by 则自动转 parent_refs(子结构 node 必被父 children 引用)
           parent_refs: parent_refs ?? (produced_by ? [[produced_by, child_slot ?? '']] : []) }
}

// bottom_burst 的 4 节点 DAG:down/side → bo → tb
const NODES: TopoNode[] = [
  node('down'),
  node('side'),
  node('bo'),
  node('tb'),
]
const EDGES: TopoEdge[] = [
  { src: 'down', dst: 'bo', kind: 'TemporalEdge', rule: 'before · gap∈[1,120]' },
  { src: 'side', dst: 'bo', kind: 'ContainmentEdge', rule: 'contains' },
  { src: 'bo', dst: 'tb', kind: 'TemporalEdge', rule: 'gap=1' },
]
const xOf = (nodes: { node: TopoNode; x: number }[], id: string) =>
  nodes.find((b) => b.node.node_id === id)!.x
const yOf = (nodes: { node: TopoNode; y: number }[], id: string) =>
  nodes.find((b) => b.node.node_id === id)!.y

describe('layoutTopology', () => {
  it('layers left→right: down/side same column, bo middle, tb rightmost', () => {
    const { nodes } = layoutTopology(NODES, EDGES)
    expect(xOf(nodes, 'down')).toBe(xOf(nodes, 'side'))        // 源同层
    expect(xOf(nodes, 'bo')).toBeGreaterThan(xOf(nodes, 'down')) // 汇聚在右
    expect(xOf(nodes, 'tb')).toBeGreaterThan(xOf(nodes, 'bo'))   // 终点最右
  })

  it('returns one box per node, referencing the original node', () => {
    const { nodes } = layoutTopology(NODES, EDGES)
    expect(nodes.length).toBe(4)
    const bo = nodes.find((b) => b.node.node_id === 'bo')!
    expect(bo.w).toBeGreaterThan(2 * 12)  // w = 2*HPAD + chars*CH_W > bare padding
    expect(bo.h).toBe(30)
  })

  it('emits one curved path per edge, endpoints aligned to node edges', () => {
    const { nodes, edges } = layoutTopology(NODES, EDGES)
    expect(edges.length).toBe(3)
    const e = edges.find((x) => x.edge.src === 'down' && x.edge.dst === 'bo')!
    expect(e.d.startsWith('M ')).toBe(true)
    expect(e.d).toContain('C')                                  // 三次贝塞尔曲线
    const down = nodes.find((b) => b.node.node_id === 'down')!
    const bo = nodes.find((b) => b.node.node_id === 'bo')!
    expect(e.d).toContain(`M ${down.x + down.w},`)              // 起点 x = src 右缘
    const endX = e.d.split(' ').pop()!.split(',')[0]            // 终点 "dx,dy" 的 dx
    expect(endX).toBe(String(bo.x))                             // 终点 x = dst 左缘(不依赖具体高度常量)
    expect(e.edge.rule).toBe('before · gap∈[1,120]')           // 原边引用保留
  })

  it('ignores edges referencing unknown nodes', () => {
    const { edges } = layoutTopology(NODES, [
      ...EDGES,
      { src: 'ghost', dst: 'bo', kind: 'TemporalEdge', rule: 'x' },
    ])
    expect(edges.length).toBe(3)
  })

  it('is deterministic: same input → identical output', () => {
    expect(layoutTopology(NODES, EDGES)).toEqual(layoutTopology(NODES, EDGES))
  })

  it('overall size is positive', () => {
    const { width, height } = layoutTopology(NODES, EDGES)
    expect(width).toBeGreaterThan(0)
    expect(height).toBeGreaterThan(0)
  })
})

describe('layoutTopology — type-agnostic generalization', () => {
  const node = (id: string): TopoNode =>
    ({ node_id: id, where_rules: [] })
  const edge = (src: string, dst: string): TopoEdge =>
    ({ src, dst, kind: 'TemporalEdge', rule: '' })
  const colX = (nodes: { node: TopoNode; x: number }[], id: string) =>
    nodes.find((b) => b.node.node_id === id)!.x

  it('linear chain a→b→c yields 3 strictly increasing columns', () => {
    const { nodes } = layoutTopology(
      [node('a'), node('b'), node('c')],
      [edge('a', 'b'), edge('b', 'c')],
    )
    expect(colX(nodes, 'a')).toBeLessThan(colX(nodes, 'b'))
    expect(colX(nodes, 'b')).toBeLessThan(colX(nodes, 'c'))
  })

  it('diamond a→b,a→c,b→d,c→d: b/c share a column, d sits at max(pred)+1', () => {
    const { nodes } = layoutTopology(
      [node('a'), node('b'), node('c'), node('d')],
      [edge('a', 'b'), edge('a', 'c'), edge('b', 'd'), edge('c', 'd')],
    )
    expect(colX(nodes, 'a')).toBeLessThan(colX(nodes, 'b'))
    expect(colX(nodes, 'b')).toBe(colX(nodes, 'c'))            // 同层
    expect(colX(nodes, 'd')).toBeGreaterThan(colX(nodes, 'b')) // 汇聚在最右
  })

  it('single isolated node lays out without edges', () => {
    const { nodes, edges } = layoutTopology([node('solo')], [])
    expect(nodes.length).toBe(1)
    expect(edges.length).toBe(0)
  })

  it('skip edge a→b→c plus a→c: c sits at longest-path layer (right of b), not BFS layer', () => {
    const { nodes } = layoutTopology(
      [node('a'), node('b'), node('c')],
      [edge('a', 'b'), edge('b', 'c'), edge('a', 'c')],
    )
    expect(colX(nodes, 'c')).toBeGreaterThan(colX(nodes, 'b')) // max(pred)+1, not min
  })
})

describe('layoutTopology — adaptive column gap fits edge labels', () => {
  const n = (id: string): TopoNode =>
    ({ node_id: id, where_rules: [] })
  const ed = (src: string, dst: string, rule: string): TopoEdge =>
    ({ src, dst, kind: 'TemporalEdge', rule })
  // src 右缘 → dst 左缘的横向距离 = 这条边可用来放标签的长度
  const gapBetween = (L: TopoLayout, srcId: string, dstId: string) => {
    const s = L.nodes.find((b) => b.node.node_id === srcId)!
    const d = L.nodes.find((b) => b.node.node_id === dstId)!
    return d.x - (s.x + s.w)
  }

  it('a long edge label produces a wider gap than a short one', () => {
    const long = layoutTopology([n('a'), n('b')], [ed('a', 'b', 'before · gap∈[1,120]')])
    const short = layoutTopology([n('a'), n('b')], [ed('a', 'b', 'x')])
    expect(gapBetween(long, 'a', 'b')).toBeGreaterThan(gapBetween(short, 'a', 'b'))
  })

  it('the widened gap is at least as wide as the label text (conservative)', () => {
    const long = layoutTopology([n('a'), n('b')], [ed('a', 'b', 'before · gap∈[1,120]')])
    // 20 字符标签,保守按每字符 6px 估 → 间隙应 ≥ 120px(远超固定 96)
    expect(gapBetween(long, 'a', 'b')).toBeGreaterThanOrEqual('before · gap∈[1,120]'.length * 6)
  })

  it('a short label falls back to the base minimum gap (no needless widening)', () => {
    const short = layoutTopology([n('a'), n('b')], [ed('a', 'b', 'x')])
    expect(gapBetween(short, 'a', 'b')).toBe(96)   // COL_GAP 下限
  })

  it('only the spanned gap widens; sibling gaps stay at the minimum', () => {
    const L = layoutTopology(
      [n('a'), n('b'), n('c')],
      [ed('a', 'b', 'before · gap∈[1,120]'), ed('b', 'c', 'x')],
    )
    expect(gapBetween(L, 'a', 'b')).toBeGreaterThan(gapBetween(L, 'b', 'c'))
    expect(gapBetween(L, 'b', 'c')).toBe(96)
  })

  it('is deterministic with adaptive gaps', () => {
    const nodes = [n('a'), n('b')]
    const edges = [ed('a', 'b', 'before · gap∈[1,120]')]
    expect(layoutTopology(nodes, edges)).toEqual(layoutTopology(nodes, edges))
  })

  it('a multi-layer skip-edge averages its label width across the spanned gaps', () => {
    // a→b→c 链 + a→c skip-edge(span=2)带超长标签;长标签宽均摊到两段间隙
    const longRule = 'x'.repeat(40)   // estLabelWidth ≈ 280 → 均摊每段 (280+24)/2 = 152 > 96 base
    const L = layoutTopology(
      [n('a'), n('b'), n('c')],
      [ed('a', 'b', 'x'), ed('b', 'c', 'x'), ed('a', 'c', longRule)],
    )
    const gAB = gapBetween(L, 'a', 'b')
    const gBC = gapBetween(L, 'b', 'c')
    expect(gAB).toBeGreaterThan(96)              // skip-edge 把两段都撑过 base
    expect(gBC).toBeGreaterThan(96)
    expect(gAB).toBe(gBC)                          // 均摊对称:两段等宽
    expect(gAB).toBeLessThan(longRule.length * 7) // < 全标签宽 → 证明是均摊而非给单段全宽
  })

  it('a CJK edge label yields a wider gap than an ASCII label of the same length', () => {
    const cjk = layoutTopology([n('a'), n('b')], [ed('a', 'b', '一二三四五六七八九十甲乙')])  // 12 CJK
    const ascii = layoutTopology([n('a'), n('b')], [ed('a', 'b', 'abcdefghijkl')])             // 12 ASCII
    expect(gapBetween(cjk, 'a', 'b')).toBeGreaterThan(gapBetween(ascii, 'a', 'b'))  // CJK 12px > ASCII 7px/字
  })

  it('anchors a sub-structure node in an indented tree below its parent', () => {
    const L = layoutTopology(
      [node('bo'), node('tb'), node('tb_seg', 'tb', 'segments')],
      [ed('bo', 'tb', 'gap=1')],
    )
    const c = L.nodes.find((b) => b.node.node_id === 'tb_seg')!
    const p = L.nodes.find((b) => b.node.node_id === 'tb')!
    expect(c.x).toBe(p.x + TRUNK_DX + BRANCH_LEAD + slotWidth('segments') + BRANCH_TAIL)   // 缩进:主干 + 树杈 + 位置名
    expect(c.y).toBe(p.y + p.h + TREE_ROW_GAP)                       // 紧接在父下面
    expect(xOf(L.nodes, 'tb')).toBeGreaterThan(xOf(L.nodes, 'bo'))  // 业务边分层不受影响
  })

  it('draws a tree edge: trunk down from the parent bottom, branch across to the child, slot name on the branch, no arrow', () => {
    const L = layoutTopology([node('tb'), node('tb_seg', 'tb', 'segments')], [])
    expect(L.parentEdges).toHaveLength(1)
    const pe = L.parentEdges[0]
    expect([pe.child.node_id, pe.parent_id, pe.slot, pe.tree]).toEqual(['tb_seg', 'tb', 'segments', true])
    const c = L.nodes.find((b) => b.node.node_id === 'tb_seg')!
    const p = L.nodes.find((b) => b.node.node_id === 'tb')!
    const tx = p.x + TRUNK_DX, cy = c.y + c.h / 2
    expect(pe.d).toBe(`M ${tx},${p.y + p.h} L ${tx},${cy} L ${c.x},${cy}`)
    expect(pe.label).toEqual({ x: tx + BRANCH_LEAD, y: cy })       // 位置名在树杈上,左缘离主干 BRANCH_LEAD
    expect(pe.label.x + slotWidth('segments')).toBeLessThanOrEqual(c.x)   // 不压到子 node 上
  })

  it('new_step: four children of one parent each get their own row and branch; nothing overlaps', () => {
    const kids = [['old_plat', 'old'], ['step', 'step'], ['new_plat', 'new'], ['today', 'today']] as const
    const L = layoutTopology([node('plateau'), ...kids.map(([id, slot]) => node(id, 'plateau', slot))], [])
    const p = L.nodes.find((b) => b.node.node_id === 'plateau')!
    const rows = kids.map(([id]) => L.nodes.find((b) => b.node.node_id === id)!)
    // 按 nodes 的先后(同副图轨名)一行一个,上下不重叠
    for (let i = 1; i < rows.length; i++) expect(rows[i].y).toBe(rows[i - 1].y + rows[i - 1].h + TREE_ROW_GAP)
    // 每条树杈的横线各在自己那一行的中线上(不再有两条线重合);主干接上一个兄弟的中线
    const edges = kids.map(([id]) => L.parentEdges.find((e) => e.child.node_id === id)!)
    const tx = p.x + TRUNK_DX
    edges.forEach((e, i) => {
      const cy = rows[i].y + rows[i].h / 2
      const prevY = i === 0 ? p.y + p.h : rows[i - 1].y + rows[i - 1].h / 2
      expect(e.d).toBe(`M ${tx},${prevY} L ${tx},${cy} L ${rows[i].x},${cy}`)
      expect(e.label.y).toBe(cy)
    })
    expect(new Set(edges.map((e) => e.d)).size).toBe(4)
    // 位置名不压到任何 node 框上
    for (const e of edges) {
      const [x0, x1] = [e.label.x, e.label.x + slotWidth(e.slot)]
      for (const b of L.nodes) {
        const overlapX = x0 < b.x + b.w && x1 > b.x
        const overlapY = e.label.y > b.y && e.label.y < b.y + b.h
        expect(overlapX && overlapY).toBe(false)
      }
    }
  })

  it('a child of a child is indented one level further', () => {
    const L = layoutTopology([node('a'), node('b', 'a', 's'), node('c', 'b', 't')], [])
    const [a, b, c] = ['a', 'b', 'c'].map((id) => L.nodes.find((x) => x.node.node_id === id)!)
    expect(b.x).toBeGreaterThan(a.x)
    expect(c.x).toBeGreaterThan(b.x)
    expect(c.y).toBe(b.y + b.h + TREE_ROW_GAP)
    expect(L.parentEdges.every((e) => e.tree)).toBe(true)
  })

  it('a parent cycle falls back to the flow (no infinite tree)', () => {
    const L = layoutTopology([node('a', undefined, undefined, [['b', 's']]), node('b', undefined, undefined, [['a', 't']])], [])
    expect(L.nodes).toHaveLength(2)
    expect(L.parentEdges.every((e) => !e.tree)).toBe(true)
  })

  it('emits no parent edge for ordinary nodes', () => {
    const L = layoutTopology([node('a'), node('b')], [ed('a', 'b', 'x')])
    expect(L.parentEdges).toEqual([])
  })

  it('anchors a standalone node referenced by a container below it (bo → burst)', () => {
    // 情况一:burst children={"members": "bo"}——bo 是独立 node 但被容器引用;无业务边 → 挂靠
    const L = layoutTopology(
      [node('burst'), node('bo', undefined, undefined, [['burst', 'members']]), node('tb')],
      [ed('burst', 'tb', 'gap=1')],
    )
    const pe = L.parentEdges.find((p) => p.child.node_id === 'bo')
    expect(pe?.parent_id).toBe('burst')
    expect(pe?.slot).toBe('members')
    expect(pe?.tree).toBe(true)                                  // 独立 node 也挂在父下面的缩进树里
    const c = L.nodes.find((b) => b.node.node_id === 'bo')!
    const p = L.nodes.find((b) => b.node.node_id === 'burst')!
    expect(c.x).toBe(p.x + TRUNK_DX + BRANCH_LEAD + slotWidth('members') + BRANCH_TAIL)
    expect(c.y).toBe(p.y + p.h + TREE_ROW_GAP)
  })

  it('keeps a referenced business-edge endpoint in the flow with a horizontal parent edge (fallback)', () => {
    // 回退:bo 是业务边端点(down→bo、bo→tb)→ 不挂靠,留水平流(父后列),虚线水平画法
    const L = layoutTopology(
      [node('burst'), node('bo', undefined, undefined, [['burst', 'members']]),
       node('down'), node('tb')],
      [ed('down', 'bo', 'x'), ed('bo', 'tb', 'gap=1')],
    )
    const pe = L.parentEdges.find((p) => p.child.node_id === 'bo')
    expect(pe?.parent_id).toBe('burst')
    expect(xOf(L.nodes, 'bo')).toBeGreaterThan(xOf(L.nodes, 'burst'))  // 仍在水平流、父后列
    const c = L.nodes.find((b) => b.node.node_id === 'bo')!
    const p = L.nodes.find((b) => b.node.node_id === 'burst')!
    expect(pe!.d.startsWith(`M ${c.x},${c.y + c.h / 2}`)).toBe(true)     // 水平画法:子左缘中点
    expect(pe!.d.endsWith(`${p.x + p.w},${p.y + p.h / 2}`)).toBe(true)   // 父右缘中点
    expect(pe!.tree).toBe(false)
  })

  it('a parent that is not the last node of its layer keeps its tree; the next node in that layer stacks below the tree', () => {
    const L = layoutTopology(
      [node('a'), node('c'), node('b'), node('x', undefined, undefined, [['a', 's']])],
      [ed('a', 'b', 'x'), ed('c', 'b', 'x')],
    )
    const [a, c, x] = ['a', 'c', 'x'].map((id) => L.nodes.find((n) => n.node.node_id === id)!)
    expect(x.x).toBeGreaterThan(a.x)                       // x 缩进挂在 a 下面
    expect(x.y).toBe(a.y + a.h + TREE_ROW_GAP)
    expect(c.x).toBe(a.x)                                  // c 和 a 同一列
    expect(c.y).toBeGreaterThan(x.y + x.h)                 // 排在 a 那一整块下面,不压树
    expect(L.parentEdges.find((p) => p.child.node_id === 'x')!.tree).toBe(true)
  })

})
