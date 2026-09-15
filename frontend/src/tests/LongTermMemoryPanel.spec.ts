import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LongTermMemoryPanel from '@/components/LongTermMemoryPanel.vue'
import type { LongTermMemoryRecord } from '@/types'


const records: LongTermMemoryRecord[] = [
  {
    id: 'pending-1', user_id: 'local-user', kind: 'preference', content: '喜欢慢节奏',
    scope_city: '', status: 'pending', source_conversation_id: 'archive-1',
    source_message_ids: ['12'], evidence: '我喜欢慢慢逛', created_at: '2026-09-13', updated_at: '2026-09-13'
  },
  {
    id: 'approved-1', user_id: 'local-user', kind: 'avoidance', content: '不坐红眼航班',
    scope_city: '', status: 'approved', source_conversation_id: 'archive-2',
    source_message_ids: ['20'], evidence: '我不坐红眼航班', created_at: '2026-09-13', updated_at: '2026-09-13'
  }
]

describe('LongTermMemoryPanel', () => {
  it('shows traceable pending and approved memories with temporary override', async () => {
    const wrapper = mount(LongTermMemoryPanel, {
      props: { records, loading: false, archiving: false, canArchive: true, disabledIds: ['approved-1'] }
    })

    expect(wrapper.text()).toContain('旅行习惯与个人画像')
    expect(wrapper.text()).toContain('待确认的新发现')
    expect(wrapper.text()).toContain('依据原话：“我喜欢慢慢逛”')
    expect(wrapper.text()).toContain('可追溯来源：对话 archive-1 · 消息 12')
    expect(wrapper.text()).toContain('本次不使用')

    const approve = wrapper.findAll('button').find(button => button.text().includes('确认加入画像'))
    await approve?.trigger('click')
    expect(wrapper.emitted('approve')).toHaveLength(1)

    const toggle = wrapper.findAll('button').find(button => button.text().includes('本次不使用'))
    await toggle?.trigger('click')
    expect(wrapper.emitted('toggle')?.[0]).toEqual(['approved-1'])
  })
})
