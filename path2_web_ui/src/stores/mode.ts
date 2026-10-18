import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ModeInfo } from '../types'
import { getMode } from '../api'

/** 后端的模式(正式 / 看图工作流的调试模式)。启动时由 App 读一次;读不到按正式模式处理(不挂横幅)。 */
export const useModeStore = defineStore('mode', () => {
  const info = ref<ModeInfo | null>(null)
  async function load() {
    try { info.value = await getMode() } catch { info.value = null }
  }
  return { info, load }
})
