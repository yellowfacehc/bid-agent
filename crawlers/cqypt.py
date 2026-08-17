#!/usr/bin/env python3
"""
重庆市政府采购云平台爬虫
=========================
网站: https://xj.ccgp-chongqing.gov.cn/
API:  /yptjc-gateway/zcjcpcenter/v1/public/package-text/query
"""

import logging
import time
from datetime import datetime
from typing import List
from urllib.parse import quote

import requests

from crawlers.base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

API_URL = "https://www.ccgp-chongqing.gov.cn/yptjc-gateway/zcjcpcenter/v1/public/package-text/query"
BASE_URL = "https://xj.ccgp-chongqing.gov.cn"


class CQYPTCrawler(BaseCrawler):
    """重庆市政府采购云平台爬虫"""

    def __init__(self):
        super().__init__(name="重庆市政府采购云平台")

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
            "Referer": f"{BASE_URL}/ge/list?keyword={quote(keyword)}",
            "Origin": "https://www.ccgp-chongqing.gov.cn",
        }

        all_items: List[BidItem] = []

        for page in range(1, max_pages + 1):
            params = {
                "noticeName": keyword,
                "pageIndex": str(page),
                "pageSize": "12",
                "belongToGPW": "false",
                "startTime": str(start_ts),
                "endTime": str(end_ts),
                "__platDomain__": "xj.ccgp-chongqing.gov.cn",
            }

            try:
                resp = self.session.get(API_URL, params=params, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                # 此API直接返回数组
                records = data if isinstance(data, list) else data.get("datas", [])
                if not records:
                    logger.info(f"[{self.name}] 第{page}页无数据，停止")
                    break

                for rec in records:
                    pub_time = rec.get("publishTime")
                    if pub_time:
                        pub_date = datetime.fromtimestamp(pub_time / 1000).strftime("%Y-%m-%d")
                    else:
                        pub_date = ""

                    # 采购方式映射
                    purchase_way = rec.get("purchaseWayType", 0)
                    way_map = {1: "公开招标", 2: "邀请招标", 3: "竞争性谈判", 4: "竞争性磋商", 5: "询价", 6: "单一来源"}
                    category = way_map.get(purchase_way, "网上竞采")

                    # 构建详情链接: 优先使用 noticeAddress，否则按 platType 生成
                    detail_url = rec.get("noticeAddress", "")
                    if not detail_url:
                        rec_id = rec.get("id", "")
                        enquiry_no = rec.get("enquiryNo", "")
                        plat_type = rec.get("platType", 0)
                        if plat_type == 3:
                            # GMSOFT 平台内部链接
                            detail_url = f"{BASE_URL}/ge/notice/view-notice?noticeId={rec_id}" if rec_id else ""
                        elif plat_type == 2:
                            # 猪八戒平台
                            detail_url = f"https://chinazhyc.zbj.com/detailsDemand?id={enquiry_no}" if enquiry_no else ""
                        elif plat_type == 1:
                            # 政采云平台
                            detail_url = f"https://www.zcygov.cn/bidding/detail?requisitionId={enquiry_no}&type=BIDDING_INVITATION&changeCode=509900" if enquiry_no else ""
                        else:
                            detail_url = f"{BASE_URL}/ge/notice/view-notice?noticeId={rec_id}" if rec_id else ""

                    item = BidItem(
                        title=rec.get("noticeName", ""),
                        url=detail_url,
                        publish_date=pub_date,
                        region="重庆市",
                        category=category,
                        buyer=rec.get("buyers", ""),
                        agency=rec.get("stockOrgName", ""),
                        source=self.name,
                        project_code=rec.get("enquiryNo", ""),
                    )
                    all_items.append(item)

                logger.info(f"[{self.name}] 第{page}页获取 {len(records)} 条")
                time.sleep(0.3)

            except Exception as e:
                logger.error(f"[{self.name}] 第{page}页请求失败: {e}")
                break

        return all_items
