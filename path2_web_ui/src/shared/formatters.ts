/**
 * 硬伤 E · kind-aware · 按 measured.kind 加前缀。
 * kind 是自由字符串、非闭合枚举 · 契约与生产 kind 清单见
 * path2/dag/gate_failure.py::MeasuredKindAware。
 * 本文件只对下方 case 列出的 kind 有专属前缀 · 其余(如 count / pullback_atr /
 * breakout_price / window_start / side_bars_offset / peak_idx / window_min_low /
 * relative_height 等)走 default 分支落 String(val) · 不报错、只是没前缀。
 * strict_clear 留位、生产未使用。
 */
export function fmt(val: any, kind: string): string {
    switch (kind) {
        case 'gap':
            return `gap=${val}`
        case 'anchor_delta':
            return `Δanchor=${Number(val).toFixed(3)}`
        case 'strict_clear':
            return `strict候选=${val}`
        case 'negation_bars':
            return `禁区bars=${val}`
        case 'window_offset':
            return `起点偏移=${val}`
        case 'unknown':
            return '?'
        default:
            return String(val)
    }
}

/**
 * 硬伤 D · 数组分支 · multi-value where 完整展示。
 * 递归处理嵌套数组,数字统一 3 位小数。
 */
export function fmtValue(val: any): string {
    if (Array.isArray(val)) {
        return `[${val.map(fmtValue).join(', ')}]`
    }
    if (typeof val === 'number') {
        return val.toFixed(3)
    }
    return String(val)
}
