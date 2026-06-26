import { describe, it, expect } from 'vitest'
import { layoutTopology } from '../src/render/topology'
import type { TopoLayout } from '../src/render/topology'
import type { TopoNode, TopoEdge } from '../src/types'

function node(node_id: string, label: string): TopoNode {
  return { node_id, class_id: 't', label, source_tag: node_id, where_rules: [] }
}

// bottom_breakout_burst 的 4 节点 DAG:down/side → bo → tb
const NODES: TopoNode[] = [
  node('down', '下跌段'),
  node('side', '横盘段'),
  node('bo', '突破点串'),
  node('tb', '回踩确认'),
]
const EDGES: TopoEdge[] = [
  { src: 'down', dst: 'bo', kind: 'TemporalEdge', rule: 'before · gap∈[1,120]' },
  { src: 'side', dst: 'bo', kind: 'ContainmentEdge', rule: 'contains' },
  { src: 'bo', dst: 'tb', kind: 'TemporalEdge', rule: 'gap=1' },
]
const xOf = (nodes: { node: TopoNode; x: number }[], id: string) =>
  nodes.find((b) => b.node.node_id === id)!.x

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
    expect(bo.node.label).toBe('突破点串')
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
    ({ node_id: id, class_id: 't', label: id.toUpperCase(), source_tag: id, where_rules: [] })
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
    ({ node_id: id, class_id: 't', label: id, source_tag: id, where_rules: [] })
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
})
