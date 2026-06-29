// 三个 UI 面板(Topology/Sidebar/Slider)的显隐 store,localStorage 持久化。
// 默认全隐(首次访问 / key 缺失 / JSON 解析失败均回落 false)。
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'path2_web_ui.panels.v1'

interface PanelsState {
  topology: boolean
  sidebar:  boolean
  slider:   boolean
}

function loadState(): PanelsState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { topology: false, sidebar: false, slider: false }
    const obj = JSON.parse(raw)
    return {
      topology: !!obj.topology,
      sidebar:  !!obj.sidebar,
      slider:   !!obj.slider,
    }
  } catch {
    return { topology: false, sidebar: false, slider: false }
  }
}

export type PanelKey = 'topology' | 'sidebar' | 'slider'

export const usePanelsStore = defineStore('panels', () => {
  const init = loadState()
  const showTopology = ref(init.topology)
  const showSidebar  = ref(init.sidebar)
  const showSlider   = ref(init.slider)

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        topology: showTopology.value,
        sidebar:  showSidebar.value,
        slider:   showSlider.value,
      }))
    } catch { /* 配额满/隐私模式:静默吞,不阻塞 UI */ }
  }
  watch([showTopology, showSidebar, showSlider], persist)

  function toggle(key: PanelKey) {
    if (key === 'topology') showTopology.value = !showTopology.value
    else if (key === 'sidebar') showSidebar.value = !showSidebar.value
    else showSlider.value = !showSlider.value
  }

  return { showTopology, showSidebar, showSlider, toggle }
})
