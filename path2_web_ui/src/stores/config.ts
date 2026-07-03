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
  async function load() { config.value = await getConfig() }
  async function save(c: AppConfig) { config.value = c; await putConfig(c) }
  return { config, load, save }
})
