"""数据模型定义"""

from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date


# ============ 请求模型 ============

class SelectedRecommendation(BaseModel):
    """游客选中的推荐地点。"""
    name: str = Field(..., min_length=1, max_length=80)
    category: str = Field(default="景点", max_length=20)
    reason: str = Field(default="", max_length=300)
    source_url: str = Field(default="", max_length=1000)


class TripRequest(BaseModel):
    """旅行规划请求"""
    city: str = Field(..., description="目的地城市", example="北京")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD", example="2025-06-01")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD", example="2025-06-03")
    travel_days: int = Field(..., description="旅行天数", ge=1, le=30, example=3)
    transportation: str = Field(..., description="交通方式", example="公共交通")
    accommodation: str = Field(..., description="住宿偏好", example="经济型酒店")
    preferences: List[str] = Field(default=[], description="旅行偏好标签", example=["历史文化", "美食"])
    free_text_input: Optional[str] = Field(default="", description="额外要求", example="希望多安排一些博物馆")
    selected_recommendations: List[SelectedRecommendation] = Field(
        default_factory=list,
        description="游客从实时推荐榜单中主动选择的地点"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "city": "北京",
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "travel_days": 3,
                "transportation": "公共交通",
                "accommodation": "经济型酒店",
                "preferences": ["历史文化", "美食"],
                "free_text_input": "希望多安排一些博物馆"
            }
        }


class POISearchRequest(BaseModel):
    """POI搜索请求"""
    keywords: str = Field(..., description="搜索关键词", example="故宫")
    city: str = Field(..., description="城市", example="北京")
    citylimit: bool = Field(default=True, description="是否限制在城市范围内")


class RouteRequest(BaseModel):
    """路线规划请求"""
    origin_address: str = Field(..., description="起点地址", example="北京市朝阳区阜通东大街6号")
    destination_address: str = Field(..., description="终点地址", example="北京市海淀区上地十街10号")
    origin_city: Optional[str] = Field(default=None, description="起点城市")
    destination_city: Optional[str] = Field(default=None, description="终点城市")
    route_type: str = Field(default="walking", description="路线类型: walking/driving/transit")


class RecommendationRequest(BaseModel):
    """实时推荐榜单请求。"""
    city: str = Field(..., min_length=1, max_length=50, description="目的地城市")
    preferences: List[str] = Field(default_factory=list, description="旅行偏好")
    limit: int = Field(default=18, ge=4, le=24, description="返回推荐数量")


class IntakeChatMessage(BaseModel):
    """旅行需求澄清阶段的一条对话。"""
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class IntakeMemoryItem(BaseModel):
    """发送给需求 Agent 的最小旅行记忆，不包含敏感信息。"""
    name: str = Field(..., min_length=1, max_length=100)
    city: str = Field(default="", max_length=50)
    category: str = Field(default="景点", max_length=30)


class LongTermMemoryContext(BaseModel):
    """A user-approved durable memory supplied to one planning conversation."""
    id: str = Field(..., min_length=1, max_length=80)
    kind: Literal["preference", "avoidance"]
    content: str = Field(..., min_length=1, max_length=240)
    scope_city: str = Field(default="", max_length=50)
    source_conversation_id: str = Field(default="", max_length=100)
    evidence: str = Field(default="", max_length=500)


class ProjectedLongTermMemory(BaseModel):
    id: str
    content: str
    evidence: str = ""
    source_conversation_id: str = ""


class PlanningMemoryProjection(BaseModel):
    """与本次目的地相关的记忆投影。"""
    visited_places: List[str] = Field(default_factory=list)
    carryover_places: List[str] = Field(default_factory=list)
    applied_preferences: List[ProjectedLongTermMemory] = Field(default_factory=list)
    applied_avoidances: List[ProjectedLongTermMemory] = Field(default_factory=list)


class PlanningBrief(BaseModel):
    """正式启动多智能体规划前，由多轮对话逐步形成的结构化简报。"""
    city: Optional[str] = Field(default=None, max_length=50)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    requested_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=30,
        description="用户在对话中明确说出的旅行天数，用于和日期跨度校验",
    )
    travel_days: Optional[int] = Field(default=None, ge=1, le=30)
    transportation: str = Field(default="公共交通", max_length=30)
    accommodation: str = Field(default="舒适型酒店", max_length=30)
    preferences: List[str] = Field(default_factory=list)
    free_text_input: str = Field(default="", max_length=1000)
    memory_projection: PlanningMemoryProjection = Field(default_factory=PlanningMemoryProjection)

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_iso_date(cls, value):
        if value in {None, ""}:
            return None
        from datetime import datetime
        datetime.strptime(value, "%Y-%m-%d")
        return value

    @model_validator(mode="after")
    def calculate_days(self):
        if self.start_date and self.end_date:
            from datetime import datetime
            start = datetime.strptime(self.start_date, "%Y-%m-%d")
            end = datetime.strptime(self.end_date, "%Y-%m-%d")
            days = (end - start).days + 1
            if not 1 <= days <= 30:
                raise ValueError("旅行日期必须为 1 至 30 天，且返程不得早于出发")
            self.travel_days = days
        return self


class PlanningIntakeRequest(BaseModel):
    messages: List[IntakeChatMessage] = Field(..., min_length=1, max_length=30)
    brief: PlanningBrief = Field(default_factory=PlanningBrief)
    travel_memory: List[IntakeMemoryItem] = Field(default_factory=list, max_length=100)
    carryover_places: List[str] = Field(default_factory=list, max_length=30)
    long_term_memory: List[LongTermMemoryContext] = Field(default_factory=list, max_length=100)


class PlanningIntakeResponse(BaseModel):
    success: bool = True
    assistant_message: str
    brief: PlanningBrief
    missing_fields: List[str] = Field(default_factory=list)
    ready_to_confirm: bool = False


class ArchivedConversationMessage(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class MemoryExtractionRequest(BaseModel):
    user_id: str = Field(default="local-user", min_length=1, max_length=80)
    conversation_id: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=50)
    messages: List[ArchivedConversationMessage] = Field(..., min_length=1, max_length=60)


class LongTermMemoryRecord(BaseModel):
    id: str
    user_id: str
    kind: Literal["preference", "avoidance"]
    content: str
    scope_city: str = ""
    status: Literal["pending", "approved"]
    source_conversation_id: str
    source_message_ids: List[str] = Field(default_factory=list)
    evidence: str = ""
    created_at: str
    updated_at: str


class MemoryExtractionResponse(BaseModel):
    success: bool = True
    conversation_id: str
    memories: List[LongTermMemoryRecord] = Field(default_factory=list)


class MemoryListResponse(BaseModel):
    success: bool = True
    memories: List[LongTermMemoryRecord] = Field(default_factory=list)


class ArchivedConversationResponse(BaseModel):
    success: bool = True
    conversation_id: str
    user_id: str
    city: str = ""
    archived_at: str
    messages: List[ArchivedConversationMessage] = Field(default_factory=list)


class MemoryUpdateRequest(BaseModel):
    user_id: str = Field(default="local-user", min_length=1, max_length=80)
    content: Optional[str] = Field(default=None, min_length=1, max_length=240)
    scope_city: Optional[str] = Field(default=None, max_length=50)
    status: Optional[Literal["pending", "approved"]] = None


# ============ 响应模型 ============

class Location(BaseModel):
    """地理位置"""
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")


class Attraction(BaseModel):
    """景点信息"""
    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="地址")
    location: Optional[Location] = Field(default=None, description="经高德核验的经纬度坐标")
    visit_duration: int = Field(..., description="建议游览时间(分钟)")
    description: str = Field(..., description="景点描述")
    category: Optional[str] = Field(default="景点", description="景点类别")
    rating: Optional[float] = Field(default=None, description="评分")
    photos: Optional[List[str]] = Field(default_factory=list, description="景点图片URL列表")
    poi_id: Optional[str] = Field(default="", description="POI ID")
    city: str = Field(default="", description="高德返回的城市")
    district: str = Field(default="", description="高德返回的行政区")
    poi_type: str = Field(default="", description="高德 POI 类型名称")
    poi_typecode: str = Field(default="", description="高德 POI 类型编码")
    operational_status: str = Field(
        default="unknown",
        description="最近一次核验时的营业可用状态: available/unavailable/unknown",
    )
    data_source: str = Field(default="", description="地点数据来源，例如 amap")
    verified_at: str = Field(default="", description="地点最近核验时间（ISO 8601）")
    verification_confidence: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="地点名称、城市与地址综合匹配置信度",
    )
    image_url: Optional[str] = Field(default=None, description="图片URL")
    ticket_price: int = Field(default=0, description="门票价格(元)")


class Meal(BaseModel):
    """餐饮信息"""
    type: str = Field(..., description="餐饮类型: breakfast/lunch/dinner/snack")
    name: str = Field(..., description="餐饮名称")
    address: Optional[str] = Field(default=None, description="地址")
    location: Optional[Location] = Field(default=None, description="经纬度坐标")
    description: Optional[str] = Field(default=None, description="描述")
    estimated_cost: int = Field(default=0, description="预估费用(元)")


class Hotel(BaseModel):
    """酒店信息"""
    name: str = Field(..., description="酒店名称")
    address: str = Field(default="", description="酒店地址")
    location: Optional[Location] = Field(default=None, description="酒店位置")
    price_range: str = Field(default="", description="价格范围")
    rating: str = Field(default="", description="评分")
    distance: str = Field(default="", description="距离景点距离")
    type: str = Field(default="", description="酒店类型")
    estimated_cost: int = Field(default=0, description="预估费用(元/晚)")


class TimelineItem(BaseModel):
    """一天内按时间排列的活动或移动路段。"""
    start_time: str = Field(..., description="开始时间 HH:MM", examples=["09:00"])
    end_time: str = Field(..., description="结束时间 HH:MM", examples=["11:00"])
    item_type: str = Field(..., description="类型: attraction/meal/transport/hotel/activity")
    title: str = Field(..., description="活动或路段标题")
    location: str = Field(default="", description="活动地点或地址")
    description: str = Field(default="", description="安排说明")
    from_location: str = Field(default="", description="移动起点")
    to_location: str = Field(default="", description="移动终点")
    transport_mode: str = Field(default="", description="步行/地铁/公交/打车/自驾")
    duration_minutes: int = Field(default=0, ge=0, le=1440, description="活动或移动时长(分钟)")
    distance: str = Field(default="", description="路程距离，例如 2.3公里")
    estimated_cost: int = Field(default=0, ge=0, description="预计费用(元)")


class DayPlan(BaseModel):
    """单日行程"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="第几天(从0开始)")
    description: str = Field(..., description="当日行程描述")
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: List[Attraction] = Field(default=[], description="景点列表")
    meals: List[Meal] = Field(default=[], description="餐饮列表")
    schedule: List[TimelineItem] = Field(default_factory=list, description="按时间顺序排列的当日日程")


class WeatherInfo(BaseModel):
    """天气信息"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", description="白天天气")
    night_weather: str = Field(default="", description="夜间天气")
    day_temp: Union[int, str] = Field(default=0, description="白天温度")
    night_temp: Union[int, str] = Field(default=0, description="夜间温度")
    wind_direction: str = Field(default="", description="风向")
    wind_power: str = Field(default="", description="风力")

    @field_validator('day_temp', 'night_temp', mode='before')
    @classmethod
    def parse_temperature(cls, v):
        """解析温度,移除°C等单位"""
        if isinstance(v, str):
            # 移除°C, ℃等单位符号
            v = v.replace('°C', '').replace('℃', '').replace('°', '').strip()
            try:
                return int(v)
            except ValueError:
                return 0
        return v


class Budget(BaseModel):
    """预算信息"""
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: int = Field(default=0, description="酒店总费用")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_transportation: int = Field(default=0, description="交通总费用")
    total: int = Field(default=0, description="总费用")


class TripPlan(BaseModel):
    """旅行计划"""
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: List[DayPlan] = Field(..., description="每日行程")
    weather_info: List[WeatherInfo] = Field(default=[], description="天气信息")
    overall_suggestions: str = Field(..., description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="预算信息")


class TripPlanResponse(BaseModel):
    """旅行计划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划数据")


class TripWorkflowStartRequest(BaseModel):
    """创建一个可审批、可恢复的 LangGraph 旅行规划工作流。"""
    trip: TripRequest
    require_approval: bool = True
    workflow_id: Optional[str] = Field(default=None, min_length=1, max_length=100)


class TripWorkflowResumeRequest(BaseModel):
    """恢复工作流；approved 用于回答 Planning Brief 审批中断。"""
    approved: Optional[bool] = None


class TripWorkflowResponse(BaseModel):
    success: bool = True
    workflow_id: str
    status: str
    message: str = ""
    approval_prompt: Optional[Dict[str, Any]] = None
    data: Optional[TripPlan] = None
    poi_validation_report: Dict[str, Any] = Field(default_factory=dict)
    errors: Dict[str, str] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)


class TripJobResponse(BaseModel):
    """Persistent background planning job returned to the web client."""
    success: bool = True
    job_id: str
    workflow_id: str
    parent_job_id: Optional[str] = None
    status: Literal[
        "queued", "running", "cancelling", "cancelled", "failed", "interrupted", "completed"
    ]
    progress: int = Field(default=0, ge=0, le=100)
    current_step: str = ""
    message: str = ""
    can_cancel: bool = False
    can_retry: bool = False
    can_resume: bool = False
    data: Optional[TripPlan] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class POIInfo(BaseModel):
    """POI信息"""
    id: str = Field(..., description="POI ID")
    name: str = Field(..., description="名称")
    type: str = Field(..., description="类型")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="经纬度坐标")
    tel: Optional[str] = Field(default=None, description="电话")


class POISearchResponse(BaseModel):
    """POI搜索响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: List[POIInfo] = Field(default=[], description="POI列表")


class RouteInfo(BaseModel):
    """路线信息"""
    distance: float = Field(..., description="距离(米)")
    duration: int = Field(..., description="时间(秒)")
    route_type: str = Field(..., description="路线类型")
    description: str = Field(..., description="路线描述")


class RouteResponse(BaseModel):
    """路线规划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[RouteInfo] = Field(default=None, description="路线信息")


class WeatherResponse(BaseModel):
    """天气查询响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: List[WeatherInfo] = Field(default=[], description="天气信息")


class RecommendationItem(BaseModel):
    """经过聚合分析的单条推荐。"""
    id: str
    name: str
    category: str = "景点"
    reason: str
    score: int = Field(ge=0, le=100)
    evidence_count: int = Field(default=1, ge=1)
    source_title: str
    source_url: str


class RecommendationResponse(BaseModel):
    """Tavily 实时推荐榜单响应。"""
    success: bool
    message: str = ""
    query: str = ""
    data: List[RecommendationItem] = Field(default_factory=list)


# ============ 错误响应 ============

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = Field(default=False, description="是否成功")
    message: str = Field(..., description="错误消息")
    error_code: Optional[str] = Field(default=None, description="错误代码")
