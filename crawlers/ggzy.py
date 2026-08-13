"""
全国公共资源交易平台爬虫 (ggzy.gov.cn)

平台已升级为 Vue.js + 验证码系统, 数据接口:
  - 旧接口: http://deal.ggzy.gov.cn/ds/deal/dealList_find.jsp (已废弃, 返回502)
  - 新接口: /information/pubTradingInfo/getTradList (需验证码token)

本模块尝试新旧两个接口, 若均不可用则返回空列表并记录警告。
"""

import json
import logging
from datetime import timedelta
from typing import List

from .base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

# 新旧两个接口端点
SEARCH_URLS = [
    "http://deal.ggzy.gov.cn/ds/deal/dealList_find.jsp",        # 旧接口
    "http://www.ggzy.gov.cn/information/pubTradingInfo/getTradList",  # 新接口
]


class GGZYCrawler(BaseCrawler):
    """全国公共资源交易平台爬虫"""

    def __init__(self):
        super().__init__(name="全国公共资源交易平台")
        self._working_url = None  # 缓存可用的 URL

    def search(self, keyword: str, days: int = 20, max_pages: int = 5, region: str = "", start_date: str = "", end_date: str = "") -> List[BidItem]:
        """
        搜索公共资源交易公告

        尝试新旧两个接口端点。旧接口限制单次查询时间跨度不超过10天,
        当 days > 10 时自动分段查询。
        """
        # 确定可用的 URL
        search_url = self._get_working_url()
        if not search_url:
            logger.warning(
                f"[{self.name}] 所有接口端点均不可用 (旧接口已废弃502, "
                f"新接口需验证码token)。跳过此平台。"
            )
            return []

        start_date, end_date = self.get_date_range(days)
        all_items: List[BidItem] = []

        # 分段查询 (旧接口限制10天, 新接口无此限制但保守分段)
        segment_days = 10
        current_start = start_date

        while current_start <= end_date:
            current_end = min(current_start + timedelta(days=segment_days - 1), end_date)
            start_str = current_start.strftime("%Y-%m-%d")
            end_str = current_end.strftime("%Y-%m-%d")

            logger.info(
                f"[{self.name}] 查询时间段: {start_str} ~ {end_str}, 关键词='{keyword}'"
            )

            for page in range(1, max_pages + 1):
                items = self._search_single_page(keyword, start_str, end_str, page, search_url)
                if not items:
                    break
                all_items.extend(items)
                if len(items) < 20:
                    break

            current_start = current_end + timedelta(days=1)

        logger.info(f"[{self.name}] 共获取 {len(all_items)} 条记录")
        return all_items

    def _get_working_url(self) -> str:
        """测试并返回可用的搜索 URL"""
        if self._working_url:
            return self._working_url

        for url in SEARCH_URLS:
            try:
                # 快速测试 (发送一个最小请求)
                headers = self._get_random_headers()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                test_data = {
                    "TIMEBEGIN": "2026-08-13",
                    "TIMEEND": "2026-08-13",
                    "PAGENUMBER": "1",
                    "FINDTXT": "",
                    "DEAL_CLASSIFY": "00",
                    "DEAL_PROVINCE": "0",
                    "DEAL_CITY": "0",
                    "DEAL_STAGE": "0000",
                    "DEAL_PLATFORM": "0",
                    "BID_PLATFORM": "0",
                    "DEAL_TRADE": "0",
                    "isShowAll": "1",
                }
                import requests as req
                resp = req.post(url, data=test_data, headers=headers, timeout=10)
                if resp.status_code == 200:
                    # 检查是否返回 JSON
                    try:
                        resp.json()
                        self._working_url = url
                        logger.info(f"[{self.name}] 使用接口: {url}")
                        return url
                    except (json.JSONDecodeError, ValueError):
                        pass
            except Exception:
                continue

        return ""

    def _search_single_page(
        self, keyword: str, start_date: str, end_date: str, page: int, search_url: str
    ) -> List[BidItem]:
        """查询单页数据"""
        params = {
            "TIMEBEGIN_SHOW": start_date,
            "TIMEEND_SHOW": end_date,
            "TIMEBEGIN": start_date,
            "TIMEEND": end_date,
            "SOURCE_TYPE": "1",
            "DEAL_TIME": "01",
            "DEAL_CLASSIFY": "00",
            "DEAL_STAGE": "0000",
            "DEAL_PROVINCE": "0",
            "DEAL_CITY": "0",
            "DEAL_PLATFORM": "0",
            "BID_PLATFORM": "0",
            "DEAL_TRADE": "0",
            "isShowAll": "1",
            "PAGENUMBER": str(page),
            "FINDTXT": keyword,
        }

        headers = self._get_random_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = "http://www.ggzy.gov.cn/deal/dealList.html"
        headers["X-Requested-With"] = "XMLHttpRequest"

        resp = self._request_with_retry(
            search_url, method="POST", data=params, headers=headers
        )

        if not resp:
            return []

        return self._parse_json_response(resp.text)

    def _parse_json_response(self, text: str) -> List[BidItem]:
        """解析 JSON 响应"""
        items: List[BidItem] = []
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.debug(f"[{self.name}] JSON解析失败, 响应前200字符: {text[:200]}")
            return items

        records = data if isinstance(data, list) else data.get("data", data.get("list", []))
        if isinstance(records, dict):
            records = records.get("list", [])

        if not isinstance(records, list):
            return items

        for record in records:
            try:
                item = BidItem(source=self.name)
                item.title = record.get("title", "") or record.get("titleShow", "")
                item.publish_date = record.get("timeShow", "") or record.get("time", "")
                parsed = self._parse_date(item.publish_date)
                if parsed:
                    item.publish_date = parsed

                item.region = record.get("districtShow", "") or record.get("district", "")
                item.category = record.get("stageName", "") or record.get("stageShow", "")
                classify = record.get("classifyShow", "") or record.get("classify", "")
                if classify:
                    item.category = f"{item.category} - {classify}" if item.category else classify

                url = record.get("url", "") or record.get("detailUrl", "")
                if url and not url.startswith("http"):
                    url = "http://www.ggzy.gov.cn" + url if url.startswith("/") else "http://" + url
                item.url = url

                platform = record.get("platformName", "")
                if platform:
                    item.buyer = platform

                if item.title and item.url:
                    items.append(item)
            except Exception:
                continue

        return items
