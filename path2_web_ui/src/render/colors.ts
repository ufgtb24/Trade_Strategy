// node 色(spec §8.3):event_styles 是 node_id 粒度,每个 node 直接用它的原色。
// 后端兜底调色板是中蓝 / 大红两色交替(path2_web/serialize.py 的 _PALETTE),隔一条轨同色是有意的,
// 这里不为同色 node 散开明度。
import type { Topology, Tier } from '../types'

const NEUTRAL = '#888888'

/**
 * 两档灰(对白底与副图隔行底 BAND_STRIPE_FILL ≈ #ebebeb 的对比,看图的用户靠深浅分色):
 * - qualified 深灰 #9ca3af:对隔行底 2.1;
 * - detected 浅灰 #b4bac2:对隔行底 1.64、对白底 1.95(再浅的灰,例如对隔行底只有 1.4 的,矮格压在隔行底上几乎看不见);
 *   比 qualified 浅(两者之间 1.3),深浅顺序 in_hit > qualified > detected 不变,两档主要靠格高(TIER_H)分开。
 */
export const QUALIFIED_GRAY = '#9ca3af'
export const DETECTED_GRAY = '#b4bac2'

/** 三档配色:in_hit=node 本色(缺色兜底 NEUTRAL)/ qualified=深灰 / detected=浅灰。 */
export function colorOf(tier: Tier, node: string | null, nodeColors: Record<string, string>): string {
  if (tier === 'in_hit') return (node && nodeColors[node]) || NEUTRAL
  if (tier === 'qualified') return QUALIFIED_GRAY
  return DETECTED_GRAY
}

/** topology + event_styles → { node_id: hexColor }。键 = node_id;缺色的 node 落 NEUTRAL。
 *  同色的多个 node 保持同色(两色交替的调色板本来就让隔一条轨的 node 同色)。 */
export function deriveNodeColors(topology: Topology, eventStyles: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const n of topology.nodes) out[n.node_id] = eventStyles[n.node_id] ?? NEUTRAL
  return out
}

/**
 * 同一个颜色深一档:各通道朝黑色收 k(0..1)。有关的方块的细边用它(render/selHighlight.ts 的 relatedEdgeColor),
 * 靠深浅和方块本色拉开、色相不变;认不出的写法(非 #rgb / #rrggbb)原样返回。
 */
export function darken(hex: string, k: number): string {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return hex
  const h = m[1].length === 3 ? [...m[1]].map(c => c + c).join('') : m[1]
  const ch = [0, 2, 4].map(i => Math.round(parseInt(h.slice(i, i + 2), 16) * (1 - k)))
  return `#${ch.map(v => v.toString(16).padStart(2, '0')).join('')}`
}
