// 框套框的前端实现逐例通过后端参照实现共用的例子文件(唯一的事实来源,不另抄答案)。
// 例子里框的起止写成 days 的下标,调用前换成日期。本文件跑 parents 例子;members、tree、slots 三种
// 讲的是样本的成员框、骨架与空槽,由放样本、归组那部分的前端实现去过。
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parents, MembershipInputError, type NestBox } from '../src/annotate/membership'

const FILE = resolve(__dirname, '../../tests/path2_web/fixtures/membership_examples.json')
const doc = JSON.parse(readFileSync(FILE, 'utf8'))
const days: string[] = doc.days

const toDates = (boxes: any[]): NestBox[] =>
  boxes.map(b => ({ ...b, start: days[b.start], end: days[b.end] }))

const casesOf = (fn: string) => (doc.cases as any[]).filter(c => c.fn === fn)

describe('框套框:membership_examples.json 的 parents 例子', () => {
  const cases = casesOf('parents')
  it('例子文件里有 parents 例子', () => expect(cases.length).toBeGreaterThan(0))
  for (const c of cases) {
    it(c.name, () => {
      if (c.expect_error) {
        let err: unknown = null
        try { parents(toDates(c.boxes), days) } catch (e) { err = e }
        expect(err).toBeInstanceOf(MembershipInputError)
        expect((err as MembershipInputError).code).toBe(c.expect_error)
      } else {
        expect(parents(toDates(c.boxes), days)).toEqual(c.expect)
      }
    })
  }
})
