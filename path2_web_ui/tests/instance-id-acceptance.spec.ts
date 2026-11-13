// Task 11 · instance_id 真实数据验收(APCX 双实例)。
// 数据源:tests/fixtures/apcx-instance-id-acceptance.json —— 新后端(instance_id 契约)
// 对 APCX 单股重算的快照(与历史 scan 20260813T005540 同窗同参;旧 -instanced 文件为
// 新契约前产物含 event_id/source_tag/class_id/instance_key,不兼容,故重算单存新文件)。
// 断言(数据级 + 实例级入口 + 真共享):
//   ① 数据级:事件行无 event_id/source_tag/class_id/instance_key 字段;instance_id 恒带 #idx;
//      tb_293#0/#1 两实例(node_id='tb')各被一个 hit 的 node_index 精确引用
//   ② 实例级入口:focusEvent('tb_293#0') → 选中 #0,细框是 hit A;focusEvent('tb_293#1') → 选中 #1,细框是 hit B
//   ③ 真共享 fixture:同一 instance_id 被两 hit 引用 → 选中这个实例,两次 hit 都画细框
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import fs from 'node:fs'
import path from 'node:path'
import { useViewStore } from '../src/stores/view'
import type { MultiScanResultFile, HitDict, EventDict } from '../src/types'

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

/** node_index 中引用 instanceId 的 hit 列表(值 = instance_id 字符串精确引用)。 */
function hitsReferencing(instanceId: string): HitDict[] {
  return analysis.hits.filter(m => Object.values(m.node_index).includes(instanceId))
}

/** 真共享 fixture:基于真实 scan 深拷贝,把两 hit 的 node_index 都改成引用
 *  tb_293#0(同一 instance_id 被两 hit 引用——真正的场景 B)。 */
function makeSharedFixture(): MultiScanResultFile {
  const base = JSON.parse(JSON.stringify(scanJson)) as MultiScanResultFile
  const a = base.results[0].per_pattern['bb_v1'].analysis
  const ev0 = a.events.find(e => e.instance_id === 'tb_293#0') as EventDict
  a.hits = [
    { hit_id: 'm-shared-a', start_idx: 293, end_idx: 293,
      node_index: { burst: 'burst_282_289#0', tb: 'tb_293#0' },
      children: ['burst_282_289#0', 'tb_293#0'] } as HitDict,
    { hit_id: 'm-shared-b', start_idx: 293, end_idx: 293,
      node_index: { burst: 'burst_282_290#0', tb: 'tb_293#0' },
      children: ['burst_282_290#0', 'tb_293#0'] } as HitDict,
  ]
  void ev0
  return base
}

describe('instance-id 真实数据验收(APCX · bb_v1)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('① 数据级:事件行无旧身份字段;instance_id 恒带 #idx;tb_293#0/#1 各被一个 hit 精确引用', () => {
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
    // 每实例恰被一个 hit 引用(实例分属,无共享)
    expect(hitsReferencing('tb_293#0')).toHaveLength(1)
    expect(hitsReferencing('tb_293#1')).toHaveLength(1)
    // 两引用对应不同 hit
    expect(hitsReferencing('tb_293#0')[0].hit_id).not.toBe(hitsReferencing('tb_293#1')[0].hit_id)
    // hit.node_index 值是 instance_id 字符串,且 hits 也引用同一批实例
    for (const m of analysis.hits) {
      for (const inst of Object.values(m.node_index)) {
        expect(typeof inst).toBe('string')
        expect(analysis.events.some(e => e.instance_id === inst)).toBe(true)
      }
    }
  })

  it('② 实例级入口:focusEvent 按实例认——选中的是点的那个实例,用到它的那次 hit 画细框(两个实例各对各的)', () => {
    const view = useViewStore()
    view.loadScanFile(scanJson)
    const m0 = hitsReferencing('tb_293#0')[0]
    const m1 = hitsReferencing('tb_293#1')[0]

    view.focusEvent('tb_293#0')
    expect(view.selectedInstanceId).toBe('tb_293#0')
    expect([...view.candidateHitIds]).toEqual([m0.hit_id])  // 用到 #0 的是 hit A
    expect(view.focusedHitId).toBeNull()                    // 点 event 只选中 event
    expect(view.pendingDisambigInstanceId).toBeNull()

    view.focusEvent('tb_293#1')
    expect(view.selectedInstanceId).toBe('tb_293#1')
    expect([...view.candidateHitIds]).toEqual([m1.hit_id])  // 用到 #1 的是 hit B
    expect(view.pendingDisambigInstanceId).toBeNull()
  })

  it('③ 真共享 fixture:同一 instance_id 被两 hit 引用;共享的就是买点(买入日相同)→ 选中这个实例,两次都画细框', () => {
    const view = useViewStore()
    view.loadScanFile(makeSharedFixture())
    view.focusEvent('tb_293#0')                             // 实例级入口,实例真共享,且就是 end_node(tb)
    expect(view.selectedInstanceId).toBe('tb_293#0')
    expect([...view.candidateHitIds]).toEqual(['m-shared-a', 'm-shared-b'])
    expect(view.focusedHitId).toBeNull()
    expect(view.selInfo!.buys).toBe('293 ×1')               // 两次买在同一天(没有交易日表时写下标)
    expect(view.selInfo!.hits!.head).toBe('×2')
  })
})
