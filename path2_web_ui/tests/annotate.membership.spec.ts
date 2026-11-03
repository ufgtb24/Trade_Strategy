// 框套框、成员框、骨架与空槽的前端实现,逐例通过后端参照实现共用的例子文件(唯一的事实来源,不另抄答案)。
// 例子里框的起止、样本日写成 days 的下标,调用前换成日期;gap、near 用例子文件自带的 params。
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  dupFeatures, emptySlots, memberTree, parents, sampleMembers, skeleton, MembershipInputError,
} from '../src/annotate/membership'

const FILE = resolve(__dirname, '../../tests/path2_web/fixtures/membership_examples.json')
const doc = JSON.parse(readFileSync(FILE, 'utf8'))
const days: string[] = doc.days
const { gap, near } = doc.params as { gap: number; near: number }

/** 把例子里写成 days 下标的 start / end / date 换成日期,其余原样。 */
function dated(x: any): any {
  if (Array.isArray(x)) return x.map(dated)
  if (x && typeof x === 'object') {
    return Object.fromEntries(Object.entries(x).map(([k, v]) =>
      [k, ['start', 'end', 'date'].includes(k) && typeof v === 'number' ? days[v] : dated(v)]))
  }
  return x
}

function run(c: any): unknown {
  const d = dated(c)
  switch (c.fn) {
    case 'parents': return parents(d.boxes, days)
    case 'members': return sampleMembers(d.date, d.boxes, days,
      { stored: d.stored ?? null, newBoxes: d.new_boxes ?? [], manual: d.manual ?? null, gap })
    case 'tree': return { tree: memberTree(d.members, d.boxes, days), skeleton: skeleton(d.members, d.boxes, days),
                          dup: dupFeatures(d.members, d.boxes, days) }
    case 'slots': return emptySlots(d.charts, d.symbol, d.sample, days, near)
    default: throw new Error(`unknown fn ${c.fn}`)
  }
}

describe('membership_examples.json 的全部例子', () => {
  const cases = doc.cases as any[]
  it('四种例子都有', () => expect(new Set(cases.map(c => c.fn))).toEqual(new Set(['parents', 'members', 'tree', 'slots'])))
  for (const c of cases) {
    it(`${c.fn}: ${c.name}`, () => {
      if (c.expect_error) {
        let err: unknown = null
        try { run(c) } catch (e) { err = e }
        expect(err).toBeInstanceOf(MembershipInputError)
        expect((err as MembershipInputError).code).toBe(c.expect_error)
      } else {
        expect(run(c)).toEqual(c.expect)
      }
    })
  }
})

describe('空槽:坏输入', () => {
  it('找不到图或样本时报 unknown_chart / unknown_sample', () => {
    const charts = [{ symbol: 'AAA', boxes: [], samples: [] }]
    expect(() => emptySlots(charts, 'BBB', 's1', days, near)).toThrow(MembershipInputError)
    try { emptySlots(charts, 'AAA', 's1', days, near) } catch (e) { expect((e as MembershipInputError).code).toBe('unknown_sample') }
  })
})
