/**
 * compare 下 hits 行底部的反馈带(spec 6.13「图上」):这只股票、当前 pattern 的每条反馈一个横跨 [start, end] 的记号,
 * 几条范围交叠时错行(render/geometry.ts 的 packLanes),不叠压。本文件只管数据:日期 → K 线下标、错行、配色档、
 * 悬停文字、字放不放得下;画法在 render/chart.ts(makeRenderFeedbackMark),行高与带的顶在 render/subGeometry.ts。
 *
 * - 只画用户自己挑的(source = picked):盲看标记(6.5)不在这里画,也打不开面板(stores/feedback.ts 的 openRecord);
 * - 配色档只照后端状态接口给的 red(朱红与否只在后端判一次):red → 朱红底黑字;其余(含状态还没取到)→ 常色,
 *   白底深灰描边黑字。hits 区底色是浅黄,常色靠描边认,不靠白底。页面上的状态只有 matched / unmatched
 *   (「起点认不出」在后端已并进 unmatched,见 path2_web/annotation/match.py 的 shown_status);
 * - 选中的那条(feedbackMarkStyle):描边换成黑色并明显加粗(加粗的部分画在记号外侧,不挤字),压在别的记号上面;图上另有一条贯穿主副图的竖带
 *   标出它的日期范围(components/KlineChart.vue);
 * - 记号上的字(feedbackLabelText)是点出的 node 名,逗号连起来;整串放不下时退成「第一个 node 名加 +n」
 *   (n 是没写出来的个数),再放不下或一个 node 都没点就只画记号,内容靠悬停看;
 * - 悬停文字不写任何「旧版本 / 过期」提示(反馈不过期,1.11);nodes 里当前拓扑已没有的 node 原样显示;
 * - 以前存下的记录上的 answer、dag 不上记号、不进悬停。
 */
import type { AnnFeedback } from '../annotate/model'
import type { FeedbackStatusOf } from '../annotate/feedback'
import { endIndex, startIndex } from '../annotate/boxGeometry'
import { packLanes } from './geometry'
import { VERMILION } from './annotateLanes'
import { MONO } from './fonts'

/** 反馈带系列名(副图点击按它分流;e2e 也按它找) */
export const FEEDBACK_SERIES = 'feedback-strip'

/** 配色档:常色 / 朱红(app 和你相反) */
export type FeedbackTone = 'plain' | 'red'

/** 反馈带上的一个记号:K 线下标范围、错行后的行号、点出的 node(记号上的字由它来)、配色档、选没选中。 */
export interface FeedbackMark {
  id: string
  start: number
  end: number
  lane: number
  nodes: string[]
  tone: FeedbackTone
  selected: boolean
}

/** 记号的底色与描边(字一律黑)。常色描边是中等深度的深灰;朱红底也描同一种深灰 */
export const FEEDBACK_EDGE = '#555555'
export const FEEDBACK_TONE: Record<FeedbackTone, { fill: string; stroke: string }> = {
  plain: { fill: '#ffffff', stroke: FEEDBACK_EDGE },
  red: { fill: VERMILION, stroke: FEEDBACK_EDGE },
}
export const FEEDBACK_STROKE_W = 1.5
/** 选中的记号:黑色粗边(不论哪一档),比平常的描边粗一倍多 */
export const FEEDBACK_SELECTED_EDGE = '#000000'
export const FEEDBACK_SELECTED_STROKE_W = 3.5
/** 选中的记号向外扩的量:粗边多出来的部分全画在记号外侧,里面留给字的地方和没选中时一样 */
export const FEEDBACK_SELECTED_OUTSET = (FEEDBACK_SELECTED_STROKE_W - FEEDBACK_STROKE_W) / 2
/** 记号在一行里上下各留的空(行高 FEEDBACK_ROW_H 减两倍即记号高) */
export const FEEDBACK_MARK_PAD = 1.5
export const FEEDBACK_FONT_PX = 10
/** 字距记号左边的空 */
export const FEEDBACK_TEXT_PAD = 3

/** 记号的画法:底色照配色档;描边平常照配色档、细,选中时一律黑色粗边。 */
export function feedbackMarkStyle(m: Pick<FeedbackMark, 'tone' | 'selected'>): { fill: string; stroke: string; lineWidth: number } {
  const tone = FEEDBACK_TONE[m.tone]
  return m.selected
    ? { fill: tone.fill, stroke: FEEDBACK_SELECTED_EDGE, lineWidth: FEEDBACK_SELECTED_STROKE_W }
    : { fill: tone.fill, stroke: tone.stroke, lineWidth: FEEDBACK_STROKE_W }
}

/** 配色档:只照后端给的 red;没取到状态按常色。 */
export function feedbackTone(st: FeedbackStatusOf | null | undefined): FeedbackTone {
  return st?.red ? 'red' : 'plain'
}

/** 日期范围 → K 线下标范围(起点取当天或之后第一根,终点取当天或之前最后一根);整段落在 K 线外时为 null。 */
export function dateSpanToIdx(dates: readonly string[], start: string, end: string): [number, number] | null {
  if (!dates.length || start > end || start > dates[dates.length - 1] || end < dates[0]) return null
  const s = startIndex(dates, start)
  const e = endIndex(dates, end)
  return s <= e ? [s, e] : null
}

/**
 * 这只股票当前 pattern 的反馈 → 反馈带上的记号(已错行)。只取用户自己挑的;落不到 K 线上的丢掉。
 * 错行:按起点先后贪心放进第一条放得下的行(范围交叠的不同行)。
 */
export function feedbackMarks(list: readonly AnnFeedback[], dates: readonly string[],
                              statusById: Readonly<Record<string, FeedbackStatusOf | undefined>>,
                              selectedId: string | null): FeedbackMark[] {
  const spans: { start_idx: number; end_idx: number; fb: AnnFeedback }[] = []
  for (const fb of list) {
    if (fb.source !== 'picked') continue
    const span = dateSpanToIdx(dates, fb.start, fb.end)
    if (span) spans.push({ start_idx: span[0], end_idx: span[1], fb })
  }
  return packLanes(spans).map(({ start_idx, end_idx, lane, fb }) => ({
    id: fb.id, start: start_idx, end: end_idx, lane, nodes: [...(fb.nodes ?? [])],
    tone: feedbackTone(statusById[fb.id]), selected: fb.id === selectedId,
  }))
}

/** 反馈带的行数(没有记号为 0)。 */
export function feedbackRowCount(marks: readonly FeedbackMark[]): number {
  return marks.length ? Math.max(...marks.map((m) => m.lane)) + 1 : 0
}

/** 字(等宽)写在宽 widthPx 的记号里放不放得下:按等宽字宽约 0.62 个字号估。 */
export function feedbackLabelFits(label: string, widthPx: number): boolean {
  return label.length * FEEDBACK_FONT_PX * 0.62 + 2 * FEEDBACK_TEXT_PAD <= widthPx
}

/**
 * 宽 widthPx 的记号上写什么字:点出的 node 名用逗号连起来;整串放不下时退成「第一个 node 名加 +n」
 * (n 是没写出来的个数);再放不下、或一个 node 都没点,返回空串(不画字,只画记号)。
 */
export function feedbackLabelText(nodes: readonly string[], widthPx: number): string {
  if (!nodes.length) return ''
  const full = nodes.join(', ')
  if (feedbackLabelFits(full, widthPx)) return full
  if (nodes.length < 2) return ''
  const short = `${nodes[0]}+${nodes.length - 1}`
  return feedbackLabelFits(short, widthPx) ? short : ''
}

const esc = (t: string) => t.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))

/**
 * 悬停文字(HTML,键值排),依次:target、日期范围、family 的起点(一族才有)、`shared: n places`(这条所在的
 * issue 有两处以上才有;places = 几处反馈共享同一份内容)、nodes(点了才有)、note、status、会话写的原因标签、
 * 状态取不到的原因、范围里有正样本时一行 `pos sample inside`。键与程序给的值等宽;
 * note 是用户写的,正常字体加浅灰底。字一律黑。记录上以前存下的 answer、dag 不写。
 */
export function feedbackTip(fb: AnnFeedback, st: FeedbackStatusOf | null | undefined, posInside: boolean,
                            places = 1): string {
  const range = fb.start === fb.end ? fb.start : `${fb.start} … ${fb.end}`
  const rows = [`target: ${esc(fb.target)}`, `range: ${esc(range)}`]
  if (fb.target === 'family' && fb.family_start) rows.push(`family_start: ${esc(fb.family_start)}`)
  if (places >= 2) rows.push(`shared: ${places} places`)
  if (fb.nodes?.length) rows.push(`nodes: ${fb.nodes.map(esc).join(', ')}`)
  if (fb.note) {
    rows.push(`note: <span style='font-family:sans-serif;background:#f4f4f5;padding:0 4px;border-radius:3px'>`
              + `${esc(fb.note)}</span>`)
  }
  rows.push(`status: ${esc(st?.status ?? 'null')}`)
  if (st?.tag) rows.push(`tag: ${esc(st.tag)}`)
  if (st?.reason) rows.push(`reason: ${esc(st.reason)}`)
  if (posInside) rows.push('pos sample inside')
  return `<span style='font-family:${MONO};color:#000000'>${rows.join('<br/>')}</span>`
}
