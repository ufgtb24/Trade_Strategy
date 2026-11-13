/**
 * 反馈(spec 6.13)作答面板与 feedback 工具在界面上的纯函数(不碰 Vue、ECharts、store),
 * 面板组件见 FeedbackPanel.vue,接线见 KlineChart.vue:
 * - panelKeyAction:面板开着时这一下按键归不归面板——Enter 保存(焦点在面板的按钮上也是保存,浏览器默认的
 *   「Enter 点按钮」被截下;按住不放的自动重复截下但不存)、Esc 只关面板;Shift+Enter 不截(note 是多行文本区,它在里面是换行);输入法组字中(isComposing,或 keyCode 229)一律不截:中文理由组字时
 *   Enter 是上屏、Esc 是取消组字。焦点在面板外的输入框里(顶栏代码框、侧栏的 note 等)时也不截,按键归那个框。
 *   ←/→ 不截,照旧在族里走(面板不抢焦点就是为了它);
 * - placePanel:面板的默认位置——横向靠在它管的那段日期的竖带旁边(不压竖带),底边贴住副图上方显示栏的上沿
 *   (显示栏和副图都露着);clampToViewport:按住页头拖动时,面板整块留在视口里;
 * - rangeBandPx:贯穿主副图的竖带(拖选中的那条、选中的反馈那条)的左右(像素):整根 K 线对齐,裁到图区内;
 * - selectedBandPx:选中的反馈那条竖带,另给出哪一侧被图区裁掉(那一侧不画边线);
 * - NOTE_MAX_H / noteHeight:note 文本区随内容长高,到上限为止(再多就在框里滚动)。
 */

/** 判定要用到的按键字段(KeyboardEvent 的子集,单测好造)。 */
export interface KeyLike {
  key: string
  isComposing?: boolean
  keyCode?: number
  shiftKey?: boolean
  repeat?: boolean
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
}

export type PanelKeyAction = 'save' | 'close' | 'ignore' | null

/** 输入法组字中:组字期间的按键 keyCode 恒为 229(有的浏览器上屏那一下 isComposing 已为假,靠它兜住)。 */
export function isComposingKey(e: Pick<KeyLike, 'isComposing' | 'keyCode'>): boolean {
  return !!e.isComposing || e.keyCode === 229
}

/**
 * 面板开着时这一下按键归面板做什么:'save'、'close'、'ignore'(截下不做事:按住 Enter 的自动重复),
 * 或 null(不截,照常往下传)。
 * @param e 按键
 * @param outsideEditable 焦点在面板外的输入框 / 文本区 / 可编辑元素里
 */
export function panelKeyAction(e: KeyLike, outsideEditable = false): PanelKeyAction {
  if (isComposingKey(e) || outsideEditable) return null
  if (e.ctrlKey || e.metaKey || e.altKey) return null
  // 按住 Enter 的自动重复不存:按住 Enter 开面板时,重复的那几下不能顺手把它存了(截下但不做事)
  if (e.key === 'Enter') return e.shiftKey ? null : e.repeat ? 'ignore' : 'save'
  if (e.key === 'Escape') return 'close'
  return null
}

export interface Pt { x: number; y: number }
export interface Size { w: number; h: number }

/**
 * 面板落点要用的几样(视口坐标,图表组件量出来给面板):
 * - band:面板管的那段日期的竖带露在图区里的左右;整段在图窗外为 null;
 * - bottom:面板底边贴住的那条线(副图上方显示栏的上沿);
 * - left / right:面板左右不出这个范围(图表区的左右:不压左侧列表和右侧栏)。
 */
export interface PanelAnchor { band: { left: number; right: number } | null; bottom: number; left: number; right: number }

/** 面板离竖带的距离、底边离显示栏的距离(像素,待验证)。 */
export const PANEL_GAP = 8
export const PANEL_BAR_GAP = 4

/**
 * 面板的左上角(视口坐标)。横向:靠在竖带右边;右边放不下翻到竖带左边;两边都放不下(竖带太宽)贴住右边界,
 * 这时会压住竖带的一部分;竖带不在图窗里时放在左右范围的正中。纵向:底边贴住 bottom(显示栏上沿),
 * 上边放不下(主图太矮)贴住视口上沿。
 */
export function placePanel(a: PanelAnchor, size: Size, gap = PANEL_GAP): Pt {
  const hi = Math.max(a.left, a.right - size.w)
  let x: number
  if (!a.band) x = Math.min(Math.max((a.left + a.right - size.w) / 2, a.left), hi)
  else if (a.band.right + gap + size.w <= a.right) x = a.band.right + gap
  else if (a.band.left - gap - size.w >= a.left) x = a.band.left - gap - size.w
  else x = hi
  return { x, y: Math.max(0, a.bottom - PANEL_BAR_GAP - size.h) }
}

/** 拖动后的左上角:整块留在视口里(面板比视口还大时贴住左上)。 */
export function clampToViewport(p: Pt, size: Size, viewport: Size): Pt {
  return { x: Math.min(Math.max(p.x, 0), Math.max(0, viewport.w - size.w)),
           y: Math.min(Math.max(p.y, 0), Math.max(0, viewport.h - size.h)) }
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

/**
 * 选中的那条反馈的竖带:左右同 rangeBandPx;另给出哪一侧被图区裁掉了(范围伸到图窗之外),那一侧不画边线,
 * 免得把图窗的边当成范围的头或尾。
 */
export function selectedBandPx(i0: number, i1: number, toPx: (i: number) => number, plotLeft: number, plotRight: number,
): { left: number; width: number; cutLeft: boolean; cutRight: boolean } | null {
  const band = rangeBandPx(i0, i1, toPx, plotLeft, plotRight)
  if (!band) return null
  const bw = Math.abs(toPx(i0 + 1) - toPx(i0))
  return { ...band, cutLeft: Math.min(toPx(i0), toPx(i1)) - bw / 2 < plotLeft,
           cutRight: Math.max(toPx(i0), toPx(i1)) + bw / 2 > plotRight }
}

/** note 文本区的最高高度(像素,待验证):约八行,再多就在框里滚动。 */
export const NOTE_MAX_H = 160

/** note 文本区该有的高度:内容高 contentH 加上下边框 borderH,不超过上限。 */
export function noteHeight(contentH: number, borderH: number, max = NOTE_MAX_H): number {
  return Math.min(contentH + borderH, max)
}
