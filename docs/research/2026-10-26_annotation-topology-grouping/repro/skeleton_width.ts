// 用现有拓扑面板的布局函数(未改动)画「用户骨架」：节点名 = 用户的词、边只有先后、无规则文本、套框挂在父下。
// 量整图宽度，看放不放得进 380px 侧栏(扣两侧 10px 内边距约 360px)。
// 运行：path2_web_ui/node_modules/.bin/vite-node docs/research/2026-10-26_annotation-topology-grouping/repro/skeleton_width.ts
import { layoutTopology } from '../../../../path2_web_ui/src/render/topology'

type Sk = { chain: string[]; nested?: Record<string, string> }   // nested: 子 → 父
const cases: Record<string, Sk> = {
  '横盘(缩量)→放量突破→回踩': { chain: ['横盘', '放量突破', '回踩'], nested: { 缩量: '横盘' } },
  '同上 + 买点▲': { chain: ['横盘', '放量突破', '回踩', '▲'], nested: { 缩量: '横盘' } },
  '下跌→底部(W形低点)→放量突破→回踩→企稳': { chain: ['下跌', '底部', '放量突破', '回踩', '企稳'], nested: { W形低点: '底部' } },
}
for (const [k, sk] of Object.entries(cases)) {
  const nodes: any[] = [...sk.chain, ...Object.keys(sk.nested ?? {})].map((id) => ({
    node_id: id, parent_refs: sk.nested?.[id] ? [[sk.nested[id], '']] : [], produced_by: null,
  }))
  const edges: any[] = sk.chain.slice(1).map((d, i) => ({ src: sk.chain[i], dst: d, kind: '', rule: '' }))
  const L = layoutTopology(nodes, edges)
  console.log(`${k}: width=${Math.round(L.width)} height=${Math.round(L.height)}`)
}
