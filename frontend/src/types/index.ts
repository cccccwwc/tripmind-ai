// 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location?: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  poi_id?: string
  city?: string
  district?: string
  operational_status?: 'available' | 'unavailable' | 'unknown' | string
  data_source?: string
  verified_at?: string
  verification_confidence?: number
  ticket_price?: number
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

export interface TimelineItem {
  start_time: string
  end_time: string
  item_type: 'attraction' | 'meal' | 'transport' | 'hotel' | 'activity' | string
  title: string
  location?: string
  description?: string
  from_location?: string
  to_location?: string
  transport_mode?: string
  duration_minutes?: number
  distance?: string
  estimated_cost?: number
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
  schedule?: TimelineItem[]
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  selected_recommendations?: SelectedRecommendation[]
}

export interface SelectedRecommendation {
  name: string
  category: string
  reason: string
  source_url: string
}

export interface RecommendationItem extends SelectedRecommendation {
  id: string
  score: number
  evidence_count: number
  source_title: string
}

export interface IntakeChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface PlanningBrief {
  city?: string | null
  start_date?: string | null
  end_date?: string | null
  requested_days?: number | null
  travel_days?: number | null
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  memory_projection: {
    visited_places: string[]
    carryover_places: string[]
    applied_preferences?: ProjectedLongTermMemory[]
    applied_avoidances?: ProjectedLongTermMemory[]
  }
}

export interface ProjectedLongTermMemory {
  id: string
  content: string
  evidence: string
  source_conversation_id: string
}

export interface LongTermMemoryRecord {
  id: string
  user_id: string
  kind: 'preference' | 'avoidance'
  content: string
  scope_city: string
  status: 'pending' | 'approved'
  source_conversation_id: string
  source_message_ids: string[]
  evidence: string
  created_at: string
  updated_at: string
}

export interface MemoryExtractionRequest {
  user_id?: string
  conversation_id?: string
  city?: string
  messages: Array<{ id: string; role: 'user' | 'assistant'; content: string }>
}

export interface PlanningIntakeRequest {
  messages: IntakeChatMessage[]
  brief: PlanningBrief
  travel_memory: Array<{ name: string; city: string; category: string }>
  carryover_places: string[]
  long_term_memory: Array<Pick<LongTermMemoryRecord, 'id' | 'kind' | 'content' | 'scope_city' | 'source_conversation_id' | 'evidence'>>
}

export interface PlanningIntakeResponse {
  success: boolean
  assistant_message: string
  brief: PlanningBrief
  missing_fields: string[]
  ready_to_confirm: boolean
}

export interface RecommendationRequest {
  city: string
  preferences: string[]
  limit?: number
}

export interface RecommendationResponse {
  success: boolean
  message: string
  query: string
  data: RecommendationItem[]
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

export type TripJobStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'cancelled'
  | 'failed'
  | 'interrupted'
  | 'completed'

export interface TripJobResponse {
  success: boolean
  job_id: string
  workflow_id: string
  parent_job_id?: string | null
  status: TripJobStatus
  progress: number
  current_step: string
  message: string
  can_cancel: boolean
  can_retry: boolean
  can_resume: boolean
  data?: TripPlan | null
  error?: string | null
  created_at: string
  updated_at: string
}

export interface TripJobEvent {
  id?: number
  job_id: string
  type: 'queued' | 'started' | 'resumed' | 'progress' | 'cancelling' | 'cancelled' | 'failed' | 'completed' | 'interrupted'
  status: TripJobStatus
  progress: number
  current_step: string
  message: string
  node?: string
  node_status?: string
  data?: TripPlan | null
  error?: string | null
  created_at?: string
}
