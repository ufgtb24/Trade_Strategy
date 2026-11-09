// 样本 match 的前端实现(compareRead.ts 的 matchOf)逐例通过与后端 path2_web/annotation/match.py 的 sample_match
// 共用的例子文件(唯一的事实来源,不另抄答案)。样本日、买点日写成 days 的下标;容差用例子文件自带的 params。
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { matchOf } from '../src/annotate/compareRead'
import type { HitDict } from '../src/types'

const FILE = resolve(__dirname, '../../tests/path2_web/fixtures/match_examples.json')
const doc = JSON.parse(readFileSync(FILE, 'utf8'))
const days: string[] = doc.days
const dayIdx = new Map(days.map((d, i) => [d, i]))
const tol = { pos: doc.params.pos as number, neg: doc.params.neg as number, sub: 0 }

function run(c: any): 'matched' | 'unmatched' {
  // 样本日写成日期且不在 K 线里时:界面上画不出这个样本(stores/compare.ts 先按 K 线日期过滤样本),不求 match
  const day = typeof c.day === 'number' ? c.day : dayIdx.get(c.date)
  if (day === undefined) return 'unmatched'
  const buys = c.hits as number[][]
  const hits = buys.map((_, i) => ({ hit_id: `h${i}` }) as unknown as HitDict)
  const byHit = new Map(hits.map((h, i) => [h.hit_id, buys[i]]))
  return matchOf(day, c.judgment, hits, h => byHit.get(h.hit_id)!, tol).state
}

describe('match_examples.json 的全部例子', () => {
  const cases = doc.cases as any[]
  it('两种 judgment、两种答案都有', () => {
    expect(new Set(cases.map(c => `${c.judgment}:${c.expect}`)))
      .toEqual(new Set(['pos:matched', 'pos:unmatched', 'neg:matched', 'neg:unmatched']))
  })
  for (const c of cases) {
    it(`${c.name}`, () => expect(run(c)).toBe(c.expect))
  }
})
