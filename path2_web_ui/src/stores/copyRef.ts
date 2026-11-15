/**
 * 「复制指代」的状态与动作(纯逻辑见 annotate/copyRef.ts):
 * - copy():把选中的那一个写成一行放进剪贴板,并用底部提示条把这一行显示几秒。按一下就是它,不分层、不循环。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useViewStore } from './view'
import { useAnnotationStore } from './annotation'
import { useFeedbackStore } from './feedback'
import { useCompareStore } from './compare'
import { copyLine, resolveTarget, type CopyTarget } from '../annotate/copyRef'

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

  /** 选中的那一个的那一行;没有打开股票时为 null。 */
  function line(): string | null {
    const symbol = view.symbol
    if (!symbol) return null
    return copyLine(target(), {
      symbol,
      // annotate / compare 的 pattern 是顶栏的当前 pattern(compare 的 app 就是它对上的那个);app 模式是主视图选的
      pattern: view.annotating ? ann.currentPattern : view.activePatternId,
      dates: view.barDates,
      currentDay: view.currentDay,
      chart: ann.state?.charts.find(c => c.symbol === symbol) ?? null,
      featureName: ann.nameOf,
    })
  }

  /** 复制选中的那一个;返回复制出去的那一行(没有可复制的为 null)。 */
  function copy(): string | null {
    const text = line()
    if (!text) return null
    lastText.value = text
    const done = (): void => view.showToast(`copied  ${text}`)
    const p = navigator.clipboard?.writeText(text)
    if (p) void p.then(done, () => view.showToast(`copy failed  ${text}`))
    else view.showToast(`copy failed  ${text}`)
    return text
  }

  return { lastText, target, line, copy }
})
