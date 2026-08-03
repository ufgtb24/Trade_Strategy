import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PatternStatsTooltip from '../src/components/PatternStatsTooltip.vue'

describe('PatternStatsTooltip', () => {
  it('renders 8 rows with correct formatted values', () => {
    const stats = {
      count: 203,
      mean: 0.032,
      min: -0.081,
      q25: 0.008,
      median: 0.025,
      q75: 0.057,
      max: 0.184,
      win_rate: 0.68,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    const rows = w.findAll('.row')
    expect(rows).toHaveLength(8)
    const txt = w.text()
    expect(txt).toContain('203')
    expect(txt).toContain('+3.2%')
    expect(txt).toContain('-8.1%')
    expect(txt).toContain('+0.8%')
    expect(txt).toContain('+2.5%')
    expect(txt).toContain('+5.7%')
    expect(txt).toContain('+18.4%')
    expect(txt).toContain('68%')
  })

  it('falls back to em-dash for null fields (empty samples)', () => {
    const stats = {
      count: 0,
      mean: null, min: null, q25: null, median: null,
      q75: null, max: null, win_rate: null,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    const txt = w.text()
    expect(txt).toContain('0')
    const dashes = w.findAll('.val').filter(v => v.text() === '—')
    expect(dashes.length).toBe(7)
  })

  it('formats win_rate as integer percent', () => {
    const stats = {
      count: 100, mean: 0.01, min: 0.01, q25: 0.01,
      median: 0.01, q75: 0.01, max: 0.01, win_rate: 0.755,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    expect(w.text()).toContain('76%')
  })

  it('handles zero-mean as +0.0%', () => {
    const stats = {
      count: 1, mean: 0, min: 0, q25: 0, median: 0,
      q75: 0, max: 0, win_rate: 0,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    expect(w.text()).toContain('+0.0%')
    expect(w.text()).toContain('0%')
  })

  it('无 statsDrawdown prop → 不渲染 drawdown 块(向后兼容,仅 8 行 forward_return)', () => {
    const stats = {
      count: 5, mean: 0.01, min: 0.01, q25: 0.01,
      median: 0.01, q75: 0.01, max: 0.01, win_rate: 0.5,
    }
    const w = mount(PatternStatsTooltip, { props: { stats } })
    expect(w.find('.stats-drawdown').exists()).toBe(false)
    expect(w.findAll('.row')).toHaveLength(8)
  })

  it('有 statsDrawdown prop → 追加 drawdown 块(8 行 stats + 分隔标题 + 8 行 drawdown)', () => {
    const stats = {
      count: 5, mean: 0.01, min: 0.01, q25: 0.01,
      median: 0.01, q75: 0.01, max: 0.01, win_rate: 0.5,
    }
    const statsDrawdown = {
      count: 5, mean: -0.03, min: -0.10, q25: -0.06,
      median: -0.03, q75: -0.01, max: 0.0, win_rate: 0.2,
    }
    const w = mount(PatternStatsTooltip, { props: { stats, statsDrawdown } })
    expect(w.find('.stats-drawdown').exists()).toBe(true)
    // 顶部 8 行(forward_return) + drawdown 8 行
    expect(w.findAll('.row')).toHaveLength(16)
    // drawdown 块的标题可见
    expect(w.text()).toContain('drawdown')
    // drawdown 块数值正确(同 fmtVal 带符号百分比)
    const ddTxt = w.find('.stats-drawdown').text()
    expect(ddTxt).toContain('-10.0%')   // min
    expect(ddTxt).toContain('+0.0%')    // max = 0
  })

  // ── Task 5 · 首次穿越方向块 ────────────────────────────────────────────────
  const BASE_STATS = {
    count: 5, mean: 0.01, min: 0.01, q25: 0.01,
    median: 0.01, q75: 0.01, max: 0.01, win_rate: 0.5,
  }

  it('无 firstPassageStats prop → 不渲染首次穿越块(向后兼容)', () => {
    const w = mount(PatternStatsTooltip, { props: { stats: BASE_STATS } })
    expect(w.find('.stats-first-passage').exists()).toBe(false)
  })

  it('firstPassageStats.n_match=0 → 不渲染首次穿越块(防空标题)', () => {
    const fps = { up: 0, down: 0, both: 0, none: 0, n_match: 0, ratio: null,
                  random_up: 0, random_down: 0, random_both: 0, random_none: 0, random_n: 0, random_ratio: null, k: 2 }
    const w = mount(PatternStatsTooltip, {
      props: { stats: BASE_STATS, firstPassageStats: fps },
    })
    expect(w.find('.stats-first-passage').exists()).toBe(false)
  })

  it('有 firstPassageStats(单组)→ 单行展示 ratio / random_ratio / k', () => {
    const fps = { up: 30, down: 10, both: 2, none: 3, n_match: 45, ratio: 0.75,
                  random_up: 23, random_down: 22, random_both: 0, random_none: 0, random_n: 45, random_ratio: 0.511, k: 2 }
    const w = mount(PatternStatsTooltip, {
      props: { stats: BASE_STATS, firstPassageStats: fps },
    })
    const block = w.find('.stats-first-passage')
    expect(block.exists()).toBe(true)
    // 三行:表头 pat/rdm + 方向 + 有效(均单组,不再按 pair_key 多行)
    expect(block.findAll('.fp-row')).toHaveLength(3)
    // 标题 + k 标注可见
    const txt = block.text()
    expect(txt).toContain('首次穿越')
    expect(txt).toContain('k=2')
    expect(txt).toContain('pat')   // 表头(pattern 列)
    expect(txt).toContain('rdm')   // 表头(random 列)
    // ratio / random_ratio 按后端算好的数展示
    expect(txt).toContain('75.0%')    // ratio 0.75 → toFixed(1)
    expect(txt).toContain('51.1%')    // random_ratio 0.511 → toFixed(1) 51.1%
    expect(txt).toContain('93.3%')    // 有效(非none) pattern (30+10+2)/45
    expect(txt).toContain('100.0%')   // 有效 random (23+22+0)/45
  })

  it('firstPassageStats ratio=null(分母为 0)→ 单行 ratio 显示 — 占位', () => {
    const fps = { up: 0, down: 0, both: 0, none: 5, n_match: 5, ratio: null,
                  random_up: 2, random_down: 2, random_both: 0, random_none: 1, random_n: 5, random_ratio: 0.5, k: 2 }
    const w = mount(PatternStatsTooltip, {
      props: { stats: BASE_STATS, firstPassageStats: fps },
    })
    const block = w.find('.stats-first-passage')
    expect(block.exists()).toBe(true)
    // ratio null → — ;random_ratio 仍展示
    expect(block.text()).toContain('—')
    expect(block.text()).toContain('50.0%')
  })
})
