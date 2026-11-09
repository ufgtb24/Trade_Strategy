/**
 * 反馈(spec 6.13)作答面板与 feedback 工具在界面上的纯函数(不碰 Vue、ECharts、store),
 * 面板组件见 FeedbackPanel.vue,接线见 KlineChart.vue:
 * - panelKeyAction:面板开着时这一下按键归不归面板——Enter 保存(焦点在面板的按钮上也是保存,浏览器默认的
 *   「Enter 点按钮」被截下)、Esc 只关面板;输入法组字中(isComposing,或 keyCode 229)一律不截:中文理由组字时
 *   Enter 是上屏、Esc 是取消组字。焦点在面板外的输入框里(顶栏代码框、侧栏的 note 等)时也不截,按键归那个框。
 *   ←/→ 不截,照旧在族里走(面板不抢焦点就是为了它);
 * - placePanel:面板浮在点击处(拖选时是松开处)右下,越出视口就翻到左边 / 上边(同右键菜单的翻边);
 * - rangeBandPx:拖选中那条贯穿主副图的竖带的左右(像素):整根 K 线对齐,裁到图区内。
 */

/** 判定要用到的按键字段(KeyboardEvent 的子集,单测好造)。 */
export interface KeyLike {
  key: string
  isComposing?: boolean
  keyCode?: number
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
}

export type PanelKeyAction = 'save' | 'close' | null

/** 输入法组字中:组字期间的按键 keyCode 恒为 229(有的浏览器上屏那一下 isComposing 已为假,靠它兜住)。 */
export function isComposingKey(e: Pick<KeyLike, 'isComposing' | 'keyCode'>): boolean {
  return !!e.isComposing || e.keyCode === 229
}

/**
 * 面板开着时这一下按键归面板做什么:'save'、'close',或 null(不截,照常往下传)。
 * @param e 按键
 * @param outsideEditable 焦点在面板外的输入框 / 文本区 / 可编辑元素里
 */
export function panelKeyAction(e: KeyLike, outsideEditable = false): PanelKeyAction {
  if (isComposingKey(e) || outsideEditable) return null
  if (e.ctrlKey || e.metaKey || e.altKey) return null
  if (e.key === 'Enter') return 'save'
  if (e.key === 'Escape') return 'close'
  return null
}

export interface Pt { x: number; y: number }
export interface Size { w: number; h: number }

/** 面板离点击处的距离(像素,待验证):不压在鼠标尖上。 */
export const PANEL_GAP = 8

/**
 * 面板的左上角(视口坐标):默认在点击处右下;右边放不下翻到点击处左边,下边放不下翻到上边;翻过去仍放不下时贴住视口边。
 */
export function placePanel(at: Pt, size: Size, viewport: Size, gap = PANEL_GAP): Pt {
  let x = at.x + gap
  let y = at.y + gap
  if (x + size.w > viewport.w) x = Math.max(0, at.x - gap - size.w)
  if (y + size.h > viewport.h) y = Math.max(0, at.y - gap - size.h)
  return { x, y }
}

/**
 * 拖选竖带的左右:K 线下标 i0..i1(i0 ≤ i1)整根覆盖,toPx 给某根 K 线中心的像素(相对图容器),
 * 一根 K 线宽取相邻两根中心之差;裁到图区 [plotLeft, plotRight]。整段都在图区外时为 null。
 */
export function rangeBandPx(i0: number, i1: number, toPx: (i: number) => number,
                            plotLeft: number, plotRight: number): { left: number; width: number } | null {
  const bw = Math.abs(toPx(i0 + 1) - toPx(i0))
  const left = Math.max(plotLeft, Math.min(toPx(i0), toPx(i1)) - bw / 2)
  const right = Math.min(plotRight, Math.max(toPx(i0), toPx(i1)) + bw / 2)
  return right > left ? { left, width: right - left } : null
}
