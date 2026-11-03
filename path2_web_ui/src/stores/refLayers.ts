/**
 * 参照层 ref(spec 5.7):标注图上唯一画出来的、别的系统算出来的东西。先只有 peaks:bo 检测产出的峰,
 * 画成水平线(后端 /peaks,截到训练段末日)。
 *
 * - 只在 annotate / compare 下可用(REF_MODES),还要已经打开了一只股票;
 * - 默认关;换股票自动关,切到别的模式(app)也关,回来仍是关的。开关不记在浏览器里。
 *   防的是参照层常开、把眼睛往算出来的东西上带;
 * - 打开时向后端要这只股票的峰,关掉就扔。正在要的时候换了股票或关掉,回来的结果不用。
 * status:loading 正在要;load_failed 没要到;empty 这只股票在训练段里没有峰。
 */
import { defineStore } from 'pinia'
import { computed, ref, shallowRef, watch } from 'vue'
import { getPeaks } from '../api'
import type { PeakLine } from '../types'
import { useViewStore } from './view'

/** 参照层可用的模式。按模式名判断:compare 还没有的时候也照样写上。 */
export const REF_MODES: readonly string[] = ['annotate', 'compare']

export type PeaksStatus = 'loading' | 'load_failed' | 'empty'

export const useRefLayerStore = defineStore('refLayers', () => {
  const view = useViewStore()
  const peaks = ref(false)
  const lines = shallowRef<PeakLine[]>([])
  const status = ref<PeaksStatus | null>(null)
  const available = computed(() => REF_MODES.includes(view.mode) && view.symbol != null)
  let request = 0                                   // 只认最后一次要的结果

  function off() {
    request++
    peaks.value = false
    lines.value = []
    status.value = null
  }

  async function setPeaks(on: boolean) {
    if (!on || !available.value) { off(); return }
    const mine = ++request
    peaks.value = true
    lines.value = []
    status.value = 'loading'
    try {
      const got = await getPeaks(view.symbol!)
      if (mine !== request) return
      lines.value = got
      status.value = got.length ? null : 'empty'
    } catch {
      if (mine === request) status.value = 'load_failed'
    }
  }

  // 同步关:换股票、换模式的那一刻就关,不等下一轮更新
  watch(() => view.symbol, off, { flush: 'sync' })
  watch(() => view.mode, (m) => { if (!REF_MODES.includes(m)) off() }, { flush: 'sync' })

  return { peaks, lines, status, available, setPeaks }
})
