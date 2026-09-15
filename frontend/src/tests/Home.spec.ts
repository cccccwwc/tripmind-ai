import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Home from '@/views/Home.vue'
import { createTripJob, discoverRecommendations, extractLongTermMemories, listLongTermMemories, refinePlanningBrief, subscribeTripJob } from '@/services/api'


const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
}))

vi.mock('@/services/api', () => ({
  refinePlanningBrief: vi.fn(),
  discoverRecommendations: vi.fn(),
  generateTripPlan: vi.fn(),
  createTripJob: vi.fn(),
  getTripJob: vi.fn(),
  cancelTripJob: vi.fn(),
  retryTripJob: vi.fn(),
  resumeTripJob: vi.fn(),
  subscribeTripJob: vi.fn(),
  listLongTermMemories: vi.fn().mockResolvedValue([]),
  extractLongTermMemories: vi.fn(),
  updateLongTermMemory: vi.fn(),
  forgetLongTermMemory: vi.fn(),
}))


describe('Home page', () => {
  beforeEach(() => {
    vi.mocked(listLongTermMemories).mockResolvedValue([])
    vi.mocked(extractLongTermMemories).mockResolvedValue({ conversation_id: 'conversation-auto', memories: [] })
  })

  it('renders conversation-first intake and a visible Planning Brief', () => {
    const wrapper = shallowMount(Home)
    const text = wrapper.text()

    expect(wrapper.find('.memory-sidebar').exists()).toBe(true)
    expect(wrapper.find('.chat-workspace').exists()).toBe(true)
    expect(text).toContain('我的旅行画像')
    expect(text).toContain('先对话，再开跑。')
    expect(text).toContain('对话澄清')
    expect(text).toContain('选择推荐')
    expect(text).toContain('生成行程')
    expect(text).toContain('PLANNING BRIEF')
    expect(text).toContain('目的地')
    expect(text).toContain('出发日期')
    expect(text).toContain('返程日期')
    expect(text).toContain('本次画像应用')
    expect(text).toContain('3 项待补充')
  })

  it('does not search until the user confirms a complete brief', async () => {
    vi.mocked(refinePlanningBrief).mockResolvedValue({
      success: true,
      assistant_message: '信息已经整理好了，请检查右侧简报后确认。',
      brief: {
        city: '杭州',
        start_date: '2026-09-20',
        end_date: '2026-09-23',
        travel_days: 4,
        transportation: '高铁',
        accommodation: '舒适型酒店',
        preferences: ['历史文化', '美食'],
        free_text_input: '9月20日到23日去杭州',
        memory_projection: { visited_places: ['西湖'], carryover_places: ['灵隐寺'] }
      },
      missing_fields: [],
      ready_to_confirm: true
    })
    vi.mocked(discoverRecommendations).mockResolvedValue({
      success: true,
      message: 'ok',
      query: '杭州旅行推荐',
      data: []
    })

    const wrapper = shallowMount(Home)
    const buttons = () => wrapper.findAll('button')
    const findButton = (label: string) => buttons().find(button => button.text().includes(label))
    const confirmBefore = findButton('确认 Brief')
    expect(confirmBefore?.attributes('disabled')).toBeDefined()

    await wrapper.find('textarea').setValue('9月20日到23日去杭州，喜欢历史文化和美食，坐高铁')
    await findButton('发送')?.trigger('click')
    await flushPromises()

    expect(refinePlanningBrief).toHaveBeenCalledOnce()
    expect(discoverRecommendations).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('2026-09-20 — 2026-09-23')
    expect(wrapper.text()).toContain('西湖')
    expect(wrapper.text()).toContain('灵隐寺')

    const confirmAfter = findButton('确认 Brief')
    expect(confirmAfter?.attributes('disabled')).toBeUndefined()
    await confirmAfter?.trigger('click')
    await flushPromises()

    expect(discoverRecommendations).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('杭州旅行灵感榜')
  })

  it('automatically extracts traceable profile candidates after a chat turn', async () => {
    vi.mocked(refinePlanningBrief).mockResolvedValue({
      success: true,
      assistant_message: '记住了，你更喜欢慢节奏旅行。',
      brief: {
        city: '苏州', start_date: null, end_date: null, travel_days: null,
        transportation: '公共交通', accommodation: '舒适型酒店',
        preferences: ['慢节奏'], free_text_input: '我喜欢慢慢逛，不喜欢频繁换酒店',
        memory_projection: { visited_places: [], carryover_places: [] }
      },
      missing_fields: ['start_date', 'end_date'],
      ready_to_confirm: false
    })

    const wrapper = shallowMount(Home)
    await wrapper.find('textarea').setValue('我喜欢慢慢逛，不喜欢频繁换酒店')
    const sendButton = wrapper.findAll('button').find(button => button.text().includes('发送'))
    await sendButton?.trigger('click')
    await flushPromises()

    expect(extractLongTermMemories).toHaveBeenCalledOnce()
    expect(vi.mocked(extractLongTermMemories).mock.calls[0][0]).toMatchObject({
      user_id: 'local-user',
      city: '苏州'
    })
    expect(vi.mocked(extractLongTermMemories).mock.calls[0][0].messages).toEqual(
      expect.arrayContaining([expect.objectContaining({ role: 'user', content: '我喜欢慢慢逛，不喜欢频繁换酒店' })])
    )
  })

  it('only sends newly added messages during automatic profile extraction', async () => {
    vi.mocked(refinePlanningBrief)
      .mockResolvedValueOnce({
        success: true,
        assistant_message: '好的，已记录不去西湖。',
        brief: {
          city: '杭州', start_date: null, end_date: null, travel_days: null,
          transportation: '公共交通', accommodation: '舒适型酒店',
          preferences: [], free_text_input: '不要去西湖',
          memory_projection: { visited_places: [], carryover_places: [] }
        },
        missing_fields: ['start_date', 'end_date'],
        ready_to_confirm: false
      })
      .mockResolvedValueOnce({
        success: true,
        assistant_message: '好的，已记录不喜欢烧烤。',
        brief: {
          city: '杭州', start_date: null, end_date: null, travel_days: null,
          transportation: '公共交通', accommodation: '舒适型酒店',
          preferences: [], free_text_input: '不喜欢烧烤',
          memory_projection: { visited_places: [], carryover_places: [] }
        },
        missing_fields: ['start_date', 'end_date'],
        ready_to_confirm: false
      })

    const wrapper = shallowMount(Home)
    const send = () => wrapper.findAll('button').find(button => button.text().includes('发送'))

    await wrapper.find('textarea').setValue('不要去西湖')
    await send()?.trigger('click')
    await flushPromises()

    await wrapper.find('textarea').setValue('不喜欢烧烤')
    await send()?.trigger('click')
    await flushPromises()

    expect(extractLongTermMemories).toHaveBeenCalledTimes(2)
    const secondRequest = vi.mocked(extractLongTermMemories).mock.calls[1][0]
    expect(secondRequest.conversation_id).toBe('conversation-auto')
    expect(secondRequest.messages).toEqual(
      expect.arrayContaining([expect.objectContaining({ role: 'user', content: '不喜欢烧烤' })])
    )
    expect(secondRequest.messages.some(message => message.content.includes('不要去西湖'))).toBe(false)
  })

  it('hides JSON parser internals and keeps the conversation usable', async () => {
    vi.mocked(refinePlanningBrief).mockRejectedValue(
      new Error('Expecting value: line 1 column 1 (char 0)')
    )

    const wrapper = shallowMount(Home)
    await wrapper.find('textarea').setValue('只去成都')
    const sendButton = wrapper.findAll('button').find(button => button.text().includes('发送'))
    await sendButton?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('Expecting value')
    expect(wrapper.text()).toContain('你之前提供的信息仍然保留')
    expect(wrapper.find('textarea').attributes('disabled')).toBeUndefined()
  })

  it('shows a duration conflict and blocks brief confirmation', async () => {
    vi.mocked(refinePlanningBrief).mockResolvedValue({
      success: true,
      assistant_message: '你之前计划玩 4 天，但当前日期跨度是 9 天。',
      brief: {
        city: '成都',
        start_date: '2026-10-01',
        end_date: '2026-10-09',
        requested_days: 4,
        travel_days: 9,
        transportation: '公共交通',
        accommodation: '舒适型酒店',
        preferences: [],
        free_text_input: '',
        memory_projection: { visited_places: [], carryover_places: [] }
      },
      missing_fields: ['duration_conflict'],
      ready_to_confirm: false
    })

    const wrapper = shallowMount(Home)
    await wrapper.find('textarea').setValue('10.1-10.9')
    const sendButton = wrapper.findAll('button').find(button => button.text().includes('发送'))
    await sendButton?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('天数冲突')
    expect(wrapper.text()).toContain('原计划 4 天 · 日期跨度 9 天')
    expect(wrapper.text()).toContain('按 9 天')
    const confirmButton = wrapper.findAll('button').find(button => button.text().includes('确认 Brief'))
    expect(confirmButton?.attributes('disabled')).toBeDefined()
    expect(discoverRecommendations).not.toHaveBeenCalled()
  })

  it('submits a background job and renders real SSE node progress', async () => {
    vi.mocked(refinePlanningBrief).mockResolvedValue({
      success: true,
      assistant_message: '信息已齐，请确认。',
      brief: {
        city: '开封', start_date: '2026-09-20', end_date: '2026-09-20', travel_days: 1,
        transportation: '公共交通', accommodation: '舒适型酒店', preferences: [],
        free_text_input: '', memory_projection: { visited_places: [], carryover_places: [] }
      },
      missing_fields: [],
      ready_to_confirm: true
    })
    vi.mocked(discoverRecommendations).mockResolvedValue({
      success: true, message: 'ok', query: '开封', data: []
    })
    vi.mocked(createTripJob).mockResolvedValue({
      success: true,
      job_id: 'job-1',
      workflow_id: 'trip-1',
      status: 'queued',
      progress: 2,
      current_step: 'queued',
      message: '任务已提交',
      can_cancel: true,
      can_retry: false,
      can_resume: false,
      created_at: '2026-09-14T00:00:00Z',
      updated_at: '2026-09-14T00:00:00Z'
    })
    vi.mocked(subscribeTripJob).mockImplementation((_jobId, onEvent) => {
      onEvent({
        job_id: 'job-1', type: 'progress', status: 'running', progress: 12,
        current_step: 'prepare', node: 'prepare', node_status: 'completed',
        message: '开始并行查询景点、天气和酒店'
      })
      onEvent({
        job_id: 'job-1', type: 'progress', status: 'running', progress: 44,
        current_step: 'weather', node: 'weather', node_status: 'completed',
        message: '已获得天气数据'
      })
      return vi.fn()
    })

    const wrapper = shallowMount(Home)
    const findButton = (label: string) => wrapper.findAll('button').find(button => button.text().includes(label))
    await wrapper.find('textarea').setValue('9月20日去开封')
    await findButton('发送')?.trigger('click')
    await flushPromises()
    await findButton('确认 Brief')?.trigger('click')
    await flushPromises()
    await findButton('直接生成行程')?.trigger('click')
    await flushPromises()

    expect(createTripJob).toHaveBeenCalledOnce()
    expect(subscribeTripJob).toHaveBeenCalledWith('job-1', expect.any(Function), expect.any(Function))
    expect(wrapper.text()).toContain('已获得天气数据')
    expect(wrapper.text()).toContain('已理解旅行需求')
    expect(wrapper.find('.job-progress-item.completed').text()).toContain('已理解旅行需求')
  })
})
