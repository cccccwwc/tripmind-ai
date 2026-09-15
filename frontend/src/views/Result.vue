<template>
  <div class="result-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="page-heading">
        <a-button class="back-button" size="large" @click="goBack">
          ← 返回首页
        </a-button>
        <div v-if="tripPlan" class="page-title-block">
          <span class="page-eyebrow">TRIPMIND ITINERARY</span>
          <h1>{{ tripPlan.city }} · {{ tripPlan.days.length }}日旅行计划</h1>
        </div>
      </div>
      <a-space class="header-actions" size="middle" wrap>
        <a-button
          v-if="!editMode"
          :type="savedToMyTrips ? 'default' : 'primary'"
          class="save-trip-button"
          @click="addToMyTrips"
        >
          {{ savedToMyTrips ? '✓ 已加入我的规划' : '＋ 加入我的旅行规划' }}
        </a-button>
        <a-button v-if="!editMode" @click="toggleEditMode" type="default">
          ✏️ 编辑行程
        </a-button>
        <a-button v-else @click="saveChanges" type="primary">
          💾 保存修改
        </a-button>
        <a-button v-if="editMode" @click="cancelEdit" type="default">
          ❌ 取消编辑
        </a-button>

        <!-- 导出按钮 -->
        <a-dropdown v-if="!editMode">
          <template #overlay>
            <a-menu>
              <a-menu-item key="image" @click="exportAsImage">
                📷 导出为图片
              </a-menu-item>
              <a-menu-item key="pdf" @click="exportAsPDF">
                📄 导出为PDF
              </a-menu-item>
            </a-menu>
          </template>
          <a-button type="default">
            📥 导出行程 <DownOutlined />
          </a-button>
        </a-dropdown>
      </a-space>
    </div>

    <section v-if="tripPlan && hasInvalidPlaceholderData" class="invalid-plan-state">
      <div class="invalid-plan-icon">!</div>
      <p class="page-eyebrow">RESULT QUALITY CHECK</p>
      <h2>这份旧结果没有真实地点数据</h2>
      <p>系统检测到“{{ tripPlan.city }}景点1”一类占位内容，因此没有继续展示空地图。新版规划会使用你选择的地点和高德核验坐标，请返回首页重新生成。</p>
      <a-button type="primary" size="large" @click="goBack">返回首页重新生成</a-button>
    </section>

    <div v-else-if="tripPlan" class="content-wrapper">
      <!-- 侧边导航 -->
      <div class="side-nav">
        <a-affix :offset-top="80">
          <a-menu mode="inline" :selected-keys="[activeSection]" @click="scrollToSection">
            <a-menu-item key="overview">
              <span>📋 行程概览</span>
            </a-menu-item>
            <a-menu-item key="weather">
              <span>🌤️ 天气信息</span>
            </a-menu-item>
            <a-menu-item key="budget" v-if="tripPlan.budget">
              <span>💰 预算明细</span>
            </a-menu-item>
            <a-menu-item key="map">
              <span>📍 景点地图</span>
            </a-menu-item>
            <a-sub-menu key="days" title="📅 每日行程">
              <a-menu-item v-for="(day, index) in tripPlan.days" :key="`day-${index}`">
                第{{ day.day_index + 1 }}天
              </a-menu-item>
            </a-sub-menu>
          </a-menu>
        </a-affix>
      </div>

      <!-- 主内容区 -->
      <div class="main-content">
        <!-- 顶部信息区:左侧概览+预算,右侧地图 -->
        <div class="top-info-section">
          <!-- 左侧:行程概览和预算明细 -->
          <div class="left-info">
            <!-- 行程概览 -->
            <a-card id="overview" :bordered="false" class="overview-card">
              <div class="overview-content">
                <div class="overview-heading">
                  <div>
                    <span class="status-pill"><span class="status-dot"></span>行程已生成</span>
                    <h2>{{ tripPlan.city }}旅行计划</h2>
                    <p>景点、路线、住宿、餐饮与天气，集中在一张智能行程单里。</p>
                  </div>
                  <div class="day-count">
                    <strong>{{ tripPlan.days.length }}</strong>
                    <span>天</span>
                  </div>
                </div>

                <div class="trip-meta-grid">
                  <div class="meta-chip">
                    <span class="meta-icon">📅</span>
                    <div><small>出行日期</small><strong>{{ tripPlan.start_date }}</strong></div>
                  </div>
                  <div class="meta-chip">
                    <span class="meta-icon">📍</span>
                    <div><small>目的地</small><strong>{{ tripPlan.city }}</strong></div>
                  </div>
                  <div class="meta-chip">
                    <span class="meta-icon">🧭</span>
                    <div><small>景点数量</small><strong>{{ totalAttractions }} 个</strong></div>
                  </div>
                </div>

                <section id="weather" class="weather-summary" aria-labelledby="weather-summary-title">
                  <div class="weather-summary-heading">
                    <div>
                      <span class="section-eyebrow">WEATHER</span>
                      <h3 id="weather-summary-title">逐日天气</h3>
                    </div>
                    <span class="weather-source">高德天气 · 以临近出发时为准</span>
                  </div>
                  <div v-if="weatherPreview.length" class="weather-preview-list">
                    <article v-for="item in weatherPreview" :key="item.date" class="weather-preview-item">
                      <span class="weather-preview-date">{{ formatWeatherDate(item.date) }}</span>
                      <span class="weather-preview-icon">{{ getWeatherIcon(item.day_weather, false) }}</span>
                      <strong>{{ item.day_weather || '待更新' }}</strong>
                      <small v-if="item.day_weather">{{ item.night_temp }}° / {{ item.day_temp }}°</small>
                      <small v-else>暂无温度</small>
                    </article>
                  </div>
                  <div v-else class="weather-unavailable">
                    <span class="weather-unavailable-icon">☁️</span>
                    <div>
                      <strong>当前日期暂无逐日预报</strong>
                      <p>高德只提供近期天气；{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }} 的天气会在临近出发时更新，系统不会编造远期温度。</p>
                    </div>
                  </div>
                </section>

                <section class="trip-glance" aria-labelledby="trip-glance-title">
                  <div class="trip-glance-heading">
                    <div>
                      <span class="section-eyebrow">TRIP AT A GLANCE</span>
                      <h3 id="trip-glance-title">本次行程总览</h3>
                    </div>
                    <span class="glance-total">{{ tripPlan.days.length }} 天安排</span>
                  </div>

                  <div class="trip-glance-grid">
                    <article class="glance-group hotel-glance">
                      <div class="glance-group-heading">
                        <span class="glance-icon">⌂</span>
                        <div><small>STAY</small><strong>住宿酒店</strong></div>
                        <span class="glance-count">{{ hotelOverview.length }}</span>
                      </div>
                      <ul v-if="hotelOverview.length" class="glance-list">
                        <li v-for="item in hotelOverview" :key="item.key">
                          <span class="glance-index">{{ item.order }}</span>
                          <div>
                            <strong>{{ item.name }}</strong>
                            <small>{{ item.days }}<template v-if="item.detail"> · {{ item.detail }}</template></small>
                          </div>
                        </li>
                      </ul>
                      <p v-else class="glance-empty">尚未指定具体酒店</p>
                    </article>

                    <article class="glance-group attraction-glance">
                      <div class="glance-group-heading">
                        <span class="glance-icon">⌖</span>
                        <div><small>VISIT</small><strong>要去的景点</strong></div>
                        <span class="glance-count">{{ attractionOverview.length }}</span>
                      </div>
                      <ul v-if="attractionOverview.length" class="glance-list">
                        <li v-for="item in attractionOverview" :key="item.key">
                          <span class="glance-index">{{ item.order }}</span>
                          <div>
                            <strong>{{ item.name }}</strong>
                            <small>{{ item.days }}<template v-if="item.detail"> · {{ item.detail }}</template></small>
                          </div>
                        </li>
                      </ul>
                      <p v-else class="glance-empty">尚未安排景点</p>
                    </article>

                    <article class="glance-group meal-glance">
                      <div class="glance-group-heading">
                        <span class="glance-icon">◇</span>
                        <div><small>EAT</small><strong>要吃的饭店</strong></div>
                        <span class="glance-count">{{ mealOverview.length }}</span>
                      </div>
                      <ul v-if="mealOverview.length" class="glance-list">
                        <li v-for="item in mealOverview" :key="item.key">
                          <span class="glance-index">{{ item.order }}</span>
                          <div>
                            <strong>{{ item.name }}</strong>
                            <small>{{ item.days }}<template v-if="item.detail"> · {{ item.detail }}</template></small>
                          </div>
                        </li>
                      </ul>
                      <p v-else class="glance-empty">尚未安排具体饭店</p>
                    </article>
                  </div>
                </section>

                <div class="suggestion-panel">
                  <div class="suggestion-title"><span>✨</span> 出行建议</div>
                  <p :class="['suggestion-text', { expanded: suggestionsExpanded }]">
                    {{ tripPlan.overall_suggestions }}
                  </p>
                  <button
                    v-if="tripPlan.overall_suggestions.length > 180"
                    class="text-button"
                    type="button"
                    @click="suggestionsExpanded = !suggestionsExpanded"
                  >
                    {{ suggestionsExpanded ? '收起建议' : '展开完整建议' }}
                  </button>
                </div>
              </div>
            </a-card>

            <!-- 预算明细 -->
            <a-card id="budget" v-if="tripPlan.budget" title="💰 预算明细" :bordered="false" class="budget-card">
              <div class="budget-grid">
                <div class="budget-item">
                  <div class="budget-label">景点门票</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_attractions }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">酒店住宿</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_hotels }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">餐饮费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_meals }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">交通费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_transportation }}</div>
                </div>
              </div>
              <div class="budget-total">
                <span class="total-label">预估总费用</span>
                <span class="total-value">¥{{ tripPlan.budget.total }}</span>
              </div>
            </a-card>
          </div>

          <!-- 右侧:地图 -->
          <div class="right-map">
            <a-card id="map" :bordered="false" class="map-card">
              <template #title>
                <div class="card-title-row">
                  <span>📍 景点地图</span>
                  <span :class="['map-state-badge', mapStatus]">{{ mapStatusLabel }}</span>
                </div>
              </template>
              <div class="map-shell">
                <div v-show="!staticMapUrl" id="amap-container"></div>
                <img
                  v-if="staticMapUrl"
                  :src="staticMapUrl"
                  class="static-map-image"
                  alt="景点路线地图"
                  @load="handleStaticMapLoad"
                  @error="handleStaticMapError"
                />
                <div v-if="mapStatus === 'loading'" class="map-overlay">
                  <a-spin size="large" />
                  <strong>正在加载地图</strong>
                  <span>准备景点坐标与路线...</span>
                </div>
                <div v-else-if="mapStatus === 'error' || mapStatus === 'unconfigured'" class="map-overlay map-error-state">
                  <div class="map-error-icon">🗺️</div>
                  <strong>{{ mapErrorTitle }}</strong>
                  <span>{{ mapErrorMessage }}</span>
                  <a-button v-if="mapStatus === 'error'" size="small" @click="retryMap">重新加载</a-button>
                </div>
                <div v-if="hiddenMapAttractionCount > 0 && mapStatus !== 'loading'" class="map-quality-note">
                  已隐藏 {{ hiddenMapAttractionCount }} 个不开放或距离异常的地点，避免地图被错误坐标拉远
                </div>
              </div>
            </a-card>

            <a-card :bordered="false" class="day-overview-card">
              <template #title>
                <div class="card-title-row">
                  <span>🗓 每日速览</span>
                  <span class="day-overview-count">{{ tripPlan.days.length }} 天</span>
                </div>
              </template>
              <div class="day-overview-list">
                <button
                  v-for="(day, index) in tripPlan.days"
                  :key="`quick-day-${index}`"
                  type="button"
                  class="day-overview-item"
                  @click="scrollToDay(index)"
                >
                  <span class="quick-day-number">{{ index + 1 }}</span>
                  <span class="quick-day-content">
                    <span class="quick-day-topline">
                      <strong>第{{ index + 1 }}天</strong>
                      <small>{{ day.date }}</small>
                    </span>
                    <span class="quick-day-places">
                      {{ day.attractions.slice(0, 3).map(item => item.name).join(' · ') || '自由活动' }}
                      <template v-if="day.attractions.length > 3"> 等 {{ day.attractions.length }} 处</template>
                    </span>
                    <span v-if="day.hotel?.name" class="quick-day-hotel">⌂ {{ day.hotel.name }}</span>
                  </span>
                  <span class="quick-day-arrow">›</span>
                </button>
              </div>
            </a-card>
          </div>
        </div>

        <!-- 每日行程:可折叠 -->
        <a-card title="📅 每日行程" :bordered="false" class="days-card">
          <a-collapse v-model:activeKey="activeDays" accordion>
            <a-collapse-panel
              v-for="(day, index) in tripPlan.days"
              :key="index"
              :id="`day-${index}`"
              :class="['day-collapse-panel', { 'day-focus': highlightedDay === index }]"
            >
              <template #header>
                <div class="day-header">
                  <span class="day-title">第{{ day.day_index + 1 }}天</span>
                  <span class="day-date">{{ day.date }}</span>
                </div>
              </template>

              <!-- 行程基本信息 -->
              <div class="day-info">
                <div class="info-row">
                  <span class="label">📝 行程描述:</span>
                  <span class="value">{{ day.description }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🚗 交通方式:</span>
                  <span class="value">{{ day.transportation }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🏨 住宿:</span>
                  <span class="value">{{ day.accommodation }}</span>
                </div>
              </div>

              <div v-if="getUnscheduledAttractions(day).length" class="unscheduled-attractions">
                <div>
                  <strong>未排入当天时间轴</strong>
                  <span>这些地点保留在原始规划中，但不计入历史行程完成度。</span>
                </div>
                <div class="unscheduled-place-list">
                  <span v-for="attraction in getUnscheduledAttractions(day)" :key="attraction.name">
                    {{ attraction.name }}
                  </span>
                </div>
              </div>

              <!-- 按时间和路线排列的一日计划 -->
              <a-divider orientation="left">⏱️ 按时间与路线</a-divider>
              <div class="day-timeline">
                <article
                  v-for="(event, eventIndex) in getDayTimeline(day)"
                  :key="`${event.start_time}-${event.title}-${eventIndex}`"
                  :class="['timeline-item', `timeline-${event.item_type}`]"
                >
                  <div class="timeline-time">
                    <strong>{{ event.start_time }}</strong>
                    <span>{{ event.end_time }}</span>
                  </div>

                  <div class="timeline-track" aria-hidden="true">
                    <span class="timeline-dot">{{ getTimelineIcon(event.item_type) }}</span>
                    <span v-if="eventIndex < getDayTimeline(day).length - 1" class="timeline-line"></span>
                  </div>

                  <div class="timeline-card">
                    <div class="timeline-card-topline">
                      <span class="timeline-kind">{{ getTimelineTypeLabel(event.item_type) }}</span>
                      <span v-if="event.duration_minutes" class="timeline-duration">
                        约 {{ event.duration_minutes }} 分钟
                      </span>
                    </div>
                    <h3>{{ event.title }}</h3>
                    <p
                      v-if="event.item_type === 'attraction' && getTimelineAttraction(event, day)?.data_source === 'amap'"
                      class="poi-verification"
                    >
                      <span>✓ 高德已核验</span>
                      <template v-if="getTimelineAttraction(event, day)?.district">
                        · {{ getTimelineAttraction(event, day)?.district }}
                      </template>
                      <template v-if="getTimelineAttraction(event, day)?.verification_confidence">
                        · 匹配 {{ Math.round((getTimelineAttraction(event, day)?.verification_confidence || 0) * 100) }}%
                      </template>
                    </p>

                    <template v-if="event.item_type === 'transport'">
                      <div class="timeline-route">
                        <span>{{ event.from_location || '上一站' }}</span>
                        <b>→</b>
                        <span>{{ event.to_location || '下一站' }}</span>
                      </div>
                      <p class="timeline-meta">
                        {{ event.transport_mode || day.transportation }}
                        <template v-if="event.distance"> · {{ event.distance }}</template>
                        <span> · 路线以实时导航为准</span>
                      </p>
                    </template>

                    <template v-else>
                      <p v-if="event.location" class="timeline-location">⌖ {{ event.location }}</p>
                      <p v-if="event.description" class="timeline-description">{{ event.description }}</p>
                      <p v-if="event.estimated_cost" class="timeline-cost">预计 ¥{{ event.estimated_cost }}</p>
                      <button
                        v-if="event.item_type === 'attraction'"
                        type="button"
                        class="timeline-visited-button"
                        :class="{ active: isTimelineVisited(event, day) }"
                        @click="toggleTimelineVisited(event, day)"
                      >
                        {{ isTimelineVisited(event, day) ? '✓ 已去过' : '标记为已去过' }}
                      </button>
                      <div v-if="event.item_type === 'attraction'" class="timeline-image-shell">
                        <img
                          :key="`${getAttractionPhotoKey(event.title, day)}-${getAttractionPhotoIndex(event.title, day)}`"
                          :src="getAttractionImage(event.title, eventIndex, day)"
                          :alt="event.title"
                          class="timeline-image"
                          width="720"
                          height="450"
                          loading="lazy"
                          decoding="async"
                          @error="handleImageError"
                        />
                        <button
                          type="button"
                          class="change-photo-button"
                          :disabled="isChangingAttractionPhoto(event.title, day)"
                          :aria-label="`更换${event.title}的图片`"
                          @click="changeAttractionPhoto(event.title, day)"
                        >
                          {{ isChangingAttractionPhoto(event.title, day) ? '加载中…' : '↻ 换一张' }}
                        </button>
                      </div>
                    </template>
                  </div>
                </article>
              </div>

              <!-- 编辑模式保留景点排序与内容修改 -->
              <template v-if="editMode">
                <a-divider orientation="left">✏️ 调整景点顺序</a-divider>
                <a-list
                  :data-source="day.attractions"
                  :grid="{ gutter: 18, xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 3 }"
                >
                  <template #renderItem="{ item, index }">
                    <a-list-item>
                      <a-card :title="item.name" size="small" class="attraction-card">
                        <template #extra>
                          <a-space>
                            <a-button size="small" @click="moveAttraction(day.day_index, index, 'up')" :disabled="index === 0">↑</a-button>
                            <a-button size="small" @click="moveAttraction(day.day_index, index, 'down')" :disabled="index === day.attractions.length - 1">↓</a-button>
                            <a-button size="small" danger @click="deleteAttraction(day.day_index, index)">🗑️</a-button>
                          </a-space>
                        </template>
                        <p><strong>地址:</strong></p>
                        <a-input v-model:value="item.address" size="small" style="margin-bottom: 8px" />
                        <p><strong>游览时长(分钟):</strong></p>
                        <a-input-number v-model:value="item.visit_duration" :min="10" :max="480" size="small" style="width: 100%; margin-bottom: 8px" />
                        <p><strong>描述:</strong></p>
                        <a-textarea v-model:value="item.description" :rows="2" size="small" />
                      </a-card>
                    </a-list-item>
                  </template>
                </a-list>
              </template>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

      </div>
    </div>

    <a-empty v-else description="还没有创建旅行计划">
      <template #image>
        <div style="font-size: 80px;">🗺️</div>
      </template>
      <template #description>
        <span style="color: #999;">返回首页输入目的地，让 TripMind 为你生成第一份行程。</span>
      </template>
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </a-empty>

    <!-- 回到顶部按钮 -->
    <a-back-top :visibility-height="300">
      <div class="back-top-button">
        ↑
      </div>
    </a-back-top>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownOutlined } from '@ant-design/icons-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import type { Attraction, DayPlan, Location, TimelineItem, TripPlan, WeatherInfo } from '@/types'
import { normalizePlaceName, useTravelMemory } from '@/services/travelMemory'
import { useTripPlanMemory } from '@/services/tripPlanMemory'

const router = useRouter()
const tripPlan = ref<TripPlan | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const attractionPhotoIndexes = ref<Record<string, number>>({})
const changingAttractionPhotos = ref<Record<string, boolean>>({})
const activeSection = ref('overview')
const activeDays = ref<number[]>([0]) // 默认展开第一天
const highlightedDay = ref<number | null>(null)
const suggestionsExpanded = ref(false)
type MapStatus = 'loading' | 'ready' | 'fallback' | 'error' | 'unconfigured'
const mapStatus = ref<MapStatus>('loading')
const mapErrorTitle = ref('地图暂时无法显示')
const mapErrorMessage = ref('请稍后重新加载。')
const staticMapUrl = ref('')
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
const { isVisited, toggleVisited } = useTravelMemory()
const { isTripSaved, saveTripPlan } = useTripPlanMemory()
let map: any = null

const totalAttractions = computed(() =>
  tripPlan.value?.days.reduce((sum, day) => sum + day.attractions.length, 0) ?? 0
)

type MappedAttraction = Omit<Attraction, 'location'> & {
  location: Location
  dayIndex: number
  attrIndex: number
}

const MAP_CLUSTER_RADIUS_KM = 90
const unavailablePlacePattern = /(不对外开放|暂停开放|停止开放|永久关闭|暂不开放|闭园)/u

const coordinateDistanceKm = (first: [number, number], second: [number, number]): number => {
  const toRadians = (value: number) => value * Math.PI / 180
  const [firstLng, firstLat] = first
  const [secondLng, secondLat] = second
  const latitudeDelta = toRadians(secondLat - firstLat)
  const longitudeDelta = toRadians(secondLng - firstLng)
  const value = Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(toRadians(firstLat)) * Math.cos(toRadians(secondLat))
    * Math.sin(longitudeDelta / 2) ** 2
  return 6371 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value))
}

const median = (values: number[]): number => {
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

const allLocatedAttractions = computed<MappedAttraction[]>(() => {
  if (!tripPlan.value) return []
  return tripPlan.value.days.flatMap((day, dayIndex) => day.attractions.flatMap((attraction, attrIndex) => {
    const longitude = Number(attraction.location?.longitude)
    const latitude = Number(attraction.location?.latitude)
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || longitude === 0 || latitude === 0) return []
    return [{ ...attraction, location: { longitude, latitude }, dayIndex, attrIndex }]
  }))
})

const mappedAttractions = computed<MappedAttraction[]>(() => {
  const usable = allLocatedAttractions.value.filter(item => !unavailablePlacePattern.test(item.name))
  if (usable.length < 4) return usable

  const center: [number, number] = [
    median(usable.map(item => Number(item.location!.longitude))),
    median(usable.map(item => Number(item.location!.latitude)))
  ]
  const nearby = usable.filter(item => coordinateDistanceKm(
    center,
    [Number(item.location!.longitude), Number(item.location!.latitude)]
  ) <= MAP_CLUSTER_RADIUS_KM)

  // 只有形成稳定主城区簇时才排除离群点，避免小型郊区行程被误判。
  return nearby.length >= 3 ? nearby : usable
})

const hiddenMapAttractionCount = computed(() => allLocatedAttractions.value.length - mappedAttractions.value.length)
const weatherPreview = computed<WeatherInfo[]>(() => (tripPlan.value?.weather_info || []).slice(0, 7))

const formatWeatherDate = (value: string): string => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  return match ? `${Number(match[2])}月${Number(match[3])}日` : value
}

const hasInvalidPlaceholderData = computed(() => {
  if (!tripPlan.value) return false
  const placeholderAttraction = new RegExp(`^${tripPlan.value.city}景点\\d+$`)
  return tripPlan.value.days.some(day =>
    day.attractions.some(attraction => placeholderAttraction.test(attraction.name))
    || day.meals.some(meal => /^第\d+天(?:早餐|午餐|晚餐)$/u.test(meal.name))
  )
})

interface GlanceItem {
  key: string
  order: number
  name: string
  days: string
  detail: string
}

interface GlanceAccumulator {
  name: string
  dayNumbers: number[]
  detail: string
}

const normalizeSummaryName = (name: string): string => name
  .replace(/^(入住|早餐|午餐|晚餐|加餐)\s*[·：:]?\s*/u, '')
  .replace(/[（(][^）)]*(?:推荐|用餐)[^）)]*[）)]/gu, '')
  .replace(/\s+/g, '')
  .toLowerCase()

const formatDayNumbers = (dayNumbers: number[]): string => {
  const uniqueDays = [...new Set(dayNumbers)].sort((a, b) => a - b)
  return uniqueDays.length === 1
    ? `第 ${uniqueDays[0]} 天`
    : `第 ${uniqueDays.join('、')} 天`
}

const buildGlanceItems = (items: Array<{ name: string; day: number; detail?: string }>): GlanceItem[] => {
  const grouped = new Map<string, GlanceAccumulator>()
  items.forEach(item => {
    const key = normalizeSummaryName(item.name)
    if (!key) return
    const existing = grouped.get(key)
    if (existing) {
      existing.dayNumbers.push(item.day)
      if (!existing.detail && item.detail) existing.detail = item.detail
      return
    }
    grouped.set(key, {
      name: item.name.trim(),
      dayNumbers: [item.day],
      detail: item.detail?.trim() || ''
    })
  })
  return [...grouped.entries()].map(([key, item], index) => ({
    key,
    order: index + 1,
    name: item.name,
    days: formatDayNumbers(item.dayNumbers),
    detail: item.detail
  }))
}

const hotelOverview = computed<GlanceItem[]>(() => {
  if (!tripPlan.value) return []
  return buildGlanceItems(tripPlan.value.days.flatMap((day, index) => {
    if (!day.hotel?.name) return []
    return [{
      name: day.hotel.name,
      day: index + 1,
      detail: day.hotel.address || day.hotel.price_range || day.hotel.type || ''
    }]
  }))
})

const attractionOverview = computed<GlanceItem[]>(() => {
  if (!tripPlan.value) return []
  return buildGlanceItems(tripPlan.value.days.flatMap((day, index) =>
    day.attractions.map(attraction => ({
      name: attraction.name,
      day: index + 1,
      detail: attraction.address || attraction.category || ''
    }))
  ))
})

const mealOverview = computed<GlanceItem[]>(() => {
  if (!tripPlan.value) return []
  const mealTypeLabels: Record<string, string> = {
    breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐'
  }
  return buildGlanceItems(tripPlan.value.days.flatMap((day, index) => {
    const meals = day.meals?.filter(meal => meal.name) || []
    if (meals.length) {
      return meals.map(meal => ({
        name: meal.name,
        day: index + 1,
        detail: [mealTypeLabels[meal.type] || '用餐', meal.address].filter(Boolean).join(' · ')
      }))
    }
    return (day.schedule || [])
      .filter(item => item.item_type === 'meal' && item.title)
      .map(item => ({
        name: item.title.replace(/^(早餐|午餐|晚餐|加餐)\s*[·：:]?\s*/u, ''),
        day: index + 1,
        detail: item.location || ''
      }))
  }))
})
const savedToMyTrips = computed(() => Boolean(tripPlan.value && isTripSaved(tripPlan.value)))

const mapStatusLabel = computed(() => ({
  loading: '加载中',
  ready: '已连接',
  fallback: '静态地图',
  error: '加载失败',
  unconfigured: '待配置'
}[mapStatus.value]))

onMounted(async () => {
  const data = sessionStorage.getItem('tripPlan')
  if (data) {
    tripPlan.value = JSON.parse(data)
    // 旧行程可能保存了模型生成的伪坐标，先用高德官方 POI 校准再绘制。
    await repairLegacyAttractionLocations()
    // 坐标校准后，图片和地图并行加载。
    void loadAttractionPhotos()
    await nextTick()
    void initMap()
  }
})

const repairLegacyAttractionLocations = async () => {
  if (!tripPlan.value) return
  const attractions = tripPlan.value.days.flatMap(day => day.attractions)
  const unverified = attractions.filter(attraction => !attraction.poi_id)
  if (!unverified.length) return

  // 旧坐标来源不可信；接口不可用时宁可不画点，也不展示错误地点。
  unverified.forEach(attraction => {
    attraction.location = undefined
  })

  try {
    const response = await fetch(`${apiBaseUrl}/api/poi/locations/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        city: tripPlan.value.city,
        places: unverified.map(attraction => ({
          name: attraction.name,
          address: attraction.address || ''
        }))
      })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    const matches = new Map<string, any>(
      (result.data || []).map((item: any) => [item.query_name, item])
    )

    tripPlan.value.days.forEach(day => {
      day.attractions.forEach(attraction => {
        const originalName = attraction.name
        const match = matches.get(originalName)
        if (!match?.matched || !match.location) return
        attraction.name = match.name || originalName
        attraction.address = match.address || attraction.address
        attraction.location = match.location
        attraction.poi_id = match.poi_id || ''

        day.schedule?.forEach(event => {
          if (event.item_type === 'attraction' && event.title === originalName) {
            event.title = attraction.name
            event.location = attraction.address
          }
        })
      })
    })

    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
    if (isTripSaved(tripPlan.value)) saveTripPlan(tripPlan.value)
  } catch (error) {
    console.warn('旧行程景点坐标校准失败:', error)
    message.warning('部分旧景点坐标无法核验，已暂时从地图隐藏')
  }
}

const goBack = () => {
  router.push('/')
}

const addToMyTrips = () => {
  if (!tripPlan.value) return
  const alreadySaved = isTripSaved(tripPlan.value)
  saveTripPlan(tripPlan.value)
  message.success(alreadySaved ? '我的旅行规划已更新' : '已加入我的旅行规划')
}

// 滚动到指定区域
const scrollToSection = ({ key }: { key: string }) => {
  const dayMatch = /^day-(\d+)$/.exec(key)
  if (dayMatch) {
    void scrollToDay(Number(dayMatch[1]))
    return
  }
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const scrollToDay = async (index: number) => {
  activeDays.value = [index]
  activeSection.value = `day-${index}`
  highlightedDay.value = index

  // Ant Design Collapse 会同时收起上一天并展开目标日期。必须等高度动画
  // 完成后再定位，否则后续的布局变化会把目标标题推离视口顶部。
  await nextTick()
  await new Promise<void>(resolve => {
    window.setTimeout(resolve, 360)
  })

  const dayElement = document.getElementById(`day-${index}`)
  const dayHeader = dayElement?.querySelector<HTMLElement>('.ant-collapse-header') ?? dayElement
  if (dayHeader) {
    const stickyHeaderHeight = document.querySelector<HTMLElement>('.site-header')?.offsetHeight ?? 52
    const targetTop = dayHeader.getBoundingClientRect().top + window.scrollY - stickyHeaderHeight - 12
    window.scrollTo({
      top: Math.max(0, targetTop),
      behavior: 'smooth'
    })
  }

  window.setTimeout(() => {
    if (highlightedDay.value === index) highlightedDay.value = null
  }, 1500)
}

// 切换编辑模式
const toggleEditMode = () => {
  editMode.value = true
  // 保存原始数据用于取消编辑
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  message.info('进入编辑模式')
}

// 保存修改
const saveChanges = () => {
  const wasSaved = Boolean(tripPlan.value && isTripSaved(tripPlan.value))
  editMode.value = false
  // 更新sessionStorage
  if (tripPlan.value) {
    // 景点内容或顺序改变后，用最新数据重新构建当天时间轴。
    tripPlan.value.days.forEach(day => {
      day.schedule = []
    })
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
    if (wasSaved) saveTripPlan(tripPlan.value)
  }
  message.success('修改已保存')

  // 重新初始化地图以反映更改
  if (map) {
    map.destroy()
    map = null
  }
  nextTick(() => {
    initMap()
  })
}

// 取消编辑
const cancelEdit = () => {
  if (originalPlan.value) {
    tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  }
  editMode.value = false
  message.info('已取消编辑')
}

// 删除景点
const deleteAttraction = (dayIndex: number, attrIndex: number) => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  if (day.attractions.length <= 1) {
    message.warning('每天至少需要保留一个景点')
    return
  }

  day.attractions.splice(attrIndex, 1)
  day.schedule = []
  message.success('景点已删除')
}

// 移动景点顺序
const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  const attractions = day.attractions

  if (direction === 'up' && attrIndex > 0) {
    [attractions[attrIndex], attractions[attrIndex - 1]] = [attractions[attrIndex - 1], attractions[attrIndex]]
  } else if (direction === 'down' && attrIndex < attractions.length - 1) {
    [attractions[attrIndex], attractions[attrIndex + 1]] = [attractions[attrIndex + 1], attractions[attrIndex]]
  }
  day.schedule = []
}

const getTimelineTypeLabel = (type: string): string => ({
  attraction: '景点',
  meal: '餐饮',
  transport: '路程',
  hotel: '住宿',
  activity: '活动'
}[type] || '安排')

const getTimelineIcon = (type: string): string => ({
  attraction: '⌖',
  meal: '🍽',
  transport: '→',
  hotel: '⌂',
  activity: '•'
}[type] || '•')

const buildLegacyTimeline = (day: DayPlan): TimelineItem[] => {
  const schedule: TimelineItem[] = []
  const meals = Object.fromEntries(day.meals.map(meal => [meal.type, meal]))

  const addMeal = (type: string, start: string, end: string): string => {
    const meal = meals[type]
    if (!meal) return ''
    const labels: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }
    schedule.push({
      start_time: start,
      end_time: end,
      item_type: 'meal',
      title: `${labels[type] || '用餐'} · ${meal.name}`,
      location: meal.address || meal.name,
      description: meal.description || '预留充足用餐时间',
      duration_minutes: type === 'breakfast' ? 40 : 60,
      estimated_cost: meal.estimated_cost || 0
    })
    return meal.name
  }

  let previous = addMeal('breakfast', '08:00', '08:40') || day.hotel?.name || day.accommodation
  const attractionSlots = [['09:10', '11:30'], ['13:30', '15:50'], ['16:20', '18:00']]
  const transportSlots = [['08:40', '09:10'], ['13:00', '13:30'], ['15:50', '16:20']]

  day.attractions.slice(0, 3).forEach((attraction, index) => {
    const [routeStart, routeEnd] = transportSlots[index]
    const [visitStart, visitEnd] = attractionSlots[index]
    schedule.push({
      start_time: routeStart,
      end_time: routeEnd,
      item_type: 'transport',
      title: `前往${attraction.name}`,
      from_location: previous,
      to_location: attraction.name,
      transport_mode: day.transportation,
      duration_minutes: 30,
      description: `从${previous}前往${attraction.name}`
    })
    schedule.push({
      start_time: visitStart,
      end_time: visitEnd,
      item_type: 'attraction',
      title: attraction.name,
      location: attraction.address,
      description: attraction.description,
      duration_minutes: attraction.visit_duration,
      estimated_cost: attraction.ticket_price || 0
    })
    previous = attraction.name
    if (index === 0) previous = addMeal('lunch', '12:00', '13:00') || previous
  })

  previous = addMeal('dinner', '18:30', '19:30') || previous
  if (day.hotel) {
    schedule.push({
      start_time: '19:30',
      end_time: '20:00',
      item_type: 'transport',
      title: '返回酒店',
      from_location: previous,
      to_location: day.hotel.name,
      transport_mode: day.transportation,
      duration_minutes: 30,
      description: '结束当天行程，返回酒店休息'
    })
    schedule.push({
      start_time: '20:00',
      end_time: '21:00',
      item_type: 'hotel',
      title: `入住 · ${day.hotel.name}`,
      location: day.hotel.address,
      description: `${day.hotel.type || day.accommodation}${day.hotel.price_range ? ` · ${day.hotel.price_range}` : ''}`,
      duration_minutes: 60,
      estimated_cost: day.hotel.estimated_cost || 0
    })
  }

  return schedule.sort((a, b) => a.start_time.localeCompare(b.start_time))
}

const getDayTimeline = (day: DayPlan): TimelineItem[] => {
  if (day.schedule?.length) {
    return [...day.schedule].sort((a, b) => a.start_time.localeCompare(b.start_time))
  }
  return buildLegacyTimeline(day)
}

const timelineMatchesAttraction = (eventTitle: string, attractionName: string): boolean => {
  const eventKey = normalizePlaceName(eventTitle)
  const attractionKey = normalizePlaceName(attractionName)
  return Boolean(
    eventKey
    && attractionKey
    && (eventKey === attractionKey || eventKey.includes(attractionKey) || attractionKey.includes(eventKey))
  )
}

const getUnscheduledAttractions = (day: DayPlan) => {
  if (!day.schedule?.length) return []
  const scheduledAttractions = day.schedule.filter(event => event.item_type === 'attraction')
  return day.attractions.filter(attraction => (
    !scheduledAttractions.some(event => timelineMatchesAttraction(event.title, attraction.name))
  ))
}

const getTimelineMemoryName = (event: TimelineItem, day: DayPlan): string => {
  const match = day.attractions
    .map(attraction => ({ attraction, key: normalizePlaceName(attraction.name) }))
    .filter(item => timelineMatchesAttraction(event.title, item.attraction.name))
    .sort((left, right) => right.key.length - left.key.length)[0]
  return match?.attraction.name || event.title
}

const getTimelineAttraction = (event: TimelineItem, day: DayPlan): Attraction | undefined => (
  day.attractions
    .map(attraction => ({ attraction, key: normalizePlaceName(attraction.name) }))
    .filter(item => timelineMatchesAttraction(event.title, item.attraction.name))
    .sort((left, right) => right.key.length - left.key.length)[0]?.attraction
)

const isTimelineVisited = (event: TimelineItem, day: DayPlan): boolean => (
  Boolean(tripPlan.value && isVisited(getTimelineMemoryName(event, day), tripPlan.value.city))
)

const toggleTimelineVisited = (event: TimelineItem, day: DayPlan) => {
  if (!tripPlan.value) return
  const placeName = getTimelineMemoryName(event, day)
  const visited = toggleVisited({
    name: placeName,
    city: tripPlan.value.city,
    category: '景点'
  })
  message.success(visited ? `已记住：去过 ${placeName}` : `${placeName} 已恢复为未去过`)
}

const getWeatherIcon = (condition: string, night: boolean): string => {
  if (/雷|暴雨/.test(condition)) return '⛈️'
  if (/雨/.test(condition)) return '🌧️'
  if (/雪/.test(condition)) return '🌨️'
  if (/雾|霾/.test(condition)) return '🌫️'
  if (/阴/.test(condition)) return '☁️'
  if (/云/.test(condition)) return night ? '☁️' : '⛅'
  return night ? '🌙' : '☀️'
}

// 加载所有景点图片
const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return

  const attractions = tripPlan.value.days.flatMap(day => day.attractions)
  const names = [...new Set(attractions.map(attraction => attraction.name).filter(Boolean))]

  const applyPhotoUrls = (source: 'amap' | 'verified') => {
    attractions.forEach(attraction => {
      attractionPhotos.value[attraction.name] =
        `${apiBaseUrl}/api/poi/photo/image?name=${encodeURIComponent(attraction.name)}` +
        `&city=${encodeURIComponent(tripPlan.value?.city || '')}` +
        `&address=${encodeURIComponent(attraction.address || '')}&v=4&source=${source}`

      if (attractionPhotoIndexes.value[attraction.name] === undefined) {
        const storageKey = `tripmind_photo_${tripPlan.value?.city || ''}_${attraction.name}`
        const savedIndex = Number(localStorage.getItem(storageKey) || 0)
        attractionPhotoIndexes.value[attraction.name] = Number.isFinite(savedIndex) ? savedIndex : 0
      }
    })
  }

  // 先立即显示高德图片，不让 Tavily 图片核验阻塞页面。
  applyPhotoUrls('amap')
  try {
    const response = await fetch(`${apiBaseUrl}/api/poi/photos/prepare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ city: tripPlan.value.city, names })
    })
    const result = await response.json().catch(() => ({ prepared: 0 }))
    if (response.ok && result.prepared > 0) applyPhotoUrls('verified')
  } catch (error) {
    console.warn('景点图片预检不可用，将使用高德图片。', error)
  }
}

// 获取景点图片
const normalizeAttractionName = (name: string): string => name
  .replace(/[（(].*?[）)]/g, '')
  .replace(/^(前往|抵达|游览|参观|打卡|漫步|探索)\s*/, '')
  .replace(/[·—–｜|/：:].*$/, '')
  .replace(/\s+/g, '')

const findMatchedAttraction = (name: string, day?: DayPlan) => {
  const normalizedName = normalizeAttractionName(name)
  return day?.attractions.find(attraction => {
    const candidate = normalizeAttractionName(attraction.name)
    return candidate === normalizedName || candidate.includes(normalizedName) || normalizedName.includes(candidate)
  })
}

const getAttractionPhotoKey = (name: string, day?: DayPlan): string =>
  findMatchedAttraction(name, day)?.name || name

const getAttractionPhotoIndex = (name: string, day?: DayPlan): number =>
  attractionPhotoIndexes.value[getAttractionPhotoKey(name, day)] || 0

const isChangingAttractionPhoto = (name: string, day?: DayPlan): boolean =>
  Boolean(changingAttractionPhotos.value[getAttractionPhotoKey(name, day)])

const changeAttractionPhoto = async (name: string, day?: DayPlan) => {
  const key = getAttractionPhotoKey(name, day)
  if (changingAttractionPhotos.value[key] || !attractionPhotos.value[key]) return
  const nextIndex = (attractionPhotoIndexes.value[key] || 0) + 1
  changingAttractionPhotos.value[key] = true
  try {
    await new Promise<void>((resolve, reject) => {
      const preloadImage = new Image()
      preloadImage.onload = () => resolve()
      preloadImage.onerror = () => reject(new Error('下一张图片加载失败'))
      preloadImage.src = `${attractionPhotos.value[key]}&index=${nextIndex}`
    })
    attractionPhotoIndexes.value[key] = nextIndex
    localStorage.setItem(`tripmind_photo_${tripPlan.value?.city || ''}_${key}`, String(nextIndex))
  } catch {
    message.warning('暂时没有更多可用图片')
  } finally {
    changingAttractionPhotos.value[key] = false
  }
}

const getAttractionImage = (name: string, index: number, day?: DayPlan): string => {
  // 如果已加载真实图片,返回真实图片
  if (attractionPhotos.value[name]) {
    return `${attractionPhotos.value[name]}&index=${getAttractionPhotoIndex(name, day)}`
  }

  const matchedAttraction = findMatchedAttraction(name, day)
  if (matchedAttraction && attractionPhotos.value[matchedAttraction.name]) {
    return `${attractionPhotos.value[matchedAttraction.name]}&index=${getAttractionPhotoIndex(name, day)}`
  }

  // 返回一个纯色占位图(避免跨域问题)
  const colors = [
    { start: '#667eea', end: '#764ba2' },
    { start: '#f093fb', end: '#f5576c' },
    { start: '#4facfe', end: '#00f2fe' },
    { start: '#43e97b', end: '#38f9d7' },
    { start: '#fa709a', end: '#fee140' }
  ]
  const colorIndex = index % colors.length
  const { start, end } = colors[colorIndex]

  // 使用base64编码避免中文问题
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
    <defs>
      <linearGradient id="grad${index}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:${start};stop-opacity:1" />
        <stop offset="100%" style="stop-color:${end};stop-opacity:1" />
      </linearGradient>
    </defs>
    <rect width="400" height="300" fill="url(#grad${index})"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="bold" fill="white">${name}</text>
  </svg>`

  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
}

// 图片加载失败时的处理
const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  if (img.dataset.fallbackApplied === 'true') return
  img.dataset.fallbackApplied = 'true'
  // 使用灰色占位图
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect width="400" height="300" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23999"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}



// 导出为图片
const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    // 创建一个独立的容器
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'

    // 复制所有内容
    exportContainer.innerHTML = element.innerHTML

    // 处理地图截图
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    // 移除所有ant-card类,替换为纯div
    const cards = exportContainer.querySelectorAll('.ant-card')
    cards.forEach((card) => {
      const cardEl = card as HTMLElement
      try {
        cardEl.className = '' // 移除所有类
        cardEl.style.setProperty('background-color', '#ffffff')
        cardEl.style.setProperty('border-radius', '12px')
        cardEl.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
        cardEl.style.setProperty('margin-bottom', '20px')
        cardEl.style.setProperty('overflow', 'hidden')
      } catch (err) {
        console.error('设置卡片样式失败:', err)
      }
    })

    // 处理卡片头部
    const cardHeads = exportContainer.querySelectorAll('.ant-card-head')
    cardHeads.forEach((head) => {
      const headEl = head as HTMLElement
      try {
        headEl.style.setProperty('background-color', '#667eea')
        headEl.style.setProperty('color', '#ffffff')
        headEl.style.setProperty('padding', '16px 24px')
        headEl.style.setProperty('font-size', '18px')
        headEl.style.setProperty('font-weight', '600')
      } catch (err) {
        console.error('设置卡片头部样式失败:', err)
      }
    })

    // 处理卡片内容
    const cardBodies = exportContainer.querySelectorAll('.ant-card-body')
    cardBodies.forEach((body) => {
      const bodyEl = body as HTMLElement
      bodyEl.style.setProperty('background-color', '#ffffff')
      bodyEl.style.setProperty('padding', '24px')
    })

    // 处理酒店卡片头部
    const hotelCards = exportContainer.querySelectorAll('.hotel-card')
    hotelCards.forEach((card) => {
      const head = card.querySelector('.ant-card-head') as HTMLElement
      if (head) {
        head.style.setProperty('background-color', '#1976d2')
      }
      (card as HTMLElement).style.setProperty('background-color', '#e3f2fd')
    })

    // 处理天气卡片
    const weatherCards = exportContainer.querySelectorAll('.weather-card')
    weatherCards.forEach((card) => {
      (card as HTMLElement).style.setProperty('background-color', '#e0f7fa')
    })

    // 处理预算总计
    const budgetTotal = exportContainer.querySelector('.budget-total')
    if (budgetTotal) {
      const el = budgetTotal as HTMLElement
      el.style.setProperty('background-color', '#667eea')
      el.style.setProperty('color', '#ffffff')
      el.style.setProperty('padding', '20px')
      el.style.setProperty('border-radius', '12px')
      el.style.setProperty('margin-bottom', '20px')
    }

    // 处理预算项
    const budgetItems = exportContainer.querySelectorAll('.budget-item')
    budgetItems.forEach((item) => {
      const el = item as HTMLElement
      el.style.setProperty('background-color', '#f5f7fa')
      el.style.setProperty('padding', '16px')
      el.style.setProperty('border-radius', '8px')
      el.style.setProperty('margin-bottom', '12px')
    })

    // 添加到body(隐藏)
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5f7fa',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    // 移除容器
    document.body.removeChild(exportContainer)

    // 转换为图片并下载
    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    message.success({ content: '图片导出成功!', key: 'export' })
  } catch (error: any) {
    console.error('导出图片失败:', error)
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

// 导出为PDF
const exportAsPDF = async () => {
  try {
    message.loading({ content: '正在生成PDF...', key: 'export', duration: 0 })

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    // 创建一个独立的容器
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'

    // 复制所有内容
    exportContainer.innerHTML = element.innerHTML

    // 处理地图截图
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    // 移除所有ant-card类,替换为纯div
    const cards = exportContainer.querySelectorAll('.ant-card')
    cards.forEach((card) => {
      const cardEl = card as HTMLElement
      try {
        cardEl.className = ''
        cardEl.style.setProperty('background-color', '#ffffff')
        cardEl.style.setProperty('border-radius', '12px')
        cardEl.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
        cardEl.style.setProperty('margin-bottom', '20px')
        cardEl.style.setProperty('overflow', 'hidden')
      } catch (err) {
        console.error('设置卡片样式失败:', err)
      }
    })

    // 处理卡片头部
    const cardHeads = exportContainer.querySelectorAll('.ant-card-head')
    cardHeads.forEach((head) => {
      const headEl = head as HTMLElement
      try {
        headEl.style.setProperty('background-color', '#667eea')
        headEl.style.setProperty('color', '#ffffff')
        headEl.style.setProperty('padding', '16px 24px')
        headEl.style.setProperty('font-size', '18px')
        headEl.style.setProperty('font-weight', '600')
      } catch (err) {
        console.error('设置卡片头部样式失败:', err)
      }
    })

    // 处理卡片内容
    const cardBodies = exportContainer.querySelectorAll('.ant-card-body')
    cardBodies.forEach((body) => {
      const bodyEl = body as HTMLElement
      bodyEl.style.setProperty('background-color', '#ffffff')
      bodyEl.style.setProperty('padding', '24px')
    })

    // 处理酒店卡片头部
    const hotelCards = exportContainer.querySelectorAll('.hotel-card')
    hotelCards.forEach((card) => {
      const head = card.querySelector('.ant-card-head') as HTMLElement
      if (head) {
        head.style.setProperty('background-color', '#1976d2')
      }
      (card as HTMLElement).style.setProperty('background-color', '#e3f2fd')
    })

    // 处理天气卡片
    const weatherCards = exportContainer.querySelectorAll('.weather-card')
    weatherCards.forEach((card) => {
      (card as HTMLElement).style.setProperty('background-color', '#e0f7fa')
    })

    // 处理预算总计
    const budgetTotal = exportContainer.querySelector('.budget-total')
    if (budgetTotal) {
      const el = budgetTotal as HTMLElement
      el.style.setProperty('background-color', '#667eea')
      el.style.setProperty('color', '#ffffff')
      el.style.setProperty('padding', '20px')
      el.style.setProperty('border-radius', '12px')
      el.style.setProperty('margin-bottom', '20px')
    }

    // 处理预算项
    const budgetItems = exportContainer.querySelectorAll('.budget-item')
    budgetItems.forEach((item) => {
      const el = item as HTMLElement
      el.style.setProperty('background-color', '#f5f7fa')
      el.style.setProperty('padding', '16px')
      el.style.setProperty('border-radius', '8px')
      el.style.setProperty('margin-bottom', '12px')
    })

    // 添加到body(隐藏)
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5f7fa',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    // 移除容器
    document.body.removeChild(exportContainer)

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    })

    const imgWidth = 210 // A4宽度(mm)
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    // 如果内容高度超过一页,分页处理
    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= 297 // A4高度

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= 297
    }

    pdf.save(`旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.pdf`)

    message.success({ content: 'PDF导出成功!', key: 'export' })
  } catch (error: any) {
    console.error('导出PDF失败:', error)
    message.error({ content: `导出PDF失败: ${error.message}`, key: 'export' })
  }
}

// 初始化地图
const initMap = async () => {
  const amapKey = import.meta.env.VITE_AMAP_WEB_JS_KEY?.trim()
  const securityJsCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE?.trim()
  const verifiedAttractions = mappedAttractions.value

  if (!verifiedAttractions.length) {
    mapStatus.value = 'error'
    mapErrorTitle.value = '这份行程没有可核验的位置'
    mapErrorMessage.value = '当前结果包含无效或过期地点，请返回首页重新生成。'
    return
  }

  if (!amapKey) {
    initStaticMap()
    return
  }

  if (!securityJsCode) {
    initStaticMap()
    return
  }

  staticMapUrl.value = ''
  mapStatus.value = 'loading'

  try {
    ;(window as any)._AMapSecurityConfig = { securityJsCode }

    const AMap = await Promise.race([
      AMapLoader.load({
        key: amapKey,
        version: '2.0',
        plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow']
      }),
      new Promise<never>((_, reject) => {
        window.setTimeout(() => reject(new Error('高德地图加载超时')), 12000)
      })
    ])

    if (map) {
      map.destroy()
      map = null
    }

    const firstAttraction = verifiedAttractions[0]

    const center = firstAttraction?.location
      ? [firstAttraction.location.longitude, firstAttraction.location.latitude]
      : [116.397128, 39.916527]

    // 创建地图实例
    map = new AMap.Map('amap-container', {
      zoom: 12,
      center,
      viewMode: '3D'
    })

    // 添加景点标记
    addAttractionMarkers(AMap)

    mapStatus.value = 'ready'
    message.success('地图加载成功')
  } catch (error: any) {
    console.error('地图加载失败:', error)
    initStaticMap()
  }
}

// 使用已配置的后端高德 Web 服务 Key 生成静态地图，不依赖前端 JS 鉴权。
const initStaticMap = () => {
  if (map) {
    map.destroy()
    map = null
  }

  const points = mappedAttractions.value
    .slice(0, 10)
    .map(attraction => `${attraction.location!.longitude},${attraction.location!.latitude}`) ?? []

  if (points.length === 0) {
    mapStatus.value = 'error'
    mapErrorTitle.value = '没有可用的景点坐标'
    mapErrorMessage.value = '请重新生成行程后再试。'
    return
  }

  mapStatus.value = 'loading'
  staticMapUrl.value = `${apiBaseUrl}/api/map/static?points=${encodeURIComponent(points.join(';'))}`
}

const handleStaticMapLoad = () => {
  mapStatus.value = 'fallback'
}

const handleStaticMapError = () => {
  mapStatus.value = 'error'
  mapErrorTitle.value = '高德静态地图加载失败'
  mapErrorMessage.value = '请确认后端 AMAP_API_KEY 是有效的 Web 服务 Key，然后重试。'
}

// 清除加载器的失败缓存后再试，避免第一次超时后一直显示空白。
const retryMap = async () => {
  if (map) {
    map.destroy()
    map = null
  }

  staticMapUrl.value = ''

  try {
    ;(AMapLoader as unknown as { reset?: () => void }).reset?.()
  } catch (error) {
    console.warn('重置高德地图加载器失败:', error)
  }

  await nextTick()
  await initMap()
}

// 添加景点标记
const addAttractionMarkers = (AMap: any) => {
  if (!tripPlan.value) return

  const markers: any[] = []
  const allAttractions = mappedAttractions.value

  // 创建标记
  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30)
      }
    })

    // 创建信息窗口
    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 10px;">
          <h4 style="margin: 0 0 8px 0;">${attraction.name}</h4>
          <p style="margin: 4px 0;"><strong>地址:</strong> ${attraction.address}</p>
          <p style="margin: 4px 0;"><strong>游览时长:</strong> ${attraction.visit_duration}分钟</p>
          <p style="margin: 4px 0;"><strong>描述:</strong> ${attraction.description}</p>
          <p style="margin: 4px 0; color: #1890ff;"><strong>第${attraction.dayIndex + 1}天 景点${attraction.attrIndex + 1}</strong></p>
        </div>
      `,
      offset: new AMap.Pixel(0, -30)
    })

    // 点击标记显示信息窗口
    marker.on('click', () => {
      infoWindow.open(map, marker.getPosition())
    })

    markers.push(marker)
  })

  // 添加标记到地图
  map.add(markers)

  // 自动调整视野以包含所有标记
  if (allAttractions.length > 0) {
    map.setFitView(markers)
  }

  // 绘制路线
  drawRoutes(AMap, allAttractions)
}

// 绘制路线
const drawRoutes = (AMap: any, attractions: any[]) => {
  if (attractions.length < 2) return

  // 按天分组绘制路线
  const dayGroups: any = {}
  attractions.forEach(attr => {
    if (!dayGroups[attr.dayIndex]) {
      dayGroups[attr.dayIndex] = []
    }
    dayGroups[attr.dayIndex].push(attr)
  })

  // 为每天的景点绘制路线
  Object.values(dayGroups).forEach((dayAttractions: any) => {
    if (dayAttractions.length < 2) return

    const path = dayAttractions.map((attr: any) => [
      attr.location.longitude,
      attr.location.latitude
    ])

    const polyline = new AMap.Polyline({
      path: path,
      strokeColor: '#1890ff',
      strokeWeight: 4,
      strokeOpacity: 0.8,
      strokeStyle: 'solid',
      showDir: true // 显示方向箭头
    })

    map.add(polyline)
  })
}
</script>

<style scoped>
.result-container {
  min-height: 100vh;
  background:
    radial-gradient(circle at 8% 4%, rgba(105, 130, 246, 0.14), transparent 28%),
    radial-gradient(circle at 92% 10%, rgba(125, 83, 201, 0.12), transparent 26%),
    #f5f7fb;
  padding: 32px 24px 64px;
}

.invalid-plan-state {
  max-width: 720px;
  margin: 90px auto;
  padding: 54px 48px;
  border: 1px solid rgba(255, 149, 0, .2);
  border-radius: 28px;
  background: rgba(255, 255, 255, .95);
  box-shadow: 0 24px 70px rgba(0, 0, 0, .08);
  text-align: center;
}

.invalid-plan-icon {
  display: grid;
  width: 52px;
  height: 52px;
  margin: 0 auto 18px;
  place-items: center;
  border-radius: 16px;
  background: #fff3e0;
  color: #b85c00;
  font-size: 25px;
  font-weight: 800;
}

.invalid-plan-state .page-eyebrow { margin-bottom: 8px; }
.invalid-plan-state h2 { margin: 0 0 13px; font-size: 30px; letter-spacing: -.035em; }
.invalid-plan-state > p:not(.page-eyebrow) { margin: 0 auto 24px; color: #6e6e73; font-size: 14px; line-height: 1.7; }

.page-header {
  max-width: 1400px;
  margin: 0 auto 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  animation: fadeInDown 0.6s ease-out;
}

.page-heading {
  display: flex;
  align-items: center;
  gap: 18px;
}

.page-title-block h1 {
  margin: 2px 0 0;
  color: #17223b;
  font-size: 24px;
  line-height: 1.25;
  letter-spacing: -0.02em;
}

.page-eyebrow {
  color: #6c63d9;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.back-button {
  border: 1px solid rgba(89, 99, 135, 0.16);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  font-weight: 600;
  box-shadow: 0 8px 20px rgba(57, 65, 100, 0.06);
}

/* 内容布局 */
.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.side-nav {
  width: 220px;
  flex-shrink: 0;
}

.side-nav :deep(.ant-menu) {
  padding: 8px 0;
  border: 1px solid rgba(89, 99, 135, 0.08);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(44, 51, 84, 0.08);
  background: rgba(255, 255, 255, 0.94);
}

.side-nav :deep(.ant-menu-item) {
  margin: 4px 8px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.side-nav :deep(.ant-menu-item-selected) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.side-nav :deep(.ant-menu-item:hover) {
  background: rgba(102, 126, 234, 0.1);
}

.main-content {
  flex: 1;
  min-width: 0;
}

/* 景点图片样式 */
.attraction-image-wrapper {
  position: relative;
  margin-bottom: 12px;
  border-radius: 8px;
  overflow: hidden;
}

.attraction-image {
  width: 100%;
  height: 200px;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.attraction-image-wrapper:hover .attraction-image {
  transform: scale(1.05);
}

.attraction-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.badge-number {
  font-size: 18px;
}

.price-tag {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(255, 77, 79, 0.9);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: bold;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

/* 天气卡片样式 */
.weather-card {
  background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%);
  border: none !important;
  transition: all 0.3s ease;
}

.weather-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
}

.weather-date {
  font-size: 16px;
  font-weight: bold;
  color: #00796b;
  margin-bottom: 12px;
  text-align: center;
}

.weather-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.weather-icon {
  font-size: 24px;
}

.weather-label {
  font-size: 12px;
  color: #666;
}

.weather-value {
  font-size: 16px;
  font-weight: 600;
  color: #00796b;
}

.weather-wind {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 121, 107, 0.2);
  text-align: center;
  color: #00796b;
  font-size: 14px;
}

/* 回到顶部按钮 */
.back-top-button {
  width: 50px;
  height: 50px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: all 0.3s ease;
}

.back-top-button:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

/* 酒店卡片样式 */
.hotel-card {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: none !important;
}

.hotel-card :deep(.ant-card-head) {
  background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
}

.hotel-title {
  color: white !important;
  font-weight: 600;
}

/* 顶部信息区布局 */
.top-info-section {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(380px, 0.85fr);
  align-items: start;
  gap: 20px;
  margin-bottom: 20px;
}

.left-info {
  display: contents;
}

.right-map {
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
}

/* 行程概览卡片 */
.overview-card {
  grid-column: 1;
  grid-row: 1;
  overflow: hidden;
  border: 1px solid rgba(91, 104, 155, 0.08);
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.98), rgba(248, 249, 255, 0.98));
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.overview-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.overview-heading h2 {
  margin: 12px 0 5px;
  color: #18213a;
  font-size: 28px;
  line-height: 1.2;
  letter-spacing: -0.03em;
}

.overview-heading p {
  margin: 0;
  color: #77809a;
  font-size: 13px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border: 1px solid #cdeedc;
  border-radius: 999px;
  background: #eefbf4;
  color: #287b51;
  font-size: 12px;
  font-weight: 700;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2eb872;
  box-shadow: 0 0 0 4px rgba(46, 184, 114, 0.12);
}

.day-count {
  min-width: 76px;
  padding: 13px 14px;
  border-radius: 18px;
  background: linear-gradient(145deg, #6d77e8, #7952bd);
  color: white;
  text-align: center;
  box-shadow: 0 12px 22px rgba(102, 93, 205, 0.22);
}

.day-count strong {
  display: block;
  font-size: 28px;
  line-height: 1;
}

.day-count span {
  font-size: 12px;
  opacity: 0.84;
}

.trip-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.weather-summary {
  scroll-margin-top: 72px;
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(145deg, #eef7ff, #f8fbff);
}

.weather-summary-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.weather-summary-heading h3 {
  margin: 2px 0 0;
  color: #1d1d1f;
  font-size: 17px;
}

.weather-source {
  color: #86868b;
  font-size: 10px;
}

.weather-preview-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(76px, 1fr));
  gap: 7px;
}

.weather-preview-item {
  display: flex;
  min-width: 0;
  padding: 9px 7px;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  border: 1px solid rgba(0, 113, 227, .08);
  border-radius: 12px;
  background: rgba(255, 255, 255, .86);
  text-align: center;
}

.weather-preview-date,
.weather-preview-item small {
  color: #86868b;
  font-size: 9px;
}

.weather-preview-icon { font-size: 19px; line-height: 1.2; }
.weather-preview-item strong { color: #1d1d1f; font-size: 11px; }

.weather-unavailable {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border: 1px solid rgba(0, 113, 227, .08);
  border-radius: 12px;
  background: rgba(255, 255, 255, .78);
}

.weather-unavailable-icon { font-size: 24px; }
.weather-unavailable strong { color: #1d1d1f; font-size: 12px; }
.weather-unavailable p { margin: 2px 0 0; color: #6e6e73; font-size: 10px; line-height: 1.5; }

.meta-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid #edf0f7;
  border-radius: 13px;
  background: white;
}

.meta-icon {
  display: grid;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 10px;
  background: #f1f2ff;
}

.meta-chip div {
  min-width: 0;
}

.meta-chip small,
.meta-chip strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-chip small {
  margin-bottom: 2px;
  color: #8d95aa;
  font-size: 11px;
}

.meta-chip strong {
  color: #303952;
  font-size: 13px;
}

.trip-glance {
  padding-top: 2px;
}

.trip-glance-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}

.section-eyebrow {
  display: block;
  margin-bottom: 3px;
  color: #0071e3;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .14em;
}

.trip-glance-heading h3 {
  margin: 0;
  color: #1d1d1f;
  font-size: 18px;
  font-weight: 680;
  letter-spacing: -.025em;
}

.glance-total {
  flex: 0 0 auto;
  color: #86868b;
  font-size: 12px;
}

.trip-glance-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.glance-group {
  min-width: 0;
  padding: 13px;
  border: 1px solid rgba(0, 0, 0, .055);
  border-radius: 16px;
  background: #f5f5f7;
}

.hotel-glance {
  grid-column: 1 / -1;
  background: linear-gradient(145deg, #f3f8ff, #f5f5f7);
}

.hotel-glance .glance-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.attraction-glance {
  background: linear-gradient(145deg, #f2fbf5, #f5f5f7);
}

.meal-glance {
  background: linear-gradient(145deg, #fff8ef, #f5f5f7);
}

.glance-group-heading {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 11px;
}

.glance-icon {
  display: grid;
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 9px;
  background: rgba(255, 255, 255, .9);
  color: #0071e3;
  font-size: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, .04);
}

.glance-group-heading div {
  min-width: 0;
}

.glance-group-heading small,
.glance-group-heading strong {
  display: block;
}

.glance-group-heading small {
  margin-bottom: 1px;
  color: #86868b;
  font-size: 8px;
  font-weight: 750;
  letter-spacing: .12em;
}

.glance-group-heading strong {
  color: #1d1d1f;
  font-size: 13px;
  font-weight: 680;
}

.glance-count {
  min-width: 22px;
  margin-left: auto;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, .82);
  color: #515154;
  font-size: 10px;
  font-weight: 700;
  text-align: center;
}

.glance-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.glance-list li {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: start;
  gap: 7px;
}

.glance-index {
  display: grid;
  width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, .94);
  color: #6e6e73;
  font-size: 9px;
  font-weight: 750;
}

.glance-list li div {
  min-width: 0;
}

.glance-list li strong,
.glance-list li small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.glance-list li strong {
  color: #1d1d1f;
  font-size: 12px;
  font-weight: 650;
}

.glance-list li small {
  margin-top: 2px;
  color: #86868b;
  font-size: 10px;
}

.glance-empty {
  margin: 4px 0 0;
  color: #86868b;
  font-size: 11px;
}

.suggestion-panel {
  padding: 16px 18px;
  border: 1px solid #e8e9fb;
  border-radius: 14px;
  background: linear-gradient(135deg, #f7f7ff, #fbf8ff);
}

.suggestion-title {
  margin-bottom: 8px;
  color: #4f4a98;
  font-size: 13px;
  font-weight: 800;
}

.suggestion-text {
  display: -webkit-box;
  overflow: hidden;
  margin: 0;
  color: #505971;
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-line;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
}

.suggestion-text.expanded {
  display: block;
  overflow: visible;
}

.text-button {
  margin-top: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #625ac7;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

/* 预算卡片 */
.budget-card {
  grid-column: 1 / -1;
  grid-row: 2;
  margin-bottom: 0 !important;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.budget-item {
  text-align: center;
  padding: 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.budget-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.budget-value {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
}

.total-label {
  font-size: 16px;
  font-weight: 600;
}

.total-value {
  font-size: 28px;
  font-weight: 700;
}

/* 地图卡片 */
.map-card {
  height: 510px;
  overflow: hidden;
}

.map-card :deep(.ant-card-body) {
  height: calc(100% - 57px);
  padding: 0;
}

.day-overview-card {
  margin-bottom: 0 !important;
}

.day-overview-card :deep(.ant-card-body) {
  padding: 10px;
}

.day-overview-count {
  padding: 3px 8px;
  border-radius: 999px;
  background: #f5f5f7;
  color: #6e6e73;
  font-size: 11px;
  font-weight: 650;
}

.day-overview-list {
  display: flex;
  max-height: 450px;
  flex-direction: column;
  gap: 5px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.day-overview-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 18px;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px 10px;
  border: 0;
  border-radius: 13px;
  background: transparent;
  color: #1d1d1f;
  text-align: left;
  cursor: pointer;
  transition: background .18s ease, transform .18s ease;
}

.day-overview-item:hover {
  background: #f5f5f7;
  transform: translateX(2px);
}

.quick-day-number {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 11px;
  background: #eaf4ff;
  color: #0066cc;
  font-size: 13px;
  font-weight: 750;
}

.quick-day-content,
.quick-day-topline,
.quick-day-places,
.quick-day-hotel {
  display: block;
  min-width: 0;
}

.quick-day-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.quick-day-topline strong {
  font-size: 13px;
  font-weight: 680;
}

.quick-day-topline small,
.quick-day-places,
.quick-day-hotel {
  color: #86868b;
  font-size: 10px;
}

.quick-day-places,
.quick-day-hotel {
  overflow: hidden;
  margin-top: 3px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-day-hotel {
  color: #6e6e73;
}

.quick-day-arrow {
  color: #aeaeb2;
  font-size: 22px;
  line-height: 1;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.map-state-badge {
  padding: 4px 9px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  color: white;
  font-size: 11px;
  font-weight: 700;
}

.map-state-badge.ready {
  background: rgba(46, 184, 114, 0.3);
}

.map-state-badge.fallback {
  background: rgba(46, 184, 114, 0.3);
}

.map-state-badge.error,
.map-state-badge.unconfigured {
  background: rgba(255, 186, 73, 0.28);
}

.map-shell {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background:
    linear-gradient(rgba(255, 255, 255, 0.52), rgba(255, 255, 255, 0.52)),
    repeating-linear-gradient(45deg, #eef0f8 0, #eef0f8 1px, transparent 1px, transparent 22px);
}

#amap-container {
  width: 100%;
  height: 100%;
}

.static-map-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.map-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 32px;
  background: rgba(248, 249, 253, 0.9);
  color: #303952;
  text-align: center;
  backdrop-filter: blur(4px);
}

.map-overlay > span {
  max-width: 320px;
  color: #7b849d;
  font-size: 13px;
  line-height: 1.6;
}

.map-quality-note {
  position: absolute;
  right: 10px;
  bottom: 10px;
  left: 10px;
  z-index: 4;
  padding: 7px 10px;
  border: 1px solid rgba(255, 159, 10, .22);
  border-radius: 10px;
  background: rgba(255, 250, 240, .92);
  color: #8a4b00;
  font-size: 10px;
  line-height: 1.45;
  text-align: center;
  box-shadow: 0 4px 14px rgba(0, 0, 0, .08);
  backdrop-filter: blur(10px);
}

.map-error-icon {
  display: grid;
  width: 62px;
  height: 62px;
  margin-bottom: 4px;
  place-items: center;
  border-radius: 18px;
  background: white;
  font-size: 29px;
  box-shadow: 0 10px 24px rgba(50, 58, 91, 0.1);
}

/* 每日行程卡片 */
.days-card {
  margin-top: 4px;
}

.weather-section {
  margin-top: 20px;
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.day-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.day-date {
  font-size: 14px;
  color: #999;
}

.day-info {
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.info-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row .label {
  font-weight: 600;
  color: #666;
  min-width: 100px;
}

.info-row .value {
  color: #333;
  flex: 1;
}

/* 卡片样式优化 */
:deep(.ant-card) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 20px;
  transition: all 0.3s ease;
  animation: fadeInUp 0.6s ease-out;
}

:deep(.ant-card:hover) {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

:deep(.ant-card-head) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white !important;
  border-radius: 12px 12px 0 0;
  font-weight: 600;
}

:deep(.ant-card-head-title) {
  color: white !important;
  font-size: 18px;
}

:deep(.ant-card-head-title span) {
  color: white !important;
}

/* Collapse样式 */
:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  overflow: hidden;
}

:deep(.ant-collapse-header) {
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  padding: 16px 20px !important;
  font-weight: 600;
}

:deep(.ant-collapse-content) {
  border-top: 1px solid #e8e8e8;
}

:deep(.ant-collapse-content-box) {
  padding: 20px;
}

/* 统计卡片样式 */
:deep(.ant-statistic-title) {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

:deep(.ant-statistic-content) {
  font-size: 24px;
  font-weight: 600;
  color: #1890ff;
}

/* 景点卡片样式 */
:deep(.ant-list-item) {
  transition: all 0.3s ease;
}

:deep(.ant-list-item:hover) {
  transform: scale(1.02);
}

/* 动画 */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 响应式设计 */
@media (max-width: 1120px) {
  .side-nav {
    display: none;
  }

  .top-info-section {
    grid-template-columns: minmax(0, 1.1fr) minmax(340px, 0.9fr);
  }
}

@media (max-width: 860px) {
  .top-info-section {
    grid-template-columns: 1fr;
  }

  .overview-card {
    grid-column: 1;
    grid-row: 1;
  }

  .right-map {
    grid-column: 1;
    grid-row: 2;
  }

  .budget-card {
    grid-column: 1;
    grid-row: 3;
  }

  .map-card {
    height: 440px;
  }

  .day-overview-list {
    display: grid;
    max-height: none;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    overflow: visible;
  }
}

@media (max-width: 768px) {
  .result-container {
    padding: 18px 12px 48px;
  }

  .page-header {
    align-items: stretch;
    flex-direction: column;
    gap: 14px;
  }

  .page-heading {
    align-items: flex-start;
  }

  .page-title-block h1 {
    font-size: 20px;
  }

  .header-actions {
    justify-content: flex-end;
  }

  .trip-meta-grid {
    grid-template-columns: 1fr;
  }

  .trip-glance-grid {
    grid-template-columns: 1fr;
  }

  .hotel-glance .glance-list {
    grid-template-columns: 1fr;
  }

  .glance-list li strong {
    font-size: 12px;
  }

  .overview-heading h2 {
    font-size: 24px;
  }

  .day-count {
    min-width: 66px;
  }

  .map-card {
    height: 380px;
  }

  .day-overview-list {
    grid-template-columns: 1fr;
  }

  .info-row {
    flex-direction: column;
    gap: 3px;
  }

  .info-row .label {
    min-width: 0;
  }

  .budget-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .total-value {
    font-size: 24px;
  }

  :deep(.ant-collapse-content-box) {
    padding: 14px;
  }

  :deep(.ant-card-body) {
    padding: 18px;
  }
}

/* Apple-inspired visual system */
.result-container {
  padding: 46px 28px 80px;
  background:
    radial-gradient(circle at 12% 0%, rgba(90, 200, 250, 0.09), transparent 28%),
    radial-gradient(circle at 88% 4%, rgba(0, 113, 227, 0.06), transparent 24%),
    #f5f5f7;
  color: #1d1d1f;
}

.page-header,
.content-wrapper {
  max-width: 1480px;
}

.page-header {
  margin-bottom: 30px;
}

.page-heading {
  gap: 20px;
}

.page-title-block h1 {
  margin-top: 4px;
  color: #1d1d1f;
  font-size: 30px;
  font-weight: 650;
  letter-spacing: -0.045em;
}

.page-eyebrow {
  color: #0071e3;
  font-size: 10px;
  letter-spacing: 0.19em;
}

.back-button,
.header-actions :deep(.ant-btn) {
  height: 40px;
  padding-inline: 17px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  color: #1d1d1f;
  box-shadow: 0 5px 18px rgba(0, 0, 0, 0.05);
  backdrop-filter: blur(16px);
}

.header-actions :deep(.ant-btn-primary) {
  border-color: #0071e3;
  background: #0071e3;
  color: white;
}

.back-button:hover,
.header-actions :deep(.ant-btn-default:hover) {
  border-color: rgba(0, 113, 227, 0.45);
  color: #0066cc;
}

.content-wrapper {
  gap: 24px;
}

.side-nav {
  width: 208px;
}

.side-nav :deep(.ant-menu) {
  padding: 10px 8px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
}

.side-nav :deep(.ant-menu-item),
.side-nav :deep(.ant-menu-submenu-title) {
  height: 42px;
  margin: 3px 0;
  border-radius: 12px;
  color: #515154;
  font-size: 13px;
  line-height: 42px;
}

.side-nav :deep(.ant-menu-item-selected) {
  background: #eaf4ff;
  color: #0066cc;
  font-weight: 600;
}

.side-nav :deep(.ant-menu-item:hover),
.side-nav :deep(.ant-menu-submenu-title:hover) {
  background: #f5f5f7;
  color: #1d1d1f;
}

.top-info-section {
  grid-template-columns: minmax(0, 1.12fr) minmax(400px, 0.88fr);
  gap: 22px;
  margin-bottom: 22px;
}

:deep(.ant-card) {
  margin-bottom: 22px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.055) !important;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 14px 38px rgba(0, 0, 0, 0.055);
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease;
}

:deep(.ant-card:hover) {
  border-color: rgba(0, 0, 0, 0.09) !important;
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.075);
}

:deep(.ant-card-head),
.hotel-card :deep(.ant-card-head) {
  min-height: 58px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.065);
  border-radius: 22px 22px 0 0;
  background: rgba(255, 255, 255, 0.96);
  color: #1d1d1f !important;
}

:deep(.ant-card-head-title),
:deep(.ant-card-head-title span),
.hotel-title {
  color: #1d1d1f !important;
  font-size: 16px;
  font-weight: 650;
  letter-spacing: -0.015em;
}

.overview-card {
  border-color: rgba(0, 0, 0, 0.055) !important;
  background: rgba(255, 255, 255, 0.96);
}

.overview-heading h2 {
  color: #1d1d1f;
  font-size: 32px;
  font-weight: 650;
  letter-spacing: -0.045em;
}

.overview-heading p {
  color: #86868b;
  font-size: 13px;
}

.status-pill {
  border-color: rgba(52, 199, 89, 0.2);
  background: rgba(52, 199, 89, 0.09);
  color: #248a3d;
}

.status-dot {
  background: #34c759;
  box-shadow: 0 0 0 4px rgba(52, 199, 89, 0.11);
}

.day-count {
  min-width: 78px;
  border-radius: 22px;
  background: #0071e3;
  box-shadow: 0 12px 26px rgba(0, 113, 227, 0.2);
}

.day-count strong {
  font-size: 30px;
}

.meta-chip {
  padding: 13px;
  border-color: transparent;
  border-radius: 15px;
  background: #f5f5f7;
}

.meta-icon {
  border-radius: 11px;
  background: white;
  box-shadow: 0 2px 7px rgba(0, 0, 0, 0.04);
}

.meta-chip small {
  color: #86868b;
}

.meta-chip strong {
  color: #1d1d1f;
}

.suggestion-panel {
  border-color: transparent;
  border-radius: 17px;
  background: #f5f5f7;
}

.suggestion-title,
.text-button {
  color: #0066cc;
}

.suggestion-text {
  color: #515154;
}

.budget-item {
  padding: 15px 12px;
  border-color: transparent;
  border-radius: 14px;
  background: #f5f5f7;
}

.budget-label {
  color: #86868b;
}

.budget-value {
  color: #1d1d1f;
}

.budget-total {
  padding: 18px 20px;
  border-radius: 16px;
  background: #1d1d1f;
}

.map-card {
  height: 510px;
}

.map-card :deep(.ant-card-head) {
  background: rgba(255, 255, 255, 0.96);
}

.map-state-badge {
  border-color: rgba(0, 0, 0, 0.07);
  background: #f5f5f7;
  color: #6e6e73;
}

.map-state-badge.ready,
.map-state-badge.fallback {
  border-color: rgba(52, 199, 89, 0.16);
  background: rgba(52, 199, 89, 0.1);
  color: #248a3d;
}

.map-state-badge.error,
.map-state-badge.unconfigured {
  border-color: rgba(255, 159, 10, 0.16);
  background: rgba(255, 159, 10, 0.1);
  color: #a05a00;
}

.map-shell {
  background: #eef1f4;
}

.map-overlay {
  background: rgba(245, 245, 247, 0.9);
  color: #1d1d1f;
  backdrop-filter: blur(16px);
}

.map-overlay > span {
  color: #86868b;
}

.map-error-icon {
  border-radius: 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
}

:deep(.ant-collapse-item) {
  margin-bottom: 12px;
  border: 1px solid rgba(0, 0, 0, 0.065);
  border-radius: 16px !important;
}

:deep(.ant-collapse-header) {
  padding: 18px 20px !important;
  background: #f5f5f7;
}

:deep(.ant-collapse-content) {
  border-top-color: rgba(0, 0, 0, 0.06);
}

.day-title {
  color: #1d1d1f;
  font-weight: 650;
}

.day-date {
  color: #86868b;
}

.day-info {
  padding: 18px;
  border-color: transparent;
  border-radius: 15px;
  background: #f5f5f7;
}

.info-row .label {
  color: #515154;
}

.info-row .value {
  color: #1d1d1f;
}

.day-timeline {
  max-width: 940px;
  margin: 6px auto 22px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 72px 42px minmax(0, 1fr);
  gap: 14px;
  align-items: stretch;
  min-height: 106px;
}

.timeline-time {
  padding-top: 18px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.timeline-time strong,
.timeline-time span {
  display: block;
}

.timeline-time strong {
  color: #1d1d1f;
  font-size: 16px;
  font-weight: 700;
}

.timeline-time span {
  margin-top: 3px;
  color: #86868b;
  font-size: 12px;
}

.timeline-track {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.timeline-dot {
  position: relative;
  z-index: 2;
  display: grid;
  width: 36px;
  height: 36px;
  margin-top: 14px;
  place-items: center;
  border: 5px solid #fff;
  border-radius: 50%;
  background: #0071e3;
  color: #fff;
  font-size: 15px;
  font-weight: 750;
  box-shadow: 0 4px 14px rgba(0, 113, 227, 0.2);
}

.timeline-transport .timeline-dot {
  background: #f5f5f7;
  color: #6e6e73;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.07);
}

.timeline-meal .timeline-dot {
  background: #ff9f0a;
  box-shadow: 0 4px 14px rgba(255, 159, 10, 0.2);
}

.timeline-hotel .timeline-dot {
  background: #5856d6;
  box-shadow: 0 4px 14px rgba(88, 86, 214, 0.2);
}

.timeline-line {
  position: absolute;
  top: 48px;
  bottom: -14px;
  width: 2px;
  background: linear-gradient(#d2d2d7 60%, rgba(210, 210, 215, 0));
}

.timeline-card {
  position: relative;
  margin-bottom: 14px;
  padding: 18px 20px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.045);
}

.timeline-transport .timeline-card {
  padding-block: 15px;
  border-style: dashed;
  background: #f5f5f7;
  box-shadow: none;
}

.timeline-card-topline {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 7px;
}

.timeline-kind {
  color: #0071e3;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
}

.timeline-meal .timeline-kind {
  color: #b65e00;
}

.timeline-hotel .timeline-kind {
  color: #5856d6;
}

.timeline-duration {
  color: #86868b;
  font-size: 12px;
}

.timeline-card h3 {
  margin: 0 0 8px;
  color: #1d1d1f;
  font-size: 18px;
  line-height: 1.35;
}

.poi-verification {
  display: inline-flex;
  align-items: center;
  margin: 0 0 5px !important;
  padding: 4px 8px;
  border-radius: 999px;
  color: #18783b;
  background: #edf9f0;
  font-size: 11px;
  font-weight: 650;
}

.timeline-card p {
  margin: 5px 0 0;
  line-height: 1.65;
}

.timeline-location,
.timeline-meta,
.timeline-description {
  color: #6e6e73;
}

.timeline-route {
  display: flex;
  gap: 10px;
  align-items: center;
  color: #1d1d1f;
  font-weight: 650;
}

.timeline-route b {
  color: #0071e3;
  font-size: 18px;
}

.timeline-cost {
  color: #248a3d;
  font-size: 13px;
  font-weight: 600;
}

.timeline-visited-button {
  margin-top: 11px;
  padding: 7px 11px;
  border: 1px solid #d2d2d7;
  border-radius: 999px;
  background: #fff;
  color: #515154;
  cursor: pointer;
  font-size: 11px;
  font-weight: 650;
}

.timeline-visited-button:hover {
  border-color: #8fc1ef;
  color: #0071e3;
}

.timeline-visited-button.active {
  border-color: rgba(52, 199, 89, .18);
  background: rgba(52, 199, 89, .1);
  color: #248a3d;
}

.timeline-image-shell {
  position: relative;
  width: 100%;
  height: clamp(180px, 22vw, 240px);
  margin-top: 14px;
  overflow: hidden;
  border-radius: 13px;
  background: #f5f5f7;
}

.timeline-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  background: #f5f5f7;
}

.change-photo-button {
  position: absolute;
  right: 10px;
  bottom: 10px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid rgba(255, 255, 255, .48);
  border-radius: 999px;
  background: rgba(29, 29, 31, .72);
  color: #fff;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, .18);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  transition: transform .18s ease, background .18s ease;
}

.change-photo-button:hover {
  background: rgba(29, 29, 31, .88);
  transform: translateY(-1px);
}

.change-photo-button:disabled {
  cursor: wait;
  opacity: .72;
  transform: none;
}

.attraction-card {
  border-radius: 18px !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.05);
}

.attraction-image-wrapper {
  border-radius: 14px;
}

.attraction-image-wrapper:hover .attraction-image {
  transform: scale(1.025);
}

.attraction-badge {
  width: 34px;
  height: 34px;
  background: rgba(29, 29, 31, 0.9);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(12px);
}

.badge-number {
  font-size: 15px;
}

.price-tag {
  border-radius: 999px;
  background: rgba(29, 29, 31, 0.86);
  font-size: 12px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.14);
  backdrop-filter: blur(12px);
}

.hotel-card {
  border: 1px solid rgba(0, 0, 0, 0.055) !important;
  background: #f5f5f7;
}

.weather-card {
  border: 1px solid rgba(0, 113, 227, 0.08) !important;
  background: linear-gradient(145deg, #f3f9ff, #ffffff);
}

.weather-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 30px rgba(0, 113, 227, 0.08);
}

.weather-date,
.weather-value,
.weather-wind {
  color: #1d1d1f;
}

.weather-wind {
  border-top-color: rgba(0, 0, 0, 0.07);
}

.weather-label {
  color: #86868b;
}

.back-top-button {
  width: 46px;
  height: 46px;
  background: rgba(29, 29, 31, 0.9);
  font-size: 19px;
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(14px);
}

.back-top-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 13px 30px rgba(0, 0, 0, 0.22);
}

:deep(.ant-statistic-title) {
  color: #86868b;
}

:deep(.ant-statistic-content) {
  color: #0071e3;
}

/* Compact itinerary: keep more of the trip visible in one viewport. */
.result-container { padding: 28px 22px 58px; }
.page-header { margin-bottom: 18px; }
.page-title-block h1 { font-size: 26px; }
.back-button,
.header-actions :deep(.ant-btn) { height: 36px; padding-inline: 14px; font-size: 12px; }
.content-wrapper { gap: 18px; }
.side-nav { width: 184px; }
.side-nav :deep(.ant-menu) { padding: 7px 6px; border-radius: 18px; }
.side-nav :deep(.ant-menu-item),
.side-nav :deep(.ant-menu-submenu-title) { height: 36px; margin: 2px 0; border-radius: 10px; font-size: 12px; line-height: 36px; }
.top-info-section { grid-template-columns: minmax(0, 1.18fr) minmax(360px, .82fr); gap: 16px; margin-bottom: 16px; }
:deep(.ant-card) { margin-bottom: 15px; border-radius: 18px; }
:deep(.ant-card-head),
.hotel-card :deep(.ant-card-head) { min-height: 48px; border-radius: 18px 18px 0 0; }
:deep(.ant-card-head-title),
:deep(.ant-card-head-title span),
.hotel-title { font-size: 14px; }
.overview-card :deep(.ant-card-body) { padding: 23px; }
.overview-heading h2 { font-size: 27px; }
.overview-heading p { margin-bottom: 0; font-size: 12px; }
.day-count { min-width: 64px; min-height: 64px; border-radius: 18px; }
.day-count strong { font-size: 25px; }
.meta-chip { padding: 10px; border-radius: 13px; }
.trip-glance { margin-top: 18px; }
.trip-glance-grid { gap: 9px; }
.glance-group { padding: 13px; border-radius: 15px; }
.glance-list { max-height: 172px; overflow-y: auto; }
.glance-list li { gap: 8px; padding-block: 6px; }
.glance-list strong { font-size: 11px; }
.glance-list small { font-size: 9px; }
.suggestion-panel { margin-top: 14px; padding: 14px; }
.suggestion-text { font-size: 11px; line-height: 1.55; }
.budget-card :deep(.ant-card-body) { padding: 16px; }
.budget-item { padding: 11px 9px; }
.budget-total { padding: 14px 16px; }
.map-card { height: 400px; }
.day-overview-card :deep(.ant-card-body) { padding: 7px; }
.day-overview-list { max-height: 320px; gap: 2px; }
.day-overview-item { grid-template-columns: 30px minmax(0, 1fr) 14px; gap: 8px; padding: 8px; border-radius: 11px; }
.quick-day-number { width: 30px; height: 30px; border-radius: 9px; font-size: 12px; }
.quick-day-topline strong { font-size: 12px; }
.quick-day-topline small,
.quick-day-places,
.quick-day-hotel { font-size: 9px; }
.days-card :deep(.ant-card-body) { padding: 15px; }
.day-collapse-panel { scroll-margin-top: 64px; transition: box-shadow .25s ease; }
.day-focus { border-color: rgba(0, 113, 227, .35) !important; box-shadow: 0 0 0 4px rgba(0, 113, 227, .09); }
.day-focus :deep(.ant-collapse-header) { background: #eaf4ff; }
:deep(.ant-collapse-item) { margin-bottom: 8px; border-radius: 13px !important; }
:deep(.ant-collapse-header) { padding: 13px 16px !important; }
:deep(.ant-collapse-content-box) { padding: 14px 16px !important; }
.day-info { padding: 12px 14px; border-radius: 13px; }
.info-row { margin-bottom: 6px; font-size: 11px; }
.unscheduled-attractions { display: flex; margin: 10px 0 12px; padding: 11px 13px; align-items: flex-start; justify-content: space-between; gap: 14px; border: 1px solid rgba(255, 149, 0, .2); border-radius: 13px; background: #fff8ec; }
.unscheduled-attractions strong { display: block; color: #8a4b00; font-size: 11px; }
.unscheduled-attractions > div > span { display: block; margin-top: 3px; color: #8a6a43; font-size: 9px; }
.unscheduled-place-list { display: flex; max-width: 52%; flex-wrap: wrap; justify-content: flex-end; gap: 5px; }
.unscheduled-place-list span { margin: 0 !important; padding: 4px 7px; border-radius: 999px; background: rgba(255, 149, 0, .12); color: #8a4b00 !important; font-size: 9px !important; font-weight: 650; }
.day-timeline { margin: 4px auto 14px; }
.timeline-item { grid-template-columns: 62px 34px minmax(0, 1fr); min-height: 86px; gap: 10px; }
.timeline-time { padding-top: 13px; }
.timeline-time strong { font-size: 14px; }
.timeline-time span { font-size: 10px; }
.timeline-dot { width: 30px; height: 30px; margin-top: 10px; border-width: 4px; font-size: 12px; }
.timeline-line { top: 40px; bottom: -10px; }
.timeline-card { margin-bottom: 10px; padding: 13px 16px; border-radius: 15px; }
.timeline-transport .timeline-card { padding-block: 11px; }
.timeline-card-topline { margin-bottom: 4px; }
.timeline-kind, .timeline-duration { font-size: 10px; }
.timeline-card h3 { margin-bottom: 5px; font-size: 16px; }
.timeline-card p { margin-top: 3px; font-size: 11px; line-height: 1.5; }
.timeline-visited-button { margin-top: 8px; padding: 5px 9px; font-size: 10px; }
.timeline-image-shell { height: clamp(145px, 17vw, 190px); margin-top: 10px; border-radius: 11px; }
.change-photo-button { right: 8px; bottom: 8px; height: 28px; padding-inline: 10px; font-size: 10px; }

@media (max-width: 1120px) {
  .top-info-section {
    grid-template-columns: minmax(0, 1.05fr) minmax(340px, 0.95fr);
  }
}

@media (max-width: 768px) {
  .result-container {
    padding: 28px 14px 54px;
  }

  .page-header {
    margin-bottom: 22px;
  }

  .page-heading {
    gap: 13px;
  }

  .page-title-block h1 {
    font-size: 23px;
  }

  .back-button {
    height: 38px;
    padding-inline: 14px;
  }

  .timeline-item {
    grid-template-columns: 52px 30px minmax(0, 1fr);
    gap: 8px;
  }

  .timeline-time {
    padding-top: 16px;
  }

  .timeline-time strong {
    font-size: 13px;
  }

  .timeline-dot {
    width: 28px;
    height: 28px;
    border-width: 4px;
    font-size: 12px;
  }

  .timeline-line {
    top: 40px;
  }

  .timeline-card {
    padding: 15px;
    border-radius: 15px;
  }

  .timeline-card h3 {
    font-size: 16px;
  }

  .timeline-route {
    flex-wrap: wrap;
  }

  :deep(.ant-card) {
    border-radius: 18px;
  }

  :deep(.ant-card-head),
  .hotel-card :deep(.ant-card-head) {
    border-radius: 18px 18px 0 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  :deep(.ant-card),
  .page-header,
  .attraction-image,
  .weather-card,
  .back-top-button {
    animation: none;
    transition: none;
  }
}
</style>
