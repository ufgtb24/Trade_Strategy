/**
 * tier tag(spec 5.2、4.4):app 的 event 灰条右端挂的 tag,说这个 event 最深到了哪一档——
 * qualified_only(过了所在 node 的全部 where,但没进任何 hit)、detected_only(只是被检测出来)。
 * 进了 hit 的 event 画 node 本色,不挂 tag。顶栏 tiers 开关管它(app、compare 两档),默认开。
 *
 * 配色:tag 和 event 条同一种档位色——qualified 深灰 #9ca3af、detected 浅灰 #d1d5db(render/colors.ts 的 colorOf),
 * 不套琥珀;细黑实线边、黑字、等宽字体(tag 一律实线,虚线只表示用户画的)。
 * 位置:贴在 event 条右端外侧、和条同高;会压到同一行下一个 event 条、伸出图的右缘,或(compare 下)横跨用户框的
 * 竖边时不挂(条的灰色还在)。
 */
import type { Tier } from '../types'
import { colorOf } from './colors'

export type TierTagText = 'qualified_only' | 'detected_only'

/** event 的档位 → 它挂的 tag;进了 hit(matched)的不挂。 */
export function tierTagOf(tier: Tier): TierTagText | null {
  return tier === 'qualified' ? 'qualified_only' : tier === 'detected' ? 'detected_only' : null
}

/** tag 的底色:和同档的 event 条一样。 */
export function tierTagFill(text: TierTagText): string {
  return colorOf(text === 'qualified_only' ? 'qualified' : 'detected', null, {})
}

/** 悬停:tag 说的是什么。 */
export const TIER_TAG_TIP: Record<TierTagText, string> = {
  qualified_only: 'qualified: passed every where of its node, but in no hit',
  detected_only: 'detected: found by the detector, did not pass every where of its node',
}

export const TIER_TAG_GAP = 2           // tag 与 event 条右端、与下一个条之间留的空
const FONT = 8.5
const MONO = 'ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace'

/** tag 的宽度(按等宽字估算)。 */
export function tierTagWidth(text: TierTagText): number {
  return text.length * 5.3 + 5
}

/**
 * 一个 tag 的图形(ECharts custom series 的 group 子元素);放不下返回 null。
 * x:event 条右端;y、h:条的上沿与高;limit:tag 的右端不能越过的位置(tierTagLimit)。
 * 放得下与否随缩放变,renderItem 不挂时要原样返回 null:ECharts 收到 null 会删掉这条数据上次画的元素,
 * 收到空 group 却按下标合并子元素、什么也不删,上次缩放时画的 tag 会留在原来的像素位置上。
 */
export function tierTagShape(text: TierTagText, x: number, y: number, h: number, limit: number, opacity = 1): any | null {
  const w = tierTagWidth(text)
  const x0 = x + TIER_TAG_GAP
  if (x0 + w > limit - TIER_TAG_GAP) return null
  const th = Math.max(h + 2, FONT + 1)
  const ty = y + h / 2 - th / 2
  return {
    type: 'group', silent: true,
    children: [
      { type: 'rect', shape: { x: x0, y: ty, width: w, height: th, r: 1.5 },
        style: { fill: tierTagFill(text), stroke: '#111', lineWidth: 0.6, opacity } },
      { type: 'text', style: { text, x: x0 + 2.5, y: ty + th / 2, verticalAlign: 'middle',
                               font: `${FONT}px ${MONO}`, fill: '#111', opacity } },
    ],
  }
}

/** tag 的右端不能越过的位置:同一行下一个 event 条的左端(next 是它的起点下标,-1 = 没有)与图的右缘取小。
 *  api、coordSys 是 ECharts custom series renderItem 拿到的。 */
export function tierTagLimit(api: any, coordSys: { x: number; width: number }, next: number): number {
  return Math.min(coordSys.x + coordSys.width, next >= 0 ? api.coord([next, 0])[0] - api.size([1, 0])[0] / 2 : Infinity)
}

/** 同一行里每个 event 条的下一个条的起点(没有为 -1):tag 据此让开。items 的 key 相同的算同一行。 */
export function nextStarts(items: readonly { key: string; start: number; end: number }[]): number[] {
  const out = new Array<number>(items.length).fill(-1)
  const byKey = new Map<string, number[]>()
  items.forEach((it, i) => { if (!byKey.has(it.key)) byKey.set(it.key, []); byKey.get(it.key)!.push(i) })
  for (const idx of byKey.values()) {
    idx.sort((a, b) => items[a].start - items[b].start || items[a].end - items[b].end)
    for (let k = 0; k < idx.length; k++) {
      const me = items[idx[k]]
      const nxt = idx.slice(k + 1).find(j => items[j].start > me.end)
      out[idx[k]] = nxt === undefined ? -1 : items[nxt].start
    }
  }
  return out
}
