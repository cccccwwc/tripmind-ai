import { afterEach, beforeEach, vi } from 'vitest'
import { config } from '@vue/test-utils'


class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class MemoryStorage implements Storage {
  private values = new Map<string, string>()

  get length() { return this.values.size }
  clear() { this.values.clear() }
  getItem(key: string) { return this.values.get(key) ?? null }
  key(index: number) { return [...this.values.keys()][index] ?? null }
  removeItem(key: string) { this.values.delete(key) }
  setItem(key: string, value: string) { this.values.set(key, String(value)) }
}

const localStorageMock = new MemoryStorage()
const sessionStorageMock = new MemoryStorage()
Object.defineProperty(window, 'localStorage', { configurable: true, value: localStorageMock })
Object.defineProperty(window, 'sessionStorage', { configurable: true, value: sessionStorageMock })
vi.stubGlobal('localStorage', localStorageMock)
vi.stubGlobal('sessionStorage', sessionStorageMock)

vi.stubGlobal('ResizeObserver', ResizeObserverMock)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})
Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
})

// Lightweight stubs keep page tests focused on TripMind behavior rather than
// Ant Design's portal, animation and layout internals.
config.global.stubs = {
  'a-layout': { template: '<div><slot /></div>' },
  'a-layout-header': { template: '<header><slot /></header>' },
  'a-layout-content': { template: '<main><slot /></main>' },
  'a-layout-footer': { template: '<footer><slot /></footer>' },
  'a-card': { props: ['title'], template: '<section><slot name="title">{{ title }}</slot><slot /></section>' },
  'a-form': { template: '<form><slot /></form>', methods: { validateFields: () => Promise.resolve() } },
  'a-form-item': { props: ['label'], template: '<label><span>{{ label }}</span><slot /></label>' },
  'a-row': { template: '<div><slot /></div>' },
  'a-col': { template: '<div><slot /></div>' },
  'a-input': { inheritAttrs: false, template: '<div><slot name="prefix" /></div>' },
  'a-textarea': { inheritAttrs: false, template: '<div></div>' },
  'a-date-picker': { inheritAttrs: false, template: '<div></div>' },
  'a-input-number': { inheritAttrs: false, template: '<div></div>' },
  'a-select': { template: '<select><slot /></select>' },
  'a-select-option': { template: '<option><slot /></option>' },
  'a-button': { template: '<button><slot /></button>' },
  'a-spin': { template: '<div><slot /></div>' },
  'a-progress': { template: '<div class="progress-stub"></div>' },
  'a-empty': { template: '<div><slot name="image" /><slot name="description" /><slot /></div>' },
  'a-back-top': { template: '<div><slot /></div>' },
  'a-dropdown': { template: '<div><slot /><slot name="overlay" /></div>' },
  'a-menu': { template: '<div><slot /></div>' },
  'a-menu-item': { template: '<div><slot /></div>' },
  'a-collapse': { template: '<div><slot /></div>' },
  'a-collapse-panel': { template: '<section><slot name="header" /><slot /></section>' },
  'a-divider': { template: '<div><slot /></div>' },
  'a-alert': { template: '<div><slot /></div>' },
  'a-space': { template: '<div><slot /></div>' },
  'a-sub-menu': { props: ['title'], template: '<div>{{ title }}<slot /></div>' },
  'a-affix': { template: '<div><slot /></div>' },
  'a-list': { template: '<div><slot /></div>' },
  'a-list-item': { template: '<div><slot /></div>' },
  'router-link': { template: '<a><slot /></a>' },
  'router-view': { template: '<div data-test="router-view"></div>' },
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  vi.clearAllMocks()
})
