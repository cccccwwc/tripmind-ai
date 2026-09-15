<template>
  <section :class="['memory-panel', { compact }]" aria-labelledby="travel-profile-title">
    <header>
      <div>
        <p>USER PROFILE</p>
        <h2 id="travel-profile-title">旅行习惯与个人画像</h2>
        <span>自动从以往对话发现偏好与避雷项；只有经你确认后才会用于行程。</span>
      </div>
      <button type="button" :disabled="!canArchive || archiving" @click="$emit('archive')">
        {{ archiving ? '正在更新画像…' : '重新分析本次对话' }}
      </button>
    </header>

    <div class="profile-summary" aria-label="个人画像摘要">
      <div><strong>{{ approvedPreferences.length }}</strong><span>旅行偏好</span></div>
      <div><strong>{{ approvedAvoidances.length }}</strong><span>避雷事项</span></div>
      <div><strong>{{ pending.length }}</strong><span>等待确认</span></div>
    </div>

    <div v-if="loading" class="memory-empty">正在读取你的旅行习惯…</div>
    <template v-else>
      <section v-if="pending.length" class="memory-group pending-group">
        <div class="group-heading"><strong>待确认的新发现</strong><span>{{ pending.length }} 条</span></div>
        <article v-for="item in pending" :key="item.id" class="memory-card pending">
          <div class="memory-kind">{{ item.kind === 'preference' ? '可能是你的偏好' : '可能需要避开' }}</div>
          <input v-model="drafts[item.id].content" maxlength="240" aria-label="记忆内容" />
          <input v-model="drafts[item.id].scope_city" maxlength="50" placeholder="适用城市（留空表示全局）" aria-label="适用城市" />
          <p>依据原话：“{{ item.evidence }}”</p>
          <small>可追溯来源：对话 {{ item.source_conversation_id }} · 消息 {{ item.source_message_ids.join('、') }}</small>
          <div class="memory-actions">
            <button type="button" class="approve" @click="$emit('approve', item, drafts[item.id])">确认加入画像</button>
            <button type="button" @click="$emit('forget', item)">不记录</button>
          </div>
        </article>
      </section>

      <section class="memory-group">
        <div class="group-heading"><strong>我的旅行画像</strong><span>{{ approved.length }} 条</span></div>
        <div v-if="!approved.length" class="memory-empty">还没有已确认的习惯。继续和旅行顾问聊天，我会自动整理。</div>
        <article v-for="item in approved" :key="item.id" class="memory-card" :class="{ disabled: disabledIds.includes(item.id) }">
          <div class="memory-card-topline">
            <span :class="['kind-pill', item.kind]">{{ item.kind === 'preference' ? '偏好' : '避雷' }}</span>
            <button type="button" class="trip-toggle" @click="$emit('toggle', item.id)">
              {{ disabledIds.includes(item.id) ? '本次不使用' : '本次已启用' }}
            </button>
          </div>
          <input v-model="drafts[item.id].content" maxlength="240" aria-label="记忆内容" />
          <input v-model="drafts[item.id].scope_city" maxlength="50" placeholder="全部城市" aria-label="适用城市" />
          <p>依据原话：“{{ item.evidence }}”</p>
          <small>可追溯来源：对话 {{ item.source_conversation_id }} · 消息 {{ item.source_message_ids.join('、') }}</small>
          <div class="memory-actions">
            <button type="button" class="save" @click="$emit('save', item, drafts[item.id])">保存修改</button>
            <button type="button" @click="$emit('forget', item)">忘记</button>
          </div>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { LongTermMemoryRecord } from '@/types'

type Draft = { content: string; scope_city: string }
const props = defineProps<{
  records: LongTermMemoryRecord[]
  loading: boolean
  archiving: boolean
  canArchive: boolean
  disabledIds: string[]
  compact?: boolean
}>()

defineEmits<{
  archive: []
  approve: [item: LongTermMemoryRecord, draft: Draft]
  save: [item: LongTermMemoryRecord, draft: Draft]
  forget: [item: LongTermMemoryRecord]
  toggle: [id: string]
}>()

const drafts = reactive<Record<string, Draft>>({})
const pending = computed(() => props.records.filter(item => item.status === 'pending'))
const approved = computed(() => props.records.filter(item => item.status === 'approved'))
const approvedPreferences = computed(() => approved.value.filter(item => item.kind === 'preference'))
const approvedAvoidances = computed(() => approved.value.filter(item => item.kind === 'avoidance'))

watch(() => props.records, records => {
  records.forEach(item => {
    drafts[item.id] = { content: item.content, scope_city: item.scope_city }
  })
}, { immediate: true, deep: true })
</script>

<style scoped>
.memory-panel { margin-bottom: 28px; padding: 24px; border: 1px solid rgba(0,0,0,.06); border-radius: 26px; background: rgba(255,255,255,.9); box-shadow: 0 18px 50px rgba(0,0,0,.055); }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
header p { margin: 0 0 5px; color: #0071e3; font-size: 10px; font-weight: 800; letter-spacing: .15em; }
header h2 { margin: 0; font-size: 25px; letter-spacing: -.035em; }
header span { display: block; margin-top: 7px; color: #86868b; font-size: 12px; }
header button, .memory-actions button, .trip-toggle { border: 0; cursor: pointer; font-weight: 700; }
header button { padding: 10px 15px; border-radius: 999px; background: #1d1d1f; color: #fff; }
header button:disabled { background: #e5e5ea; color: #aeaeb2; cursor: default; }
.profile-summary { display: grid; margin-top: 16px; padding: 8px; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; border-radius: 15px; background: #f5f5f7; }
.profile-summary > div { display: flex; min-width: 0; padding: 7px 5px; align-items: center; justify-content: center; flex-direction: column; border-radius: 11px; background: #fff; }
.profile-summary strong { color: #1d1d1f; font-size: 16px; line-height: 1; }
.profile-summary span { margin-top: 4px; color: #86868b; font-size: 8px; white-space: nowrap; }
.memory-group { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 10px; margin-top: 18px; }
.group-heading { display: flex; grid-column: 1/-1; align-items: center; justify-content: space-between; color: #515154; font-size: 12px; }
.group-heading span { color: #86868b; }
.memory-card { padding: 14px; border: 1px solid #e5e5ea; border-radius: 17px; background: #fff; transition: .2s ease; }
.memory-card.pending { background: #f5faff; border-color: #d8eaff; }
.memory-card.disabled { opacity: .55; background: #f5f5f7; }
.memory-kind { margin-bottom: 9px; color: #0066cc; font-size: 10px; font-weight: 800; }
.memory-card-topline { display: flex; align-items: center; justify-content: space-between; margin-bottom: 9px; }
.kind-pill { padding: 4px 7px; border-radius: 999px; background: rgba(52,199,89,.1); color: #248a3d; font-size: 9px; font-weight: 800; }
.kind-pill.avoidance { background: rgba(255,59,48,.1); color: #d70015; }
.trip-toggle { padding: 5px 8px; border-radius: 999px; background: #f2f2f4; color: #515154; font-size: 9px; }
input { box-sizing: border-box; width: 100%; margin-bottom: 7px; padding: 8px 9px; border: 1px solid #dedee3; border-radius: 10px; outline: none; font: inherit; font-size: 11px; }
input:focus { border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0,113,227,.08); }
.memory-card p { margin: 4px 0; color: #515154; font-size: 10px; line-height: 1.5; }
.memory-card small { display: block; color: #86868b; font-size: 9px; overflow-wrap: anywhere; }
.memory-actions { display: flex; gap: 7px; margin-top: 11px; }
.memory-actions button { padding: 7px 9px; border-radius: 9px; background: #f2f2f4; color: #515154; font-size: 9px; }
.memory-actions .approve, .memory-actions .save { background: #0071e3; color: #fff; }
.memory-empty { grid-column: 1/-1; margin-top: 16px; padding: 18px; border-radius: 15px; background: #f5f5f7; color: #86868b; font-size: 11px; text-align: center; }
.memory-panel.compact { margin: 0; padding: 6px 2px 20px; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
.compact header { padding: 12px 7px; flex-direction: column; gap: 11px; border-top: 1px solid #e5e5ea; }
.compact header p { font-size: 8px; }
.compact header h2 { font-size: 16px; }
.compact header span { margin-top: 4px; font-size: 10px; line-height: 1.45; }
.compact header button { width: 100%; padding: 9px 11px; border-radius: 10px; font-size: 10px; }
.compact .profile-summary { margin: 0 6px 8px; padding: 5px; }
.compact .profile-summary > div { padding: 6px 2px; }
.compact .profile-summary strong { font-size: 14px; }
.compact .profile-summary span { font-size: 7px; }
.compact .memory-group { display: grid; grid-template-columns: 1fr; gap: 7px; margin-top: 9px; padding: 0 6px; }
.compact .group-heading { position: sticky; top: -1px; z-index: 2; padding: 5px 1px; background: #f7f7f8; font-size: 10px; }
.compact .memory-card { padding: 11px; border-radius: 13px; }
.compact .memory-card input { padding: 7px 8px; font-size: 10px; }
.compact .memory-card p { font-size: 9px; }
.compact .memory-card small { font-size: 8px; }
.compact .memory-empty { margin-top: 7px; padding: 14px 10px; font-size: 9px; }
.compact .memory-actions button { flex: 1; }
@media (max-width: 780px) { .memory-group { grid-template-columns: 1fr; } header { flex-direction: column; } }
</style>
