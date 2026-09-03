// Task 11 · instance_id 真实数据验收(APCX 双实例)。
// 数据源:tests/fixtures/apcx-instance-id-acceptance.json —— 新后端(instance_id 契约)
// 对 APCX 单股重算的快照(与历史 scan 20260813T005540 同窗同参;旧 -instanced 文件为
// 新契约前产物含 event_id/source_tag/class_id/instance_key,不兼容,故重算单存新文件)。
// 断言(数据级 + 实例级入口 + 真共享待选择):
//   ① 数据级:事件行无 event_id/source_tag/class_id/instance_key 字段;instance_id 恒带 #idx;
//      tb_293#0/#1 两实例(node_id='tb')各被一个 match 的 node_index 精确引用
//   ② 实例级入口:focusEvent('tb_293#0') → 直选 match A;focusEvent('tb_293#1') → 直选 match B;无待选择
//   ③ 真共享 fixture:同一 instance_id 被两 match 引用 → 待选择
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import fs from 'node:fs'
import path from 'node:path'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, MatchDict, EventDict } from '../src/types'

// vitest 环境不便 import json(项目无此先例),按旧 instance-binding 测试用 fs.readFile + JSON.parse,
// fixture 挪入 tests/fixtures(outputs 不进 git);路径相对 path2_web_ui/(vitest 调用方 cwd)。
const scanJson = JSON.parse(
  fs.readFileSync(
    path.resolve(process.cwd(), 'tests/fixtures/apcx-instance-id-acceptance.json'),
    'utf-8',
  ),
) as MultiScanResultFile

const analysis = scanJson.results[0].per_pattern['bb_v1'].analysis

const OLD_IDENTITY_FIELDS = ['event_id', 'source_tag', 'class_id', 'instance_key']

/** node_index 中引用 instanceId 的 match 列表(值 = instance_id 字符串精确引用)。 */
function matchesReferencing(instanceId: string): MatchDict[] {
  return analysis.matches.filter(m => Object.values(m.node_index).includes(instanceId))
}

/** 真共享 fixture:基于真实 scan 深拷贝,把两 match 的 node_index 都改成引用
 *  tb_293#0(同一 instance_id 被两 match 引用——真正的场景 B)。 */
function makeSharedFixture(): MultiScanResultFile {
  const base = JSON.parse(JSON.stringify(scanJson)) as MultiScanResultFile
  const a = base.results[0].per_pattern['bb_v1'].analysis
  const ev0 = a.events.find(e => e.instance_id === 'tb_293#0') as EventDict
  a.matches = [
    { match_id: 'm-shared-a', start_idx: 293, end_idx: 293,
      node_index: { burst: 'burst_282_289#0', tb: 'tb_293#0' },
      children: ['burst_282_289#0', 'tb_293#0'] } as MatchDict,
    { match_id: 'm-shared-b', start_idx: 293, end_idx: 293,
      node_index: { burst: 'burst_282_290#0', tb: 'tb_293#0' },
      children: ['burst_282_290#0', 'tb_293#0'] } as MatchDict,
  ]
  void ev0
  return base
}

describe('instance-id 真实数据验收(APCX · bb_v1)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('① 数据级:事件行无旧身份字段;instance_id 恒带 #idx;tb_293#0/#1 各被一个 match 精确引用', () => {
    // 事件行无 event_id/source_tag/class_id/instance_key 字段
    for (const e of analysis.events) {
      for (const f of OLD_IDENTITY_FIELDS) {
        expect(e).not.toHaveProperty(f)
      }
    }
    // instance_id 恒带 #idx
    for (const e of analysis.events) {
      expect(e.instance_id).toMatch(/#\d+$/)
      expect(e.instance_id).toBe(`${e.node_id}_${e.start_idx}${e.end_idx !== e.start_idx ? `_${e.end_idx}` : ''}#${e.instance_idx}`)
    }
    // tb 双实例(同一 (node_id, span) 桶内 idx 0/1)
    const tbEvs = analysis.events.filter(e => e.node_id === 'tb') as EventDict[]
    const tb293 = tbEvs.filter(e => e.start_idx === 293 && e.end_idx === 293)
    expect(tb293).toHaveLength(2)
    expect(tb293.map(e => e.instance_id).sort()).toEqual(['tb_293#0', 'tb_293#1'])
    // 每实例恰被一个 match 引用(实例分属,无共享)
    expect(matchesReferencing('tb_293#0')).toHaveLength(1)
    expect(matchesReferencing('tb_293#1')).toHaveLength(1)
    // 两引用对应不同 match
    expect(matchesReferencing('tb_293#0')[0].match_id).not.toBe(matchesReferencing('tb_293#1')[0].match_id)
    // match.node_index 值是 instance_id 字符串,且 matches 也引用同一批实例
    for (const m of analysis.matches) {
      for (const inst of Object.values(m.node_index)) {
        expect(typeof inst).toBe('string')
        expect(analysis.events.some(e => e.instance_id === inst)).toBe(true)
      }
    }
  })

  it('② 实例级入口:focusEvent 分别直选对应 match,不弹待选择', () => {
    const view = useViewStore()
    view.loadScanFile(scanJson)
    const m0 = matchesReferencing('tb_293#0')[0]
    const m1 = matchesReferencing('tb_293#1')[0]

    view.focusEvent('tb_293#0')
    expect(view.focusedMatchId).toBe(m0.match_id)          // 直选 match A(引用 #0)
    expect(view.focusedInstanceId).toBe('tb_293#0')
    expect(view.pendingDisambigInstanceId).toBeNull()       // 不再弹待选择

    view.focusEvent('tb_293#1')
    expect(view.focusedMatchId).toBe(m1.match_id)          // 直选 match B(引用 #1)
    expect(view.focusedInstanceId).toBe('tb_293#1')
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('③ 真共享 fixture:同一 instance_id 被两 match 引用 → 仍待选择', () => {
    const view = useViewStore()
    view.loadScanFile(makeSharedFixture())
    view.focusEvent('tb_293#0')                             // 实例级入口,但实例真共享
    expect(view.pendingDisambigInstanceId).toBe('tb_293#0')
    expect(view.candidateMatchIds.size).toBe(2)
    expect(view.focusedMatchId).toBeNull()
  })
})
