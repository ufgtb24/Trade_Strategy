import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PendingIcon from '../src/shared/PendingIcon.vue'

describe('PendingIcon', () => {
  it('refs_other_node 显 ⚠ + title', () => {
    const w = mount(PendingIcon, { props: { reason: 'refs_other_node' } })
    expect(w.text()).toContain('⚠')
    expect(w.attributes('title')).toContain('跨节点')
  })
  it('cross_node_pending 显 ⚠', () => {
    const w = mount(PendingIcon, { props: { reason: 'cross_node_pending' } })
    expect(w.text()).toContain('⚠')
  })
})
