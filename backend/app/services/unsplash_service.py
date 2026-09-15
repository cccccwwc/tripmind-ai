"""景点图片服务（高德优先，Unsplash 兜底）。"""

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse
import requests
from typing import List, Optional, Tuple
from ..config import get_settings

class UnsplashService:
    """Unsplash图片服务类"""
    
    def __init__(self):
        """初始化服务"""
        settings = get_settings()
        self.access_key = settings.unsplash_access_key
        self.amap_api_key = settings.amap_api_key
        self.tavily_api_key = settings.tavily_api_key
        self.base_url = "https://api.unsplash.com"
        self._verified_photo_urls: dict[tuple[str, str], List[str]] = {}
    
    def search_photos(self, query: str, per_page: int = 5) -> List[dict]:
        """
        搜索图片
        
        Args:
            query: 搜索关键词
            per_page: 每页数量
            
        Returns:
            图片列表
        """
        try:
            url = f"{self.base_url}/search/photos"
            params = {
                "query": query,
                "per_page": per_page,
                "client_id": self.access_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            # 提取图片URL
            photos = []
            for photo in results:
                photos.append({
                    "id": photo.get("id"),
                    "url": photo.get("urls", {}).get("regular"),
                    "thumb": photo.get("urls", {}).get("thumb"),
                    "description": photo.get("description") or photo.get("alt_description"),
                    "photographer": photo.get("user", {}).get("name")
                })
            
            return photos
            
        except Exception as e:
            print(f"❌ Unsplash搜索失败: {str(e)}")
            return []
    
    def get_photo_url(self, query: str) -> Optional[str]:
        """
        获取单张图片URL

        Args:
            query: 搜索关键词

        Returns:
            图片URL
        """
        photos = self.search_photos(query, per_page=1)
        if photos:
            return photos[0].get("url")
        return None

    @staticmethod
    def _clean_place_name(name: str) -> str:
        """去掉行程文案和预约说明，保留可用于 POI 精确匹配的景点名。"""
        cleaned = re.sub(r"[（(].*?[）)]", "", name or "")
        cleaned = re.sub(r"^(?:前往|抵达|游览|参观|打卡|漫步|探索)\s*", "", cleaned)
        cleaned = re.split(r"[·—–｜|/：:]", cleaned, maxsplit=1)[0]
        return cleaned.strip()

    @staticmethod
    def _normalized_place_name(name: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (name or "").lower())

    @classmethod
    def _poi_match_score(cls, query: str, poi: dict, city: str = "", address: str = "") -> float:
        """计算 POI 与行程景点的匹配度，避免直接采用搜索结果第一项。"""
        query_name = cls._normalized_place_name(cls._clean_place_name(query))
        poi_name = cls._normalized_place_name(poi.get("name", ""))
        if not query_name or not poi_name:
            return 0.0

        if query_name == poi_name:
            name_score = 1.0
        elif query_name in poi_name or poi_name in query_name:
            name_score = 0.9 * min(len(query_name), len(poi_name)) / max(len(query_name), len(poi_name)) + 0.1
        else:
            name_score = SequenceMatcher(None, query_name, poi_name).ratio()

        haystack = cls._normalized_place_name(
            " ".join(str(poi.get(key, "")) for key in ("address", "pname", "cityname", "adname"))
        )
        city_name = cls._normalized_place_name(city)
        address_name = cls._normalized_place_name(address)
        city_bonus = 0.06 if city_name and city_name in haystack else 0.0
        address_bonus = 0.04 if address_name and any(
            token in haystack for token in (address_name, address_name[-6:]) if len(token) >= 4
        ) else 0.0
        return min(1.0, name_score + city_bonus + address_bonus)

    def get_attraction_photo(
        self,
        name: str,
        city: str = "",
        address: str = "",
        index: int = 0,
    ) -> Optional[Tuple[bytes, str]]:
        """搜索景点图片并由后端下载，避免浏览器直连图片 CDN 失败。"""
        # Tavily 的图片描述可用于核对图片内容；没有可信结果时再回退高德。
        photo_urls = self._get_tavily_photo_urls(name, city)
        photo_urls.extend(self._get_amap_photo_urls(name, city, address))

        # Unsplash 对很长、带括号的中文查询有时会返回 410，先简化名称再搜索。
        if not photo_urls and not re.search(r"[\u4e00-\u9fff]", name):
            clean_name = self._clean_place_name(name)
            candidates = [clean_name, name]
            seen = set()
            for candidate in candidates:
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                photo_url = self.get_photo_url(f"{candidate} China landmark")
                if photo_url:
                    photo_urls.append(photo_url)
                    break

        if not photo_urls:
            return None

        # 去重后从用户选择的位置开始轮换；某个源加载失败时自动尝试下一张。
        photo_urls = list(dict.fromkeys(photo_urls))
        start_index = max(0, index) % len(photo_urls)
        photo_urls = photo_urls[start_index:] + photo_urls[:start_index]

        for photo_url in photo_urls:
            if not self._is_public_image_url(photo_url):
                continue
            try:
                response = requests.get(
                    photo_url,
                    headers={"User-Agent": "TripMind-AI/1.0"},
                    timeout=(5, 20),
                )
                response.raise_for_status()
                content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
                if not content_type.startswith("image/") or len(response.content) < 8_000:
                    continue
                return response.content, content_type
            except requests.RequestException as e:
                print(f"❌ 景点图片下载失败，尝试下一来源: {str(e)}")
        return None

    @staticmethod
    def _is_public_image_url(url: str) -> bool:
        """仅代理 Tavily/高德返回的公开 HTTP(S) 图片地址。"""
        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower()
            return (
                parsed.scheme in {"http", "https"}
                and bool(hostname)
                and hostname not in {"localhost", "127.0.0.1", "::1"}
                and not hostname.endswith(".local")
            )
        except ValueError:
            return False

    def _get_tavily_photo_urls(self, name: str, city: str = "") -> List[str]:
        """读取批量搜索阶段已经通过图片描述核验的 URL。"""
        key = (
            self._normalized_place_name(city),
            self._normalized_place_name(self._clean_place_name(name)),
        )
        return list(self._verified_photo_urls.get(key, []))

    def prepare_attraction_photos(self, names: List[str], city: str = "") -> int:
        """一次 Tavily 请求批量预热景点图片，避免每个景点分别消耗搜索额度。"""
        if not self.tavily_api_key:
            return 0

        clean_names = []
        seen = set()
        for name in names[:18]:
            clean_name = self._clean_place_name(name)
            normalized = self._normalized_place_name(clean_name)
            if clean_name and normalized and normalized not in seen:
                clean_names.append((clean_name, normalized))
                seen.add(normalized)
        if not clean_names:
            return 0

        try:
            response = requests.post(
                "https://api.tavily.com/search",
                headers={
                    "Authorization": f"Bearer {self.tavily_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": f"{city}景点实景照片：" + "、".join(item[0] for item in clean_names),
                    "topic": "general",
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_images": True,
                    "include_image_descriptions": True,
                },
                timeout=(6, 25),
            )
            response.raise_for_status()
            images = response.json().get("images") or []
            prepared = 0
            for image in images:
                if not isinstance(image, dict):
                    continue
                url = str(image.get("url") or "").strip()
                description = self._normalized_place_name(str(image.get("description") or ""))
                if not url or not description or not self._is_public_image_url(url):
                    continue
                matches = [item for item in clean_names if item[1] in description]
                if not matches:
                    continue
                # 若描述同时出现多个地点，优先采用名称更具体的一个。
                clean_name, normalized_name = max(matches, key=lambda item: len(item[1]))
                key = (self._normalized_place_name(city), normalized_name)
                urls = self._verified_photo_urls.setdefault(key, [])
                if url not in urls and len(urls) < 3:
                    urls.append(url)
                    prepared += 1
            return prepared
        except (requests.RequestException, ValueError) as e:
            print(f"⚠️ Tavily 景点图片搜索失败，将回退高德: {str(e)}")
            return 0

    def _get_amap_photo_urls(self, name: str, city: str = "", address: str = "") -> List[str]:
        """从高德中选取最匹配 POI 的多张照片，供前端按需切换。"""
        if not self.amap_api_key:
            return []

        try:
            params = {
                "key": self.amap_api_key,
                "keywords": self._clean_place_name(name),
                "offset": 10,
                "page": 1,
                "extensions": "all",
            }
            if city:
                params.update({"city": city, "citylimit": "true"})

            response = requests.get(
                "https://restapi.amap.com/v3/place/text",
                params=params,
                timeout=(5, 15),
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "1":
                return []

            candidates = []
            for poi in data.get("pois", []):
                photos = poi.get("photos") or []
                if not photos:
                    continue
                score = self._poi_match_score(name, poi, city, address)
                candidates.append((score, poi, photos))

            if not candidates:
                return []

            score, poi, photos = max(candidates, key=lambda item: item[0])
            if score < 0.72:
                print(
                    f"⚠️ 未采用低匹配度景点图片: 查询={name}, "
                    f"候选={poi.get('name', '')}, 匹配度={score:.2f}"
                )
                return []

            return [
                str(photo.get("url"))
                for photo in photos[:8]
                if photo.get("url")
            ]
        except (requests.RequestException, ValueError) as e:
            print(f"❌ 高德景点图片搜索失败: {str(e)}")
        return []


# 全局服务实例
_unsplash_service = None


def get_unsplash_service() -> UnsplashService:
    """获取Unsplash服务实例(单例模式)"""
    global _unsplash_service
    
    if _unsplash_service is None:
        _unsplash_service = UnsplashService()
    
    return _unsplash_service
