#!/usr/bin/env python3
"""
重庆市政府采购网爬虫
=====================
网站: https://www.ccgp-chongqing.gov.cn/
API:  /yw-gateway/zcjquery/v1/website-content-aggregations/front

关键修复:
  1. 使用 _safe_get() 替代直接 session.get() - 自动SSL降级+重试
  2. 使用 _get_full_headers() - 完整浏览器请求头，绕过WAF
  3. 记录 last_error - 便于调试
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
    "aggregation-complainthandle": "投诉处理",
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
        # 日期处理
        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            start_dt, end_dt = self.get_date_range(days)

        # API使用毫秒时间戳
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)

        # 客户端日期过滤范围（API可能返回范围外的数据）
        client_start = start_dt.strftime("%Y-%m-%d")
        client_end = end_dt.strftime("%Y-%m-%d")

        # 使用完整的浏览器请求头（关键修复）
        keyword_encoded = quote(keyword)
        headers = self._get_full_headers(
            referer=f"{BASE_URL}/search/{keyword_encoded}",
            origin=BASE_URL,
            accept_json=True,
        )

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
                # 使用 _safe_get 替代直接 session.get（关键修复）
                # 首页用5秒超时快速失败，避免海外服务器长时间等待不可达的政府网站
                resp = self._safe_get(API_URL, params=params, headers=headers, timeout=5)
                if resp is None:
                    logger.error(f"[{self.name}] 第{page}页请求失败: {self.last_error}")
                    break

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

                    # 客户端日期过滤: 确保结果在用户指定范围内
                    if pub_date and client_start and client_end:
                        try:
                            item_date = datetime.strptime(pub_date, "%Y-%m-%d")
                            range_start = datetime.strptime(client_start, "%Y-%m-%d")
                            range_end = datetime.strptime(client_end, "%Y-%m-%d")
                            if not (range_start <= item_date <= range_end):
                                logger.debug(
                                    f"[{self.name}] 日期过滤: 排除 {pub_date} "
                                    f"(范围: {client_start} ~ {client_end})"
                                )
                                continue
                        except ValueError:
                            pass

                    type_code = rec.get("typeCode", "")
                    category = TYPE_MAP.get(type_code, rec.get("typeName", "其他"))

                    # 构建详情链接
                    # 官方网站使用 bizId(数字ID) 而非 id(哈希) 构造URL
                    # URL格式根据typeCode不同而不同:
                    #   采购/招标/中标/更正/其他公告 → /info-notice/procument-notice-detail/{bizId}
                    #   投诉处理 → /info-notice/complaint-list-detail/{bizId}
                    #   合同公告 → /stock-resources-front/performanceNoticeView?id={bizId}
                    biz_id = rec.get("bizId", "")
                    item_id = rec.get("id", "")

                    # 优先使用API返回的完整URL字段
                    detail_url = (
                        rec.get("url", "")
                        or rec.get("detailUrl", "")
                        or rec.get("linkUrl", "")
                    )

                    if not detail_url and biz_id:
                        if type_code == "aggregation-complainthandle":
                            # 投诉处理
                            detail_url = f"{BASE_URL}/info-notice/complaint-list-detail/{biz_id}?type=2"
                        elif type_code == "aggregation-contractpublish":
                            # 合同公告/履约结果
                            detail_url = f"{BASE_URL}/stock-resources-front/performanceNoticeView?id={biz_id}"
                        else:
                            # 采购公告/招标公告/中标公告/更正公告/其他公告
                            detail_url = f"{BASE_URL}/info-notice/procument-notice-detail/{biz_id}"

                    # 调试日志
                    if not detail_url:
                        logger.warning(
                            f"[{self.name}] 无法构造URL, "
                            f"bizId={biz_id}, id={item_id}, typeCode={type_code}"
                        )

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
                logger.error(f"[{self.name}] 第{page}页解析失败: {e}")
                self.last_error = str(e)
                break

        if not all_items and self.last_error:
            logger.warning(f"[{self.name}] 无结果，最后错误: {self.last_error}")
        return all_items
