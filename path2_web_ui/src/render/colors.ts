// node 色确定性派生(spec §8.3):event_styles 是 node_id 粒度;
// 同 node_id 多 node 用明度区分,按 topology.nodes 出现序生成;单 node 直接用原色。
import type { Topology, Tier } from '../types'

const NEUTRAL = '#888888'

export function hexToHsl(hex: string): [number, number, number] {
  const m = hex.replace('#', '')
  const r = parseInt(m.slice(0, 2), 16) / 255
  const g = parseInt(m.slice(2, 4), 16) / 255
  const b = parseInt(m.slice(4, 6), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0
  const l = (max + min) / 2
  const d = max - min
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1))
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
    if (h < 0) h += 360
  }
  return [h, s, l]
}

function hslToHex(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const mm = l - c / 2
  let r = 0, g = 0, b = 0
  if (h < 60) [r, g, b] = [c, x, 0]
  else if (h < 120) [r, g, b] = [x, c, 0]
  else if (h < 180) [r, g, b] = [0, c, x]
  else if (h < 240) [r, g, b] = [0, x, c]
  else if (h < 300) [r, g, b] = [x, 0, c]
  else [r, g, b] = [c, 0, x]
  const to = (v: number) => Math.round((v + mm) * 255).toString(16).padStart(2, '0')
  return `#${to(r)}${to(g)}${to(b)}`
}

/** 三档配色:matched=node 本色(缺色兜底 NEUTRAL)/ qualified=深灰 / detected=浅灰。 */
export function colorOf(tier: Tier, node: string | null, nodeColors: Record<string, string>): string {
  if (tier === 'matched') return (node && nodeColors[node]) || NEUTRAL
  if (tier === 'qualified') return '#9ca3af'
  return '#d1d5db'
}

/** topology + event_styles → { node_id: hexColor }。
 *  实例化契约:样式键 = node_id(Task 5 静态层按 node_id setdefault)。分组键由 node_id;
 *  同色(共享同一 event_styles 值)的多 node 用明度区分,单 node 直接用原色。 */
export function deriveNodeColors(topology: Topology, eventStyles: Record<string, string>): Record<string, string> {
  const byColor: Record<string, string[]> = {}
  for (const n of topology.nodes) {
    const base = eventStyles[n.node_id] ?? NEUTRAL
    ;(byColor[base] ??= []).push(n.node_id)
  }
  const out: Record<string, string> = {}
  for (const [base, nodes] of Object.entries(byColor)) {
    if (nodes.length === 1) {
      out[nodes[0]] = base
      continue
    }
    const [h, s, l] = hexToHsl(base)
    // 多 node 同色:明度在 base 附近确定性散开([l-0.18, l+0.18] 线性)
    nodes.forEach((rid, i) => {
      const t = i / (nodes.length - 1)   // 0..1
      const ll = Math.min(0.85, Math.max(0.25, l - 0.18 + t * 0.36))
      out[rid] = hslToHex(h, s, ll)
    })
  }
  return out
}
