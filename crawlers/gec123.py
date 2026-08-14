#!/usr/bin/env python3
"""
gec123 平台爬虫（通用）
========================
支持两个站点:
  1. 政企行业采购网 (www.gec123.com)  - publishSite=1
  2. 九龙坡区小额平台 (cqjlp.gec123.com) - publishSite=2

API: /xcj-gateway/api/v1/notices/stable
"""

import logging
import time
from datetime import datetime
from typing import List
from urllib.parse import quote

import requests

from crawlers.base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

# noticeType 映射
NOTICE_TYPE_MAP = {
    100: "采购公告",
    200: "结果公告",
    300: "成交公告",
    400: "变更公告",
    500: "其他公告",
}


class GEC123Crawler(BaseCrawler):
    """gec123平台通用爬虫"""

    def __init__(self, site_name: str, plat_domain: str, publish_site: str, api_base: str):
        """
        Args:
            site_name: 站点显示名称
            plat_domain: __platDomain__ 参数值
            publish_site: publishSite 参数值
            api_base: API基础URL (如 https://www.gec123.com 或 https://qypt.gec123.com)
        """
        super().__init__(name=site_name)
        self.plat_domain = plat_domain
        self.publish_site = publish_site
        self.api_url = f"{api_base}/xcj-gateway/api/v1/notices/stable"
        self.front_base = f"https://{plat_domain}"

    def search(
        self,
        keyword: str,
        days: int = 20,
        max_pages: int = 5,
        region: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[BidItem]:
        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            start_dt, end_dt = self.get_date_range(days)

        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)

        headers = {
            "User-Agent": self._get_random_ua(),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.front_base}/notices/list?keyword={quote(keyword)}",
            "Origin": self.front_base,
        }

        all_items: List[BidItem] = []

        for page in range(1, max_pages + 1):
            params = {
                "keyword": keyword,
                "pi": str(page),
                "ps": "12",
                "publishSite": self.publish_site,
                "sourceType": "2,6",
                "startTime": str(start_ts),
                "endTime": str(end_ts),
                "__platDomain__": self.plat_domain,
            }

            try:
                resp = self.session.get(self.api_url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                records = data.get("notices", [])
                if not records:
                    logger.info(f"[{self.name}] 第{page}页无数据，停止")
                    break

                for rec in records:
                    # 地区筛选
                    item_district = rec.get("districtName", "")
                    if region and region not in item_district:
                        continue

                    issue_time = rec.get("issueTime")
                    if issue_time:
                        pub_date = datetime.fromtimestamp(issue_time / 1000).strftime("%Y-%m-%d")
                    else:
                        pub_date = ""

                    notice_type = rec.get("noticeType", 500)
                    category = NOTICE_TYPE_MAP.get(notice_type, "其他公告")

                    # 构建详情链接 (RESTful路径参数格式)
                    rec_id = rec.get("id", "")
                    detail_url = f"{self.front_base}/notices/detail/{rec_id}" if rec_id else ""

                    item = BidItem(
                        title=rec.get("title", ""),
                        url=detail_url,
                        publish_date=pub_date,
                        region=item_district or "重庆市",
                        category=category,
                        buyer=rec.get("buyerName", "") or rec.get("creatorOrgName", ""),
                        agency=rec.get("creatorOrgName", ""),
                        source=self.name,
                        project_code=rec.get("projectCode", ""),
                    )
                    all_items.append(item)

                logger.info(f"[{self.name}] 第{page}页获取 {len(records)} 条")
                time.sleep(0.3)

            except Exception as e:
                logger.error(f"[{self.name}] 第{page}页请求失败: {e}")
                break

        return all_items
