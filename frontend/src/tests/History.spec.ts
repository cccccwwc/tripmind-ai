import { shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import History from '@/views/History.vue'
import { useTravelMemory } from '@/services/travelMemory'
import { useTripPlanMemory } from '@/services/tripPlanMemory'


const mocks = vi.hoisted(() => ({ routerPush: vi.fn() }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
}))

const savedTrip = {
  id: 'trip-hangzhou',
  title: '杭州 · 2日旅行计划',
  created_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-09-02T08:00:00Z',
  plan: {
    city: '杭州',
    start_date: '2026-10-01',
    end_date: '2026-10-02',
    weather_info: [],
    overall_suggestions: '提前预约。',
    days: [{
      date: '2026-10-01', day_index: 0, description: '西湖漫步',
      transportation: '公共交通', accommodation: '舒适型酒店', meals: [],
      attractions: [{ name: '西湖', address: '杭州市西湖区', visit_duration: 120, description: '游览西湖' }]
    }, {
      date: '2026-10-02', day_index: 1, description: '寺院文化',
      transportation: '公共交通', accommodation: '舒适型酒店', meals: [],
      attractions: [{ name: '灵隐寺', address: '杭州市西湖区', visit_duration: 120, description: '参观寺院' }]
    }]
  }
}

describe('History page', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    mocks.routerPush.mockReset()
    localStorage.setItem('tripmind_saved_trip_plans_v1', JSON.stringify([savedTrip]))
    const { removeVisited } = useTravelMemory()
    removeVisited('西湖', '杭州')
    removeVisited('灵隐寺', '杭州')
  })

  it('renders saved trip summaries and opens a trip on its own route', async () => {
    const wrapper = shallowMount(History)
    const text = wrapper.text()

    expect(text).toContain('历史行程')
    expect(text).toContain('杭州 · 2日旅行计划')
    expect(text).toContain('西湖')
    expect(text).toContain('灵隐寺')

    const openButton = wrapper.findAll('button').find(button => button.text().includes('查看完整行程'))
    await openButton?.trigger('click')

    expect(mocks.routerPush).toHaveBeenCalledWith('/result')
    expect(JSON.parse(sessionStorage.getItem('tripPlan') || '{}').city).toBe('杭州')

    const continueButton = wrapper.findAll('button').find(button => button.text().includes('继续规划'))
    await continueButton?.trigger('click')

    expect(mocks.routerPush).toHaveBeenCalledWith('/')
    expect(JSON.parse(sessionStorage.getItem('tripmindContinueTrip') || '{}').plan.city).toBe('杭州')
  })

  it('shows the remaining place first instead of hiding it behind visited places', () => {
    const { markVisited } = useTravelMemory()
    markVisited({ name: '西湖', city: '杭州', category: '景点' })

    const wrapper = shallowMount(History)
    const places = wrapper.findAll('.place-list > span')

    expect(wrapper.text()).toContain('待去 1 · 共 2')
    expect(places[0].text()).toContain('灵隐寺')
    expect(wrapper.text()).toContain('继续规划 1 处')
  })

  it('recognizes legacy timeline labels as the same attraction', () => {
    const { markVisited } = useTravelMemory()
    markVisited({ name: '游览灵隐寺（含预约）', city: '杭州', category: '景点' })

    const wrapper = shallowMount(History)

    expect(wrapper.text()).toContain('待去 1 · 共 2')
    expect(wrapper.findAll('.place-list > span')[1].classes()).toContain('visited')
  })

  it('does not count attractions omitted from the actual daily timeline', () => {
    const scheduledPlan = JSON.parse(JSON.stringify(savedTrip.plan))
    scheduledPlan.days[0].attractions.push({
      name: '未排入时间轴的地点', address: '杭州', visit_duration: 60, description: '仅存在于原始列表'
    })
    scheduledPlan.days[0].schedule = [{
      start_time: '09:00', end_time: '11:00', item_type: 'attraction',
      title: '游览西湖', location: '杭州市西湖区', duration_minutes: 120
    }]
    scheduledPlan.days[1].schedule = [{
      start_time: '09:00', end_time: '11:00', item_type: 'attraction',
      title: '灵隐寺（含预约）', location: '杭州市西湖区', duration_minutes: 120
    }]
    useTripPlanMemory().saveTripPlan(scheduledPlan)

    const wrapper = shallowMount(History)

    expect(wrapper.text()).toContain('待去 2 · 共 2')
    expect(wrapper.text()).not.toContain('未排入时间轴的地点')
  })
})
