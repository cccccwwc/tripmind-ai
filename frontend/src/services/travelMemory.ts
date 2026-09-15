import { computed, ref } from 'vue'

export interface TravelMemoryEntry {
  id: string
  name: string
  city: string
  category: string
  visited_at: string
}

const STORAGE_KEY = 'tripmind_travel_memory_v1'
const visitedEntries = ref<TravelMemoryEntry[]>([])
let hydrated = false

export function normalizePlaceName(name: string): string {
  return name
    .replace(/[（(][^）)]*[）)]/g, '')
    .replace(/^(?:上午|下午|晚上|夜间)?(?:游览|参观|前往|打卡|夜游|漫步)+/u, '')
    .replace(/(?:风景区|旅游区|景区|深度游|半日游|一日游|游览|参观|打卡|夜游|漫步)+$/u, '')
    .replace(/[\s·•・/\\-]+/g, '')
    .toLocaleLowerCase()
}

function makePlaceId(city: string, name: string): string {
  return `${city.trim().toLocaleLowerCase()}:${normalizePlaceName(name)}`
}

function isSamePlace(entry: TravelMemoryEntry, name: string, city: string): boolean {
  // 根据名称重新计算 ID，兼容旧版本曾经用时间轴文案保存的历史记录。
  return makePlaceId(entry.city, entry.name) === makePlaceId(city, name)
}

function hydrate() {
  if (hydrated || typeof window === 'undefined') return
  hydrated = true
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]')
    if (Array.isArray(saved)) visitedEntries.value = saved
  } catch {
    visitedEntries.value = []
  }
}

function persist() {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(visitedEntries.value))
}

export function useTravelMemory() {
  hydrate()

  const visitedCount = computed(() => visitedEntries.value.length)

  function isVisited(name: string, city: string): boolean {
    return visitedEntries.value.some(entry => isSamePlace(entry, name, city))
  }

  function markVisited(place: { name: string; city: string; category?: string }) {
    const id = makePlaceId(place.city, place.name)
    const existing = visitedEntries.value.find(entry => isSamePlace(entry, place.name, place.city))
    if (existing) return existing

    const entry: TravelMemoryEntry = {
      id,
      name: place.name.trim(),
      city: place.city.trim(),
      category: place.category || '景点',
      visited_at: new Date().toISOString()
    }
    visitedEntries.value = [entry, ...visitedEntries.value]
    persist()
    return entry
  }

  function removeVisited(name: string, city: string) {
    visitedEntries.value = visitedEntries.value.filter(entry => !isSamePlace(entry, name, city))
    persist()
  }

  function toggleVisited(place: { name: string; city: string; category?: string }): boolean {
    if (isVisited(place.name, place.city)) {
      removeVisited(place.name, place.city)
      return false
    }
    markVisited(place)
    return true
  }

  return {
    visitedEntries,
    visitedCount,
    isVisited,
    markVisited,
    removeVisited,
    toggleVisited
  }
}
