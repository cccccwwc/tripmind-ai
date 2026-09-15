<template>
  <main class="home-page">
    <div class="ambient ambient-left"></div>
    <div class="ambient ambient-right"></div>
    <section class="planner-shell">
      <aside class="memory-sidebar" aria-label="个人画像与规划进度">
        <div class="sidebar-heading">
          <div>
            <p>TRIPMIND PROFILE</p>
            <h2>我的旅行画像</h2>
            <span>延续习惯，也允许每次旅行临时改变</span>
          </div>
          <button type="button" class="new-chat-button" aria-label="开始新的旅行对话" @click="resetConversation">＋</button>
        </div>

        <nav class="steps" aria-label="行程生成步骤">
          <div v-for="item in stepItems" :key="item.number" class="step-group">
            <div class="step" :class="{ active: currentStep === item.number, done: currentStep > item.number }">
              <span class="step-number">{{ currentStep > item.number ? '✓' : item.number }}</span>
              <span>{{ item.label }}</span>
            </div>
            <span v-if="item.number < 3" class="step-line" :class="{ done: currentStep > item.number }"></span>
          </div>
        </nav>

        <LongTermMemoryPanel
          compact
          :records="longTermMemories"
          :loading="memoryLoading"
          :archiving="memoryArchiving"
          :can-archive="hasUserMessages"
          :disabled-ids="temporarilyDisabledMemoryIds"
          @archive="archiveCurrentConversation"
          @approve="approveLongTermMemory"
          @save="saveLongTermMemory"
          @forget="forgetLongTermMemoryItem"
          @toggle="toggleMemoryForCurrentTrip"
        />
      </aside>

      <section class="chat-workspace">
        <header class="workspace-topbar">
          <div class="workspace-title">
            <p class="eyebrow">AI TRAVEL PLANNER</p>
            <h1>{{ currentStep === 1 ? '先对话，再开跑。' : currentStep === 2 ? `${formData.city}旅行灵感榜` : '正在生成你的行程' }}</h1>
            <span>{{ currentStep === 1 ? '告诉我目的地、时间与偏好，我会边聊边整理。' : currentStep === 2 ? '从实时推荐中选择你真正想去的地方。' : loadingStatus }}</span>
          </div>

        </header>

      <a-card class="planner-card" :bordered="false">
        <a-form :model="formData" layout="vertical">
          <section v-show="currentStep === 1" class="chat-intake-step">
            <div class="section-heading chat-heading">
              <div>
                <p class="section-kicker">CONVERSATION FIRST</p>
                <h2>先聊清楚，再开始规划。</h2>
                <p>像聊天一样告诉旅行顾问目的地、日期和偏好；信息确认前不会启动正式规划。</p>
              </div>
              <button v-if="hasUserMessages" type="button" class="reset-chat-button" @click="resetConversation">重新开始</button>
            </div>

            <div class="intake-layout">
              <section class="chat-panel" aria-label="旅行需求对话">
                <div ref="chatFeedRef" class="chat-feed" aria-live="polite">
                  <article
                    v-for="messageItem in chatMessages"
                    :key="messageItem.id"
                    :class="['chat-message', messageItem.role]"
                  >
                    <div class="chat-avatar">{{ messageItem.role === 'assistant' ? '✦' : '你' }}</div>
                    <div class="chat-bubble">
                      <span>{{ messageItem.role === 'assistant' ? 'TripMind 顾问' : '你' }}</span>
                      <p>{{ messageItem.content }}</p>
                    </div>
                  </article>
                  <article v-if="intakeLoading" class="chat-message assistant">
                    <div class="chat-avatar">✦</div>
                    <div class="chat-bubble thinking-bubble"><i></i><i></i><i></i></div>
                  </article>
                </div>

                <div v-if="!hasUserMessages" class="prompt-suggestions">
                  <button v-for="prompt in starterPrompts" :key="prompt" type="button" @click="useStarterPrompt(prompt)">
                    {{ prompt }}
                  </button>
                </div>

                <div class="chat-composer">
                  <textarea
                    v-model="chatDraft"
                    rows="2"
                    maxlength="2000"
                    placeholder="例如：9月20日到23日去杭州，喜欢历史文化和美食，住舒适型酒店"
                    aria-label="告诉旅行顾问你的需求"
                    @keydown.enter.exact.prevent="sendChatMessage"
                  ></textarea>
                  <div class="composer-footer">
                    <span>Enter 发送 · Shift + Enter 换行</span>
                    <button type="button" :disabled="!chatDraft.trim() || intakeLoading" @click="sendChatMessage">
                      {{ intakeLoading ? '理解中…' : '发送' }} <b>↑</b>
                    </button>
                  </div>
                </div>
              </section>

              <aside class="planning-brief" aria-labelledby="planning-brief-title">
                <div class="brief-heading">
                  <div>
                    <p>PLANNING BRIEF</p>
                    <h3 id="planning-brief-title">出发前确认</h3>
                  </div>
                  <span :class="['brief-status', { ready: intakeReady, conflict: hasDurationConflict }]">
                    {{ hasDurationConflict ? '天数冲突' : intakeReady ? '信息已齐' : `${missingFieldLabels.length} 项待补充` }}
                  </span>
                </div>

                <dl class="brief-fields">
                  <div :class="{ missing: !planningBrief.city }">
                    <dt>目的地</dt><dd>{{ planningBrief.city || '等待你告诉我' }}</dd>
                  </div>
                  <div :class="{ missing: !planningBrief.start_date || !planningBrief.end_date, conflict: hasDurationConflict }">
                    <dt>旅行日期</dt>
                    <dd>{{ planningDateLabel }}</dd>
                    <small v-if="hasDurationConflict" class="duration-conflict-copy">
                      原计划 {{ planningBrief.requested_days }} 天 · 日期跨度 {{ planningBrief.travel_days }} 天
                    </small>
                    <small v-else-if="planningBrief.travel_days">共 {{ planningBrief.travel_days }} 天</small>
                    <small v-else-if="planningBrief.requested_days">计划 {{ planningBrief.requested_days }} 天，等待具体日期</small>
                  </div>
                  <div><dt>交通方式</dt><dd>{{ planningBrief.transportation }}</dd></div>
                  <div><dt>住宿偏好</dt><dd>{{ planningBrief.accommodation }}</dd></div>
                  <div class="brief-wide">
                    <dt>兴趣偏好</dt>
                    <dd v-if="planningBrief.preferences.length" class="brief-tags">
                      <span v-for="preference in planningBrief.preferences" :key="preference">{{ preference }}</span>
                    </dd>
                    <dd v-else>暂未指定，由 Agent 综合推荐</dd>
                  </div>
                </dl>

                <section class="memory-projection">
                  <div class="memory-projection-title"><span>⌁</span><strong>本次画像应用</strong></div>
                  <p v-if="projectedVisitedPlaces.length">在 {{ planningBrief.city }} 已去过 {{ projectedVisitedPlaces.length }} 处，本次会优先避开。</p>
                  <p v-else-if="planningBrief.city">没有找到你在 {{ planningBrief.city }} 的已到访记录。</p>
                  <p v-else>确认目的地后，会自动匹配与该城市相关的旅行习惯。</p>
                  <div v-if="projectedVisitedPlaces.length" class="projection-tags visited">
                    <span v-for="place in projectedVisitedPlaces.slice(0, 5)" :key="place">{{ place }}</span>
                  </div>
                  <template v-if="projectedCarryoverPlaces.length">
                    <p>上次未去地点将优先加入候选：</p>
                    <div class="projection-tags"><span v-for="place in projectedCarryoverPlaces" :key="place">{{ place }}</span></div>
                  </template>
                  <template v-if="projectedLongTermPreferences.length">
                    <p>本次启用的长期偏好：</p>
                    <div class="projection-tags">
                      <span v-for="item in projectedLongTermPreferences" :key="item.id" :title="item.evidence">{{ item.content }}</span>
                    </div>
                  </template>
                  <template v-if="projectedLongTermAvoidances.length">
                    <p>本次启用的避雷项：</p>
                    <div class="projection-tags avoidance">
                      <span v-for="item in projectedLongTermAvoidances" :key="item.id" :title="item.evidence">{{ item.content }}</span>
                    </div>
                  </template>
                </section>

                <div v-if="hasDurationConflict" class="duration-conflict-alert">
                  <strong>旅行天数需要确认</strong>
                  <span>请在对话中回复“按 {{ planningBrief.travel_days }} 天”，或重新提供 {{ planningBrief.requested_days }} 天的起止日期。</span>
                </div>
                <div v-if="missingFieldLabels.length" class="missing-fields">
                  还需要：{{ missingFieldLabels.join('、') }}
                </div>
                <button
                  type="button"
                  class="confirm-brief-button"
                  :disabled="!intakeReady || intakeLoading || recommendationLoading"
                  @click="confirmPlanningBrief"
                >
                  {{ recommendationLoading ? '正在准备推荐…' : '确认 Brief，查看推荐' }}
                  <span>→</span>
                </button>
                <p class="confirmation-note">点击即代表你确认以上信息；在此之前不会调用正式规划 Agent。</p>
              </aside>
            </div>
          </section>

          <section v-show="currentStep === 2" class="ranking-step">
            <div class="section-heading ranking-heading">
              <div>
                <p class="section-kicker">TAVILY 实时推荐</p>
                <h2>{{ formData.city }}旅行灵感榜</h2>
                <p>来自公开攻略的聚合结果。推荐指数反映来源数量和排序，不是第三方平台评分。</p>
              </div>
              <button type="button" class="refresh-button" :disabled="recommendationLoading" @click="loadRecommendations">
                {{ recommendationLoading ? '搜索中…' : '↻ 重新搜索' }}
              </button>
            </div>

            <div v-if="recommendations.length" class="ranking-toolbar">
              <div class="ranking-filters">
                <div class="memory-filter" aria-label="到访状态筛选">
                  <button type="button" :class="{ active: activeMemoryFilter === 'unvisited' }" @click="activeMemoryFilter = 'unvisited'">未去过</button>
                  <button type="button" :class="{ active: activeMemoryFilter === 'visited' }" @click="activeMemoryFilter = 'visited'">已去过</button>
                  <button type="button" :class="{ active: activeMemoryFilter === 'all' }" @click="activeMemoryFilter = 'all'">全部</button>
                </div>
                <div class="filter-chips">
                  <button v-for="category in categories" :key="category" type="button" :class="{ active: activeCategory === category }" @click="activeCategory = category">
                    {{ category }}
                  </button>
                </div>
              </div>
              <span class="selection-count">共 {{ recommendations.length }} 条 · 已选 {{ selectedRecommendationIds.length }} 项</span>
            </div>

            <a-spin :spinning="recommendationLoading" tip="正在检索近期公开攻略…">
              <div v-if="filteredRecommendations.length" class="recommendation-grid">
                <article
                  v-for="(item, index) in displayedRecommendations"
                  :key="item.id"
                  class="recommendation-card"
                  :class="{ selected: isSelected(item.id), visited: isVisited(item.name, formData.city) }"
                  tabindex="0"
                  role="checkbox"
                  :aria-checked="isSelected(item.id)"
                  :aria-disabled="isVisited(item.name, formData.city)"
                  @click="handleRecommendationClick(item)"
                  @keydown.enter.prevent="handleRecommendationClick(item)"
                  @keydown.space.prevent="handleRecommendationClick(item)"
                >
                  <div class="card-topline">
                    <span class="rank">{{ String(index + 1).padStart(2, '0') }}</span>
                    <span class="category">{{ item.category }}</span>
                    <button
                      type="button"
                      class="visited-toggle"
                      :class="{ active: isVisited(item.name, formData.city) }"
                      :aria-label="isVisited(item.name, formData.city) ? `将${item.name}标记为未去过` : `将${item.name}标记为已去过`"
                      @click.stop="toggleRecommendationVisited(item)"
                    >
                      {{ isVisited(item.name, formData.city) ? '已去过' : '标记去过' }}
                    </button>
                    <span v-if="!isVisited(item.name, formData.city)" class="selection-dot">{{ isSelected(item.id) ? '✓' : '+' }}</span>
                  </div>
                  <h3>{{ item.name }}</h3>
                  <p class="reason">{{ item.reason }}</p>
                  <div class="score-row">
                    <div><strong>{{ item.score }}</strong><span> 推荐指数</span></div>
                    <span>{{ item.evidence_count }} 个来源提及</span>
                  </div>
                  <div class="score-track"><span :style="{ width: `${item.score}%` }"></span></div>
                  <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer" class="source-link" @click.stop>
                    来源：{{ item.source_title }} <span>↗</span>
                  </a>
                  <span v-else class="source-link memory-source">{{ item.source_title }}</span>
                </article>
              </div>

              <div v-if="displayedRecommendations.length < filteredRecommendations.length" class="load-more-row">
                <button type="button" class="load-more-button" @click="showMoreRecommendations">
                  显示更多推荐
                  <span>还有 {{ filteredRecommendations.length - displayedRecommendations.length }} 条</span>
                </button>
              </div>

              <div v-else-if="!recommendationLoading" class="empty-state">
                <div class="empty-icon">⌕</div>
                <h3>暂时没有可用推荐</h3>
                <p>{{ recommendationError || '换一个偏好重新搜索，或直接生成行程。' }}</p>
              </div>
            </a-spin>

            <div class="ranking-actions">
              <button type="button" class="secondary-button" @click="currentStep = 1">← 返回修改</button>
              <a-button v-if="recommendations.length" type="primary" size="large" class="primary-button compact" :disabled="!selectedRecommendationIds.length" @click="handleSubmit">
                用已选 {{ selectedRecommendationIds.length }} 项生成行程 <span>→</span>
              </a-button>
              <button v-else type="button" class="text-button" @click="generateWithoutRecommendations">直接生成行程</button>
            </div>
          </section>

          <section v-if="currentStep === 3" class="generating-step">
            <div class="loading-orb"><span></span></div>
            <p class="section-kicker">多智能体协作中</p>
            <h2>正在把选择变成一份好行程</h2>
            <p>{{ loadingStatus }}</p>
            <a-progress :percent="loadingProgress" :show-info="false" :stroke-width="8" stroke-color="#0071e3" />
            <div class="job-progress-list" aria-live="polite">
              <div v-for="step in jobSteps" :key="step.key" class="job-progress-item" :class="step.state">
                <span class="job-step-icon">{{ step.state === 'completed' ? '✓' : step.state === 'active' ? '→' : '○' }}</span>
                <span>{{ step.label }}</span>
              </div>
            </div>
            <p v-if="jobError" class="job-error">{{ jobError }}</p>
            <div class="job-actions">
              <button v-if="jobCanCancel" type="button" class="secondary-button" @click="cancelActiveJob">取消任务</button>
              <button v-if="jobCanResume" type="button" class="secondary-button" @click="resumeActiveJob">从断点继续</button>
              <a-button v-if="jobCanRetry" type="primary" class="primary-button compact" @click="retryActiveJob">重新开始</a-button>
            </div>
          </section>
        </a-form>
      </a-card>

      <p class="privacy-note">Tavily 只用于检索公开网页；API Key 保存在后端，不会发送到浏览器。</p>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import {
  cancelTripJob,
  createTripJob,
  discoverRecommendations,
  extractLongTermMemories,
  forgetLongTermMemory,
  getTripJob,
  listLongTermMemories,
  refinePlanningBrief,
  resumeTripJob,
  retryTripJob,
  subscribeTripJob,
  updateLongTermMemory
} from '@/services/api'
import LongTermMemoryPanel from '@/components/LongTermMemoryPanel.vue'
import { normalizePlaceName, useTravelMemory } from '@/services/travelMemory'
import type { SavedTripPlan } from '@/services/tripPlanMemory'
import type { IntakeChatMessage, LongTermMemoryRecord, PlanningBrief, RecommendationItem, TripFormData, TripJobEvent, TripJobResponse, TripPlan } from '@/types'

type TripFormState = Omit<TripFormData, 'start_date' | 'end_date'> & {
  start_date: Dayjs | null
  end_date: Dayjs | null
}

const router = useRouter()
const currentStep = ref(1)
const loading = ref(false)
const recommendationLoading = ref(false)
const recommendationError = ref('')
const loadingProgress = ref(0)
const loadingStatus = ref('正在准备旅行信息…')
const activeJobId = ref('')
const jobCanCancel = ref(false)
const jobCanRetry = ref(false)
const jobCanResume = ref(false)
const jobError = ref('')
type JobStepState = 'pending' | 'active' | 'completed'
type JobStep = { key: string; label: string; state: JobStepState }
const createJobSteps = (): JobStep[] => [
  { key: 'brief', label: '已理解旅行需求', state: 'pending' },
  { key: 'attractions', label: '搜索景点', state: 'pending' },
  { key: 'weather', label: '获取天气', state: 'pending' },
  { key: 'hotel', label: '匹配酒店', state: 'pending' },
  { key: 'validation', label: '校验地点数据', state: 'pending' },
  { key: 'route', label: '生成每日路线与预算', state: 'pending' }
]
const jobSteps = ref<JobStep[]>(createJobSteps())
let stopJobSubscription: (() => void) | null = null
let finishingJob = false
const recommendations = ref<RecommendationItem[]>([])
const selectedRecommendationIds = ref<string[]>([])
const activeCategory = ref('全部')
const activeMemoryFilter = ref<'unvisited' | 'visited' | 'all'>('unvisited')
const visibleRecommendationCount = ref(9)
const { visitedEntries, isVisited, toggleVisited } = useTravelMemory()
const carryoverPlaces = ref<RecommendationItem[]>([])
const carryoverCity = ref('')
const chatDraft = ref('')
const intakeLoading = ref(false)
const intakeReady = ref(false)
const missingFields = ref<string[]>(['city', 'start_date', 'end_date'])
const chatFeedRef = ref<HTMLElement | null>(null)
const longTermMemories = ref<LongTermMemoryRecord[]>([])
const memoryLoading = ref(false)
const memoryArchiving = ref(false)
const temporarilyDisabledMemoryIds = ref<string[]>([])
const archivedConversationId = ref('')
const lastProfileSyncedMessageId = ref(0)
let profileSyncQueued = false
let profileConversationVersion = 0

type UIChatMessage = IntakeChatMessage & { id: number }
let chatMessageId = 1

const createInitialBrief = (): PlanningBrief => ({
  city: null,
  start_date: null,
  end_date: null,
  requested_days: null,
  travel_days: null,
  transportation: '公共交通',
  accommodation: '舒适型酒店',
  preferences: [],
  free_text_input: '',
  memory_projection: {
    visited_places: [],
    carryover_places: [],
    applied_preferences: [],
    applied_avoidances: []
  }
})

const planningBrief = reactive<PlanningBrief>(createInitialBrief())
const chatMessages = ref<UIChatMessage[]>([{
  id: chatMessageId++,
  role: 'assistant',
  content: '你好，我是你的旅行需求顾问。先告诉我想去哪里、什么时候出发；偏好、交通和住宿也可以一起说。'
}])

const starterPrompts = [
  '9月20日到23日去杭州，喜欢历史文化和美食',
  '下个月想去成都玩4天，预算适中',
  '带父母去北京，想慢节奏游览经典景点'
]

const stepItems = [
  { number: 1, label: '对话澄清' },
  { number: 2, label: '选择推荐' },
  { number: 3, label: '生成行程' }
]

const formData = reactive<TripFormState>({
  city: '',
  start_date: null,
  end_date: null,
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '舒适型酒店',
  preferences: [],
  free_text_input: '',
  selected_recommendations: []
})

const categories = computed(() => ['全部', ...Array.from(new Set(recommendations.value.map(item => item.category)))])
const hasUserMessages = computed(() => chatMessages.value.some(item => item.role === 'user'))
const fieldLabelMap: Record<string, string> = {
  city: '目的地', start_date: '出发日期', end_date: '返程日期', duration_conflict: '旅行天数冲突'
}
const missingFieldLabels = computed(() => missingFields.value.map(field => fieldLabelMap[field] || field))
const hasDurationConflict = computed(() => Boolean(
  planningBrief.requested_days
  && planningBrief.travel_days
  && planningBrief.requested_days !== planningBrief.travel_days
))
const planningDateLabel = computed(() => {
  if (planningBrief.start_date && planningBrief.end_date) {
    return `${planningBrief.start_date} — ${planningBrief.end_date}`
  }
  if (planningBrief.start_date) return `${planningBrief.start_date} — 等待返程日期`
  return '等待你告诉我'
})
const projectedVisitedPlaces = computed(() => planningBrief.memory_projection.visited_places || [])
const projectedCarryoverPlaces = computed(() => planningBrief.memory_projection.carryover_places || [])
const projectedLongTermPreferences = computed(() => planningBrief.memory_projection.applied_preferences || [])
const projectedLongTermAvoidances = computed(() => planningBrief.memory_projection.applied_avoidances || [])
const activeApprovedMemories = computed(() => longTermMemories.value.filter(item => (
  item.status === 'approved' && !temporarilyDisabledMemoryIds.value.includes(item.id)
)))
const applicableActiveMemories = computed(() => {
  const city = (planningBrief.city || formData.city || '').trim().toLocaleLowerCase()
  return activeApprovedMemories.value.filter(item => (
    !item.scope_city.trim() || !city || item.scope_city.trim().toLocaleLowerCase() === city
  ))
})
const filteredRecommendations = computed(() => recommendations.value.filter(item => {
  const categoryMatches = activeCategory.value === '全部' || item.category === activeCategory.value
  const visited = isVisited(item.name, formData.city)
  const memoryMatches = activeMemoryFilter.value === 'all'
    || (activeMemoryFilter.value === 'visited' ? visited : !visited)
  return categoryMatches && memoryMatches
}))
const displayedRecommendations = computed(() => filteredRecommendations.value.slice(0, visibleRecommendationCount.value))

watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (!start || !end) return
  const days = end.diff(start, 'day') + 1
  if (days > 30) {
    message.warning('一次最多规划 30 天')
    formData.end_date = null
  } else if (days <= 0) {
    message.warning('返程日期不能早于出发日期')
    formData.end_date = null
  } else {
    formData.travel_days = days
  }
})

watch(activeCategory, () => {
  visibleRecommendationCount.value = 9
})

watch(activeMemoryFilter, () => {
  visibleRecommendationCount.value = 9
})

watch(() => formData.city, city => {
  if (carryoverCity.value && city.trim() !== carryoverCity.value) {
    carryoverPlaces.value = []
    carryoverCity.value = ''
  }
})

function showMoreRecommendations() {
  visibleRecommendationCount.value += 9
}

const scrollChatToBottom = async () => {
  await nextTick()
  if (chatFeedRef.value) chatFeedRef.value.scrollTop = chatFeedRef.value.scrollHeight
}

function syncFormFromBrief(brief: PlanningBrief) {
  formData.city = brief.city?.trim() || ''
  formData.start_date = brief.start_date ? dayjs(brief.start_date) : null
  formData.end_date = brief.end_date ? dayjs(brief.end_date) : null
  formData.travel_days = brief.travel_days || 1
  formData.transportation = brief.transportation || '公共交通'
  formData.accommodation = brief.accommodation || '舒适型酒店'
  formData.preferences = [...(brief.preferences || [])]
  formData.free_text_input = brief.free_text_input || ''
}

function useStarterPrompt(prompt: string) {
  chatDraft.value = prompt
  void sendChatMessage()
}

function friendlyIntakeError(error: any): string {
  const detail = String(error?.message || '').trim()
  const exposesParserInternals = /JSON|Expecting|delimiter|line \d+ column|char \d+|decode|解析/i.test(detail)
  if (!detail || exposesParserInternals) {
    return '我暂时没有正确整理这条信息，请换一种说法再试一次。你之前提供的信息仍然保留。'
  }
  return detail
}

async function sendChatMessage() {
  const content = chatDraft.value.trim()
  if (!content || intakeLoading.value) return
  chatMessages.value.push({ id: chatMessageId++, role: 'user', content })
  chatDraft.value = ''
  intakeLoading.value = true
  await scrollChatToBottom()

  try {
    const response = await refinePlanningBrief({
      messages: chatMessages.value.map(({ role, content: messageContent }) => ({ role, content: messageContent })),
      brief: JSON.parse(JSON.stringify(planningBrief)),
      travel_memory: visitedEntries.value.map(item => ({
        name: item.name, city: item.city, category: item.category
      })),
      carryover_places: carryoverPlaces.value.map(item => item.name),
      long_term_memory: activeApprovedMemories.value.map(item => ({
        id: item.id,
        kind: item.kind,
        content: item.content,
        scope_city: item.scope_city,
        source_conversation_id: item.source_conversation_id,
        evidence: item.evidence
      }))
    })
    Object.assign(planningBrief, response.brief)
    syncFormFromBrief(response.brief)
    missingFields.value = response.missing_fields
    intakeReady.value = response.ready_to_confirm
    chatMessages.value.push({
      id: chatMessageId++, role: 'assistant', content: response.assistant_message
    })
    void archiveCurrentConversation(true)
  } catch (error: any) {
    chatMessages.value.push({
      id: chatMessageId++,
      role: 'assistant',
      content: friendlyIntakeError(error)
    })
  } finally {
    intakeLoading.value = false
    await scrollChatToBottom()
  }
}

function resetConversation() {
  profileConversationVersion += 1
  profileSyncQueued = false
  lastProfileSyncedMessageId.value = 0
  Object.assign(planningBrief, createInitialBrief())
  syncFormFromBrief(planningBrief)
  missingFields.value = ['city', 'start_date', 'end_date']
  intakeReady.value = false
  temporarilyDisabledMemoryIds.value = []
  archivedConversationId.value = ''
  chatDraft.value = ''
  chatMessages.value = [{
    id: chatMessageId++, role: 'assistant',
    content: '我们重新开始。请告诉我想去哪里，以及计划什么时候出发和返程。'
  }]
}

async function loadLongTermMemoryRecords() {
  memoryLoading.value = true
  try {
    longTermMemories.value = await listLongTermMemories()
  } catch (error: any) {
    message.error(error.message || '长期旅行记忆加载失败')
  } finally {
    memoryLoading.value = false
  }
}

async function archiveCurrentConversation(automatic = false) {
  if (!hasUserMessages.value) return
  if (memoryArchiving.value) {
    if (automatic) profileSyncQueued = true
    return
  }

  const sourceMessages = automatic
    ? chatMessages.value.filter(item => item.id > lastProfileSyncedMessageId.value)
    : chatMessages.value
  if (!sourceMessages.some(item => item.role === 'user')) return

  const snapshotLastMessageId = Math.max(...sourceMessages.map(item => item.id))
  const snapshotConversationId = archivedConversationId.value
  const snapshotVersion = profileConversationVersion
  memoryArchiving.value = true
  try {
    const knownMemoryIds = new Set(longTermMemories.value.map(item => item.id))
    const response = await extractLongTermMemories({
      user_id: 'local-user',
      conversation_id: snapshotConversationId,
      city: planningBrief.city || '',
      messages: sourceMessages.map(item => ({
        id: String(item.id),
        role: item.role,
        content: item.content
      }))
    })
    if (snapshotVersion === profileConversationVersion) {
      archivedConversationId.value = response.conversation_id
      lastProfileSyncedMessageId.value = Math.max(
        lastProfileSyncedMessageId.value,
        snapshotLastMessageId
      )
    }
    await loadLongTermMemoryRecords()
    const newMemories = response.memories.filter(item => !knownMemoryIds.has(item.id))
    if (newMemories.length) {
      message.success(`自动发现 ${newMemories.length} 条旅行习惯，请在左侧确认`)
    } else if (!automatic) {
      message.info('个人画像已是最新，本次对话没有发现新的长期习惯')
    }
  } catch (error: any) {
    if (!automatic) message.error(error.message || '个人画像更新失败')
  } finally {
    memoryArchiving.value = false
    if (profileSyncQueued) {
      profileSyncQueued = false
      void archiveCurrentConversation(true)
    }
  }
}

function replaceLongTermMemory(updated: LongTermMemoryRecord) {
  longTermMemories.value = longTermMemories.value.map(item => item.id === updated.id ? updated : item)
}

async function approveLongTermMemory(item: LongTermMemoryRecord, draft: { content: string; scope_city: string }) {
  try {
    const updated = await updateLongTermMemory(item.id, {
      content: draft.content.trim(),
      scope_city: draft.scope_city.trim(),
      status: 'approved'
    })
    replaceLongTermMemory(updated)
    message.success('已加入个人画像，后续旅行将默认使用')
  } catch (error: any) {
    message.error(error.message || '批准记忆失败')
  }
}

async function saveLongTermMemory(item: LongTermMemoryRecord, draft: { content: string; scope_city: string }) {
  try {
    const updated = await updateLongTermMemory(item.id, {
      content: draft.content.trim(),
      scope_city: draft.scope_city.trim()
    })
    replaceLongTermMemory(updated)
    message.success('个人画像已更新')
  } catch (error: any) {
    message.error(error.message || '保存记忆失败')
  }
}

async function forgetLongTermMemoryItem(item: LongTermMemoryRecord) {
  if (!window.confirm(`确定忘记“${item.content}”吗？此操作会从个人画像中永久删除。`)) return
  try {
    await forgetLongTermMemory(item.id)
    longTermMemories.value = longTermMemories.value.filter(memory => memory.id !== item.id)
    temporarilyDisabledMemoryIds.value = temporarilyDisabledMemoryIds.value.filter(id => id !== item.id)
    message.success('已从个人画像中忘记这条记录')
  } catch (error: any) {
    message.error(error.message || '忘记记忆失败')
  }
}

function toggleMemoryForCurrentTrip(id: string) {
  if (temporarilyDisabledMemoryIds.value.includes(id)) {
    temporarilyDisabledMemoryIds.value = temporarilyDisabledMemoryIds.value.filter(item => item !== id)
    message.info('本次旅行将使用这条记忆')
  } else {
    temporarilyDisabledMemoryIds.value = [...temporarilyDisabledMemoryIds.value, id]
    message.info('本次旅行已临时忽略这条记忆，长期记录不会被删除')
  }
}

async function confirmPlanningBrief() {
  if (!intakeReady.value) {
    message.warning(`请先补充：${missingFieldLabels.value.join('、')}`)
    return
  }
  await loadRecommendations()
}

function toggleRecommendation(id: string) {
  const index = selectedRecommendationIds.value.indexOf(id)
  if (index >= 0) selectedRecommendationIds.value.splice(index, 1)
  else selectedRecommendationIds.value.push(id)
}

function handleRecommendationClick(item: RecommendationItem) {
  if (isVisited(item.name, formData.city)) {
    message.info('这个地点已在旅行记忆中；取消“已去过”后可以重新加入行程。')
    return
  }
  toggleRecommendation(item.id)
}

function toggleRecommendationVisited(item: RecommendationItem) {
  const visited = toggleVisited({ name: item.name, city: formData.city, category: item.category })
  if (visited) {
    selectedRecommendationIds.value = selectedRecommendationIds.value.filter(id => id !== item.id)
    message.success(`已记住：去过 ${item.name}`)
  } else {
    message.info(`${item.name} 已恢复为未去过，可加入后续行程`)
  }
}

function isSelected(id: string) {
  return selectedRecommendationIds.value.includes(id)
}

function getSavedTripAttractions(savedTrip: SavedTripPlan) {
  const unique = new Map<string, { name: string; category: string; description: string }>()
  savedTrip.plan.days.forEach(day => {
    day.attractions.forEach(attraction => {
      const key = normalizePlaceName(attraction.name)
      if (!unique.has(key)) {
        unique.set(key, {
          name: attraction.name,
          category: attraction.category || '景点',
          description: attraction.description
        })
      }
    })
  })
  return [...unique.values()]
}

function continueUnvisitedPlaces(savedTrip: SavedTripPlan) {
  const remaining = getSavedTripAttractions(savedTrip)
    .filter(item => !isVisited(item.name, savedTrip.plan.city))
    .map((item, index): RecommendationItem => ({
      id: `carry-${normalizePlaceName(savedTrip.plan.city)}-${normalizePlaceName(item.name)}-${index}`,
      name: item.name,
      category: item.category,
      reason: item.description || '来自上一次尚未完成的旅行规划',
      source_url: '',
      source_title: '来自上一次未完成的行程',
      score: 100,
      evidence_count: 1
    }))

  if (!remaining.length) {
    message.success('这份旅行规划中的地点已经全部去过了')
    return
  }

  carryoverCity.value = savedTrip.plan.city
  carryoverPlaces.value = remaining
  formData.city = savedTrip.plan.city
  formData.start_date = null
  formData.end_date = null
  formData.travel_days = Math.max(1, Math.ceil(remaining.length / 3))
  formData.transportation = savedTrip.plan.days[0]?.transportation || '公共交通'
  formData.accommodation = savedTrip.plan.days[0]?.accommodation || '舒适型酒店'
  formData.free_text_input = `优先继续安排上次没有去成的地点：${remaining.map(item => item.name).join('、')}`
  Object.assign(planningBrief, {
    ...createInitialBrief(),
    city: savedTrip.plan.city,
    travel_days: formData.travel_days,
    transportation: formData.transportation,
    accommodation: formData.accommodation,
    free_text_input: formData.free_text_input,
    memory_projection: {
      visited_places: visitedEntries.value
        .filter(item => item.city === savedTrip.plan.city)
        .map(item => item.name),
      carryover_places: remaining.map(item => item.name)
    }
  })
  missingFields.value = ['start_date', 'end_date']
  intakeReady.value = false
  chatMessages.value = [{
    id: chatMessageId++, role: 'assistant',
    content: `已带入 ${remaining.length} 个上次未去地点。请告诉我这次的出发和返程日期。`
  }]
  recommendations.value = []
  selectedRecommendationIds.value = []
  currentStep.value = 1
  document.querySelector('.planner-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  message.success(`已带入 ${remaining.length} 个未去地点，请选择新的旅行日期`)
}

async function validateBasics() {
  if (!intakeReady.value || !formData.city || !formData.start_date || !formData.end_date) {
    message.warning(`请先通过对话补充并确认：${missingFieldLabels.value.join('、') || '旅行信息'}`)
    currentStep.value = 1
    return false
  }
  return true
}

async function loadRecommendations() {
  try {
    if (!(await validateBasics())) return
    recommendationLoading.value = true
    recommendationError.value = ''
    currentStep.value = 2
    activeCategory.value = '全部'
    activeMemoryFilter.value = 'unvisited'
    visibleRecommendationCount.value = 9
    const rememberedPreferences = applicableActiveMemories.value
      .filter(item => item.kind === 'preference')
      .map(item => item.content)
    const response = await discoverRecommendations({
      city: formData.city.trim(),
      preferences: [...new Set([...formData.preferences, ...rememberedPreferences])],
      limit: 18
    })
    const carryover = carryoverPlaces.value.filter(item => !isVisited(item.name, formData.city))
    const carryoverNames = new Set(carryover.map(item => normalizePlaceName(item.name)))
    recommendations.value = [
      ...carryover,
      ...response.data.filter(item => !carryoverNames.has(normalizePlaceName(item.name)))
    ]
    const carryoverIds = carryover.map(item => item.id)
    const additionalIds = recommendations.value
      .filter(item => !isVisited(item.name, formData.city))
      .filter(item => !carryoverIds.includes(item.id))
      .slice(0, Math.max(0, 4 - carryoverIds.length))
      .map(item => item.id)
    selectedRecommendationIds.value = [...carryoverIds, ...additionalIds]
    if (!recommendations.value.length) recommendationError.value = '没有从本次搜索中提取到具体地点。'
  } catch (error: any) {
    recommendationError.value = error.message || '实时推荐加载失败'
    const carryover = carryoverPlaces.value.filter(item => !isVisited(item.name, formData.city))
    recommendations.value = carryover
    selectedRecommendationIds.value = carryover.map(item => item.id)
    if (carryover.length) {
      message.warning('实时推荐暂时不可用，已保留上次未去的地点，可以继续生成行程')
    } else {
      message.error(recommendationError.value)
    }
  } finally {
    recommendationLoading.value = false
  }
}

async function generateWithoutRecommendations() {
  try {
    if (!(await validateBasics())) return
    const carryover = carryoverPlaces.value.filter(item => !isVisited(item.name, formData.city))
    recommendations.value = carryover
    selectedRecommendationIds.value = carryover.map(item => item.id)
    await handleSubmit()
  } catch {
    // 表单组件已显示具体校验提示。
  }
}

function resetJobProgress() {
  jobSteps.value = createJobSteps()
  loadingProgress.value = 2
  loadingStatus.value = '任务已提交，等待后台执行…'
  jobError.value = ''
  jobCanCancel.value = true
  jobCanRetry.value = false
  jobCanResume.value = false
  finishingJob = false
}

function setJobStep(key: string, state: JobStepState) {
  const step = jobSteps.value.find(item => item.key === key)
  if (step) step.state = state
}

function applyJobProgress(event: TripJobEvent) {
  loadingProgress.value = Math.max(loadingProgress.value, event.progress || 0)
  loadingStatus.value = event.message || loadingStatus.value
  jobCanCancel.value = ['queued', 'running'].includes(event.status)

  const node = event.node || event.current_step
  if (['approval', 'prepare'].includes(node)) {
    setJobStep('brief', node === 'prepare' ? 'completed' : 'active')
    if (node === 'prepare') {
      setJobStep('attractions', 'active')
      setJobStep('weather', 'active')
      setJobStep('hotel', 'active')
    }
  }
  if (['attractions', 'retry_attractions'].includes(node)) setJobStep('attractions', 'completed')
  if (node === 'weather') setJobStep('weather', 'completed')
  if (node === 'hotel') setJobStep('hotel', 'completed')
  if (node === 'validate_research') {
    setJobStep('attractions', 'completed')
    setJobStep('weather', 'completed')
    setJobStep('hotel', 'completed')
    setJobStep('validation', 'completed')
    setJobStep('route', 'active')
  }
  if (node === 'plan') setJobStep('route', 'active')
  if (['validate_plan', 'fallback_plan', 'completed'].includes(node)) setJobStep('route', 'completed')
}

function finishTripJob(plan: TripPlan | null | undefined) {
  if (finishingJob || !plan) return
  finishingJob = true
  stopJobSubscription?.()
  stopJobSubscription = null
  localStorage.removeItem('tripmindActiveJobId')
  jobCanCancel.value = false
  loading.value = false
  loadingProgress.value = 100
  loadingStatus.value = '行程已完成'
  jobSteps.value.forEach(step => { step.state = 'completed' })
  sessionStorage.setItem('tripPlan', JSON.stringify(plan))
  message.success('旅行计划生成成功')
  window.setTimeout(() => router.push('/result'), 300)
}

function handleJobEvent(event: TripJobEvent) {
  applyJobProgress(event)
  if (['queued', 'started', 'resumed', 'progress', 'cancelling'].includes(event.type)) {
    jobCanRetry.value = false
    jobCanResume.value = false
    jobError.value = ''
    loading.value = true
  }
  if (event.type === 'completed') {
    finishTripJob(event.data)
    return
  }
  if (event.type === 'failed') {
    loading.value = false
    jobCanCancel.value = false
    jobCanRetry.value = true
    jobCanResume.value = true
    jobError.value = event.error || '任务执行失败，可以从断点继续或重新开始。'
  } else if (event.type === 'cancelled') {
    loading.value = false
    jobCanCancel.value = false
    jobCanRetry.value = true
    jobCanResume.value = true
    jobError.value = '任务已取消，已完成进度仍保存在检查点中。'
  } else if (event.type === 'interrupted') {
    loading.value = false
    jobCanCancel.value = false
    jobCanRetry.value = true
    jobCanResume.value = true
    jobError.value = event.message
  }
}

function connectToTripJob(job: TripJobResponse) {
  stopJobSubscription?.()
  activeJobId.value = job.job_id
  localStorage.setItem('tripmindActiveJobId', job.job_id)
  loadingProgress.value = Math.max(loadingProgress.value, job.progress)
  loadingStatus.value = job.message
  jobCanCancel.value = job.can_cancel
  jobCanRetry.value = job.can_retry
  jobCanResume.value = job.can_resume
  if (job.status === 'completed') {
    finishTripJob(job.data)
    return
  }
  loading.value = ['queued', 'running', 'cancelling'].includes(job.status)
  stopJobSubscription = subscribeTripJob(job.job_id, handleJobEvent, async () => {
    try {
      const latest = await getTripJob(job.job_id)
      if (latest.status === 'completed') finishTripJob(latest.data)
      else if (['failed', 'cancelled', 'interrupted'].includes(latest.status)) {
        handleJobEvent({
          job_id: latest.job_id,
          type: latest.status as TripJobEvent['type'],
          status: latest.status,
          progress: latest.progress,
          current_step: latest.current_step,
          message: latest.message,
          error: latest.error
        })
      } else {
        loadingStatus.value = '实时连接暂时中断，浏览器正在自动重连…'
      }
    } catch {
      loadingStatus.value = '暂时无法读取任务状态，可稍后点击继续。'
    }
  })
}

async function cancelActiveJob() {
  if (!activeJobId.value || !jobCanCancel.value) return
  try {
    const job = await cancelTripJob(activeJobId.value)
    loadingStatus.value = job.message
    jobCanCancel.value = job.can_cancel
  } catch (error: any) {
    message.error(error.response?.data?.detail || error.message || '取消任务失败')
  }
}

async function retryActiveJob() {
  if (!activeJobId.value) return
  try {
    resetJobProgress()
    loading.value = true
    const job = await retryTripJob(activeJobId.value)
    connectToTripJob(job)
  } catch (error: any) {
    loading.value = false
    message.error(error.response?.data?.detail || error.message || '重新开始失败')
  }
}

async function resumeActiveJob() {
  if (!activeJobId.value) return
  try {
    resetJobProgress()
    loading.value = true
    const job = await resumeTripJob(activeJobId.value)
    connectToTripJob(job)
  } catch (error: any) {
    loading.value = false
    message.error(error.response?.data?.detail || error.message || '继续任务失败')
  }
}

async function handleSubmit() {
  if (!intakeReady.value || !formData.start_date || !formData.end_date || loading.value) {
    currentStep.value = 1
    message.warning('请先在对话中补齐信息，并明确确认 Planning Brief')
    return
  }
  loading.value = true
  currentStep.value = 3
  resetJobProgress()

  try {
    const selected = recommendations.value
      .filter(item => selectedRecommendationIds.value.includes(item.id))
      .map(item => ({ name: item.name, category: item.category, reason: item.reason, source_url: item.source_url }))
    const requestData: TripFormData = {
      city: formData.city.trim(),
      start_date: formData.start_date.format('YYYY-MM-DD'),
      end_date: formData.end_date.format('YYYY-MM-DD'),
      travel_days: formData.travel_days,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: formData.preferences,
      free_text_input: [
        formData.free_text_input,
        applicableActiveMemories.value.filter(item => item.kind === 'preference').length
          ? `已审批长期偏好：${applicableActiveMemories.value.filter(item => item.kind === 'preference').map(item => item.content).join('；')}`
          : '',
        applicableActiveMemories.value.filter(item => item.kind === 'avoidance').length
          ? `必须避开：${applicableActiveMemories.value.filter(item => item.kind === 'avoidance').map(item => item.content).join('；')}`
          : ''
      ].filter(Boolean).join('\n'),
      selected_recommendations: selected
    }
    const job = await createTripJob(requestData)
    connectToTripJob(job)
  } catch (error: any) {
    loading.value = false
    currentStep.value = recommendations.value.length ? 2 : 1
    message.error(error.message || '任务提交失败，请稍后重试')
  }
}

onMounted(() => {
  void loadLongTermMemoryRecords()
  const activeJob = localStorage.getItem('tripmindActiveJobId')
  if (activeJob) {
    currentStep.value = 3
    resetJobProgress()
    void getTripJob(activeJob)
      .then(connectToTripJob)
      .catch(() => localStorage.removeItem('tripmindActiveJobId'))
  }
  const pendingTrip = sessionStorage.getItem('tripmindContinueTrip')
  if (!pendingTrip) return
  sessionStorage.removeItem('tripmindContinueTrip')
  try {
    continueUnvisitedPlaces(JSON.parse(pendingTrip) as SavedTripPlan)
  } catch {
    message.error('未能读取需要继续规划的历史行程')
  }
})

onBeforeUnmount(() => {
  stopJobSubscription?.()
  stopJobSubscription = null
})
</script>

<style scoped>
.home-page { position: relative; min-height: 100vh; overflow: hidden; padding: 68px 22px 80px; background: #f5f5f7; color: #1d1d1f; }
.ambient { position: absolute; border-radius: 50%; filter: blur(8px); pointer-events: none; }
.ambient-left { width: 420px; height: 420px; left: -170px; top: 20px; background: rgba(90, 200, 250, .13); }
.ambient-right { width: 360px; height: 360px; right: -140px; top: 260px; background: rgba(175, 82, 222, .08); }
.hero { position: relative; z-index: 1; max-width: 860px; margin: 0 auto 34px; text-align: center; }
.hero-logo { width: 52px; height: 52px; border-radius: 16px; box-shadow: 0 14px 34px rgba(0, 0, 0, .14); }
.eyebrow, .section-kicker { margin: 16px 0 8px; color: #0071e3; font-size: 12px; font-weight: 750; letter-spacing: .16em; }
.hero h1 { margin: 0; font-size: clamp(40px, 5vw, 64px); line-height: 1.07; letter-spacing: -.055em; }
.hero-copy { max-width: 680px; margin: 15px auto 0; color: #6e6e73; font-size: 18px; line-height: 1.55; }
.planner-shell { position: relative; z-index: 1; max-width: 1120px; margin: 0 auto; }
.saved-plans-section { margin-bottom: 28px; padding: 25px; border: 1px solid rgba(0, 0, 0, .06); border-radius: 26px; background: rgba(255, 255, 255, .9); box-shadow: 0 18px 50px rgba(0, 0, 0, .055); backdrop-filter: blur(20px); }
.saved-plans-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin-bottom: 17px; }
.saved-plans-heading .section-kicker { margin: 0 0 5px; }
.saved-plans-heading h2 { margin: 0; font-size: 25px; letter-spacing: -.035em; }
.saved-plans-heading > span { color: #86868b; font-size: 12px; }
.saved-plans-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.saved-plan-card { padding: 17px; border: 1px solid #e5e5ea; border-radius: 18px; background: #fff; }
.saved-plan-topline { display: flex; justify-content: space-between; color: #0071e3; font-size: 11px; font-weight: 700; }
.saved-plan-card h3 { margin: 11px 0 4px; font-size: 17px; letter-spacing: -.02em; }
.saved-plan-card > p { margin: 0; color: #86868b; font-size: 11px; }
.trip-progress-copy { display: flex; justify-content: space-between; margin-top: 15px; color: #6e6e73; font-size: 10px; }
.trip-progress-copy strong { color: #248a3d; }
.trip-progress-track { height: 4px; margin-top: 6px; overflow: hidden; border-radius: 5px; background: #e5e5ea; }
.trip-progress-track span { display: block; height: 100%; border-radius: inherit; background: #34c759; }
.saved-plan-actions { display: flex; gap: 7px; margin-top: 15px; }
.saved-plan-actions button { min-height: 34px; padding: 7px 10px; border-radius: 10px; cursor: pointer; font-size: 10px; font-weight: 650; }
.view-trip-button { border: 1px solid #d2d2d7; background: #fff; color: #515154; }
.continue-trip-button { flex: 1; border: 0; background: #eaf4ff; color: #0071e3; }
.continue-trip-button:disabled { background: #f5f5f7; color: #aeaeb2; cursor: default; }
.steps { display: flex; align-items: center; justify-content: center; margin: 0 auto 18px; }
.step-group { display: flex; align-items: center; }
.step { display: flex; gap: 8px; align-items: center; color: #86868b; font-size: 13px; font-weight: 650; white-space: nowrap; }
.step.active, .step.done { color: #1d1d1f; }
.step-number { display: grid; width: 27px; height: 27px; place-items: center; border-radius: 50%; background: #e5e5ea; font-size: 12px; }
.step.active .step-number { color: #fff; background: #0071e3; box-shadow: 0 5px 16px rgba(0, 113, 227, .25); }
.step.done .step-number { color: #fff; background: #34c759; }
.step-line { width: 68px; height: 1px; margin: 0 14px; background: #d2d2d7; }
.step-line.done { background: #34c759; }
.planner-card { overflow: hidden; border: 1px solid rgba(0, 0, 0, .06); border-radius: 28px; background: rgba(255, 255, 255, .94) !important; box-shadow: 0 26px 80px rgba(0, 0, 0, .08); backdrop-filter: blur(22px); }
.planner-card :deep(.ant-card-body) { padding: 38px; }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
.section-heading .section-kicker { margin-top: 0; }
.section-heading h2 { margin: 0 0 7px; font-size: 30px; line-height: 1.15; letter-spacing: -.035em; }
.section-heading p:last-child { margin: 0; color: #86868b; font-size: 14px; line-height: 1.5; }
.chat-heading { align-items: center; }
.reset-chat-button { padding: 9px 13px; border: 1px solid #d2d2d7; border-radius: 999px; background: #fff; color: #515154; cursor: pointer; font-size: 12px; font-weight: 650; white-space: nowrap; }
.reset-chat-button:hover { border-color: #9bc9f7; color: #0071e3; }
.intake-layout { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(300px, .8fr); gap: 18px; }
.chat-panel, .planning-brief { min-width: 0; border: 1px solid #e5e5ea; border-radius: 23px; background: #fff; }
.chat-panel { display: flex; min-height: 570px; overflow: hidden; flex-direction: column; background: #f7f7f9; }
.chat-feed { display: flex; height: 390px; padding: 24px; overflow-y: auto; flex-direction: column; gap: 18px; scroll-behavior: smooth; }
.chat-message { display: flex; align-items: flex-end; gap: 10px; }
.chat-message.user { flex-direction: row-reverse; }
.chat-avatar { display: grid; width: 31px; height: 31px; flex: 0 0 31px; place-items: center; border-radius: 10px; background: #1d1d1f; color: #fff; font-size: 12px; font-weight: 750; }
.chat-message.user .chat-avatar { background: #0071e3; }
.chat-bubble { max-width: min(82%, 520px); }
.chat-bubble > span { display: block; margin: 0 7px 5px; color: #86868b; font-size: 10px; font-weight: 700; letter-spacing: .03em; }
.chat-message.user .chat-bubble > span { text-align: right; }
.chat-bubble p, .thinking-bubble { margin: 0; padding: 12px 15px; border: 1px solid #e5e5ea; border-radius: 17px 17px 17px 5px; background: #fff; color: #1d1d1f; font-size: 13px; line-height: 1.62; white-space: pre-wrap; }
.chat-message.user .chat-bubble p { border-color: #0071e3; border-radius: 17px 17px 5px; background: #0071e3; color: #fff; }
.thinking-bubble { display: flex; gap: 4px; width: fit-content; }
.thinking-bubble i { width: 5px; height: 5px; border-radius: 50%; background: #86868b; animation: thinking 1.1s ease-in-out infinite; }
.thinking-bubble i:nth-child(2) { animation-delay: .15s; }
.thinking-bubble i:nth-child(3) { animation-delay: .3s; }
.prompt-suggestions { display: flex; padding: 0 24px 14px; flex-wrap: wrap; gap: 7px; }
.prompt-suggestions button { padding: 7px 10px; border: 1px solid #dfeaf6; border-radius: 999px; background: #fff; color: #0066cc; cursor: pointer; font-size: 10px; }
.prompt-suggestions button:hover { border-color: #83b9ed; background: #f5faff; }
.chat-composer { margin: auto 14px 14px; padding: 12px; border: 1px solid #d2d2d7; border-radius: 18px; background: #fff; box-shadow: 0 8px 25px rgba(0, 0, 0, .045); }
.chat-composer:focus-within { border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0, 113, 227, .1); }
.chat-composer textarea { display: block; width: 100%; min-height: 54px; padding: 1px 3px; resize: none; border: 0; outline: 0; background: transparent; color: #1d1d1f; font: inherit; font-size: 13px; line-height: 1.55; }
.chat-composer textarea::placeholder { color: #aeaeb2; }
.composer-footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.composer-footer > span { color: #aeaeb2; font-size: 9px; }
.composer-footer button { display: flex; height: 32px; padding: 0 6px 0 12px; align-items: center; gap: 8px; border: 0; border-radius: 999px; background: #0071e3; color: #fff; cursor: pointer; font-size: 11px; font-weight: 700; }
.composer-footer button b { display: grid; width: 23px; height: 23px; place-items: center; border-radius: 50%; background: rgba(255, 255, 255, .18); }
.composer-footer button:disabled { background: #d2d2d7; cursor: default; }
.planning-brief { padding: 21px; }
.brief-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 17px; border-bottom: 1px solid #ededf0; }
.brief-heading p { margin: 0 0 5px; color: #0071e3; font-size: 9px; font-weight: 800; letter-spacing: .14em; }
.brief-heading h3 { margin: 0; font-size: 21px; letter-spacing: -.03em; }
.brief-status { padding: 6px 9px; border-radius: 999px; background: #f2f2f4; color: #86868b; font-size: 9px; font-weight: 700; white-space: nowrap; }
.brief-status.ready { background: rgba(52, 199, 89, .12); color: #248a3d; }
.brief-status.conflict { background: rgba(255, 59, 48, .1); color: #d70015; }
.brief-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin: 16px 0; }
.brief-fields > div { min-height: 68px; padding: 11px; border-radius: 13px; background: #f5f5f7; }
.brief-fields > div.missing { background: #fff7ed; box-shadow: inset 0 0 0 1px rgba(255, 149, 0, .18); }
.brief-fields > div.conflict { background: #fff2f1; box-shadow: inset 0 0 0 1px rgba(255, 59, 48, .18); }
.brief-fields dt { margin-bottom: 5px; color: #86868b; font-size: 9px; font-weight: 700; }
.brief-fields dd { margin: 0; color: #1d1d1f; font-size: 12px; font-weight: 650; line-height: 1.4; overflow-wrap: anywhere; }
.brief-fields small { display: block; margin-top: 3px; color: #86868b; font-size: 9px; }
.brief-fields small.duration-conflict-copy { color: #d70015; font-weight: 700; }
.brief-wide { grid-column: 1 / -1; }
.brief-tags, .projection-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.brief-tags span, .projection-tags span { padding: 4px 7px; border-radius: 999px; background: #fff; color: #0066cc; font-size: 9px; font-weight: 650; }
.memory-projection { padding: 13px; border: 1px solid rgba(0, 113, 227, .1); border-radius: 15px; background: #f5faff; }
.memory-projection-title { display: flex; align-items: center; gap: 6px; color: #0066cc; font-size: 11px; }
.memory-projection p { margin: 7px 0 0; color: #6e6e73; font-size: 10px; line-height: 1.5; }
.projection-tags { margin-top: 8px; }
.projection-tags.visited span { color: #248a3d; }
.projection-tags.avoidance span { color: #d70015; background: #fff2f1; }
.missing-fields { margin-top: 13px; padding: 9px 11px; border-radius: 11px; background: #fff7ed; color: #9a5b00; font-size: 10px; }
.duration-conflict-alert { display: flex; margin-top: 13px; padding: 10px 11px; flex-direction: column; gap: 3px; border-radius: 11px; background: #fff2f1; color: #d70015; font-size: 10px; line-height: 1.45; }
.duration-conflict-alert strong { font-size: 11px; }
.confirm-brief-button { display: flex; width: 100%; height: 45px; margin-top: 13px; padding: 0 16px; align-items: center; justify-content: space-between; border: 0; border-radius: 999px; background: #0071e3; color: #fff; cursor: pointer; font-size: 12px; font-weight: 750; box-shadow: 0 9px 24px rgba(0, 113, 227, .2); }
.confirm-brief-button:not(:disabled):hover { background: #0077ed; transform: translateY(-1px); }
.confirm-brief-button:disabled { background: #e5e5ea; color: #aeaeb2; cursor: not-allowed; box-shadow: none; }
.confirmation-note { margin: 9px 7px 0; color: #aeaeb2; font-size: 9px; line-height: 1.45; text-align: center; }
.trip-days { display: grid; width: 70px; height: 70px; flex: 0 0 auto; place-items: center; border-radius: 21px; background: #1d1d1f; color: #fff; }
.trip-days strong { align-self: end; font-size: 25px; line-height: 1; }
.trip-days span { align-self: start; margin-top: 3px; color: #a1a1a6; font-size: 11px; }
.form-step :deep(.ant-form-item-label > label), .field-block > label { color: #515154; font-size: 13px; font-weight: 650; }
.date-control { width: 100%; }
.soft-control, .date-control, .soft-textarea { border-color: transparent !important; border-radius: 13px !important; background: #f2f2f4 !important; }
.soft-control:hover, .date-control:hover, .soft-textarea:hover { border-color: rgba(0, 113, 227, .35) !important; }
.soft-control:focus, .date-control.ant-picker-focused, .soft-textarea:focus { border-color: #0071e3 !important; box-shadow: 0 0 0 3px rgba(0, 113, 227, .1) !important; }
.soft-select :deep(.ant-select-selector) { border-color: transparent !important; border-radius: 13px !important; background: #f2f2f4 !important; }
.control-icon { color: #0071e3; font-size: 18px; }
.field-block { margin-top: 2px; }
.field-block > label { display: block; margin-bottom: 12px; }
.choice-chips { display: flex; flex-wrap: wrap; gap: 9px; }
.choice-chip { padding: 9px 14px; border: 1px solid #dedee3; border-radius: 999px; background: #fff; color: #515154; cursor: pointer; font-size: 13px; transition: .2s ease; }
.choice-chip span { margin-right: 6px; }
.choice-chip:hover { border-color: #9bc9f7; background: #f5faff; }
.choice-chip.selected { border-color: #0071e3; background: #eaf4ff; color: #0066cc; box-shadow: inset 0 0 0 1px #0071e3; }
.more-options { margin-top: 24px; padding: 0 18px; border-radius: 16px; background: #f8f8fa; }
.more-options summary { padding: 16px 0; color: #1d1d1f; cursor: pointer; font-size: 14px; font-weight: 650; }
.more-options summary span { margin-left: 8px; color: #86868b; font-size: 12px; font-weight: 400; }
.more-grid { padding-top: 4px; }
.last-item { padding-bottom: 16px; }
.primary-actions, .ranking-actions { display: flex; align-items: center; justify-content: center; gap: 18px; margin-top: 28px; }
.primary-button { height: 50px; padding: 0 25px; border: 0; border-radius: 999px; background: #0071e3; font-size: 15px; font-weight: 650; box-shadow: 0 9px 24px rgba(0, 113, 227, .2); }
.primary-button:not(:disabled):hover { background: #0077ed; transform: translateY(-1px); }
.primary-button span { margin-left: 7px; }
.text-button, .secondary-button, .refresh-button { border: 0; background: transparent; color: #0071e3; cursor: pointer; font-size: 13px; font-weight: 600; }
.text-button:disabled, .refresh-button:disabled { opacity: .45; cursor: not-allowed; }
.secondary-button { height: 46px; padding: 0 20px; border: 1px solid #d2d2d7; border-radius: 999px; background: #fff; color: #515154; }
.memory-summary { display: flex; align-items: center; gap: 13px; margin: 19px 0 4px; padding: 14px 16px; border: 1px solid rgba(0, 113, 227, .1); border-radius: 17px; background: #f5faff; }
.memory-icon { display: grid; flex: 0 0 36px; width: 36px; height: 36px; place-items: center; border-radius: 12px; background: #0071e3; color: #fff; font-size: 20px; }
.memory-copy { display: flex; min-width: 210px; flex-direction: column; gap: 2px; }
.memory-copy strong { font-size: 13px; }
.memory-copy span { color: #6e6e73; font-size: 11px; line-height: 1.5; }
.memory-places { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; margin-left: auto; }
.memory-places span { max-width: 120px; padding: 5px 8px; overflow: hidden; border-radius: 999px; background: #fff; color: #515154; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.carryover-summary { margin-top: 12px; padding: 15px 16px; border: 1px solid rgba(52, 199, 89, .14); border-radius: 17px; background: rgba(52, 199, 89, .07); }
.carryover-summary > div:first-child { display: flex; flex-direction: column; gap: 3px; }
.carryover-summary strong { color: #1d1d1f; font-size: 13px; }
.carryover-summary span { color: #6e6e73; font-size: 11px; line-height: 1.5; }
.carryover-places { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.carryover-places span { padding: 5px 8px; border-radius: 999px; background: #fff; color: #248a3d; }
.ranking-heading { margin-bottom: 18px; }
.ranking-heading > div { max-width: 770px; }
.refresh-button { padding: 9px 0; white-space: nowrap; }
.ranking-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.ranking-filters { display: flex; flex-direction: column; gap: 8px; }
.memory-filter { display: inline-flex; width: fit-content; padding: 3px; border-radius: 10px; background: #f2f2f4; }
.memory-filter button { padding: 6px 12px; border: 0; border-radius: 8px; background: transparent; color: #6e6e73; cursor: pointer; font-size: 11px; font-weight: 600; }
.memory-filter button.active { background: #fff; color: #1d1d1f; box-shadow: 0 1px 5px rgba(0, 0, 0, .09); }
.filter-chips { display: flex; flex-wrap: wrap; gap: 7px; }
.filter-chips button { padding: 7px 12px; border: 0; border-radius: 999px; background: #f2f2f4; color: #6e6e73; cursor: pointer; font-size: 12px; }
.filter-chips button.active { background: #1d1d1f; color: #fff; }
.selection-count { color: #0071e3; font-size: 12px; font-weight: 650; white-space: nowrap; }
.recommendation-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; min-height: 200px; }
.recommendation-card { min-height: 238px; padding: 19px; border: 1px solid #e5e5ea; border-radius: 19px; background: #fff; cursor: pointer; outline: none; transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease; }
.recommendation-card:hover { transform: translateY(-2px); border-color: #b6d8f8; box-shadow: 0 14px 30px rgba(0, 0, 0, .07); }
.recommendation-card:focus-visible { box-shadow: 0 0 0 3px rgba(0, 113, 227, .18); }
.recommendation-card.selected { border-color: #0071e3; background: linear-gradient(145deg, #fff, #f5faff); box-shadow: inset 0 0 0 1px #0071e3; }
.recommendation-card.visited { border-color: #e5e5ea; background: #f5f5f7; box-shadow: none; }
.recommendation-card.visited h3,
.recommendation-card.visited .reason { color: #86868b; }
.card-topline { display: flex; align-items: center; gap: 8px; }
.rank { color: #86868b; font-size: 12px; font-weight: 700; letter-spacing: .06em; }
.category { padding: 4px 8px; border-radius: 999px; background: #f2f2f4; color: #6e6e73; font-size: 11px; }
.selection-dot { display: grid; width: 25px; height: 25px; margin-left: auto; place-items: center; border-radius: 50%; background: #f2f2f4; color: #86868b; font-weight: 700; }
.selected .selection-dot { background: #0071e3; color: #fff; }
.visited-toggle { margin-left: auto; padding: 5px 8px; border: 0; border-radius: 999px; background: #f2f2f4; color: #86868b; cursor: pointer; font-size: 10px; font-weight: 650; }
.visited-toggle.active { background: rgba(52, 199, 89, .12); color: #248a3d; }
.visited-toggle + .selection-dot { margin-left: 0; }
.recommendation-card h3 { margin: 17px 0 8px; font-size: 20px; line-height: 1.25; letter-spacing: -.025em; }
.reason { min-height: 59px; margin: 0; color: #6e6e73; font-size: 13px; line-height: 1.5; }
.score-row { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-top: 16px; color: #86868b; font-size: 10px; }
.score-row strong { color: #1d1d1f; font-size: 18px; }
.score-track { height: 4px; margin: 7px 0 14px; overflow: hidden; border-radius: 4px; background: #e5e5ea; }
.score-track span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #0071e3, #5ac8fa); }
.source-link { display: block; overflow: hidden; color: #0071e3; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.memory-source { color: #248a3d; }
.load-more-row { display: flex; justify-content: center; margin-top: 22px; }
.load-more-button { min-width: 220px; padding: 12px 20px; border: 1px solid #d2d2d7; border-radius: 999px; background: #fff; color: #1d1d1f; cursor: pointer; font-size: 13px; font-weight: 650; transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease; }
.load-more-button span { margin-left: 7px; color: #86868b; font-size: 11px; font-weight: 500; }
.load-more-button:hover { transform: translateY(-1px); border-color: #9bc7f2; box-shadow: 0 8px 20px rgba(0, 113, 227, .08); }
.empty-state { padding: 48px 20px; border: 1px dashed #d2d2d7; border-radius: 20px; text-align: center; }
.empty-icon { color: #86868b; font-size: 34px; }
.empty-state h3 { margin: 10px 0 5px; }
.empty-state p { margin: 0; color: #86868b; }
.compact { min-width: 250px; }
.generating-step { max-width: 620px; margin: 0 auto; padding: 40px 10px 32px; text-align: center; }
.loading-orb { display: grid; width: 72px; height: 72px; margin: 0 auto 20px; place-items: center; border-radius: 24px; background: #eaf4ff; }
.loading-orb span { width: 24px; height: 24px; border: 3px solid rgba(0, 113, 227, .2); border-top-color: #0071e3; border-radius: 50%; animation: spin .9s linear infinite; }
.generating-step h2 { margin: 0 0 10px; font-size: 30px; letter-spacing: -.035em; }
.generating-step > p:not(.section-kicker) { margin-bottom: 28px; color: #6e6e73; }
.job-progress-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin-top: 20px; text-align: left; }
.job-progress-item { display: flex; align-items: center; gap: 9px; padding: 10px 12px; border-radius: 13px; background: #f5f5f7; color: #86868b; font-size: 12px; transition: .2s ease; }
.job-progress-item.active { background: #eaf4ff; color: #0071e3; font-weight: 650; }
.job-progress-item.completed { background: #eefaf1; color: #248a3d; }
.job-step-icon { display: grid; width: 20px; height: 20px; flex: 0 0 20px; place-items: center; border-radius: 50%; background: rgba(255, 255, 255, .82); font-weight: 750; }
.job-error { margin: 18px 0 0 !important; padding: 11px 14px; border-radius: 12px; background: #fff2f0; color: #c9342f !important; font-size: 12px; }
.job-actions { display: flex; justify-content: center; gap: 10px; margin-top: 18px; }
.privacy-note { margin: 14px 0 0; color: #86868b; font-size: 11px; text-align: center; }

/* GPT-style planning workspace */
.home-page {
  min-height: calc(100vh - 52px);
  padding: 0;
  overflow: visible;
  background: #fff;
}
.ambient { display: none; }
.planner-shell {
  display: grid;
  width: 100%;
  max-width: none;
  min-height: calc(100vh - 52px);
  grid-template-columns: 286px minmax(0, 1fr);
  margin: 0;
}
.memory-sidebar {
  position: sticky;
  top: 52px;
  z-index: 30;
  display: flex;
  height: calc(100vh - 52px);
  min-height: 640px;
  padding: 20px 14px 16px;
  overflow-y: auto;
  flex-direction: column;
  border-right: 1px solid #e8e8eb;
  background: #f7f7f8;
}
.sidebar-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 4px 7px 18px; }
.sidebar-heading p { margin: 0 0 3px; color: #0071e3; font-size: 9px; font-weight: 800; letter-spacing: .16em; }
.sidebar-heading h2 { margin: 0; font-size: 18px; letter-spacing: -.025em; }
.sidebar-heading span { color: #86868b; font-size: 10px; }
.new-chat-button { display: grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center; border: 1px solid #dedee3; border-radius: 10px; background: #fff; color: #1d1d1f; cursor: pointer; font-size: 20px; line-height: 1; }
.new-chat-button:hover { border-color: #b8d8f7; color: #0071e3; }
.memory-sidebar .steps { display: flex; align-items: stretch; justify-content: flex-start; margin: 0 0 12px; padding: 8px; flex-direction: column; gap: 1px; border-radius: 14px; background: #ededf0; }
.memory-sidebar .step-group { display: block; }
.memory-sidebar .step { min-height: 39px; padding: 6px 8px; border-radius: 9px; color: #6e6e73; font-size: 11px; }
.memory-sidebar .step.active { background: #fff; color: #1d1d1f; box-shadow: 0 1px 4px rgba(0, 0, 0, .07); }
.memory-sidebar .step.done { color: #248a3d; }
.memory-sidebar .step-number { width: 24px; height: 24px; background: transparent; }
.memory-sidebar .step.active .step-number { background: #0071e3; }
.memory-sidebar .step.done .step-number { background: #34c759; }
.memory-sidebar .step-line { display: none; }
.chat-workspace { min-width: 0; padding: 0 28px 46px; background: #fff; }
.workspace-topbar {
  position: sticky;
  top: 52px;
  z-index: 45;
  display: flex;
  min-height: 104px;
  padding: 21px 0 17px;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid rgba(0, 0, 0, .07);
  background: rgba(255, 255, 255, .92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}
.workspace-title { min-width: 0; }
.workspace-title .eyebrow { margin: 0 0 4px; font-size: 9px; }
.workspace-title h1 { margin: 0; font-size: clamp(25px, 2.6vw, 36px); line-height: 1.12; letter-spacing: -.045em; }
.workspace-title > span { display: block; margin-top: 5px; color: #86868b; font-size: 12px; }
.history-picker { position: relative; flex: 0 0 auto; }
.history-picker summary { display: flex; min-width: 142px; height: 42px; padding: 0 12px; align-items: center; gap: 8px; border: 1px solid #dedee3; border-radius: 12px; background: #fff; color: #1d1d1f; cursor: pointer; list-style: none; font-size: 12px; font-weight: 650; box-shadow: 0 3px 12px rgba(0, 0, 0, .04); }
.history-picker summary::-webkit-details-marker { display: none; }
.history-picker summary:hover { border-color: #b8d8f7; }
.history-picker summary b { display: grid; min-width: 20px; height: 20px; padding: 0 5px; place-items: center; border-radius: 999px; background: #f2f2f4; color: #6e6e73; font-size: 9px; }
.history-picker summary i { margin-left: auto; color: #86868b; font-style: normal; transition: transform .2s ease; }
.history-picker[open] summary i { transform: rotate(180deg); }
.history-icon { font-size: 14px; }
.history-popover { position: absolute; top: 50px; right: 0; width: min(390px, calc(100vw - 36px)); max-height: min(620px, calc(100vh - 130px)); padding: 10px; overflow-y: auto; border: 1px solid #e5e5ea; border-radius: 18px; background: rgba(255, 255, 255, .98); box-shadow: 0 24px 70px rgba(0, 0, 0, .17); }
.history-popover-heading { padding: 7px 8px 12px; border-bottom: 1px solid #ededf0; }
.history-popover-heading div { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.history-popover-heading strong { font-size: 14px; }
.history-popover-heading span { color: #86868b; font-size: 10px; }
.history-list { display: flex; padding-top: 7px; flex-direction: column; gap: 6px; }
.history-item { padding: 5px; border-radius: 13px; background: #f7f7f8; }
.history-main { display: flex; width: 100%; padding: 7px; align-items: center; gap: 10px; border: 0; background: transparent; color: #1d1d1f; cursor: pointer; text-align: left; }
.history-main > span:nth-child(2) { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; }
.history-main strong, .history-main small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-main strong { font-size: 11px; }
.history-main small { color: #86868b; font-size: 9px; }
.history-main i { color: #aeaeb2; font-size: 19px; font-style: normal; }
.history-city { display: grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center; border-radius: 10px; background: #eaf4ff; color: #0071e3; font-size: 13px; font-weight: 750; }
.history-progress { display: flex; padding: 1px 7px 5px 51px; align-items: center; justify-content: space-between; gap: 8px; }
.history-progress > span { color: #86868b; font-size: 9px; }
.history-progress button { padding: 4px 7px; border: 0; border-radius: 7px; background: #fff; color: #0071e3; cursor: pointer; font-size: 9px; font-weight: 650; }
.history-progress button:disabled { color: #aeaeb2; cursor: default; }
.history-empty { padding: 32px 12px; color: #86868b; font-size: 11px; text-align: center; }
.planner-card { max-width: 1240px; margin: 22px auto 0; overflow: visible; border: 0; border-radius: 0; background: transparent !important; box-shadow: none; backdrop-filter: none; }
.planner-card :deep(.ant-card-body) { padding: 0; }
.chat-heading { min-height: 34px; margin: 0 0 10px; justify-content: flex-end; }
.chat-heading > div { display: none; }
.intake-layout { grid-template-columns: minmax(460px, 1fr) minmax(270px, 320px); align-items: start; gap: 20px; }
.chat-panel { height: calc(100vh - 214px); min-height: 570px; max-height: 820px; border-radius: 19px; background: #f7f7f8; }
.chat-feed { height: auto; min-height: 0; flex: 1; padding: 30px clamp(20px, 5vw, 72px); }
.chat-bubble { max-width: min(85%, 680px); }
.chat-bubble p, .thinking-bubble { font-size: 14px; }
.prompt-suggestions { padding: 0 clamp(20px, 5vw, 72px) 14px; }
.chat-composer { margin: auto clamp(14px, 3vw, 36px) 18px; border-radius: 22px; box-shadow: 0 8px 30px rgba(0, 0, 0, .07); }
.planning-brief { position: sticky; top: 178px; max-height: calc(100vh - 204px); padding: 18px; overflow-y: auto; border-radius: 19px; }
.ranking-step { max-width: 1180px; margin: 0 auto; }
.privacy-note { margin-bottom: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes thinking { 0%, 60%, 100% { transform: translateY(0); opacity: .45; } 30% { transform: translateY(-3px); opacity: 1; } }

@media (max-width: 1120px) {
  .planner-shell { grid-template-columns: 250px minmax(0, 1fr); }
  .chat-workspace { padding-inline: 20px; }
  .intake-layout { grid-template-columns: 1fr; }
  .chat-panel { height: min(680px, calc(100vh - 214px)); min-height: 520px; }
  .planning-brief { position: static; max-height: none; }
  .recommendation-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .planner-shell { display: block; }
  .memory-sidebar { position: relative; top: auto; width: 100%; height: auto; min-height: 0; padding: 13px; overflow: visible; border-right: 0; border-bottom: 1px solid #e5e5ea; }
  .sidebar-heading { padding-bottom: 10px; }
  .memory-sidebar .steps { display: grid; grid-template-columns: repeat(3, 1fr); }
  .memory-sidebar .step { justify-content: center; padding-inline: 4px; }
  .chat-workspace { padding: 0 13px 38px; }
  .workspace-topbar { position: relative; top: auto; min-height: 88px; padding-block: 14px; }
  .workspace-title > span { display: none; }
  .history-picker summary { min-width: 44px; padding: 0 10px; }
  .history-picker summary > span:not(.history-icon), .history-picker summary > i { display: none; }
  .history-popover { position: fixed; top: 112px; right: 13px; left: 13px; width: auto; }
  .planner-card { margin-top: 14px; }
  .chat-heading { display: none; }
  .chat-panel { height: 68vh; min-height: 500px; }
  .chat-feed { padding: 20px 14px; }
  .prompt-suggestions { padding: 0 14px 12px; }
  .chat-composer { margin: auto 10px 10px; }
  .chat-bubble { max-width: 90%; }
  .recommendation-grid { grid-template-columns: 1fr; }
  .ranking-toolbar, .ranking-actions, .primary-actions { align-items: stretch; flex-direction: column; }
  .memory-summary { align-items: flex-start; flex-wrap: wrap; }
  .memory-places { width: 100%; justify-content: flex-start; margin-left: 49px; }
  .selection-count { align-self: flex-start; }
  .primary-button, .secondary-button, .compact { width: 100%; }
  .brief-fields { grid-template-columns: 1fr; }
  .brief-wide { grid-column: auto; }
  .composer-footer > span { display: none; }
  .composer-footer { justify-content: flex-end; }
  .job-progress-list { grid-template-columns: 1fr; }
  .job-actions { flex-wrap: wrap; }
}

@media (prefers-reduced-motion: reduce) {
  .loading-orb span, .thinking-bubble i { animation: none; }
  .recommendation-card, .primary-button { transition: none; }
}
</style>
