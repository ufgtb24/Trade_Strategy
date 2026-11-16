// 界面布局的显隐与尺寸,localStorage 持久化(只是界面布局,不算标注或反馈):
// - 三个 UI 面板(Topology/Sidebar/Slider)的显隐 + 副图高度相对 offset。
//   默认全隐(首次访问 / key 缺失 / JSON 解析失败均回落 false);subHeightOffset 默认 null(fit)。
//   spec: docs/superpowers/specs/2026-07-03-subchart-boundary-model-design.md §1
// - 左右栏的收起与拖宽(几何见 components/columnLayout.ts):左栏、标注侧栏的收起;左栏、标注侧栏、诊断侧栏
//   各一份拖出的宽度(null = 没拖过:左栏按内容全开,右栏用各自的默认宽度)。换股、切档都保持,刷新后记得。
//   诊断侧栏的显隐仍是上面的 sidebar(图上方的 Sidebar 按钮),不另加收起。
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'path2_web_ui.panels.v1'

interface PanelsState {
  topology: boolean
  sidebar:  boolean
  slider:   boolean
  subHeightOffset: number | null
  leftCollapsed: boolean
  annCollapsed: boolean
  leftWidth: number | null
  annWidth: number | null
  detailWidth: number | null
}

const DEFAULTS: PanelsState = {
  topology: false, sidebar: false, slider: false, subHeightOffset: null,
  leftCollapsed: false, annCollapsed: false, leftWidth: null, annWidth: null, detailWidth: null,
}

// offset = drag 藏掉的像素数,恒 ≤ 0;正值防御性钳 0,NaN → null(fit)
function normalizeOffset(v: number | null): number | null {
  if (v === null) return null
  if (Number.isNaN(v)) return null
  if (v > 0) return 0
  return v
}

/** 存下的栏宽:正的有限数才算,其余(缺、坏值)当没拖过。 */
function normalizeWidth(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null
}

function loadState(): PanelsState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    const obj = JSON.parse(raw)
    // 旧字段 subHeightOverride(绝对高度语义)直接忽略 → 回 fit(spec §1 迁移)
    const offset = typeof obj.subHeightOffset === 'number' ? normalizeOffset(obj.subHeightOffset) : null
    return {
      topology: !!obj.topology,
      sidebar:  !!obj.sidebar,
      slider:   !!obj.slider,
      subHeightOffset: offset,
      leftCollapsed: !!obj.leftCollapsed,
      annCollapsed: !!obj.annCollapsed,
      leftWidth: normalizeWidth(obj.leftWidth),
      annWidth: normalizeWidth(obj.annWidth),
      detailWidth: normalizeWidth(obj.detailWidth),
    }
  } catch {
    return { ...DEFAULTS }
  }
}

export type PanelKey = 'topology' | 'sidebar' | 'slider'

export const usePanelsStore = defineStore('panels', () => {
  const init = loadState()
  const showTopology = ref(init.topology)
  const showSidebar  = ref(init.sidebar)
  const showSlider   = ref(init.slider)
  const subHeightOffset = ref<number | null>(init.subHeightOffset)
  const leftCollapsed = ref(init.leftCollapsed)
  const annCollapsed = ref(init.annCollapsed)
  const leftWidth = ref<number | null>(init.leftWidth)
  const annWidth = ref<number | null>(init.annWidth)
  const detailWidth = ref<number | null>(init.detailWidth)

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        topology: showTopology.value,
        sidebar:  showSidebar.value,
        slider:   showSlider.value,
        subHeightOffset: subHeightOffset.value,
        leftCollapsed: leftCollapsed.value,
        annCollapsed: annCollapsed.value,
        leftWidth: leftWidth.value,
        annWidth: annWidth.value,
        detailWidth: detailWidth.value,
      }))
    } catch { /* 配额满/隐私模式:静默吞,不阻塞 UI */ }
  }
  watch([showTopology, showSidebar, showSlider, subHeightOffset,
         leftCollapsed, annCollapsed, leftWidth, annWidth, detailWidth], persist)

  function toggle(key: PanelKey) {
    if (key === 'topology') showTopology.value = !showTopology.value
    else if (key === 'sidebar') showSidebar.value = !showSidebar.value
    else showSlider.value = !showSlider.value
  }

  function setSubHeightOffset(v: number | null) {
    subHeightOffset.value = normalizeOffset(v)
  }

  return {
    showTopology, showSidebar, showSlider, subHeightOffset, toggle, setSubHeightOffset,
    leftCollapsed, annCollapsed, leftWidth, annWidth, detailWidth,
  }
})
