// 反馈的纯函数(annotate/feedback.ts):同范围查重、范围里的正样本、买点日、分段按钮(含孙 node 的合成拓扑)、
// 保存条件(与后端校验逐条对上)、草稿转记录、侧栏排序。
import { describe, it, expect } from 'vitest'
import {
  buyDatesIn, draftToFeedback, feedbackRank, findSameRange, hitsBuyingIn, posSamplesInside, saveProblems,
  segmentChoices, sortFeedbackRows, type FeedbackDraft, type FeedbackRow,
} from '../src/annotate/feedback'
import type { AnnChart, AnnFeedback } from '../src/annotate/model'
import type { EventDict, HitDict, Topology } from '../src/types'

const fb = (id: string, start: string, end: string, extra: Partial<AnnFeedback> = {}): AnnFeedback => ({
  id, pattern: 'p', app_id: 'app1', app_ver: 'v1', start, end, target: 'range', source: 'picked', answer: 'neg',
  note: 'x', ...extra })

describe('同范围查重', () => {
  const chart: AnnChart = { symbol: 'AAA', boxes: [], samples: [], feedback: [
    fb('f-pc-1', '2025-01-06', '2025-01-10'),
    fb('f-pc-2', '2025-01-06', '2025-01-10', { pattern: 'q' }),
    fb('f-pc-3', '2025-01-13', '2025-01-13', { source: 'random', target: 'point' }),
  ] }

  it('同股票、同 pattern、start 与 end 都相同的才算', () => {
    expect(findSameRange(chart, 'p', '2025-01-06', '2025-01-10')?.id).toBe('f-pc-1')
    expect(findSameRange(chart, 'q', '2025-01-06', '2025-01-10')?.id).toBe('f-pc-2')
    expect(findSameRange(chart, 'p', '2025-01-06', '2025-01-09')).toBeNull()
    expect(findSameRange(chart, 'p', '2025-01-07', '2025-01-10')).toBeNull()
  })

  it('盲看标记不算(不可改,不拿来打开);没有图或没有 pattern 为 null', () => {
    expect(findSameRange(chart, 'p', '2025-01-13', '2025-01-13')).toBeNull()
    expect(findSameRange(null, 'p', '2025-01-06', '2025-01-10')).toBeNull()
    expect(findSameRange(chart, null, '2025-01-06', '2025-01-10')).toBeNull()
  })
})

describe('范围里的正样本(pos sample inside)', () => {
  const chart: AnnChart = { symbol: 'AAA', boxes: [], samples: [
    { id: 's1', date: '2025-01-06', pattern: 'p', judgment: 'pos', members: [] },
    { id: 's2', date: '2025-01-08', pattern: 'p', judgment: 'neg', members: [] },
    { id: 's3', date: '2025-01-09', pattern: 'q', judgment: 'pos', members: [] },
    { id: 's4', date: '2025-01-10', pattern: 'p', judgment: 'pos', members: [] },
    { id: 's5', date: '2025-01-13', pattern: 'p', judgment: 'pos', members: [] },
  ] }

  it('当前 pattern 的 pos、样本日落在 [start, end](两端都算)', () => {
    expect(posSamplesInside(chart, 'p', '2025-01-06', '2025-01-10').map(s => s.id)).toEqual(['s1', 's4'])
    expect(posSamplesInside(chart, 'p', '2025-01-07', '2025-01-09')).toEqual([])
    expect(posSamplesInside(chart, 'q', '2025-01-06', '2025-01-10').map(s => s.id)).toEqual(['s3'])
    expect(posSamplesInside(chart, null, '2025-01-01', '2025-12-31')).toEqual([])
  })
})

// 容器 plateau 引用 step / today;买点 node = plateau.today。两次 hit:阶跃到 2、今天 4;阶跃到 2、今天 6
const ev = (node: string, s: number, e: number, idx = 0, child_refs: Record<string, string[]> = {}): EventDict =>
  ({ instance_id: `${node}_${s}_${e}#${idx}`, node_id: node, instance_idx: idx, start_idx: s, end_idx: e, child_refs })
const S2 = ev('step', 2, 2), T4 = ev('today', 4, 4), T6 = ev('today', 5, 6)
const P4 = ev('plateau', 0, 4, 0, { step: [S2.instance_id], today: [T4.instance_id] })
const P6 = ev('plateau', 0, 6, 0, { step: [S2.instance_id], today: [T6.instance_id] })
const hit = (id: string, p: EventDict, extra: Record<string, string> = {}): HitDict => ({
  hit_id: id, start_idx: p.start_idx, end_idx: p.end_idx, node_index: { plateau: p.instance_id, ...extra }, children: [] })
const EVENTS = [S2, T4, T6, P4, P6]
const HITS = [hit('h4', P4), hit('h6', P6)]
const DATES = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09', '2025-01-10']

describe('买点日', () => {
  it('按买点 node 取,跨度里每一根都是;换成日期、升序去重', () => {
    expect(buyDatesIn(HITS, EVENTS, 'plateau.today', DATES, '2025-01-01', '2025-12-31'))
      .toEqual(['2025-01-08', '2025-01-09', '2025-01-10'])
    expect(buyDatesIn(HITS, EVENTS, 'plateau.today', DATES, '2025-01-02', '2025-01-07')).toEqual([])
    expect(buyDatesIn(HITS, EVENTS, null, DATES, '2025-01-01', '2025-12-31')).toEqual([])
  })

  it('范围里买的 hit:有一个买点日落在范围里就算', () => {
    expect(hitsBuyingIn(HITS, EVENTS, 'plateau.today', DATES, '2025-01-08', '2025-01-08').map(h => h.hit_id)).toEqual(['h4'])
    expect(hitsBuyingIn(HITS, EVENTS, 'plateau.today', DATES, '2025-01-09', '2025-01-09').map(h => h.hit_id)).toEqual(['h6'])
    expect(hitsBuyingIn(HITS, EVENTS, 'plateau.today', DATES, '2025-01-06', '2025-01-12').map(h => h.hit_id)).toEqual(['h4', 'h6'])
    expect(hitsBuyingIn(HITS, EVENTS, 'plateau.today', DATES, '2025-01-02', '2025-01-07')).toEqual([])
  })
})

describe('off_pattern 的分段按钮', () => {
  // 拓扑顺序里根 node 不在最前;step 下面还有孙 node step_seg;other 是另一个根,带子 node other_kid
  const TOPO: Topology = { edges: [], nodes: [
    { node_id: 'other', where_rules: [] },
    { node_id: 'plateau', where_rules: [] },
    { node_id: 'step', where_rules: [], parent_refs: [['plateau', 'step']] },
    { node_id: 'step_seg', where_rules: [], parent_refs: [['step', 'seg']] },
    { node_id: 'other_kid', where_rules: [], parent_refs: [['other', 'x']] },
    { node_id: 'today', where_rules: [], parent_refs: [['plateau', 'today']] },
  ] }

  it('hit 绑定的 node 加子 node(递归到孙 node),按拓扑顺序,根 node 保留', () => {
    expect(segmentChoices([hit('h4', P4)], TOPO)).toEqual(['plateau', 'step', 'step_seg', 'today'])
  })

  it('几次 hit 绑定的 node 合起来;不相干的根和它的子 node 不出现', () => {
    expect(segmentChoices([hit('h4', P4), hit('h6', P6, { other: 'o#0' })], TOPO))
      .toEqual(['other', 'plateau', 'step', 'step_seg', 'other_kid', 'today'])
    expect(segmentChoices([hit('h4', P4)], TOPO)).not.toContain('other_kid')
  })

  it('已选上的分段当前拓扑里没有了:留着排在最后;没有 hit 时只有它们', () => {
    expect(segmentChoices([hit('h4', P4)], TOPO, ['gone', 'step', 'gone'])).toEqual(['plateau', 'step', 'step_seg', 'today', 'gone'])
    expect(segmentChoices([], TOPO, ['step'])).toEqual(['step'])
    expect(segmentChoices([hit('h4', P4)], null, ['gone'])).toEqual(['gone'])
  })

  it('parent_refs 绕成环也不死循环', () => {
    const loop: Topology = { edges: [], nodes: [
      { node_id: 'a', where_rules: [], parent_refs: [['b', 's']] },
      { node_id: 'b', where_rules: [], parent_refs: [['a', 's']] },
    ] }
    expect(segmentChoices([{ node_index: { a: 'a#0' } }], loop)).toEqual(['a', 'b'])
  })
})

describe('保存条件', () => {
  const d = (extra: Partial<FeedbackDraft>): FeedbackDraft =>
    ({ symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'range', ...extra })

  it('还没选答案;neg 要理由(全是空白不算);off_pattern 分段或理由至少一样', () => {
    expect(saveProblems(d({}))).toEqual(['answer'])
    expect(saveProblems(d({ answer: 'neg' }))).toEqual(['note'])
    expect(saveProblems(d({ answer: 'neg', note: '  ' }))).toEqual(['note'])
    expect(saveProblems(d({ answer: 'neg', note: '追高' }))).toEqual([])
    expect(saveProblems(d({ answer: 'neg', note: '追高', segments: ['step'] }))).toEqual([])
    expect(saveProblems(d({ answer: 'off_pattern' }))).toEqual(['segments_or_note'])
    expect(saveProblems(d({ answer: 'off_pattern', segments: ['step'] }))).toEqual([])
    expect(saveProblems(d({ answer: 'off_pattern', note: '不像' }))).toEqual([])
  })

  it('分段不得重复或为空', () => {
    expect(saveProblems(d({ answer: 'off_pattern', segments: ['step', 'step'] }))).toEqual(['segments'])
    expect(saveProblems(d({ answer: 'off_pattern', segments: [''] }))).toEqual(['segments'])
  })

  it('日期:start 不晚于 end,end 不晚于训练段末日;point 是同一天', () => {
    expect(saveProblems(d({ answer: 'neg', note: 'x', start: '2025-01-11' }))).toEqual(['range'])
    expect(saveProblems(d({ answer: 'neg', note: 'x', end: '2026-01-02' }))).toEqual(['after_train_end'])
    expect(saveProblems(d({ answer: 'neg', note: 'x', end: '2025-12-31' }))).toEqual([])
    expect(saveProblems(d({ answer: 'neg', note: 'x', target: 'point' }))).toEqual(['point'])
    expect(saveProblems(d({ answer: 'neg', note: 'x', target: 'point', start: '2025-01-10' }))).toEqual([])
  })

  it('family 必有起点且不晚于 start;别的 target 不带起点', () => {
    expect(saveProblems(d({ answer: 'neg', note: 'x', target: 'family' }))).toEqual(['family_start'])
    expect(saveProblems(d({ answer: 'neg', note: 'x', target: 'family', family_start: '2025-01-07' }))).toEqual(['family_start'])
    expect(saveProblems(d({ answer: 'neg', note: 'x', target: 'family', family_start: '2025-01-06' }))).toEqual([])
    expect(saveProblems(d({ answer: 'neg', note: 'x', target: 'family', family_start: '2024-12-02' }))).toEqual([])
    expect(saveProblems(d({ answer: 'neg', note: 'x', family_start: '2025-01-02' }))).toEqual(['family_start'])
  })
})

describe('草稿转记录', () => {
  const origin = { id: 'f-pc-9', pattern: 'p', app_id: 'app1', app_ver: 'v2' }

  it('理由去掉首尾空白;neg 不带分段;family_start 只在 family 时带;source 恒为 picked', () => {
    expect(draftToFeedback({ symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'range',
                             family_start: '2025-01-02', answer: 'neg', note: ' 追高 ', segments: ['step'] }, origin))
      .toEqual({ id: 'f-pc-9', pattern: 'p', app_id: 'app1', app_ver: 'v2', start: '2025-01-06', end: '2025-01-10',
                 target: 'range', source: 'picked', answer: 'neg', note: '追高' })
    expect(draftToFeedback({ symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'family',
                             family_start: '2025-01-02', answer: 'off_pattern', note: '', segments: ['step'] }, origin))
      .toEqual({ id: 'f-pc-9', pattern: 'p', app_id: 'app1', app_ver: 'v2', start: '2025-01-06', end: '2025-01-10',
                 target: 'family', source: 'picked', answer: 'off_pattern', segments: ['step'], family_start: '2025-01-02' })
  })
})

describe('侧栏排序', () => {
  const row = (symbol: string, id: string, start: string, end = start): FeedbackRow => ({ symbol, feedback: fb(id, start, end) })

  it('朱红在前、lost 其次、其余(含状态还没取到的)在后;同档按股票、start、end、编号;不改入参', () => {
    const rows = [
      row('BBB', 'f-pc-1', '2025-01-06'),
      row('AAA', 'f-pc-2', '2025-01-08'),
      row('AAA', 'f-pc-3', '2025-01-06', '2025-01-09'),
      row('AAA', 'f-pc-4', '2025-01-06', '2025-01-07'),
      row('CCC', 'f-pc-5', '2025-01-01'),
      row('AAA', 'f-pc-6', '2025-01-01'),
    ]
    const st = {
      'f-pc-1': { status: 'matched' as const, tag: null, red: true, reason: null },
      'f-pc-2': { status: 'matched' as const, tag: 'redefined', red: false, reason: null },
      'f-pc-5': { status: 'lost' as const, tag: null, red: false, reason: null },
      'f-pc-6': { status: 'unmatched' as const, tag: null, red: false, reason: null },
    }
    const before = rows.map(r => r.feedback.id)
    expect(sortFeedbackRows(rows, st).map(r => r.feedback.id))
      .toEqual(['f-pc-1', 'f-pc-5', 'f-pc-6', 'f-pc-4', 'f-pc-3', 'f-pc-2'])
    expect(rows.map(r => r.feedback.id)).toEqual(before)
    expect(feedbackRank(undefined)).toBe(2)
  })
})
