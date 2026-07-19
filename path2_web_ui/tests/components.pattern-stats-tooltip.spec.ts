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
})
