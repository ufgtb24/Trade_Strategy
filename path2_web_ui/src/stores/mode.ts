import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ModeInfo } from '../types'
import { getMode } from '../api'
import { launchMode, type LaunchMode } from '../shared/launchMode'

// 以下三个时长是先取的默认值(待验证)
export const RETRY_MS = 5_000       // 读不到模式时多久重试一次
export const RECHECK_MS = 60_000    // 读到以后多久再核对一次(后端可能被换成另一种模式重启)
export const TIMEOUT_MS = 5_000     // 一次读取最多等多久,超时按读不到处理

const MODE_NAME: Record<LaunchMode, string> = { formal: '正式模式', debug: '调试模式' }

export type BannerKind = 'debug' | 'unknown' | 'mismatch'
export interface ModeBanner { kind: BannerKind; text: string }

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`超过 ${ms}ms 没有回应`)), ms)
    p.then((v) => { clearTimeout(t); resolve(v) }, (e) => { clearTimeout(t); reject(e) })
  })
}

/** 后端的模式(正式 / 看图工作流的调试模式)和页顶横幅。
 *  页顶横幅(ModeBanner)挂上后 start():读一次后端的 /mode,读不到每 RETRY_MS 重试,读到了每 RECHECK_MS
 *  再核对一次。横幅三种:
 *    - unknown:最近一次没读到(后端没连上或超时)——不知道是哪种模式,醒目提示、一直重试;
 *    - mismatch:启动脚本说的模式(launchMode)和后端报的不一样——报警;
 *    - debug:后端是调试模式——挂调试横幅。
 *  正式模式且对得上 → 不挂;还没读完第一次 → 不挂。 */
export const useModeStore = defineStore('mode', () => {
  const info = ref<ModeInfo | null>(null)
  const failed = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let running = false

  async function load() {
    try {
      info.value = await withTimeout(getMode(), TIMEOUT_MS)
      failed.value = false
    } catch {
      failed.value = true
    }
  }
  async function tick() {
    await load()
    if (running) timer = setTimeout(tick, failed.value ? RETRY_MS : RECHECK_MS)
  }
  function start() {
    if (running) return
    running = true
    void tick()
  }
  function stop() {
    running = false
    if (timer) clearTimeout(timer)
    timer = null
  }

  const banner = computed<ModeBanner | null>(() => {
    const expected = launchMode()
    const said = expected ? `；这个网页是按${MODE_NAME[expected]}启动的` : ''
    if (failed.value)
      return { kind: 'unknown', text: `模式未知：后端没连上，每 ${RETRY_MS / 1000} 秒重试一次${said}` }
    const got = info.value
    if (!got) return null
    if (expected && got.mode !== expected)
      return { kind: 'mismatch',
               text: `模式对不上：网页按${MODE_NAME[expected]}启动，后端却是${MODE_NAME[got.mode]}；别在这里看图，用对应的启动脚本重新启动` }
    if (got.mode === 'debug') return { kind: 'debug', text: got.label ?? MODE_NAME.debug }
    return null
  })
  return { info, failed, banner, load, start, stop }
})
