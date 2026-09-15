<template>
  <main class="history-page">
    <section class="history-hero">
      <router-link to="/" class="back-link">← 返回规划对话</router-link>
      <div class="hero-copy">
        <p>TRIPMIND JOURNEYS</p>
        <h1>历史行程</h1>
        <span>回看已经生成的旅行，也可以从未完成的地点继续出发。</span>
      </div>

      <div class="history-stats" aria-label="历史行程统计">
        <article><strong>{{ savedPlanCount }}</strong><span>份行程</span></article>
        <article><strong>{{ cityCount }}</strong><span>座城市</span></article>
        <article><strong>{{ totalDays }}</strong><span>个旅行日</span></article>
      </div>
    </section>

    <section v-if="savedTripPlans.length" class="history-content">
      <header class="history-toolbar">
        <div>
          <h2>我的旅行规划</h2>
          <span>按最近更新排序</span>
        </div>
        <div class="filter-tabs" aria-label="筛选历史行程">
          <button type="button" :class="{ active: activeFilter === 'all' }" @click="activeFilter = 'all'">全部</button>
          <button type="button" :class="{ active: activeFilter === 'unfinished' }" @click="activeFilter = 'unfinished'">未完成</button>
          <button type="button" :class="{ active: activeFilter === 'completed' }" @click="activeFilter = 'completed'">已完成</button>
        </div>
      </header>

      <div v-if="filteredTrips.length" class="trip-grid">
        <article v-for="savedTrip in filteredTrips" :key="savedTrip.id" class="trip-card">
          <header>
            <span class="city-monogram">{{ savedTrip.plan.city.slice(0, 1) }}</span>
            <div>
              <p>{{ savedTrip.plan.city }}</p>
              <h3>{{ savedTrip.title }}</h3>
            </div>
            <span :class="['trip-status', { completed: !getProgress(savedTrip).remaining }]">
              {{ getProgress(savedTrip).remaining ? '待继续' : '已完成' }}
            </span>
          </header>

          <div class="trip-meta">
            <span>◷ {{ savedTrip.plan.start_date }} — {{ savedTrip.plan.end_date }}</span>
            <span>{{ savedTrip.plan.days.length }} 天</span>
          </div>

          <section class="place-preview">
            <div class="section-label">
              <span>行程地点</span>
              <b>待去 {{ getProgress(savedTrip).remaining }} · 共 {{ getProgress(savedTrip).total }}</b>
            </div>
            <div v-if="getAttractions(savedTrip).length" class="place-list">
              <span
                v-for="place in getPreviewAttractions(savedTrip)"
                :key="place.name"
                :class="{ visited: isVisited(place.name, savedTrip.plan.city) }"
              >
                <i>{{ isVisited(place.name, savedTrip.plan.city) ? '✓' : '待' }}</i>{{ place.name }}
              </span>
              <small v-if="getAttractions(savedTrip).length > getPreviewAttractions(savedTrip).length">
                另有 {{ getAttractions(savedTrip).length - getPreviewAttractions(savedTrip).length }} 个已完成地点
              </small>
            </div>
            <p v-else>这份行程暂时没有景点数据。</p>
          </section>

          <div class="progress-copy">
            <span>已去 {{ getProgress(savedTrip).visited }}/{{ getProgress(savedTrip).total }} 个地点</span>
            <strong>{{ getProgress(savedTrip).percent }}%</strong>
          </div>
          <div class="progress-track"><span :style="{ width: `${getProgress(savedTrip).percent}%` }"></span></div>

          <footer>
            <button type="button" class="secondary-action" @click="openTrip(savedTrip)">查看完整行程</button>
            <button
              type="button"
              class="primary-action"
              :disabled="!getProgress(savedTrip).remaining"
              @click="continueTrip(savedTrip)"
            >
              {{ getProgress(savedTrip).remaining ? `继续规划 ${getProgress(savedTrip).remaining} 处` : '行程已完成' }}
            </button>
          </footer>
          <small class="updated-at">最近更新 {{ formatUpdatedAt(savedTrip.updated_at) }}</small>
        </article>
      </div>

      <div v-else class="filtered-empty">
        <span>⌁</span>
        <h3>这个分类暂时没有行程</h3>
        <button type="button" @click="activeFilter = 'all'">查看全部</button>
      </div>
    </section>

    <section v-else class="empty-history">
      <div class="empty-orb">✦</div>
      <p>YOUR FIRST JOURNEY</p>
      <h2>还没有历史行程</h2>
      <span>和旅行顾问聊聊目的地与时间，生成后把行程加入“我的规划”。</span>
      <router-link to="/">开始第一次规划 <b>→</b></router-link>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { normalizePlaceName, useTravelMemory } from '@/services/travelMemory'
import { useTripPlanMemory } from '@/services/tripPlanMemory'
import type { SavedTripPlan } from '@/services/tripPlanMemory'

type HistoryFilter = 'all' | 'unfinished' | 'completed'

const router = useRouter()
const activeFilter = ref<HistoryFilter>('all')
const { savedTripPlans, savedPlanCount } = useTripPlanMemory()
const { isVisited } = useTravelMemory()

const cityCount = computed(() => new Set(savedTripPlans.value.map(item => item.plan.city.trim())).size)
const totalDays = computed(() => savedTripPlans.value.reduce((total, item) => total + item.plan.days.length, 0))

function getAttractions(savedTrip: SavedTripPlan) {
  const unique = new Map<string, { name: string; category: string }>()
  savedTrip.plan.days.forEach(day => {
    const scheduledAttractions = day.schedule?.filter(item => item.item_type === 'attraction') || []
    const trackedAttractions = day.schedule?.length
      ? day.attractions.filter(attraction => {
          const attractionKey = normalizePlaceName(attraction.name)
          return Boolean(attractionKey && scheduledAttractions.some(event => {
            const eventKey = normalizePlaceName(event.title)
            return eventKey === attractionKey
              || eventKey.includes(attractionKey)
              || attractionKey.includes(eventKey)
          }))
        })
      : day.attractions

    trackedAttractions.forEach(attraction => {
      const key = normalizePlaceName(attraction.name)
      if (!unique.has(key)) unique.set(key, { name: attraction.name, category: attraction.category || '景点' })
    })
  })
  return [...unique.values()]
}

function getProgress(savedTrip: SavedTripPlan) {
  const attractions = getAttractions(savedTrip)
  const visited = attractions.filter(item => isVisited(item.name, savedTrip.plan.city)).length
  const total = attractions.length
  return {
    visited,
    total,
    remaining: Math.max(0, total - visited),
    percent: total ? Math.round((visited / total) * 100) : 0
  }
}

function getPreviewAttractions(savedTrip: SavedTripPlan) {
  const attractions = getAttractions(savedTrip)
  const unvisited = attractions.filter(item => !isVisited(item.name, savedTrip.plan.city))
  const visited = attractions.filter(item => isVisited(item.name, savedTrip.plan.city))

  // 未去地点必须优先显示，避免唯一剩余地点被前四条已完成记录隐藏。
  return [...unvisited, ...visited].slice(0, Math.max(4, unvisited.length))
}

const filteredTrips = computed(() => savedTripPlans.value.filter(item => {
  if (activeFilter.value === 'all') return true
  const completed = getProgress(item).remaining === 0
  return activeFilter.value === 'completed' ? completed : !completed
}))

function openTrip(savedTrip: SavedTripPlan) {
  sessionStorage.setItem('tripPlan', JSON.stringify(savedTrip.plan))
  void router.push('/result')
}

function continueTrip(savedTrip: SavedTripPlan) {
  if (!getProgress(savedTrip).remaining) return
  sessionStorage.setItem('tripmindContinueTrip', JSON.stringify(savedTrip))
  void router.push('/')
}

function formatUpdatedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未知时间'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: 'short', day: 'numeric'
  }).format(date)
}
</script>

<style scoped>
.history-page { min-height: calc(100vh - 52px); padding: 64px 24px 88px; background: #f5f5f7; color: #1d1d1f; }
.history-hero, .history-content, .empty-history { width: min(1120px, 100%); margin-inline: auto; }
.history-hero { position: relative; }
.back-link { display: inline-flex; padding: 8px 0; color: #515154; font-size: 12px; font-weight: 650; text-decoration: none; }
.back-link:hover { color: #0071e3; }
.hero-copy { max-width: 720px; margin-top: 34px; }
.hero-copy p, .empty-history > p { margin: 0 0 9px; color: #0071e3; font-size: 10px; font-weight: 800; letter-spacing: .17em; }
.hero-copy h1 { margin: 0; font-size: clamp(46px, 7vw, 76px); line-height: 1; letter-spacing: -.06em; }
.hero-copy > span { display: block; margin-top: 19px; color: #6e6e73; font-size: 17px; line-height: 1.6; }
.history-stats { display: grid; max-width: 560px; margin-top: 42px; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.history-stats article { display: flex; min-height: 94px; padding: 17px 20px; justify-content: center; flex-direction: column; border: 1px solid rgba(0,0,0,.06); border-radius: 21px; background: rgba(255,255,255,.86); }
.history-stats strong { font-size: 28px; line-height: 1; letter-spacing: -.04em; }
.history-stats span { margin-top: 7px; color: #86868b; font-size: 11px; }
.history-content { margin-top: 68px; }
.history-toolbar { display: flex; margin-bottom: 22px; align-items: flex-end; justify-content: space-between; gap: 20px; }
.history-toolbar h2 { margin: 0; font-size: 28px; letter-spacing: -.04em; }
.history-toolbar > div:first-child > span { color: #86868b; font-size: 11px; }
.filter-tabs { display: inline-flex; padding: 4px; border-radius: 12px; background: #e9e9ec; }
.filter-tabs button { min-width: 72px; height: 32px; padding: 0 12px; border: 0; border-radius: 9px; background: transparent; color: #6e6e73; cursor: pointer; font-size: 11px; font-weight: 650; }
.filter-tabs button.active { background: #fff; color: #1d1d1f; box-shadow: 0 1px 5px rgba(0,0,0,.09); }
.trip-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.trip-card { padding: 22px; border: 1px solid rgba(0,0,0,.065); border-radius: 25px; background: #fff; box-shadow: 0 12px 38px rgba(0,0,0,.045); }
.trip-card > header { display: flex; align-items: center; gap: 12px; }
.trip-card > header > div { min-width: 0; flex: 1; }
.trip-card header p { margin: 0 0 2px; color: #0071e3; font-size: 10px; font-weight: 750; }
.trip-card h3 { margin: 0; overflow: hidden; font-size: 20px; letter-spacing: -.03em; text-overflow: ellipsis; white-space: nowrap; }
.city-monogram { display: grid; width: 45px; height: 45px; flex: 0 0 auto; place-items: center; border-radius: 14px; background: linear-gradient(145deg, #1684ed, #0064c8); color: #fff; font-size: 17px; font-weight: 750; box-shadow: 0 8px 20px rgba(0,113,227,.2); }
.trip-status { padding: 6px 9px; border-radius: 999px; background: #fff7ed; color: #9a5b00; font-size: 9px; font-weight: 750; white-space: nowrap; }
.trip-status.completed { background: #edf9f0; color: #248a3d; }
.trip-meta { display: flex; margin: 18px 0; align-items: center; justify-content: space-between; gap: 12px; color: #6e6e73; font-size: 10px; }
.place-preview { min-height: 148px; padding: 15px; border-radius: 17px; background: #f7f7f8; }
.section-label { display: flex; margin-bottom: 11px; align-items: center; justify-content: space-between; color: #515154; font-size: 10px; font-weight: 750; }
.section-label b { color: #86868b; font-size: 9px; }
.place-list { display: flex; flex-direction: column; gap: 7px; }
.place-list > span { display: flex; align-items: center; gap: 7px; color: #1d1d1f; font-size: 11px; }
.place-list > span.visited { color: #86868b; text-decoration: line-through; }
.place-list i { display: grid; width: 16px; height: 16px; place-items: center; border-radius: 50%; background: #e5e5ea; color: #86868b; font-size: 9px; font-style: normal; }
.place-list .visited i { background: rgba(52,199,89,.13); color: #248a3d; text-decoration: none; }
.place-list small { margin-top: 2px; color: #86868b; font-size: 9px; }
.place-preview > p { color: #86868b; font-size: 10px; }
.progress-copy { display: flex; margin-top: 18px; justify-content: space-between; color: #6e6e73; font-size: 10px; }
.progress-copy strong { color: #248a3d; }
.progress-track { height: 5px; margin-top: 7px; overflow: hidden; border-radius: 999px; background: #e5e5ea; }
.progress-track span { display: block; height: 100%; border-radius: inherit; background: #34c759; }
.trip-card footer { display: grid; margin-top: 20px; grid-template-columns: 1fr 1.25fr; gap: 8px; }
.trip-card footer button { min-height: 40px; padding: 8px 12px; border-radius: 12px; cursor: pointer; font-size: 10px; font-weight: 700; }
.secondary-action { border: 1px solid #d2d2d7; background: #fff; color: #515154; }
.primary-action { border: 0; background: #0071e3; color: #fff; }
.primary-action:disabled { background: #e5e5ea; color: #aeaeb2; cursor: default; }
.updated-at { display: block; margin-top: 11px; color: #aeaeb2; font-size: 8px; text-align: center; }
.filtered-empty, .empty-history { padding: 80px 24px; border: 1px solid rgba(0,0,0,.06); border-radius: 28px; background: #fff; text-align: center; }
.filtered-empty span, .empty-orb { display: grid; width: 54px; height: 54px; margin: 0 auto 16px; place-items: center; border-radius: 17px; background: #1d1d1f; color: #fff; font-size: 20px; }
.filtered-empty h3, .empty-history h2 { margin: 0 0 10px; font-size: 28px; letter-spacing: -.04em; }
.filtered-empty button { border: 0; background: transparent; color: #0071e3; cursor: pointer; font-weight: 650; }
.empty-history { margin-top: 60px; }
.empty-history > span { display: block; max-width: 480px; margin: 0 auto; color: #86868b; font-size: 13px; line-height: 1.6; }
.empty-history a { display: inline-flex; min-height: 44px; margin-top: 24px; padding: 0 18px; align-items: center; gap: 10px; border-radius: 999px; background: #0071e3; color: #fff; font-size: 12px; font-weight: 700; text-decoration: none; }
@media (max-width: 760px) {
  .history-page { padding: 35px 14px 64px; }
  .hero-copy { margin-top: 22px; }
  .hero-copy h1 { font-size: 47px; }
  .hero-copy > span { font-size: 14px; }
  .history-stats { margin-top: 28px; }
  .history-stats article { min-height: 76px; padding: 13px; border-radius: 16px; }
  .history-stats strong { font-size: 22px; }
  .history-content { margin-top: 42px; }
  .history-toolbar { align-items: stretch; flex-direction: column; }
  .filter-tabs { display: grid; grid-template-columns: repeat(3, 1fr); }
  .trip-grid { grid-template-columns: 1fr; }
  .trip-card { padding: 17px; border-radius: 21px; }
}
</style>
