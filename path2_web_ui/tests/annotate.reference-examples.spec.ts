// 整族反馈按基准 node 认「同一次形状」:前端 annotate/feedback.ts 的 feedbackHits(选中一条反馈时牵出的 hit)与
// referenceSpans(新建整族反馈时存下的基准 event 起止)逐例通过与后端 path2_web/annotation/match.py(feedback_hits)、
// path2_web/app_run.py(app_buys)共用的例子文件(唯一的事实来源,不另抄答案;后端那一半见
// tests/path2_web/test_annotation_match.py)。状态三态只由后端判,前端不判,这里只比收进来的 hit 与存下的起止。
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { feedbackHits, referenceSpans } from '../src/annotate/feedback'
import type { EventDict, HitDict } from '../src/types'

const FILE = resolve(__dirname, '../../tests/path2_web/fixtures/reference_examples.json')
const doc = JSON.parse(readFileSync(FILE, 'utf8'))
const days: string[] = doc.days
const events = doc.analysis.events as EventDict[]
const hits = doc.analysis.hits as HitDict[]

describe('reference_examples.json:一条反馈收进来的 hit', () => {
  for (const c of doc.cases as any[]) {
    it(`${c.name}`, () => {
      const got = feedbackHits(hits, events, doc.end_node, days, c.feedback, c.declared).map(h => h.hit_id)
      expect(got, c.why).toEqual(c.expect.hits)
    })
  }
})

describe('reference_examples.json:新建整族反馈存下的基准 event 起止', () => {
  for (const f of doc.families as any[]) {
    it(`起点 ${f.start} 的那一族`, () => {
      const fam = hits.filter(h => h.start_idx === f.start)
      expect(fam.length).toBeGreaterThan(0)
      expect(referenceSpans(fam, events, doc.reference, days)).toEqual(f.spans)
    })
  }
})
