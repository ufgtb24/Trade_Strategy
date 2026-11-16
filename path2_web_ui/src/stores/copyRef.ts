/**
 * 「复制指代」的状态与动作(纯逻辑见 annotate/copyRef.ts):
 * - copy():把选中的那一个写成一行放进剪贴板,并用底部提示条把这一行显示几秒。按一下就是它,不分层、不循环。
 * - copyDates():主图上按住 Shift 点一根 / 拖一段时,把这一天、这一段写成一行复制出去(同一条提示条);
 *   只复制,不改选中与当前日。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useViewStore } from './view'
import { useAnnotationStore } from './annotation'
import { useFeedbackStore } from './feedback'
import { useCompareStore } from './compare'
import { copyLine, dateLine, resolveTarget, type CopyTarget } from '../annotate/copyRef'

export const useCopyRefStore = defineStore('copyRef', () => {
  const view = useViewStore()
  const ann = useAnnotationStore()
  const fb = useFeedbackStore()
  const cmp = useCompareStore()

  /** 最近一次复制出去的那一行(测试与提示条用) */
  const lastText = ref<string | null>(null)

  function target(): CopyTarget {
    return resolveTarget({
      tail: view.selInfo?.copyTail ?? null,
      boxId: view.annotating ? ann.selectedBoxId : null,
      sampleId: view.annotating ? (ann.selectedSampleId ?? (view.comparing ? cmp.focusedSampleId : null)) : null,
      feedbackId: view.comparing ? fb.selectedId : null,
    })
  }

  /** annotate / compare 的 pattern 是顶栏的当前 pattern(compare 的 app 就是它对上的那个);app、scan 两档是图上跑的那个
   *  app(appId:app 档现算的那个、scan 档扫描里选的那个) */
  const pattern = (): string | null => (view.annotating ? ann.currentPattern : view.appId)

  /** 选中的那一个的那一行;没有打开股票时为 null。 */
  function line(): string | null {
    const symbol = view.symbol
    if (!symbol) return null
    return copyLine(target(), {
      symbol,
      pattern: pattern(),
      dates: view.barDates,
      currentDay: view.currentDay,
      chart: ann.state?.charts.find(c => c.symbol === symbol) ?? null,
      featureName: ann.nameOf,
    })
  }

  /** 把这一行放进剪贴板,并用底部提示条显示它 */
  function put(text: string): void {
    lastText.value = text
    const done = (): void => view.showToast(`copied  ${text}`)
    const p = navigator.clipboard?.writeText(text)
    if (p) void p.then(done, () => view.showToast(`copy failed  ${text}`))
    else view.showToast(`copy failed  ${text}`)
  }

  /** 复制选中的那一个;返回复制出去的那一行(没有可复制的为 null)。 */
  function copy(): string | null {
    const text = line()
    if (!text) return null
    put(text)
    return text
  }

  /** 复制 K 线下标 i0…i1 这一天 / 这一段(同一根是一天);返回复制出去的那一行(没有打开股票、没有 K 线时为 null)。 */
  function copyDates(i0: number, i1: number): string | null {
    const symbol = view.symbol
    if (!symbol || !view.barDates.length) return null
    const text = dateLine({ symbol, pattern: pattern(), dates: view.barDates }, i0, i1)
    put(text)
    return text
  }

  return { lastText, target, line, copy, copyDates }
})
