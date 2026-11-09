// compare 下用户区与 app 区的对应(render/compareLayout.ts):两区不穿插,这里只算 map 了的特征轨 → node(⇣)、
// 没 map 的(unmapped)、所在组里没有 node 被 map 的 band(app_only)、选中框时要加粗表头的 band(node 及其子孙)。
// 只看标注的轨、mapping 与拓扑 produced_by,不认事件类型。
import { describe, it, expect } from 'vitest'
import { compareLinks } from '../src/render/compareLayout'
import type { Lane } from '../src/annotate/model'
import type { Topology } from '../src/types'

const lane = (key: string | null): Lane => ({ key, parent: null, rows: 1, boxes: [] })
const topo = (nodes: [string, string | null][]): Topology =>
  ({ nodes: nodes.map(([id, p]) => ({ node_id: id, produced_by: p } as any)), edges: [] })
// new_step 的样子:plateau 有四个子 node;用户轨:底部平稳(没 map)、站上新平台(map 到 plateau)、unnamed
const NEW_STEP = topo([['plateau', null], ['old_plat', 'plateau'], ['step', 'plateau'], ['new_plat', 'plateau'], ['today', 'plateau']])
const BANDS = ['plateau', 'old_plat', 'step', 'new_plat', 'today']
const known = () => true

describe('compareLinks', () => {
  it('new_step:map 到 plateau 的轨连 plateau 及四个子 node;没 map 的挂 unmapped;unnamed 都不算;没有 app_only', () => {
    const lanes = [lane('w-bottom'), lane('w-step'), lane(null)]
    const r = compareLinks(lanes, BANDS, NEW_STEP, { 'w-step': 'plateau' }, known)
    expect([...r.laneNode]).toEqual([[1, 'plateau']])
    expect([...r.unmapped]).toEqual([0])
    expect([...r.linkedBands]).toEqual([[1, [0, 1, 2, 3, 4]]])
    expect([...r.appOnly]).toEqual([])
  })

  it('map 到子 node 的轨只连那个子 node(及它的子孙);它所在的组不算 app_only', () => {
    const lanes = [lane('w-jump')]
    const r = compareLinks(lanes, BANDS, NEW_STEP, { 'w-jump': 'step' }, known)
    expect([...r.linkedBands]).toEqual([[0, [2]]])
    expect([...r.appOnly]).toEqual([])
  })

  it('所在组里没有任何 node 被 map 的 band 挂 app_only', () => {
    const t = topo([['bo', null], ['burst', null], ['tb', null], ['tb_seg', 'tb']])
    const bands = ['burst', 'tb', 'tb_seg']
    const r = compareLinks([lane('w-x'), lane(null)], bands, t, { 'w-x': 'tb' }, known)
    expect([...r.linkedBands]).toEqual([[0, [1, 2]]])
    expect([...r.appOnly]).toEqual([0])
  })

  it('mapping 指向拓扑里没有的 node、或特征编号不在词表里:当作没 map;指向主图上的 node(没有 band):表头照写、不连 band', () => {
    const t = topo([['bo', null], ['burst', null]])
    const lanes = [lane('w-a'), lane('w-b'), lane('w-c')]
    const r = compareLinks(lanes, ['burst'], t, { 'w-a': 'ghost', 'w-b': 'bo', 'w-c': 'burst' }, (f: string) => f !== 'w-c')
    expect([...r.unmapped].sort()).toEqual([0, 2])
    expect([...r.laneNode]).toEqual([[1, 'bo']])
    expect([...r.linkedBands]).toEqual([])
    expect([...r.appOnly]).toEqual([0])
  })
})
