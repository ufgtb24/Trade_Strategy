/**
 * 副图 chartSub canvas 几何计算 —— 由 bracket lane 数 + 各 band 内 lane 数
 * 计算 bracket 区高度、每 band 的 top offset / height、canvas 需要的总高度 subCanvasH。
 *
 * spec: docs/superpowers/specs/2026-07-01-path2-web-subchart-scroll-drag-design.md §2.2
 * spec: docs/superpowers/specs/2026-07-03-subchart-boundary-model-design.md
 *
 * 约定 canvas 局部坐标 y=0 是 canvas 顶,自上而下:
 *   [0, bracketH)                        — bracket 区(lane_i 的 rect y = 4 + i*9·z, h = 7·z)
 *   [bracketH, bracketH + DIVIDER_GAP)   — hits 区与第一条 band 之间的空隙,和 hits 区同底色(HITS_FILL),不画分隔线
 *   [bracketH + DIVIDER_GAP, subCanvasH) — band 区,band_i 累积堆叠
 *
 * (CandidateStatusBar banner 已是滚动容器外的独立 DOM 行,不再占 canvas 顶部预留;
 *  spec 2026-07-03-subchart-boundary-model §3)
 *
 * 空数据(bracketLaneCount=0, bandLaneCounts=[])兜底: subCanvasH = SUB_CANVAS_MIN_H = 120,
 * 避免 chartSub 容器塌陷到零高度导致 ECharts 报错。
 */

export const BAND_MARKER_H = 7       // 时段 marker 本体高(bracket 与 band interval 共用,乘 z)
export const BAND_LANE_GAP = 2       // lane 间隙(乘 z,gap 整体等比语义)
export const BAND_LANE_H = BAND_MARKER_H + BAND_LANE_GAP  // 9,lane stride(乘 z)
export const BAND_TOP_PAD = 4
export const BAND_BOT_PAD = 4
export const BAND_MIN_H = 20         // 保 node 名 10px + 上下呼吸空间
export const SUB_CANVAS_MIN_H = 120  // 空数据兜底
// 高亮放大公式(bracket 选中与 band interval 高亮共用;spec 2026-07-03-bracket-band-unify §3.1)
// 档位按高度分三档(底对齐,乘 lane 高):色盲下不能只靠颜色分 in_hit 与灰(亮绿对浅灰、深绿对深灰深浅几乎一样)。
// 比例待在真图上验证。
export const TIER_H = { in_hit: 1.0, qualified: 0.65, detected: 0.4 } as const
// 格 / 条横向:每根 K 线中心左右各占这么多根宽(相邻两格之间留一点空)
export const MARK_HALF_W = 0.4
// 族的底线
export const FAMILY_LINE_COLOR = '#6b7280'     // 比 detected 浅灰格深,浅底上不会消失
export const FAMILY_LINE_AFTER_WINDOW = '#d1d5db'  // 跨过扫描末日的那段:窗后灰
export const FAMILY_LINE_H = 1
export const ACTIVE_LINE_H = 2.5               // 当家行的底线
// 族底线起点的竖头:读作「这一族从这天开始」,和全宽的分隔线区分开(高度按行高的比例,待验证)
export const FAMILY_HEAD_RATIO = 0.6
export const FAMILY_HEAD_W = 1.5
// compare:用户区与 app 区(含 hits)之间的分界线:高饱和的蓝(L* 约 43),比 app 轨的天蓝格(L* 约 61)深一截,
// 上面是白、下面是 hits 的浅黄,冷暖、深浅都拉开
export const USER_APP_EDGE_COLOR = '#0050ff'
export const USER_APP_EDGE_H = 2.5
// 分界线到上面 user 行样本跨度的下沿、到下面 hit 行的上沿,距离相同(上下对称);hit 行选中时外扩的框
// (上移 1.5、描边 2.5)也碰不到线(待验证)
export const USER_APP_GAP = 12
export const CURSOR_COLOR = '#1e293b'          // 当前日竖线:与选中框同一种深色
export const CURSOR_HALO = '#ffffff'           // 两侧白边,压在任何色块上都拉开深浅
export const HL_EXPAND_H = 3         // 高度增量(乘 z),比例恒 (7+3)/7
export const HL_EXPAND_OFFSET = 1.5  // y 上移(乘 z),保居中外扩
export const DIVIDER_GAP = 4

// Task 2 新增常量: 装饰几何视觉参数 + sub-outer 最小可压缩高度 + chartSub grid 左右内边距
// spec: docs/superpowers/specs/2026-07-01-path2-web-subchart-fixed-decor-design.md
// hits 区的底:很浅的黄(L* 约 98)。比琥珀的 hit 格(#fbbf24,L* 约 81)浅得多,黄也淡得多,不会和买点混;
// 和下面第一条 band 的隔行灰底(#ebebeb)深浅差约 5,再加一点黄与灰分开(待验证)
export const HITS_FILL = '#fffbdb'
// 副图隔行底:偶数下标的 band 垫一层 8% 黑(白底上 ≈ #ebebeb,和白底的明度差 L* 约 7,看图的用户才分得开相邻两条轨);
// 再深就压近 detected 浅灰(对它现在 1.64)和天蓝(2.58),见 render/colors.ts 与 path2_web/serialize.py 的 _PALETTE
export const BAND_STRIPE_FILL = 'rgba(0,0,0,0.08)'
export const BAND_INNER_LINE_H = 1            // band 内 lane 分隔线粗细(px)
export const MIN_SUB_H = 60                   // sub-outer 可压缩到的最小像素高度(120 仅为空数据兜底,60 为容器可视下界;内容更矮时退让到内容高)
export const SUB_GRID_LEFT = 56               // chartSub grid[0].left
export const SUB_GRID_RIGHT = 16              // chartSub grid[0].right
// 副图左边那条和主图价格刻度同宽的空白(SUB_GRID_LEFT)是轨名栏:每一行的底色、分隔线从容器最左起,
// 轨名从 SUB_TITLE_LEFT 起写;事件、hit、框的记号都裁在 grid 里(系列 clip),不伸进轨名栏
export const SUB_ROW_LEFT = 0
export const SUB_TITLE_LEFT = 2
// 轨名长过轨名栏时会伸进 grid:压在记号上面(z 高过所有系列),垫一块和这一行同色的底,记号从底下穿过、字照样读得出
export const SUB_TITLE_Z = 40
export const BAND_STRIPE_OPAQUE = '#ebebeb'    // BAND_STRIPE_FILL 叠在白底上的颜色(隔行底那几行的轨名垫这个)

// ── band zoom 交互常量(spec 2026-07-03-subchart-band-zoom)──────────────
// MAIN_MIN_H:zoom 拉大副图时主图至少保留的高度,防 K 线被挤压至不可读。
export const MAIN_MIN_H = 300
export const BAND_ZOOM_MIN = 1.0
export const BAND_ZOOM_MAX = 3.0
export const BAND_ZOOM_STEP_BUTTON = 0.2      // 按钮 -/+ 每次绝对步进
export const BAND_ZOOM_STEP_WHEEL = 1.1       // Shift+wheel 每 tick 乘/除因子(相对步进)
export const LS_KEY_BAND_ZOOM = 'kline-band-zoom-v1'

export interface BandGeom {
  top: number       // band 顶在 canvas 局部 y
  h: number         // band 高
  laneCount: number // 输入透传,便于渲染时按 lane 数分配 lane 位置
}

export interface SubGeometry {
  bracketH: number      // bracket 区总高(空 hits 时 = 0)
  bandGeom: BandGeom[]  // 每 band 的 top/h/laneCount,顺序与输入 bandLaneCounts 一致
  subCanvasH: number    // 副图 canvas 需要的总高
  /** bracket 区里 hit 第 0 行的顶(lane_i 的 y = appBracketTop + i*9·z);不传 userContentBottom 时 = BAND_TOP_PAD */
  appBracketTop: number
  /** hits 区的顶(浅黄底从这里铺起):app 模式 0;compare 是两区之间那道分界线 */
  hitsAreaTop: number
  /** compare:上区(用户)与下区(app)的分界 y,画一道分界线;不传 userContentBottom 时为空 */
  userAppEdges: number[]
}

export interface SubGeometryInput {
  bracketLaneCount: number     // bracket 轨 hit 族分行后的 max lane + 1(即 lane 数)
  bandLaneCounts: number[]     // 每 band 的 lane 数(顺序按 tagList 排)
  // ── compare(主视图副图 + 标注层,两区见 render/compareLayout.ts)才传;不传时与 app 模式逐项相同 ──
  /** 用户区(特征轨 + 样本跨度那一行 user,标注层 annotateLanes 的几何,不随 band zoom 变)里最低那条样本跨度的下沿
   *  (annotateLanes 的 bracketContentBottom);分界线画在它下面 USER_APP_GAP,hit 的行再往下 USER_APP_GAP */
  userContentBottom?: number
}

export function computeSubGeometry(
  input: SubGeometryInput,
  zoomFactor: number = 1.0,   // ← 新增,default 1.0 保 backward-compat
): SubGeometry {
  // bracket 区与 band 同一套几何:顶/底呼吸 pad(不乘 z)+ laneCount * BAND_LANE_H * z
  // (spec 2026-07-03-bracket-band-unify §3.2;顶 pad 为本次新增,原区顶紧贴 banner)
  // compare:用户区最低的样本跨度下沿往下空 USER_APP_GAP 画分界线,线下再空 USER_APP_GAP 才是 hit 的行(上下对称)
  const userH = input.userContentBottom ?? 0
  const edgeY = userH + USER_APP_GAP
  const appBracketTop = userH > 0 ? edgeY + USER_APP_GAP : BAND_TOP_PAD
  const bracketH = input.bracketLaneCount > 0 || userH > 0
    ? appBracketTop + input.bracketLaneCount * BAND_LANE_H * zoomFactor + BAND_BOT_PAD
    : 0
  const bandAreaTop = bracketH + DIVIDER_GAP

  // zoomFactor 只影响 lane 高度,pad 不缩(spec §4.1)
  const bandH = (laneCount: number) =>
    Math.max(BAND_MIN_H, laneCount * BAND_LANE_H * zoomFactor + BAND_TOP_PAD + BAND_BOT_PAD)
  let cursor = bandAreaTop
  const bandGeom: BandGeom[] = input.bandLaneCounts.map((laneCount) => {
    const h = bandH(laneCount)
    const g = { top: cursor, h, laneCount }
    cursor += h
    return g
  })

  const naturalCanvasH = cursor
  // SUB_CANVAS_MIN_H 仅在真正空数据时兜底(防 ECharts 零高容器报错);
  // 非空小内容用自然高,fit 态才能贴内容无留白(boundary-model 留白修复)
  const isEmpty = bracketH === 0 && input.bandLaneCounts.length === 0
  const subCanvasH = isEmpty ? SUB_CANVAS_MIN_H : naturalCanvasH

  // compare:上下两区的分界在用户区底下 USER_APP_GAP 处
  const userAppEdges = userH > 0 ? [edgeY] : []
  const hitsAreaTop = userH > 0 ? edgeY : 0
  return { bracketH, bandGeom, subCanvasH, appBracketTop, hitsAreaTop, userAppEdges }
}

/**
 * 副图容器高度合成(spec 2026-07-03-subchart-boundary-model §1)。
 * offset = 用户 drag 藏掉的像素数(恒 ≤ 0;null = fit)。
 * maxH = 容器高减去主图至少要留的高(MAIN_MIN_H):内容再高,副图也只占到这里、其余在容器里滚,K 线主图不被挤掉
 * (compare 插进用户轨后内容常比窗口高;三种模式都用)。不传 = 不设上限。
 * 不变量:返回值 ≤ subCanvasH(永不留白);offset=null/0 且内容没超上限时 = subCanvasH(fit,无滚动条)。
 * zoom 只改 subCanvasH、不碰 offset → 分界线随 zoom 移动而隐藏量守恒。
 */
export function composeEffectiveSubH(subCanvasH: number, offset: number | null, maxH: number = Infinity): number {
  const lo = Math.min(MIN_SUB_H, subCanvasH)   // 内容比 MIN_SUB_H 还矮时,下限退让到内容高(不留白优先)
  return Math.max(lo, Math.min(subCanvasH + (offset ?? 0), subCanvasH, maxH))
}
