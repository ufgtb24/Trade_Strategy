/**
 * 「复制指代」的状态与动作(纯逻辑见 annotate/copyRef.ts):
 * - selectedNode:选中的轨名(一个 node);点轨名设,点了别的东西、点空白、Esc、换股票或换 pattern 清掉;
 * - lastPick:最后点的是不是反馈记号 / 轨名 / diagnose 的卡片。反馈记号的选中会一直留着(点了别的也不清),只看谁非空分不出先后;
 * - copy():算出当前指的东西,写进剪贴板,并用底部提示条把复制的那一行显示几秒。同一样东西连按逐层放大
 *   (hit:这一次 → 这一天的几次 → 整族;event:这一个 → 它的族),到头回到第一层;换了东西从第一层起。
 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useViewStore } from './view'
import { useAnnotationStore } from './annotation'
import { useFeedbackStore } from './feedback'
import { useCompareStore } from './compare'
import { copyLadder, resolveTarget, type CopyTarget } from '../annotate/copyRef'

export const useCopyRefStore = defineStore('copyRef', () => {
  const view = useViewStore()
  const ann = useAnnotationStore()
  const fb = useFeedbackStore()
  const cmp = useCompareStore()

  const selectedNode = ref<string | null>(null)
  const lastPick = ref<'feedback' | 'node' | 'card' | null>(null)
  let cardInstance: string | null = null   // 最后点的那张 diagnose 卡片的 event
  /** 最近一次复制出去的那一行(测试与提示条用) */
  const lastText = ref<string | null>(null)
  let lastBase: string | null = null   // 上一次复制时第一层那一行:同一样东西连按才往上走一层
  let level = 0

  /** 点轨名:选中这个 node,别的选中一并取消(再点一次同一个轨名取消)。 */
  function selectNode(node: string | null): void {
    if (node && node === selectedNode.value) node = null
    if (node) {
      view.clearFocus()
      ann.selectBox(null)
      ann.selectSample(null, { keepTab: true })
      fb.select(null)
    }
    selectedNode.value = node
    lastPick.value = node ? 'node' : null
  }

  /** 在 diagnose 块里点了一张卡片(调用方随后照常把它设成焦点):之后复制的是这张卡片的 hit / event,不是样本。 */
  function pickCard(instanceId: string): void {
    cardInstance = instanceId
    lastPick.value = 'card'
    selectedNode.value = null
  }

  // 点了反馈记号(同一条再点一次也算:pickSeq 每次点都加一)
  watch(() => fb.pickSeq, () => { if (fb.selectedId) { lastPick.value = 'feedback'; selectedNode.value = null } })
  // 点了别的东西(hit、event、当家行、框、样本)→ 不再是反馈 / 轨名
  watch(() => [view.selectedHitId, view.focusedInstanceRef, view.activeFamilyKey, view.pendingDisambigInstanceId,
               ann.selectedBoxId, ann.selectedSampleId] as const, (now) => {
    // 卡片点击自己也会改焦点:焦点还停在那张卡片的 event 上就仍算卡片
    if (lastPick.value === 'card' && view.focusedInstanceRef === cardInstance) return
    if (now.some(v => v != null)) { lastPick.value = null; selectedNode.value = null }
  })
  // 换股票、换 pattern(主视图的、顶栏的)、换模式:轨名的选中作废
  watch(() => [view.symbol, view.activePatternId, ann.currentPattern, view.mode] as const, () => {
    selectedNode.value = null
    if (lastPick.value === 'node' || lastPick.value === 'card') lastPick.value = null
  })

  function target(): CopyTarget {
    return resolveTarget({
      lastPick: lastPick.value,
      feedbackId: view.comparing ? fb.selectedId : null,
      node: selectedNode.value,
      candidateCount: view.candidateHitIds.size,
      pendingInstanceId: view.pendingDisambigInstanceId,
      familyKind: view.activeFamily?.kind ?? null,
      instanceId: view.focusedInstanceRef,
      hitId: view.selectedHitId,
      boxId: view.annotating ? ann.selectedBoxId : null,
      sampleId: view.annotating ? (ann.selectedSampleId ?? (view.comparing ? cmp.focusedSampleId : null)) : null,
    })
  }

  /** 当前指的东西的几行(从小到大);没有打开股票时为空。 */
  function ladder(): string[] {
    const symbol = view.symbol
    if (!symbol) return []
    const app = view.mode !== 'annotate'
    const topo = view.effectivePattern?.topology
    return copyLadder(target(), {
      symbol,
      // annotate / compare 的 pattern 是顶栏的当前 pattern(compare 的 app 就是它对上的那个);app 模式是主视图选的
      pattern: view.annotating ? ann.currentPattern : view.activePatternId,
      dates: view.barDates,
      currentDay: view.currentDay,
      hits: app ? view.effectiveAnalysis?.hits ?? [] : [],
      events: app ? view.effectiveAnalysis?.events ?? [] : [],
      endNode: view.endNode,
      nodeOrder: (topo?.nodes ?? []).map(n => n.node_id),
      anchorFields: [...new Set((topo?.edges ?? []).map(e => e.anchor_field).filter((f): f is string => !!f))],
      chart: ann.state?.charts.find(c => c.symbol === symbol) ?? null,
      featureName: ann.nameOf,
    })
  }

  /** 复制当前指的东西;返回复制出去的那一行(没有可复制的为 null)。 */
  function copy(): string | null {
    const lines = ladder()
    if (!lines.length) return null
    level = lines[0] === lastBase ? (level + 1) % lines.length : 0
    lastBase = lines[0]
    const text = lines[level]
    lastText.value = text
    const done = (): void => view.showToast(`copied  ${text}`)
    const p = navigator.clipboard?.writeText(text)
    if (p) void p.then(done, () => view.showToast(`copy failed  ${text}`))
    else view.showToast(`copy failed  ${text}`)
    return text
  }

  return { selectedNode, lastPick, lastText, selectNode, pickCard, target, ladder, copy }
})
