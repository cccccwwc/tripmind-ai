import { computed, ref } from 'vue'
import type { TripPlan } from '@/types'

export interface SavedTripPlan {
  id: string
  title: string
  created_at: string
  updated_at: string
  plan: TripPlan
}

const STORAGE_KEY = 'tripmind_saved_trip_plans_v1'
const savedTripPlans = ref<SavedTripPlan[]>([])
let hydrated = false

function clonePlan(plan: TripPlan): TripPlan {
  return JSON.parse(JSON.stringify(plan))
}

function makeTripId(plan: TripPlan): string {
  const identity = `${plan.city.trim()}|${plan.start_date}|${plan.end_date}`
  let hash = 2166136261
  for (let index = 0; index < identity.length; index += 1) {
    hash ^= identity.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return `trip-${(hash >>> 0).toString(16)}`
}

function hydrate() {
  if (hydrated || typeof window === 'undefined') return
  hydrated = true
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]')
    if (Array.isArray(saved)) savedTripPlans.value = saved
  } catch {
    savedTripPlans.value = []
  }
}

function persist() {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(savedTripPlans.value))
}

export function useTripPlanMemory() {
  hydrate()

  const savedPlanCount = computed(() => savedTripPlans.value.length)

  function isTripSaved(plan: TripPlan): boolean {
    const id = makeTripId(plan)
    return savedTripPlans.value.some(item => item.id === id)
  }

  function saveTripPlan(plan: TripPlan): SavedTripPlan {
    const id = makeTripId(plan)
    const now = new Date().toISOString()
    const existing = savedTripPlans.value.find(item => item.id === id)
    const entry: SavedTripPlan = {
      id,
      title: `${plan.city} · ${plan.days.length}日旅行计划`,
      created_at: existing?.created_at || now,
      updated_at: now,
      plan: clonePlan(plan)
    }
    savedTripPlans.value = [entry, ...savedTripPlans.value.filter(item => item.id !== id)]
    persist()
    return entry
  }

  return {
    savedTripPlans,
    savedPlanCount,
    isTripSaved,
    saveTripPlan
  }
}
