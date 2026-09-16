"""确定性数据查询与单一规划 Agent 组成的混合旅行规划系统。"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from hello_agents import SimpleAgent
from ..services.llm_service import get_llm
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel, TimelineItem, Budget
from ..config import get_settings
from ..services.poi_location_service import POILocationService
from ..services.poi_reliability_service import POIReliabilityService, POIValidationReport
from ..services.amap_weather_service import AmapWeatherService

# ============ Agent提示词 ============

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ],
      "schedule": [
        {
          "start_time": "08:00",
          "end_time": "08:40",
          "item_type": "meal",
          "title": "早餐 · 当地特色早餐",
          "location": "餐厅名称与地址",
          "description": "用餐建议",
          "duration_minutes": 40,
          "estimated_cost": 30
        },
        {
          "start_time": "08:40",
          "end_time": "09:10",
          "item_type": "transport",
          "title": "前往第一个景点",
          "from_location": "酒店或早餐地点",
          "to_location": "景点名称",
          "transport_mode": "地铁",
          "duration_minutes": 30,
          "distance": "5.2公里",
          "description": "地铁线路或步行换乘说明",
          "estimated_cost": 5
        },
        {
          "start_time": "09:10",
          "end_time": "11:30",
          "item_type": "attraction",
          "title": "景点名称",
          "location": "景点详细地址",
          "description": "游览重点与预约提醒",
          "duration_minutes": 140,
          "estimated_cost": 60
        }
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. weather_info数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 每天必须生成 schedule，并从早餐到返回酒店严格按 start_time 升序排列
5. 每个景点、餐饮和住宿都要出现在 schedule 中；两个不同地点之间必须插入 transport 路段
6. transport 必须写明 from_location、to_location、transport_mode、duration_minutes 和 distance
7. 时间使用24小时 HH:MM 格式，不得重叠；结合营业时间、游览时长和路程预留，避免不现实的赶场
8. 景点按地理位置就近成组，明确“几点出发、几点到达、在哪里、接下来去哪里”
9. 每天必须包含早中晚三餐，并提供实用的旅行建议
10. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
"""


class MultiAgentTripPlanner:
    """兼容旧类名的混合旅行规划系统。"""

    def __init__(self):
        """初始化确定性数据节点与路线规划 Agent。"""
        print("🔄 开始初始化混合旅行规划系统...")

        try:
            settings = get_settings()
            self.llm = get_llm()
            self.poi_location_service = POILocationService()
            self.poi_reliability_service = POIReliabilityService()
            self.weather_service = AmapWeatherService()

            print("  - 高德景点节点: 直接 HTTP 查询")
            print("  - 高德天气节点: 直接 HTTP 查询")
            print("  - 高德酒店节点: 直接 HTTP 查询")

            # 创建行程规划Agent(不需要工具)
            print("  - 创建行程规划Agent...")
            self.planner_agent = SimpleAgent(
                name="行程规划专家",
                llm=self.llm,
                system_prompt=PLANNER_AGENT_PROMPT
            )

            # LangGraph keeps orchestration durable while direct AMap services
            # provide research data without extra model calls.
            from .trip_planner_graph import TripPlanningGraph
            self.workflow = TripPlanningGraph(
                self,
                checkpoint_path=settings.langgraph_checkpoint_path or None,
            )

            print("✅ LangGraph 混合旅行规划系统初始化成功")
            print("   确定性数据节点: 景点、天气、酒店")
            print("   模型节点: 行程规划 Agent")

        except Exception as e:
            print(f"❌ 混合旅行规划系统初始化失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def plan_trip(self, request: TripRequest) -> TripPlan:
        """兼容旧接口：以已审批模式执行完整 LangGraph 工作流。"""
        try:
            print(f"\n{'='*60}")
            print("🚀 开始 LangGraph 混合工作流规划旅行...")
            print(f"目的地: {request.city}")
            print(f"日期: {request.start_date} 至 {request.end_date}")
            print(f"天数: {request.travel_days}天")
            print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            if request.selected_recommendations:
                print("已选推荐: " + "、".join(item.name for item in request.selected_recommendations))
            print(f"{'='*60}\n")

            trip_plan = self._get_workflow().run(request)

            print(f"{'='*60}")
            print(f"✅ 旅行计划生成完成!")
            print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            trip_plan = self._create_fallback_plan(request)
            report = self._validate_attraction_reliability(trip_plan, request.city)
            if not report.is_valid:
                reasons = "；".join(issue.reason for issue in report.issues[:5])
                raise RuntimeError(f"备用行程未通过 POI 可靠性校验：{reasons}") from e
            return trip_plan

    def _get_workflow(self):
        """延迟创建工作流，兼容单元测试通过 ``__new__`` 构造的实例。"""
        workflow = getattr(self, "workflow", None)
        if workflow is None:
            from .trip_planner_graph import TripPlanningGraph
            workflow = TripPlanningGraph(self)
            self.workflow = workflow
        return workflow

    def start_workflow(
        self,
        request: TripRequest,
        *,
        require_approval: bool = True,
        workflow_id: str | None = None,
    ) -> dict[str, Any]:
        """创建可持久化的规划工作流；默认在 Planning Brief 后暂停。"""
        return self._get_workflow().start(
            request,
            require_approval=require_approval,
            workflow_id=workflow_id,
        )

    def resume_workflow(self, workflow_id: str, approved: bool | None = None) -> dict[str, Any]:
        """审批或恢复先前中断的工作流。"""
        return self._get_workflow().resume(workflow_id, approved=approved)

    def get_workflow_status(self, workflow_id: str) -> dict[str, Any]:
        """读取 SQLite checkpoint 中的当前工作流状态。"""
        return self._get_workflow().status(workflow_id)

    def _verify_attraction_locations(self, trip_plan: TripPlan, city: str) -> POIValidationReport:
        """Replace model coordinates with exact, city-restricted AMap POIs.

        The LLM may copy example coordinates or invent a plausible coordinate.
        Map markers therefore use only a fresh AMap lookup. Unresolved places
        are retained only long enough to produce a structured validation issue;
        LangGraph then searches for a replacement and rebuilds the itinerary.
        """
        verified = 0
        unresolved = 0

        for day in trip_plan.days:
            for attraction in day.attractions:
                original_name = attraction.name
                resolved = self.poi_location_service.resolve(
                    original_name,
                    city,
                    attraction.address,
                )
                if resolved is None:
                    attraction.location = None
                    attraction.poi_id = ""
                    attraction.city = ""
                    attraction.district = ""
                    attraction.poi_type = ""
                    attraction.poi_typecode = ""
                    attraction.operational_status = "unknown"
                    attraction.data_source = ""
                    attraction.verified_at = ""
                    attraction.verification_confidence = 0
                    unresolved += 1
                    continue

                attraction.name = resolved.name
                attraction.address = resolved.address
                attraction.location = Location(
                    longitude=resolved.longitude,
                    latitude=resolved.latitude,
                )
                attraction.poi_id = resolved.poi_id
                attraction.city = resolved.city or city
                attraction.district = resolved.district
                attraction.poi_type = resolved.poi_type
                attraction.poi_typecode = resolved.poi_typecode
                attraction.operational_status = resolved.operational_status
                attraction.data_source = resolved.data_source or "amap"
                attraction.verified_at = resolved.verified_at or datetime.now(timezone.utc).isoformat()
                attraction.verification_confidence = resolved.confidence
                verified += 1

                # Keep the human-readable timeline consistent with the POI card.
                for event in day.schedule:
                    if event.item_type != "attraction":
                        continue
                    if event.title == original_name or event.title == resolved.name:
                        event.title = resolved.name
                        event.location = resolved.address

        report = self._validate_attraction_reliability(trip_plan, city)
        print(
            f"📌 高德地点核验完成: {verified} 个已核验, {unresolved} 个未匹配, "
            f"{len(report.issues)} 个可靠性问题"
        )
        return report

    def _validate_attraction_reliability(
        self,
        trip_plan: TripPlan,
        city: str,
    ) -> POIValidationReport:
        """Validate a plan already built from trusted AMap search results."""
        reliability_service = getattr(self, "poi_reliability_service", None)
        if reliability_service is None:
            reliability_service = POIReliabilityService()
            self.poi_reliability_service = reliability_service
        return reliability_service.validate_plan(trip_plan, city)

    def _apply_verified_hotels(
        self,
        trip_plan: TripPlan,
        candidates: list[dict[str, Any]],
        accommodation: str,
    ) -> None:
        """Replace model-created hotels with a deterministic AMap whitelist."""
        if not candidates:
            for day in trip_plan.days:
                day.hotel = None
            return
        for day in trip_plan.days:
            original = day.hotel
            original_key = self.poi_location_service._normalize(original.name if original else "")
            selected = next(
                (
                    item for item in candidates
                    if original_key
                    and (
                        self.poi_location_service._normalize(item.get("name")) == original_key
                        or original_key in self.poi_location_service._normalize(item.get("name"))
                        or self.poi_location_service._normalize(item.get("name")) in original_key
                    )
                ),
                candidates[0],
            )
            location = selected.get("location") or {}
            day.hotel = Hotel(
                name=str(selected.get("name") or "高德核验酒店"),
                address=str(selected.get("address") or trip_plan.city),
                location=Location(
                    longitude=float(location["longitude"]),
                    latitude=float(location["latitude"]),
                ) if "longitude" in location and "latitude" in location else None,
                price_range=original.price_range if original else "以平台实时价格为准",
                rating=original.rating if original else "以平台实时评分为准",
                distance=original.distance if original else "请以实时导航为准",
                type=original.type if original else accommodation,
                estimated_cost=original.estimated_cost if original else 0,
            )
    
    def _build_planner_query(self, request: TripRequest, attractions: str, weather: str, hotels: str = "") -> str:
        """构建行程规划查询"""
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**游客从实时推荐榜单中主动选择的地点:**
{self._format_selected_recommendations(request)}

**要求:**
1. 每天安排2-3个景点，并按地理位置就近组合
2. 每天必须包含早中晚三餐，并推荐一个具体酒店
3. schedule 必须覆盖当天所有景点、餐饮、移动路段和返回酒店，按时间从早到晚排序
4. 相邻地点之间必须有 transport 项，写清起点、终点、交通方式、预计分钟数和距离
5. 所有 start_time/end_time 使用 HH:MM，前后不得重叠，要给排队、步行与换乘预留时间
6. 只能使用“高德校验后的景点候选”中明确列出的地点，不得自行发明、改名或加入名单外景点
7. 景点必须原样复制候选中的 poi_id、city、district、poi_type、poi_typecode、location、operational_status、data_source、verified_at 和 verification_confidence
8. 优先安排游客主动选择的地点；除非日期、距离或营业条件明显冲突，否则不要替换
9. 酒店只能从“高德校验后的酒店候选”中选择；如果没有候选，hotel 返回 null
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query

    @staticmethod
    def _format_selected_recommendations(request: TripRequest) -> str:
        """将游客选择转换为规划 Agent 可直接理解的约束。"""
        if not request.selected_recommendations:
            return "无，由规划系统根据偏好推荐"
        return "\n".join(
            f"- {item.name}（{item.category}）：{item.reason or '游客主动选择'}"
            for item in request.selected_recommendations
        )
    
    def _parse_response_stages(
        self,
        response: str,
        request: TripRequest,
    ) -> tuple[TripPlan | None, TripPlan]:
        """
        解析Agent响应
        
        Args:
            response: Agent响应文本
            request: 原始请求
            
        Returns:
            旅行计划
        """
        try:
            # 尝试从响应中提取JSON
            # 查找JSON代码块
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "{" in response and "}" in response:
                # 直接查找JSON对象
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                raise ValueError("响应中未找到JSON数据")
            
            # 解析JSON
            data = json.loads(json_str)
            
            # 转换为TripPlan对象
            raw_trip_plan = TripPlan(**data)
            trip_plan = raw_trip_plan.model_copy(deep=True)
            for day in trip_plan.days:
                if day.schedule:
                    day.schedule.sort(key=lambda item: item.start_time)
                    if not self._schedule_has_no_overlap(day.schedule):
                        print(f"⚠️  第{day.day_index + 1}天时间轴有重叠或非法时间，已自动重建")
                        day.schedule = self._build_fallback_schedule(day)
                else:
                    day.schedule = self._build_fallback_schedule(day)
            
            return raw_trip_plan, trip_plan
            
        except Exception as e:
            print(f"⚠️  解析响应失败: {str(e)}")
            print(f"   将使用备用方案生成计划")
            return None, self._create_fallback_plan(request)

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """保留旧调用面；工作流使用分阶段接口同时保留模型原始输出。"""
        _, final_plan = self._parse_response_stages(response, request)
        return final_plan

    @staticmethod
    def _time_to_minutes(value: str) -> int | None:
        """将 HH:MM 转为分钟；非法时间返回 None。"""
        try:
            hour_text, minute_text = value.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except (AttributeError, TypeError, ValueError):
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return hour * 60 + minute

    @classmethod
    def _schedule_has_no_overlap(cls, schedule: List[TimelineItem]) -> bool:
        """确认时间轴有效、每项结束晚于开始且相邻项目不重叠。"""
        previous_end = -1
        for item in sorted(schedule, key=lambda event: event.start_time):
            start = cls._time_to_minutes(item.start_time)
            end = cls._time_to_minutes(item.end_time)
            if start is None or end is None or end <= start or start < previous_end:
                return False
            previous_end = end
        return True
    
    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """Create a truthful fallback from selected and AMap-verified POIs.

        A failed model response must never be presented as a successful plan
        containing names such as “北京景点1”. We recover with official POI
        data; if that is unavailable too, the request fails visibly.
        """
        from datetime import datetime, timedelta

        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        target_attractions = min(20, max(request.travel_days * 2, len(request.selected_recommendations)))
        poi_candidates = []
        seen_pois: set[str] = set()
        seen_poi_names: list[str] = []

        def append_poi(poi) -> None:
            if poi is None:
                return
            key = poi.poi_id or self.poi_location_service._normalize(poi.name)
            normalized_name = self.poi_location_service._normalize(poi.name)
            is_nested_duplicate = any(
                min(len(normalized_name), len(existing)) >= 4
                and (normalized_name.startswith(existing) or existing.startswith(normalized_name))
                for existing in seen_poi_names
            )
            if not key or key in seen_pois or is_nested_duplicate:
                return
            seen_pois.add(key)
            seen_poi_names.append(normalized_name)
            poi_candidates.append(poi)

        # Preserve the user's explicit choices first and attach official AMap data.
        selected_details = {
            self.poi_location_service._normalize(item.name): item
            for item in request.selected_recommendations
        }
        for item in request.selected_recommendations:
            append_poi(self.poi_location_service.resolve(item.name, request.city))

        preference_queries = [preference for preference in request.preferences if preference]
        discovery_queries = [*preference_queries, "旅游景点", "博物馆", "公园"]
        for query in discovery_queries:
            if len(poi_candidates) >= target_attractions:
                break
            added_for_query = 0
            for poi in self.poi_location_service.search(query, request.city, 25):
                before = len(poi_candidates)
                append_poi(poi)
                added_for_query += len(poi_candidates) - before
                if len(poi_candidates) >= target_attractions or added_for_query >= 3:
                    break

        # Long trips may need more than the diversity pass above can provide.
        if len(poi_candidates) < target_attractions:
            for query in discovery_queries:
                for poi in self.poi_location_service.search(query, request.city, 25):
                    append_poi(poi)
                    if len(poi_candidates) >= target_attractions:
                        break
                if len(poi_candidates) >= target_attractions:
                    break

        reliability_service = getattr(self, "poi_reliability_service", None)
        if reliability_service is None:
            reliability_service = POIReliabilityService()
            self.poi_reliability_service = reliability_service
        poi_candidates = reliability_service.order_by_proximity(
            reliability_service.filter_spatial_outliers(poi_candidates)
        )

        if not poi_candidates:
            raise RuntimeError("规划模型返回内容无效，且高德未返回可核验的景点；请稍后重新生成")

        if "豪华" in request.accommodation:
            hotel_query = "五星级酒店"
        elif "经济" in request.accommodation:
            hotel_query = "经济型酒店"
        else:
            hotel_query = "四星级酒店"
        hotels = list(self.poi_location_service.search(hotel_query, request.city, 12))
        if not hotels:
            hotels = list(self.poi_location_service.search("酒店", request.city, 8))
        restaurants = list(self.poi_location_service.search("餐厅", request.city, 25))
        if len(restaurants) < min(9, request.travel_days * 3):
            existing_restaurants = {item.poi_id for item in restaurants}
            restaurants.extend(
                item for item in self.poi_location_service.search("美食", request.city, 25)
                if item.poi_id not in existing_restaurants
            )

        hotel_cost = 260 if "经济" in request.accommodation else 850 if "豪华" in request.accommodation else 450
        meal_costs = {"breakfast": 30, "lunch": 70, "dinner": 100}
        meal_labels = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
        # Prefer one centrally located hotel to unnecessary hotel changes.
        trip_center_longitude = sum(item.longitude for item in poi_candidates) / len(poi_candidates)
        trip_center_latitude = sum(item.latitude for item in poi_candidates) / len(poi_candidates)
        trip_hotel = min(
            hotels,
            key=lambda item: (
                (item.longitude - trip_center_longitude) ** 2
                + (item.latitude - trip_center_latitude) ** 2
            ),
        ) if hotels else None

        days: List[DayPlan] = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            day_pois = poi_candidates[i * 2:(i + 1) * 2]
            if not day_pois:
                day_pois = [poi_candidates[i % len(poi_candidates)]]

            attractions = []
            for poi in day_pois:
                selected = selected_details.get(self.poi_location_service._normalize(poi.name))
                attractions.append(Attraction(
                    name=poi.name,
                    address=poi.address or request.city,
                    location=Location(longitude=poi.longitude, latitude=poi.latitude),
                    poi_id=poi.poi_id,
                    city=poi.city or request.city,
                    district=poi.district,
                    poi_type=poi.poi_type,
                    poi_typecode=poi.poi_typecode,
                    operational_status=poi.operational_status,
                    data_source=poi.data_source or "amap",
                    verified_at=poi.verified_at or datetime.now(timezone.utc).isoformat(),
                    verification_confidence=poi.confidence,
                    visit_duration=120,
                    description=(selected.reason if selected else "高德地图已核验的本地景点"),
                    category=(selected.category if selected else "景点"),
                    ticket_price=0,
                ))

            day_hotel_poi = trip_hotel
            hotel = Hotel(
                name=day_hotel_poi.name,
                address=day_hotel_poi.address or request.city,
                location=Location(longitude=day_hotel_poi.longitude, latitude=day_hotel_poi.latitude),
                price_range=f"约{hotel_cost}元/晚",
                rating="以平台实时评分为准",
                distance="请以实时导航为准",
                type=request.accommodation,
                estimated_cost=hotel_cost,
            ) if day_hotel_poi else None

            meals = []
            for meal_index, meal_type in enumerate(("breakfast", "lunch", "dinner")):
                restaurant = restaurants[(i * 3 + meal_index) % len(restaurants)] if restaurants else None
                meals.append(Meal(
                    type=meal_type,
                    name=restaurant.name if restaurant else f"当地{meal_labels[meal_type]}（待选择）",
                    address=restaurant.address if restaurant else None,
                    location=(Location(longitude=restaurant.longitude, latitude=restaurant.latitude) if restaurant else None),
                    description="高德地图推荐餐饮，请结合营业时间和实时评分选择" if restaurant else "请在景点附近选择营业中的餐厅",
                    estimated_cost=meal_costs[meal_type],
                ))

            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天：游览{'、'.join(item.name for item in attractions)}",
                transportation=request.transportation,
                accommodation=request.accommodation,
                hotel=hotel,
                attractions=attractions,
                meals=meals,
            )
            day_plan.schedule = self._build_fallback_schedule(day_plan)
            days.append(day_plan)

        total_hotels = hotel_cost * max(0, request.travel_days - 1) if hotels else 0
        total_meals = sum(meal_costs.values()) * request.travel_days
        total_transportation = 40 * request.travel_days
        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=(
                "模型生成结果不完整，本行程已自动使用高德真实 POI 恢复。"
                "请在出发前核对景点开放时间、餐厅营业状态和酒店余房。"
            ),
            budget=Budget(
                total_attractions=0,
                total_hotels=total_hotels,
                total_meals=total_meals,
                total_transportation=total_transportation,
                total=total_hotels + total_meals + total_transportation,
            ),
        )

    @staticmethod
    def _build_fallback_schedule(day: DayPlan) -> List[TimelineItem]:
        """当模型没有返回 schedule 时，根据景点和餐饮生成可用时间轴。"""
        schedule: List[TimelineItem] = []
        meals = {meal.type: meal for meal in day.meals}

        def add_meal(meal_type: str, start: str, end: str) -> str:
            meal = meals.get(meal_type)
            if not meal:
                return ""
            meal_labels = {
                "breakfast": "早餐",
                "lunch": "午餐",
                "dinner": "晚餐",
                "snack": "加餐",
            }
            schedule.append(TimelineItem(
                start_time=start,
                end_time=end,
                item_type="meal",
                title=f"{meal_labels.get(meal_type, '用餐')} · {meal.name}",
                location=meal.address or meal.name,
                description=meal.description or "预留充足用餐时间",
                duration_minutes=40 if meal_type == "breakfast" else 60,
                estimated_cost=meal.estimated_cost,
            ))
            return meal.name

        breakfast_location = add_meal("breakfast", "08:00", "08:40")
        attraction_slots = [("09:10", "11:30"), ("13:30", "15:50"), ("16:20", "18:00")]
        previous = breakfast_location or (day.hotel.name if day.hotel else day.accommodation)
        transport_slots = [("08:40", "09:10"), ("13:00", "13:30"), ("15:50", "16:20")]

        for index, attraction in enumerate(day.attractions[:3]):
            start, end = attraction_slots[index]
            route_start, route_end = transport_slots[index]
            schedule.append(TimelineItem(
                start_time=route_start,
                end_time=route_end,
                item_type="transport",
                title=f"前往{attraction.name}",
                from_location=previous,
                to_location=attraction.name,
                transport_mode=day.transportation,
                duration_minutes=30,
                description=f"从{previous}前往{attraction.name}，请以实时导航为准",
            ))
            schedule.append(TimelineItem(
                start_time=start,
                end_time=end,
                item_type="attraction",
                title=attraction.name,
                location=attraction.address,
                description=attraction.description,
                duration_minutes=attraction.visit_duration,
                estimated_cost=attraction.ticket_price,
            ))
            previous = attraction.name
            if index == 0:
                previous = add_meal("lunch", "12:00", "13:00") or previous

        previous = add_meal("dinner", "18:30", "19:30") or previous
        if day.hotel:
            schedule.append(TimelineItem(
                start_time="19:30",
                end_time="20:00",
                item_type="transport",
                title="返回酒店",
                from_location=previous,
                to_location=day.hotel.name,
                transport_mode=day.transportation,
                duration_minutes=30,
                description="结束当天行程，返回酒店休息",
            ))
            schedule.append(TimelineItem(
                start_time="20:00",
                end_time="21:00",
                item_type="hotel",
                title=f"入住 · {day.hotel.name}",
                location=day.hotel.address,
                description="办理入住并休息",
                duration_minutes=60,
            ))

        return sorted(schedule, key=lambda item: item.start_time)


# 全局旅行规划系统实例（保留变量名以兼容既有导入）
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取混合旅行规划系统实例（单例模式）。"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner
