/**
 * 当前 pattern 的 app(spec 5.8):顶栏 mode 的 compare / app 两档靠它。
 *
 * - 哪个 app、哪个 node 认哪个特征:读后端 /mappings(path2_apps/<app>/mapping.yaml,由会话为 V-S1 手工写,
 *   格式见 path2_web/mapping.py)。顶栏当前 pattern 恰好有一个没有问题的 mapping,就算「有 app」(mapping)。
 *   页面启动时读一次,之后每次窗口重新拿到焦点再读一次(会话写完 mapping、用户切回浏览器就生效);
 * - compare / app 两档只在有 app、且已经打开了一只股票时可用(available);切到这两档走 view.enterLinked;
 * - 跑 app:在 compare 或从顶栏切到的 app 下,对当前股票走 /preview,区间是这只股票截到训练段末日的全部 K 线
 *   (起点 WHOLE_HISTORY_START 早于任何行情、终点 TRAIN_END;后端读行情截到训练段末日,数据墙见 spec 4.1)。
 *   每次切进这两档、换股票、换 app 都重跑(参数文件改了,切一下就看到新结果);compare 与 app 之间互切不重跑。
 *   结果交给 view.setLinkedRun,图与诊断照它画;
 * - 正在 compare / 现算的 app 下,当前 pattern 变得没有 app(换了 pattern、mapping 被删或出了问题):回到 annotate。
 * runStatus:loading 正在跑;load_failed 没跑成。
 */
import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'
import { getMappings, getPreview } from '../api'
import type { AppMapping } from '../types'
import { TRAIN_END } from '../annotate/directLinks'
import { useAnnotationStore } from './annotation'
import { useViewStore, type ViewMode } from './view'

/** 跑 app 的区间起点:早于任何行情,后端按日期切片时等于从这只股票的第一根 K 线开始。 */
export const WHOLE_HISTORY_START = '1900-01-01'
/** hit 的前瞻收益看几根(悬停里的 ret_20);后端读行情截到训练段末日,最后这些根上的 hit 没有前瞻收益。 */
export const LABEL_HORIZON = 20

export type RunStatus = 'loading' | 'load_failed'

export const useAppLinkStore = defineStore('appLink', () => {
  const view = useViewStore()
  const ann = useAnnotationStore()
  const mappings = shallowRef<AppMapping[] | null>(null)   // null:还没读到
  const runStatus = ref<RunStatus | null>(null)

  async function load(): Promise<void> {
    try { mappings.value = await getMappings() } catch { /* 读不到就留着上次的 */ }
  }

  /** 写了当前 pattern 的 mapping(可能不止一个,也可能有问题)。 */
  const entries = computed(() => (mappings.value ?? []).filter(m => m.pattern === ann.currentPattern))
  /** 当前 pattern 的 app 的 mapping:恰好一个、没有问题的;否则 null。 */
  const mapping = computed<AppMapping | null>(() =>
    entries.value.length === 1 && entries.value[0].problem === null ? entries.value[0] : null)
  /** 写了 mapping 却用不了的原因(悬停提示用);没写 mapping 为 null。 */
  const problem = computed<string | null>(() => {
    const es = entries.value
    if (!es.length || mapping.value) return null
    return es.map(m => `${m.app}: ${m.problem}`).join('\n')
  })
  const available = computed(() => mapping.value !== null && view.symbol !== null)

  /** 顶栏 mode:annotate 随时可切;compare / app 要 available。 */
  function setMode(m: ViewMode): void {
    if (m === 'annotate') { view.enterAnnotate(); return }
    if (available.value) view.enterLinked(m)
  }

  let request = 0                                   // 只认最后一次跑的结果
  async function run(): Promise<void> {
    const mine = ++request
    const sym = view.symbol
    const app = mapping.value?.app ?? null
    view.setLinkedRun(null)
    if (!view.linkedView || !sym || !app) { runStatus.value = null; return }
    runStatus.value = 'loading'
    try {
      const r = await getPreview(app, sym, WHOLE_HISTORY_START, TRAIN_END, LABEL_HORIZON)
      if (mine !== request) return
      view.setLinkedRun({ symbol: sym, app, analysis: r.analysis, pattern_spec: r.pattern_spec, scan: r.scan })
      runStatus.value = null
    } catch {
      if (mine === request) runStatus.value = 'load_failed'
    }
  }

  // 切进 compare / 现算的 app(从 annotate 或扫描结果过来)、换股票、换 app:重跑;两档之间互切不重跑
  watch(() => [view.linkedView, view.symbol, mapping.value?.app ?? null] as const, ([on, sym, app], old) => {
    if (on && old && old[0] && old[1] === sym && old[2] === app) return
    if (on && !app) { view.enterAnnotate(); return }   // 当前 pattern 没有 app 了
    void run()
  })

  function onFocus() { void load() }
  window.addEventListener('focus', onFocus)

  return { mappings, entries, mapping, problem, available, runStatus, load, setMode }
})
