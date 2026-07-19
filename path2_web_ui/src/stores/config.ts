import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AppConfig } from '../types'
import { getConfig, putConfig } from '../api'

export const useConfigStore = defineStore('config', () => {
  const config = ref<AppConfig | null>({
    dataset_dir: '',
    scan: { start_date: '', end_date: '', workers: 1, ticker_regex: null },
    last_selected_pattern: '',
  })
  const loaded = ref(false)
  async function load() { config.value = await getConfig(); loaded.value = true }
  async function save(c: AppConfig) { config.value = c; await putConfig(c) }
  // 记住 active pattern:未 load 时只改内存(防占位符整体覆盖 YAML 抹掉 backend_port 等键)
  function saveLastPattern(pid: string) {
    if (!config.value) return
    config.value.last_selected_pattern = pid
    if (loaded.value) void putConfig(config.value)
  }
  return { config, loaded, load, save, saveLastPattern }
})
