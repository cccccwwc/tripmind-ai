import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Result from '@/views/Result.vue'


const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  mapAdd: vi.fn(),
  mapFit: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
}))

vi.mock('@amap/amap-jsapi-loader', () => ({
  default: {
    load: vi.fn().mockResolvedValue({
      Map: class {
        add = mocks.mapAdd
        setFitView = mocks.mapFit
        destroy() {}
      },
      Marker: class { on() {}; getPosition() { return [114.34, 34.8] } },
      Polyline: class {},
      InfoWindow: class { open() {} },
      Pixel: class {},
    }),
    reset: vi.fn(),
  },
}))

vi.mock('html2canvas', () => ({ default: vi.fn() }))
vi.mock('jspdf', () => ({ default: class {} }))


const tripPlan = {
  city: '开封',
  start_date: '2026-09-13',
  end_date: '2026-09-13',
  overall_suggestions: '提前预约热门景区。',
  weather_info: [],
  days: [{
    date: '2026-09-13',
    day_index: 0,
    description: '宋文化一日游',
    transportation: '公共交通',
    accommodation: '舒适型酒店',
    hotel: {
      name: '开封中心酒店', address: '鼓楼区', price_range: '300元',
      rating: '4.5', distance: '2公里', type: '舒适型', estimated_cost: 300,
    },
    attractions: [{
      name: '清明上河园',
      address: '开封市龙亭区',
      location: { longitude: 114.340685, latitude: 34.809044 },
      visit_duration: 120,
      description: '宋文化主题景区',
      category: '历史文化',
      poi_id: 'B017A00OOX',
      ticket_price: 120,
    }],
    meals: [],
    schedule: [{
      start_time: '09:00', end_time: '11:00', item_type: 'attraction',
      title: '清明上河园', location: '开封市龙亭区', description: '游览园区',
      duration_minutes: 120, estimated_cost: 120,
    }],
  }],
}


describe('Result page', () => {
  beforeEach(() => {
    mocks.mapAdd.mockClear()
    mocks.mapFit.mockClear()
  })

  it('shows an empty state when no trip has been generated', async () => {
    const wrapper = shallowMount(Result)
    await flushPromises()

    expect(wrapper.text()).toContain('返回首页输入目的地')
    expect(wrapper.text()).toContain('返回首页创建行程')
  })

  it('renders itinerary overview, verified attraction and daily timeline', async () => {
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ prepared: 0 }),
    }))

    const wrapper = shallowMount(Result)
    await flushPromises()
    const text = wrapper.text()

    expect(text).toContain('开封 · 1日旅行计划')
    expect(text).toContain('本次行程总览')
    expect(text).toContain('清明上河园')
    expect(text).toContain('每日速览')
    expect(text).toContain('09:00')
    expect(mocks.mapAdd).toHaveBeenCalled()
  })

  it('labels attractions that exist in the plan but are missing from the timeline', async () => {
    const planWithUnscheduledAttraction = JSON.parse(JSON.stringify(tripPlan))
    planWithUnscheduledAttraction.days[0].attractions.push({
      name: '汴河游船',
      address: '开封市龙亭区',
      visit_duration: 60,
      description: '原始规划景点',
      category: '游船',
    })
    sessionStorage.setItem('tripPlan', JSON.stringify(planWithUnscheduledAttraction))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ prepared: 0 }),
    }))

    const wrapper = shallowMount(Result)
    await flushPromises()

    expect(wrapper.text()).toContain('未排入当天时间轴')
    expect(wrapper.text()).toContain('汴河游船')
    expect(wrapper.text()).toContain('不计入历史行程完成度')
  })

  it('opens and scrolls to a day from the daily overview', async () => {
    vi.useFakeTimers()
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    const dayHeader = {
      getBoundingClientRect: () => ({ top: 640 }),
    } as unknown as HTMLElement
    const getElementById = vi.spyOn(document, 'getElementById').mockReturnValue({
      querySelector: () => dayHeader,
    } as unknown as HTMLElement)
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ prepared: 0 }),
    }))

    const wrapper = shallowMount(Result)
    await flushPromises()
    await wrapper.find('.day-overview-item').trigger('click')
    await vi.advanceTimersByTimeAsync(360)
    await flushPromises()

    expect(scrollTo).toHaveBeenCalledWith({
      top: 576,
      behavior: 'smooth',
    })
    expect(wrapper.find('.day-collapse-panel').classes()).toContain('day-focus')
    getElementById.mockRestore()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('shows an explicit map error instead of an empty connected map', async () => {
    const planWithoutCoordinates = JSON.parse(JSON.stringify(tripPlan))
    planWithoutCoordinates.days[0].attractions[0].location = undefined
    planWithoutCoordinates.days[0].attractions[0].poi_id = ''
    sessionStorage.setItem('tripPlan', JSON.stringify(planWithoutCoordinates))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        data: [{ query_name: '清明上河园', matched: false }],
        prepared: 0,
      }),
    }))

    const wrapper = shallowMount(Result)
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('这份行程没有可核验的位置')
    expect(wrapper.text()).toContain('请返回首页重新生成')
    expect(mocks.mapAdd).not.toHaveBeenCalled()
  })

  it('blocks legacy placeholder itineraries and asks for regeneration', async () => {
    const placeholderPlan = JSON.parse(JSON.stringify(tripPlan))
    placeholderPlan.days[0].attractions[0].name = '开封景点1'
    placeholderPlan.days[0].meals = [{ type: 'breakfast', name: '第1天早餐' }]
    sessionStorage.setItem('tripPlan', JSON.stringify(placeholderPlan))

    const wrapper = shallowMount(Result)
    await flushPromises()

    expect(wrapper.text()).toContain('这份旧结果没有真实地点数据')
    expect(wrapper.text()).toContain('返回首页重新生成')
    expect(wrapper.text()).not.toContain('本次行程总览')
  })

  it('shows weather near the overview and explains unavailable long-range forecasts', async () => {
    const planWithWeather = JSON.parse(JSON.stringify(tripPlan))
    planWithWeather.weather_info = [{
      date: '2026-09-13', day_weather: '晴', night_weather: '多云',
      day_temp: 28, night_temp: 19, wind_direction: '东风', wind_power: '1-3级',
    }]
    sessionStorage.setItem('tripPlan', JSON.stringify(planWithWeather))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ prepared: 0 }) }))

    const wrapper = shallowMount(Result)
    await flushPromises()

    expect(wrapper.find('.weather-summary').text()).toContain('9月13日')
    expect(wrapper.find('.weather-summary').text()).toContain('晴')
    expect(wrapper.find('.weather-summary').text()).toContain('19° / 28°')

    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan))
    const emptyWeatherWrapper = shallowMount(Result)
    await flushPromises()
    expect(emptyWeatherWrapper.find('.weather-summary').text()).toContain('当前日期暂无逐日预报')
    expect(emptyWeatherWrapper.find('.weather-summary').text()).toContain('系统不会编造远期温度')
  })

  it('keeps sidebar navigation in the same order as the visible result sections', async () => {
    const planWithBudget = {
      ...tripPlan,
      budget: {
        total_attractions: 120,
        total_hotels: 300,
        total_meals: 180,
        total_transportation: 40,
        total: 640,
      },
    }
    sessionStorage.setItem('tripPlan', JSON.stringify(planWithBudget))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ prepared: 0 }) }))

    const wrapper = shallowMount(Result)
    await flushPromises()
    const navigationText = wrapper.find('.side-nav').text()

    expect(navigationText.indexOf('行程概览')).toBeLessThan(navigationText.indexOf('天气信息'))
    expect(navigationText.indexOf('天气信息')).toBeLessThan(navigationText.indexOf('预算明细'))
    expect(navigationText.indexOf('预算明细')).toBeLessThan(navigationText.indexOf('景点地图'))
    expect(navigationText.indexOf('景点地图')).toBeLessThan(navigationText.indexOf('每日行程'))
  })

  it('hides unavailable and remote outlier places from the route map', async () => {
    const planWithMapOutliers = JSON.parse(JSON.stringify(tripPlan))
    planWithMapOutliers.days[0].attractions = [
      planWithMapOutliers.days[0].attractions[0],
      { ...planWithMapOutliers.days[0].attractions[0], name: '龙亭公园', poi_id: 'b', location: { longitude: 114.35, latitude: 34.81 } },
      { ...planWithMapOutliers.days[0].attractions[0], name: '铁塔公园', poi_id: 'c', location: { longitude: 114.37, latitude: 34.82 } },
      { ...planWithMapOutliers.days[0].attractions[0], name: '远海岛屿', poi_id: 'd', location: { longitude: 122.26, latitude: 28.88 } },
      { ...planWithMapOutliers.days[0].attractions[0], name: '测试景区(不对外开放)', poi_id: 'e', location: { longitude: 114.36, latitude: 34.80 } },
    ]
    sessionStorage.setItem('tripPlan', JSON.stringify(planWithMapOutliers))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ prepared: 0 }) }))

    const wrapper = shallowMount(Result)
    await flushPromises()

    expect(wrapper.text()).toContain('已隐藏 2 个不开放或距离异常的地点')
    expect(mocks.mapFit).toHaveBeenCalled()
    expect(mocks.mapFit.mock.calls.at(-1)?.[0]).toHaveLength(3)
  })
})
