import axios from 'axios'
import type {
  RecommendationRequest,
  RecommendationResponse,
  PlanningIntakeRequest,
  PlanningIntakeResponse,
  LongTermMemoryRecord,
  MemoryExtractionRequest,
  TripFormData,
  TripJobEvent,
  TripJobResponse,
  TripPlanResponse
} from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  // 正式规划已在后台运行，普通 HTTP 请求无需维持十分钟长连接。
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    if (error.code === 'ECONNABORTED') throw new Error('请求超时，请稍后重试')
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

export async function createTripJob(formData: TripFormData): Promise<TripJobResponse> {
  try {
    const response = await apiClient.post<TripJobResponse>('/api/trip/jobs', formData)
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '后台规划任务创建失败')
  }
}

export async function getTripJob(jobId: string): Promise<TripJobResponse> {
  try {
    const response = await apiClient.get<TripJobResponse>(`/api/trip/jobs/${jobId}`)
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '规划任务状态读取失败')
  }
}

export async function cancelTripJob(jobId: string): Promise<TripJobResponse> {
  const response = await apiClient.post<TripJobResponse>(`/api/trip/jobs/${jobId}/cancel`)
  return response.data
}

export async function retryTripJob(jobId: string): Promise<TripJobResponse> {
  const response = await apiClient.post<TripJobResponse>(`/api/trip/jobs/${jobId}/retry`)
  return response.data
}

export async function resumeTripJob(jobId: string): Promise<TripJobResponse> {
  const response = await apiClient.post<TripJobResponse>(`/api/trip/jobs/${jobId}/resume`)
  return response.data
}

/** Subscribe to persisted job progress. EventSource reconnects with Last-Event-ID. */
export function subscribeTripJob(
  jobId: string,
  onEvent: (event: TripJobEvent) => void,
  onConnectionError: () => void
): () => void {
  const source = new EventSource(`${API_BASE_URL}/api/trip/jobs/${encodeURIComponent(jobId)}/events`)
  const eventNames: TripJobEvent['type'][] = [
    'queued', 'started', 'resumed', 'progress', 'cancelling',
    'cancelled', 'failed', 'completed', 'interrupted'
  ]
  const listeners = eventNames.map(eventName => {
    const listener = (message: Event) => {
      try {
        const payload = JSON.parse((message as MessageEvent).data) as TripJobEvent
        onEvent(payload)
        if (['completed', 'failed', 'cancelled'].includes(payload.type)) source.close()
      } catch (error) {
        console.error('无法解析任务进度事件:', error)
      }
    }
    source.addEventListener(eventName, listener)
    return { eventName, listener }
  })
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) onConnectionError()
  }
  return () => {
    listeners.forEach(({ eventName, listener }) => source.removeEventListener(eventName, listener))
    source.close()
  }
}

/**
 * 获取 Tavily 聚合的实时旅行推荐榜单
 */
export async function discoverRecommendations(
  request: RecommendationRequest
): Promise<RecommendationResponse> {
  try {
    const response = await apiClient.post<RecommendationResponse>(
      '/api/recommendations/discover',
      request
    )
    return response.data
  } catch (error: any) {
    console.error('获取实时推荐失败:', error)
    if (error.code === 'ECONNABORTED') {
      throw new Error('实时推荐搜索超时，请稍后重试')
    }
    throw new Error(error.response?.data?.detail || error.message || '获取实时推荐失败')
  }
}

/**
 * 通过多轮对话整理 Planning Brief；该接口不会启动正式规划。
 */
export async function refinePlanningBrief(
  request: PlanningIntakeRequest
): Promise<PlanningIntakeResponse> {
  try {
    const response = await apiClient.post<PlanningIntakeResponse>('/api/trip/intake', request)
    return response.data
  } catch (error: any) {
    console.error('旅行需求澄清失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '需求顾问暂时无法回复')
  }
}

export async function listLongTermMemories(): Promise<LongTermMemoryRecord[]> {
  try {
    const response = await apiClient.get<{ success: boolean; memories: LongTermMemoryRecord[] }>('/api/memory')
    return response.data.memories
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '长期记忆加载失败')
  }
}

export async function extractLongTermMemories(
  request: MemoryExtractionRequest
): Promise<{ conversation_id: string; memories: LongTermMemoryRecord[] }> {
  try {
    const response = await apiClient.post('/api/memory/extract', request)
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '长期记忆提取失败')
  }
}

export async function updateLongTermMemory(
  id: string,
  update: { content?: string; scope_city?: string; status?: 'pending' | 'approved' }
): Promise<LongTermMemoryRecord> {
  try {
    const response = await apiClient.patch<LongTermMemoryRecord>(`/api/memory/${id}`, {
      user_id: 'local-user',
      ...update
    })
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '旅行记忆更新失败')
  }
}

export async function forgetLongTermMemory(id: string): Promise<void> {
  try {
    await apiClient.delete(`/api/memory/${id}`, { params: { user_id: 'local-user' } })
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '忘记旅行记忆失败')
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export default apiClient
