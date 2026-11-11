// 反馈的纯函数(annotate/feedback.ts):同范围查重、范围里的正样本、买点日、node 按钮(含孙 node 的合成拓扑)、
// 保存条件(与后端校验逐条对上)、草稿转记录、侧栏排序;issue(分组、可挑的列表、内容改没改、新的 issue 值、
// 一次保存的安排、侧栏分组的次序)。面板写出的反馈不带 answer、不带 dag;以前存下的带这两个键的记录照样分组、能挑。
import { describe, it, expect } from 'vitest'
import {
  buyDatesIn, draftToFeedback, feedbackRank, findSameRange, hitsBuyingIn, issueChoices, issueGroups, issueKey,
  needsIssueChoice, nextIssueValue, planIssueSave, posSamplesInside, sameContent, saveProblems,
  nodeChoices, sortFeedbackRows, sortIssueGroups, type FeedbackDraft, type FeedbackRow,
} from '../src/annotate/feedback'
import type { AnnChart, AnnFeedback } from '../src/annotate/model'
import type { EventDict, HitDict, Topology } from '../src/types'

const fb = (id: string, start: string, end: string, extra: Partial<AnnFeedback> = {}): AnnFeedback => ({
  id, pattern: 'p', app_id: 'app1', app_ver: 'v1', start, end, target: 'range', source: 'picked',
  note: 'x', ...extra })

describe('同范围查重', () => {
  const chart: AnnChart = { symbol: 'AAA', boxes: [], samples: [], feedback: [
    fb('f-pc-1', '2025-01-06', '2025-01-10'),
    fb('f-pc-2', '2025-01-06', '2025-01-10', { pattern: 'q' }),
    fb('f-pc-3', '2025-01-13', '2025-01-13', { source: 'random', target: 'point', answer: 'neg' }),
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

describe('node 按钮', () => {
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
    expect(nodeChoices([hit('h4', P4)], TOPO)).toEqual(['plateau', 'step', 'step_seg', 'today'])
  })

  it('几次 hit 绑定的 node 合起来;不相干的根和它的子 node 不出现', () => {
    expect(nodeChoices([hit('h4', P4), hit('h6', P6, { other: 'o#0' })], TOPO))
      .toEqual(['other', 'plateau', 'step', 'step_seg', 'other_kid', 'today'])
    expect(nodeChoices([hit('h4', P4)], TOPO)).not.toContain('other_kid')
  })

  it('已选上的 node 当前拓扑里没有了:留着排在最后;没有 hit 时只有它们', () => {
    expect(nodeChoices([hit('h4', P4)], TOPO, ['gone', 'step', 'gone'])).toEqual(['plateau', 'step', 'step_seg', 'today', 'gone'])
    expect(nodeChoices([], TOPO, ['step'])).toEqual(['step'])
    expect(nodeChoices([hit('h4', P4)], null, ['gone'])).toEqual(['gone'])
  })

  it('parent_refs 绕成环也不死循环', () => {
    const loop: Topology = { edges: [], nodes: [
      { node_id: 'a', where_rules: [], parent_refs: [['b', 's']] },
      { node_id: 'b', where_rules: [], parent_refs: [['a', 's']] },
    ] }
    expect(nodeChoices([{ node_index: { a: 'a#0' } }], loop)).toEqual(['a', 'b'])
  })
})

describe('保存条件', () => {
  const d = (extra: Partial<FeedbackDraft>): FeedbackDraft =>
    ({ symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'range', ...extra })

  it('只有一条:note 必写(全是空白不算);node 可点可不点', () => {
    expect(saveProblems(d({}))).toEqual(['note'])
    expect(saveProblems(d({ note: '  ' }))).toEqual(['note'])
    expect(saveProblems(d({ nodes: ['step'] }))).toEqual(['note'])                  // 只点 node 不写 note 存不了
    expect(saveProblems(d({ nodes: ['step'], note: ' \n ' }))).toEqual(['note'])
    expect(saveProblems(d({ note: '追高' }))).toEqual([])                            // 一个 node 都不点也能存
    expect(saveProblems(d({ note: '追高', nodes: [] }))).toEqual([])
    expect(saveProblems(d({ note: '不像', nodes: ['step', 'plateau'] }))).toEqual([])
  })

  it('点出的 node 不得重复或为空', () => {
    expect(saveProblems(d({ note: 'x', nodes: ['step', 'step'] }))).toEqual(['nodes'])
    expect(saveProblems(d({ note: 'x', nodes: [''] }))).toEqual(['nodes'])
    expect(saveProblems(d({ nodes: [''] }))).toEqual(['note', 'nodes'])
  })

  it('日期:start 不晚于 end,end 不晚于训练段末日;point 是同一天', () => {
    expect(saveProblems(d({ note: 'x', start: '2025-01-11' }))).toEqual(['range'])
    expect(saveProblems(d({ note: 'x', end: '2026-01-02' }))).toEqual(['after_train_end'])
    expect(saveProblems(d({ note: 'x', end: '2025-12-31' }))).toEqual([])
    expect(saveProblems(d({ note: 'x', target: 'point' }))).toEqual(['point'])
    expect(saveProblems(d({ note: 'x', target: 'point', start: '2025-01-10' }))).toEqual([])
  })

  it('family 必有起点且不晚于 start;别的 target 不带起点', () => {
    expect(saveProblems(d({ note: 'x', target: 'family' }))).toEqual(['family_start'])
    expect(saveProblems(d({ note: 'x', target: 'family', family_start: '2025-01-07' }))).toEqual(['family_start'])
    expect(saveProblems(d({ note: 'x', target: 'family', family_start: '2025-01-06' }))).toEqual([])
    expect(saveProblems(d({ note: 'x', target: 'family', family_start: '2024-12-02' }))).toEqual([])
    expect(saveProblems(d({ note: 'x', family_start: '2025-01-02' }))).toEqual(['family_start'])
  })
})

describe('草稿转记录', () => {
  const origin = { id: 'f-pc-9', pattern: 'p', app_id: 'app1', app_ver: 'v2' }

  it('不带 answer、不带 dag;理由去掉首尾空白;nodes 点了才带;family_start 只在 family 时带;source 恒为 picked', () => {
    const plain = draftToFeedback({ symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'range',
                                    family_start: '2025-01-02', note: ' 追高 ', nodes: [] }, origin)
    expect(plain).toEqual({ id: 'f-pc-9', pattern: 'p', app_id: 'app1', app_ver: 'v2', start: '2025-01-06',
                            end: '2025-01-10', target: 'range', source: 'picked', note: '追高' })
    expect(Object.keys(plain)).not.toContain('answer')
    expect(Object.keys(plain)).not.toContain('dag')
    expect(Object.keys(plain)).not.toContain('nodes')
    expect(draftToFeedback({ symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'family',
                             family_start: '2025-01-02', note: '不像', nodes: ['step'], issue: 'i-pc-3' }, origin))
      .toEqual({ id: 'f-pc-9', pattern: 'p', app_id: 'app1', app_ver: 'v2', start: '2025-01-06', end: '2025-01-10',
                 target: 'family', source: 'picked', note: '不像', nodes: ['step'], issue: 'i-pc-3',
                 family_start: '2025-01-02' })
  })

  it('草稿上多出来的 answer、dag(类型之外,旧代码传来的)也不写进记录', () => {
    const stray = { symbol: 'AAA', start: '2025-01-06', end: '2025-01-10', target: 'range' as const,
                    note: 'x', nodes: ['step'], answer: 'off_pattern', dag: true }
    const out = draftToFeedback(stray, origin)
    expect('answer' in out).toBe(false)
    expect('dag' in out).toBe(false)
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

describe('issue:几处反馈共享同一份内容', () => {
  const row = (symbol: string, id: string, extra: Partial<AnnFeedback> = {}): FeedbackRow =>
    ({ symbol, feedback: fb(id, '2025-01-06', '2025-01-06', { target: 'point', ...extra }) })
  // i-pc-1:AAA f-pc-2(以前存下的,带 answer)+ BBB f-pc-9(不带 answer),内容都是「追高」;f-pc-5 单独一处;
  // f-pc-7 以前存下的 off_pattern 带 dag;f-pc-8 盲看标记
  const ROWS = [
    row('AAA', 'f-pc-2', { answer: 'neg', note: '追高', issue: 'i-pc-1' }),
    row('AAA', 'f-pc-5', { note: '太晚' }),
    row('BBB', 'f-pc-9', { note: '追高', issue: 'i-pc-1' }),
    row('BBB', 'f-pc-7', { answer: 'off_pattern', note: '关系不对', nodes: ['step', 'plateau'], dag: true }),
    row('CCC', 'f-pc-8', { source: 'random', answer: 'pos', note: undefined }),
  ]

  it('分组:带同一个 issue 值的一组(带不带 answer 混在一组也行),不带的各自一组;组序照第一处出现的先后;内容取自成员', () => {
    const gs = issueGroups(ROWS)
    expect(gs.map(g => [g.key, g.issue, g.rows.map(r => r.feedback.id)])).toEqual([
      ['i-pc-1', 'i-pc-1', ['f-pc-2', 'f-pc-9']], ['f-pc-5', null, ['f-pc-5']], ['f-pc-7', null, ['f-pc-7']],
      ['f-pc-8', null, ['f-pc-8']]])
    expect(gs[2]).toMatchObject({ note: '关系不对', nodes: ['step', 'plateau'] })
    expect(gs[0]).toMatchObject({ note: '追高', nodes: [] })
    // 组上不留 answer、dag(界面不显示它们)
    for (const g of gs) expect(Object.keys(g).sort()).toEqual(['issue', 'key', 'nodes', 'note', 'rows'])
    // 盲看标记不参与共享:就算带了 issue 值也自成一组
    expect(issueKey({ id: 'f-pc-8', issue: 'i-pc-1', source: 'random' })).toBe('f-pc-8')
  })

  it('可挑的:用户挑的全部列出(不按答案筛,以前存下的也在);最近用过的在前;去掉只有自己这一处的组', () => {
    expect(issueChoices(ROWS).map(g => g.key)).toEqual(['i-pc-1', 'f-pc-7', 'f-pc-5'])          // 9 > 7 > 5;盲看标记不列
    expect(issueChoices(ROWS, null).map(g => g.key)).toEqual(['i-pc-1', 'f-pc-7', 'f-pc-5'])
    expect(issueChoices(ROWS, 'f-pc-5').map(g => g.key)).toEqual(['i-pc-1', 'f-pc-7'])          // 自己单独一组:不列
    expect(issueChoices(ROWS, 'f-pc-2').map(g => g.key)).toEqual(['i-pc-1', 'f-pc-7', 'f-pc-5'])   // 自己那组还有别的处:列着
    const more = [...ROWS, row('AAA', 'f-upc-30', { note: '量不够' })]
    expect(issueChoices(more).map(g => g.key)).toEqual(['f-upc-30', 'i-pc-1', 'f-pc-7', 'f-pc-5'])
  })

  it('内容改没改:note 去首尾空白后比,nodes 不论顺序;记录上的 answer、dag 不算内容', () => {
    const base = { note: '关系不对', nodes: ['step', 'plateau'] }
    expect(sameContent(base, { note: ' 关系不对 ', nodes: ['plateau', 'step'] })).toBe(true)
    expect(sameContent(base, { ...base, note: '关系不对。' })).toBe(false)
    expect(sameContent(base, { ...base, nodes: ['step'] })).toBe(false)
    expect(sameContent({ note: '' }, { nodes: [] })).toBe(true)
    // 以前存下的 off_pattern + dag 那一组,和只写了同样 note、nodes 的草稿算同一份内容
    const old = issueGroups(ROWS)[2]
    expect(sameContent({ note: '关系不对', nodes: ['plateau', 'step'] }, old)).toBe(true)
    expect(sameContent({ ...base, dag: true, answer: 'neg' } as any, base)).toBe(true)
  })

  it('新的 issue 值:同机器名最大序号加一;别的机器的、认不出的不算;没有则 1', () => {
    expect(nextIssueValue([], 'pc')).toBe('i-pc-1')
    expect(nextIssueValue(['i-pc-1', 'i-pc-12', undefined, null, 'i-upc-40', 'i-pc-x', 'hand-made'], 'pc')).toBe('i-pc-13')
    expect(nextIssueValue(['i-pc-3'], 'upc')).toBe('i-upc-1')
    expect(nextIssueValue(['i-my-pc-7', 'i-my-3'], 'my')).toBe('i-my-4')           // 机器名带连字符的不串
    expect(nextIssueValue(['i-my-pc-7', 'i-my-3'], 'my-pc')).toBe('i-my-pc-8')
  })

  it('保存的安排', () => {
    const gs = issueGroups(ROWS)
    const shared = gs[0], single = gs[1]
    const fresh = () => 'i-pc-NEW'
    // 没连着:不带,别的处不动
    expect(planIssueSave({ note: 'x' }, null, null, null, fresh)).toEqual({ ask: false, issue: null, others: [] })
    // 连着的只有自己:照存,原来的值留着(没有就没有)
    expect(planIssueSave({ note: '改了' }, single, 'f-pc-5', null, fresh)).toEqual({ ask: false, issue: null, others: [] })
    const lone = issueGroups([row('AAA', 'f-pc-2', { note: '追高', issue: 'i-pc-1' })])[0]
    expect(planIssueSave({ note: '改了' }, lone, 'f-pc-2', null, fresh)).toEqual({ ask: false, issue: 'i-pc-1', others: [] })
    // 还有别的处、内容没变:带上它的值;它还没有值就现取、原来那处同批补上
    expect(planIssueSave({ note: '追高' }, shared, null, null, fresh)).toEqual({ ask: false, issue: 'i-pc-1', others: [] })
    expect(planIssueSave({ note: '追高' }, shared, 'f-pc-9', null, fresh)).toEqual({ ask: false, issue: 'i-pc-1', others: [] })
    expect(planIssueSave({ note: '太晚' }, single, null, null, fresh)).toEqual({ ask: false, issue: 'i-pc-NEW', others: ['f-pc-5'] })
    // 还有别的处、内容变了:先问;all 各处同批改;only_this 这一处不带
    expect(planIssueSave({ note: '追高了' }, shared, 'f-pc-9', null, fresh)).toEqual({ ask: true, issue: null, others: [] })
    expect(needsIssueChoice({ note: '追高了' }, shared, 'f-pc-9')).toBe(true)
    expect(needsIssueChoice({ note: '追高' }, shared, 'f-pc-9')).toBe(false)
    expect(needsIssueChoice({ note: '改了' }, single, 'f-pc-5')).toBe(false)
    expect(needsIssueChoice({ note: '改了' }, null, null)).toBe(false)
    expect(planIssueSave({ note: '追高了' }, shared, 'f-pc-9', 'all', fresh)).toEqual({ ask: false, issue: 'i-pc-1', others: ['f-pc-2'] })
    expect(planIssueSave({ note: '追高了' }, shared, null, 'all', fresh))
      .toEqual({ ask: false, issue: 'i-pc-1', others: ['f-pc-2', 'f-pc-9'] })
    expect(planIssueSave({ note: '太晚了' }, single, null, 'all', fresh)).toEqual({ ask: false, issue: 'i-pc-NEW', others: ['f-pc-5'] })
    expect(planIssueSave({ note: '追高了' }, shared, 'f-pc-9', 'only_this', fresh)).toEqual({ ask: false, issue: null, others: [] })
  })

  it('侧栏分组的次序:有朱红的组在前、其次有 lost 的,其余在后;同档的组、组内各处照侧栏排序;不改入参', () => {
    const st = {
      'f-pc-9': { status: 'matched' as const, tag: null, red: true, reason: null },
      'f-pc-7': { status: 'lost' as const, tag: null, red: false, reason: null },
    }
    const picked = ROWS.slice(0, 4)
    const before = picked.map(r => r.feedback.id)
    const gs = sortIssueGroups(picked, st)
    expect(gs.map(g => [g.key, g.rows.map(r => r.feedback.id)])).toEqual([
      ['i-pc-1', ['f-pc-9', 'f-pc-2']],        // 组里有一处朱红:整组在前,朱红那处排组内第一
      ['f-pc-7', ['f-pc-7']],                  // lost
      ['f-pc-5', ['f-pc-5']]])
    expect(picked.map(r => r.feedback.id)).toEqual(before)
    expect(sortIssueGroups(picked, {}).map(g => g.key)).toEqual(['i-pc-1', 'f-pc-5', 'f-pc-7'])   // 都没状态:按股票、日期、编号
  })
})
