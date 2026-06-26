import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AppConfig } from '../types'
import { getConfig, putConfig } from '../api'

export const useConfigStore = defineStore('config', () => {
  const config = ref<AppConfig | null>(null)
  async function load() { config.value = await getConfig() }
  async function save(c: AppConfig) { config.value = c; await putConfig(c) }
  return { config, load, save }
})
