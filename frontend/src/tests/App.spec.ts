import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from '@/App.vue'


describe('App shell', () => {
  it('shows project identity, navigation and author information', () => {
    const wrapper = shallowMount(App)

    expect(wrapper.text()).toContain('TripMind AI')
    expect(wrapper.text()).toContain('开始规划')
    expect(wrapper.text()).toContain('历史行程')
    expect(wrapper.text()).toContain('多智能体旅行规划')
    expect(wrapper.text()).toContain('© 2026 陈稳畅')
    expect(wrapper.find('[data-test="router-view"]').exists()).toBe(true)
  })
})
