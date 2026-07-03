// 三个 UI 面板(Topology/Sidebar/Slider)的显隐 + 副图高度相对 offset,localStorage 持久化。
// 默认全隐(首次访问 / key 缺失 / JSON 解析失败均回落 false);subHeightOffset 默认 null(fit)。
// spec: docs/superpowers/specs/2026-07-03-subchart-boundary-model-design.md §1
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'path2_web_ui.panels.v1'

interface PanelsState {
  topology: boolean
  sidebar:  boolean
  slider:   boolean
  subHeightOffset: number | null
}

// offset = drag 藏掉的像素数,恒 ≤ 0;正值防御性钳 0,NaN → null(fit)
function normalizeOffset(v: number | null): number | null {
  if (v === null) return null
  if (Number.isNaN(v)) return null
  if (v > 0) return 0
  return v
}

function loadState(): PanelsState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { topology: false, sidebar: false, slider: false, subHeightOffset: null }
    const obj = JSON.parse(raw)
    // 旧字段 subHeightOverride(绝对高度语义)直接忽略 → 回 fit(spec §1 迁移)
    const offset = typeof obj.subHeightOffset === 'number' ? normalizeOffset(obj.subHeightOffset) : null
    return {
      topology: !!obj.topology,
      sidebar:  !!obj.sidebar,
      slider:   !!obj.slider,
      subHeightOffset: offset,
    }
  } catch {
    return { topology: false, sidebar: false, slider: false, subHeightOffset: null }
  }
}

export type PanelKey = 'topology' | 'sidebar' | 'slider'

export const usePanelsStore = defineStore('panels', () => {
  const init = loadState()
  const showTopology = ref(init.topology)
  const showSidebar  = ref(init.sidebar)
  const showSlider   = ref(init.slider)
  const subHeightOffset = ref<number | null>(init.subHeightOffset)

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        topology: showTopology.value,
        sidebar:  showSidebar.value,
        slider:   showSlider.value,
        subHeightOffset: subHeightOffset.value,
      }))
    } catch { /* 配额满/隐私模式:静默吞,不阻塞 UI */ }
  }
  watch([showTopology, showSidebar, showSlider, subHeightOffset], persist)

  function toggle(key: PanelKey) {
    if (key === 'topology') showTopology.value = !showTopology.value
    else if (key === 'sidebar') showSidebar.value = !showSidebar.value
    else showSlider.value = !showSlider.value
  }

  function setSubHeightOffset(v: number | null) {
    subHeightOffset.value = normalizeOffset(v)
  }

  return { showTopology, showSidebar, showSlider, subHeightOffset, toggle, setSubHeightOffset }
})
