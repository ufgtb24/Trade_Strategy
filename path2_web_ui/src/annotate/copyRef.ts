/**
 * 「复制指代」:把选中的那一个写成一行自带上下文的话,贴给会话就能定位(股票、pattern、是哪种东西、日期,
 * 末尾方括号里是内部编号)。按一下复制一行,选中什么就复制什么;同一样东西不论从哪条路选中都是同一行。这里全是纯函数。
 *
 * 拼法对所有种类相同:股票、pattern,接身份五格(种类、对应的 node、日期、叫法、区别;不适用的跳过),
 * 再接它牵出的买点日与 hit(`buys 首…尾 ×n`、`hits ×n`),最后是 `[编号]`。行里不写第几个 / 共几个。
 *   SYM pattern hit_family START buys FIRST…LAST ×n hits ×m          起点相同的整族 hit
 *   SYM pattern buy DAY hits ×m                                       一个买点日(这天叠着的几次 hit 整体)
 *   SYM pattern hit START→END 区别 buys DAY ×1 [hit_id]               一次 hit
 *   SYM pattern event NODE START→END 区别 buys FIRST…LAST ×n hits ×m [id]   一个 event(band 上的一格)
 *   SYM pattern node NODE 特征名                                      一条 band(一个 node)
 *   SYM pattern feedback NODES START→END buys … hits ×m [id]         一条反馈
 *   SYM pattern sample DATE 字母 pos|neg hits ×m [sample id]          用户的样本
 *   SYM pattern box NODE START→END 特征名 hits ×m [box id]            用户的框
 *   SYM pattern day DATE                                              什么都没选中:当前日
 *
 * 图上选中了东西(compare / app 下,stores/view.ts 的 selInfo)时,那一行的后半段由 render/selSnapshot.ts 算好
 * (`copyTail`),这里只接上股票与 pattern;annotate 下没有 app 的东西,选中的框、样本照同一拼法在这里写。
 */
import type { AnnChart } from './model'
import { sampleLetters } from './samples'

export type CopyTarget =
  | { kind: 'selection'; tail: string }
  | { kind: 'box'; id: string }
  | { kind: 'sample'; id: string }
  | { kind: 'feedback'; id: string }
  | { kind: 'day' }

/** 一次选中状态的快照。 */
export interface PickState {
  /** 图上选中的那一个的后半行(view.selInfo.copyTail);没有选中为 null */
  tail: string | null
  boxId: string | null
  /** 选中的样本;compare 下没选中时是聚焦的那个 */
  sampleId: string | null
  feedbackId: string | null
}

/** 当前指的是哪样东西:图上选中的那一个;没有时(annotate 下)框 → 样本 → 反馈;都没有 → 当前日。 */
export function resolveTarget(s: PickState): CopyTarget {
  if (s.tail) return { kind: 'selection', tail: s.tail }
  if (s.boxId) return { kind: 'box', id: s.boxId }
  if (s.sampleId) return { kind: 'sample', id: s.sampleId }
  if (s.feedbackId) return { kind: 'feedback', id: s.feedbackId }
  return { kind: 'day' }
}

export interface CopyContext {
  symbol: string
  /** app 的 pattern(compare / app 模式);annotate 下是顶栏的当前 pattern,unsorted 为 null */
  pattern: string | null
  dates: readonly string[]
  currentDay: number | null
  chart: AnnChart | null
  featureName: (fid: string | null) => string | null
}

const UNSORTED = 'unsorted'
const join = (...parts: (string | null | undefined | false)[]): string => parts.filter(Boolean).join(' ')
const span = (a: string, b: string): string => (a === b ? a : `${a}→${b}`)

/** 那样东西 → 复制的那一行;对象已经不在(换了图、被删)时退成当前日那一行。 */
export function copyLine(t: CopyTarget, c: CopyContext): string {
  const head = join(c.symbol, c.pattern)
  const dayLine = (): string => join(head, c.currentDay != null && `day ${c.dates[c.currentDay] ?? c.currentDay}`)
  if (t.kind === 'selection') return join(head, t.tail)
  if (t.kind === 'box') {
    const b = c.chart?.boxes.find(x => x.id === t.id)
    return b ? join(head, 'box', span(b.start, b.end), c.featureName(b.feature) ?? 'unnamed', `[${b.id}]`) : dayLine()
  }
  if (t.kind === 'sample') {
    const s = c.chart?.samples.find(x => x.id === t.id)
    if (!s) return dayLine()
    const letter = sampleLetters(c.chart, s.pattern).get(s.id)
    return join(c.symbol, s.pattern ?? UNSORTED, 'sample', s.date, letter, s.judgment, `[${s.id}]`)
  }
  if (t.kind === 'feedback') {
    const f = c.chart?.feedback?.find(x => x.id === t.id)
    return f ? join(c.symbol, f.pattern, 'feedback', f.nodes?.length ? f.nodes.join(',') : null,
                    span(f.start, f.end), `[${f.id}]`) : dayLine()
  }
  return dayLine()
}
