// compare 下副图的轨序(render/compareLayout.ts):用户的特征轨照 annotate 的顺序,map 了的轨下面紧跟它对的那个 node
// 的 band 组(这个 node 及其子 node,按拓扑 produced_by),没 map 的留在原位挂 unmapped,没被拉走的 band 接在后面挂
// app_only,unnamed 轨最后。只看标注的轨、mapping 与拓扑,不认事件类型。
import { describe, it, expect } from 'vitest'
import { compareSlots, type Slot } from '../src/render/compareLayout'
import type { Lane } from '../src/annotate/model'
import type { Topology } from '../src/types'

const lane = (key: string | null): Lane => ({ key, parent: null, rows: 1, boxes: [] })
const topo = (nodes: [string, string | null][]): Topology =>
  ({ nodes: nodes.map(([id, p]) => ({ node_id: id, produced_by: p } as any)), edges: [] })
// new_step 的样子:plateau 有四个子 node;用户轨:底部平稳(没 map)、站上新平台(map 到 plateau)、unnamed
const NEW_STEP = topo([['plateau', null], ['old_plat', 'plateau'], ['step', 'plateau'], ['new_plat', 'plateau'], ['today', 'plateau']])
const BANDS = ['plateau', 'old_plat', 'step', 'new_plat', 'today']
const known = () => true
const show = (slots: Slot[], lanes: readonly Lane[], bands: readonly string[]) =>
  slots.map(s => (s.kind === 'lane' ? `L:${lanes[s.lane].key ?? 'unnamed'}` : `B:${bands[s.band]}`))

describe('compareSlots', () => {
  it('new_step:没 map 的轨留原位,map 到 plateau 的轨下面跟整组 band,unnamed 最后;组的首尾、表头 node', () => {
    const lanes = [lane('w-bottom'), lane('w-step'), lane(null)]
    const r = compareSlots(lanes, BANDS, NEW_STEP, { 'w-step': 'plateau' }, known)
    expect(show(r.slots, lanes, BANDS)).toEqual(
      ['L:w-bottom', 'L:w-step', 'B:plateau', 'B:old_plat', 'B:step', 'B:new_plat', 'B:today', 'L:unnamed'])
    expect(r.groups).toEqual([{ from: 1, to: 6, node: 'plateau' }])
    expect([...r.laneNode]).toEqual([[1, 'plateau']])
    expect([...r.unmapped]).toEqual([0])
    expect([...r.appOnly]).toEqual([])
  })

  it('map 到子 node 的轨插在那条子 band 正前面,仍在同一组里;几条轨 map 到同一组时组只出现一次', () => {
    const lanes = [lane('w-step'), lane('w-jump'), lane('w-step2')]
    const r = compareSlots(lanes, BANDS, NEW_STEP, { 'w-step': 'plateau', 'w-jump': 'step', 'w-step2': 'plateau' }, known)
    expect(show(r.slots, lanes, BANDS)).toEqual(
      ['L:w-step', 'L:w-step2', 'B:plateau', 'B:old_plat', 'L:w-jump', 'B:step', 'B:new_plat', 'B:today'])
    expect(r.groups).toEqual([{ from: 0, to: 7, node: 'plateau' }])
  })

  it('只有子 node 被 map 时,由那条轨把整组拉到它的位置', () => {
    const lanes = [lane('w-a'), lane('w-jump')]
    const r = compareSlots(lanes, BANDS, NEW_STEP, { 'w-jump': 'step' }, known)
    expect(show(r.slots, lanes, BANDS)).toEqual(
      ['L:w-a', 'B:plateau', 'B:old_plat', 'L:w-jump', 'B:step', 'B:new_plat', 'B:today'])
    expect(r.groups).toEqual([{ from: 1, to: 6, node: 'plateau' }])
  })

  it('没被任何轨拉走的 band 照拓扑顺序接在用户轨后面、unnamed 前面,挂 app_only', () => {
    const t = topo([['bo', null], ['burst', null], ['tb', null], ['tb_seg', 'tb']])
    const bands = ['burst', 'tb', 'tb_seg']
    const lanes = [lane('w-x'), lane(null)]
    const r = compareSlots(lanes, bands, t, { 'w-x': 'tb' }, known)
    expect(show(r.slots, lanes, bands)).toEqual(['L:w-x', 'B:tb', 'B:tb_seg', 'B:burst', 'L:unnamed'])
    expect([...r.appOnly]).toEqual([0])
  })

  it('mapping 指向拓扑里没有的 node、或特征编号不在词表里:当作没 map;指向主图上的 node(没有 band):轨留原位、表头照写', () => {
    const t = topo([['bo', null], ['burst', null]])
    const lanes = [lane('w-a'), lane('w-b'), lane('w-c')]
    const r = compareSlots(lanes, ['burst'], t, { 'w-a': 'ghost', 'w-b': 'bo', 'w-c': 'burst' }, (f) => f !== 'w-c')
    expect(show(r.slots, lanes, ['burst'])).toEqual(['L:w-a', 'L:w-b', 'L:w-c', 'B:burst'])
    expect([...r.unmapped].sort()).toEqual([0, 2])
    expect([...r.laneNode]).toEqual([[1, 'bo']])
    expect([...r.appOnly]).toEqual([0])
  })
})
