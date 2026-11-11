/**
 * 反馈(spec 6.13)作答面板与 feedback 工具在界面上的纯函数(不碰 Vue、ECharts、store),
 * 面板组件见 FeedbackPanel.vue,接线见 KlineChart.vue:
 * - panelKeyAction:面板开着时这一下按键归不归面板——Enter 保存(焦点在面板的按钮上也是保存,浏览器默认的
 *   「Enter 点按钮」被截下)、Esc 只关面板;Shift+Enter 不截(note 是多行文本区,它在里面是换行);输入法组字中(isComposing,或 keyCode 229)一律不截:中文理由组字时
 *   Enter 是上屏、Esc 是取消组字。焦点在面板外的输入框里(顶栏代码框、侧栏的 note 等)时也不截,按键归那个框。
 *   ←/→ 不截,照旧在族里走(面板不抢焦点就是为了它);
 * - placePanel:面板浮在点击处(拖选时是松开处)右下,越出视口就翻到左边 / 上边(同右键菜单的翻边);锚点另给了 yUp
 *   (侧栏卡片的 edit:记号的顶)时,翻到上边按它算,面板落在记号上方、不压住记号;
 * - rangeBandPx:贯穿主副图的竖带(拖选中的那条、选中的反馈那条)的左右(像素):整根 K 线对齐,裁到图区内;
 * - selectedBandPx:选中的反馈那条竖带,另给出哪一侧被图区裁掉(那一侧不画边线);
 * - markAnchor:侧栏卡片的 edit 打开面板时的锚点——那条记号在视口里露出来的那一段的左下角,连同它的顶;
 * - NOTE_MAX_H / noteHeight:note 文本区随内容长高,到上限为止(再多就在框里滚动)。
 */

/** 判定要用到的按键字段(KeyboardEvent 的子集,单测好造)。 */
export interface KeyLike {
  key: string
  isComposing?: boolean
  keyCode?: number
  shiftKey?: boolean
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
  if (e.key === 'Enter') return e.shiftKey ? null : 'save'
  if (e.key === 'Escape') return 'close'
  return null
}

export interface Pt { x: number; y: number }
export interface Size { w: number; h: number }
/** 面板的锚点:x、y 同点击处;yUp 给了的话,下边放不下翻到上边时改从它往上放(锚的是一个有高度的东西时用)。 */
export interface Anchor extends Pt { yUp?: number }

/** 面板离点击处的距离(像素,待验证):不压在鼠标尖上。 */
export const PANEL_GAP = 8

/**
 * 面板的左上角(视口坐标):默认在点击处右下;右边放不下翻到点击处左边,下边放不下翻到上边(锚点给了 yUp 就从它往上);
 * 翻过去仍放不下时贴住视口边。
 */
export function placePanel(at: Anchor, size: Size, viewport: Size, gap = PANEL_GAP): Pt {
  let x = at.x + gap
  let y = at.y + gap
  if (x + size.w > viewport.w) x = Math.max(0, at.x - gap - size.w)
  if (y + size.h > viewport.h) y = Math.max(0, (at.yUp ?? at.y) - gap - size.h)
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

/** 一个矩形(视口坐标)。 */
export interface Box { left: number; top: number; right: number; bottom: number }

/**
 * 侧栏卡片的 edit 打开面板时的锚点(视口坐标):记号露在 clip 里的那一段的左下角(面板默认落在它右下),
 * yUp 是记号的顶(下边放不下时面板翻到记号上方);两种放法都不压住记号。记号整条在 clip 的左右之外时贴住
 * 最近的那条边;上下滚出 clip 时贴住 clip 的上下边。
 * @param mark 记号的矩形
 * @param clip 记号能露出来的范围(副图的可见区与图区左右的交)
 */
export function markAnchor(mark: Box, clip: Box): Required<Anchor> {
  const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), Math.max(lo, hi))
  return { x: clamp(mark.left, clip.left, clip.right), y: clamp(mark.bottom, clip.top, clip.bottom),
           yUp: clamp(mark.top, clip.top, clip.bottom) }
}

/** note 文本区的最高高度(像素,待验证):约八行,再多就在框里滚动。 */
export const NOTE_MAX_H = 160

/** note 文本区该有的高度:内容高 contentH 加上下边框 borderH,不超过上限。 */
export function noteHeight(contentH: number, borderH: number, max = NOTE_MAX_H): number {
  return Math.min(contentH + borderH, max)
}
