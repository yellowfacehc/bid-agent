#!/usr/bin/env python3
"""
重庆市政府采购网爬虫
=====================
网站: https://www.ccgp-chongqing.gov.cn/
API:  /yw-gateway/zcjquery/v1/website-content-aggregations/front
"""

import logging
import time
from datetime import datetime
from typing import List
from urllib.parse import quote

import requests

from crawlers.base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

API_URL = "https://www.ccgp-chongqing.gov.cn/yw-gateway/zcjquery/v1/website-content-aggregations/front"
BASE_URL = "https://www.ccgp-chongqing.gov.cn"

# 公告类型映射
TYPE_MAP = {
    "aggregation-notice": "采购公告",
    "aggregation-tender": "招标公告",
    "aggregation-success": "中标公告",
    "aggregation-contractpublish": "合同公告",
    "aggregation-correct": "更正公告",
    "aggregation-other": "其他公告",
}


class CQCCGPCrawler(BaseCrawler):
    """重庆市政府采购网爬虫"""

    def __init__(self):
        super().__init__(name="重庆市政府采购网")

    def search(
        self,
        keyword: str,
        days: int = 20,
        max_pages: int = 5,
        region: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[BidItem]:
        """
        搜索重庆政府采购公告

        Args:
            keyword: 搜索关键词
            days: 最近N天
            max_pages: 最大页数
            region: 区县名称 (如 "沙坪坝区"), 空字符串表示全重庆
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        """
        # 日期处理
        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            start_dt, end_dt = self.get_date_range(days)

        # API使用毫秒时间戳
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)

        headers = {
            "User-Agent": self._get_random_ua(),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{BASE_URL}/search/{quote(keyword)}",
            "Origin": BASE_URL,
        }

        all_items: List[BidItem] = []

        for page in range(1, max_pages + 1):
            params = {
                "title": keyword,
                "typeCode": "",
                "publicityStartTime": str(start_ts),
                "publicityEndTime": str(end_ts),
                "pageNum": str(page),
                "pageSize": "10",
                "searchCount": "true",
            }

            try:
                resp = self.session.get(API_URL, params=params, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                records = data.get("datas", [])
                if not records:
                    logger.info(f"[{self.name}] 第{page}页无数据，停止")
                    break

                for rec in records:
                    item_region = rec.get("regionName", "")
                    # 地区筛选
                    if region and region not in item_region:
                        continue

                    pub_time = rec.get("publishTime")
                    if pub_time:
                        pub_date = datetime.fromtimestamp(pub_time / 1000).strftime("%Y-%m-%d")
                    else:
                        pub_date = ""

                    type_code = rec.get("typeCode", "")
                    category = TYPE_MAP.get(type_code, rec.get("typeName", "其他"))

                    # 构建详情链接
                    item_id = rec.get("id", "")
                    biz_type = rec.get("bizType", "")
                    detail_url = f"{BASE_URL}/detail/{biz_type}/{item_id}" if item_id else ""

                    item = BidItem(
                        title=rec.get("title", ""),
                        url=detail_url,
                        publish_date=pub_date,
                        region=item_region or "重庆市",
                        category=category,
                        buyer=rec.get("orgName", ""),
                        agency="",
                        source=self.name,
                        project_code=rec.get("projectCode", ""),
                    )
                    all_items.append(item)

                logger.info(f"[{self.name}] 第{page}页获取 {len(records)} 条")
                time.sleep(0.2)

            except Exception as e:
                logger.error(f"[{self.name}] 第{page}页请求失败: {e}")
                break

        return all_items
