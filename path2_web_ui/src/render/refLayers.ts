/**
 * 主图 K 线区上的参照层(开关与数据见 stores/refLayers.ts)。
 *
 * peaks:每个峰一条水平线,高度是峰价,从峰那根 K 线的中心画到第一次被突破的那根(没被突破的到最后一根)。
 * 深灰细实线:配色规范里有意义的颜色一样都不用(K 线红绿、会话蓝、app 琥珀、朱红、档位的两种灰
 * #9ca3af / #b4bac2),也不用虚线(虚线只表示用户画的)。压在 K 线上面、不挡鼠标;y 轴范围照旧只看 K 线。
 */
import type { PeakLine } from '../types'

export const PEAKS_SERIES = 'ref-peaks'
export const PEAK_LINE = '#52525b'      // 深灰,比档位的两种灰都深,也不是框和文字的黑
export const PEAK_LINE_W = 1

/** 参照层 peaks 的 custom 系列,按名字合并更新;lines 为空时不画。图上没有的日期(不该出现)跳过。 */
export function peaksSeries(dates: readonly string[], lines: readonly PeakLine[]): Record<string, unknown> {
  const data: number[][] = []
  for (const p of lines) {
    const i = dates.indexOf(p.date)
    const j = dates.indexOf(p.end)
    if (i >= 0 && j >= i) data.push([i, j, p.price])
  }
  return {
    type: 'custom', name: PEAKS_SERIES, xAxisIndex: 0, yAxisIndex: 0, data, silent: true, z: 4,
    encode: { x: [0, 1] }, clip: true, tooltip: { show: false },
    renderItem: (_params: any, api: any) => {
      const [x1, y] = api.coord([api.value(0), api.value(2)])
      const [x2] = api.coord([api.value(1), api.value(2)])
      return { type: 'line', shape: { x1, y1: y, x2, y2: y }, style: { stroke: PEAK_LINE, lineWidth: PEAK_LINE_W } }
    },
  }
}
