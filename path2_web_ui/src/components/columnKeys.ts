/**
 * 左右栏的收起快捷键(App.vue 挂在 window 的 keydown 上;状态在 stores/panels.ts,箭头在 ColumnEdge.vue):
 * - Shift+L:收起 / 打开左栏(四档都起作用);
 * - Shift+R:收起 / 打开标注侧栏(只在 annotate、compare;app、scan 的诊断侧栏照旧用 Sidebar 按钮)。
 * 左右各管各,没有一下收起两边的键。焦点在任何输入框、下拉框里不响应(keyGuard.ts,同找图清单的翻页键):
 * 在 note 里打大写 L、R 是在写字。单个字母会被 scan 档扫描列表的「敲字母搜股票」接走,所以带 Shift(同 Shift+B)。
 */
import { useViewStore } from '../stores/view'
import { usePanelsStore } from '../stores/panels'
import { focusBlocksKeys } from './keyGuard'

export function onColumnKey(e: KeyboardEvent): void {
  if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.isComposing || e.repeat) return
  if (e.code !== 'KeyL' && e.code !== 'KeyR') return
  if (e.code === 'KeyR' && !useViewStore().annotating) return
  if (focusBlocksKeys()) return
  e.preventDefault()
  const panels = usePanelsStore()
  if (e.code === 'KeyL') panels.leftCollapsed = !panels.leftCollapsed
  else panels.annCollapsed = !panels.annCollapsed
}
