#!/usr/bin/env python3
"""
重庆市政府采购网 - 采购意向爬虫
=================================
网站: https://www.ccgp-chongqing.gov.cn/
API:  /yw-gateway/zcjquery/v1/website-content-aggregations/front
详情页: /stock-resources/front/intentionView?id={bizId}/front?__platDomain__=www.ccgp-chongqing.gov.cn

与 cqccgp.py（招标公告爬虫）共用同一个API端点，区别仅在于 typeCode：
  - 招标公告等: typeCode 为空或 aggregation-notice/tender/success 等
  - 采购意向:   typeCode = aggregation-purchaseintention

关键参数:
  - typeCode: aggregation-purchaseintention（采购意向）
  - bizType: 3
  - title: 关键词搜索
  - pageNum / pageSize: 分页
  - publicityStartTime / publicityEndTime: 日期范围（毫秒时间戳）
  - regionId: 地区ID（可选）
"""

import logging
import time
from datetime import datetime
from typing import List
from urllib.parse import quote

from crawlers.base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

API_URL = "https://www.ccgp-chongqing.gov.cn/yw-gateway/zcjquery/v1/website-content-aggregations/front"
BASE_URL = "https://www.ccgp-chongqing.gov.cn"

# 采购意向的 typeCode
INTENTION_TYPE_CODE = "aggregation-purchaseintention"


class CQIntentionCrawler(BaseCrawler):
    """重庆市政府采购网 - 采购意向爬虫"""

    def __init__(self):
        super().__init__(name="重庆政府采购意向")

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
        搜索重庆市政府采购网的采购意向。

        Args:
            keyword: 搜索关键词
            days: 最近多少天
            max_pages: 最大爬取页数
            region: 地区筛选（如"九龙坡区"）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            BidItem 列表
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

        # 客户端日期过滤范围
        client_start = start_dt.strftime("%Y-%m-%d")
        client_end = end_dt.strftime("%Y-%m-%d")

        # 使用完整的浏览器请求头
        keyword_encoded = quote(keyword) if keyword else ""
        headers = self._get_full_headers(
            referer=f"{BASE_URL}/search/{keyword_encoded}" if keyword else f"{BASE_URL}/",
            origin=BASE_URL,
            accept_json=True,
        )

        all_items: List[BidItem] = []

        for page in range(1, max_pages + 1):
            params = {
                "title": keyword,
                "typeCode": INTENTION_TYPE_CODE,
                "bizType": "3",
                "regionId": "130117562645086249",  # 重庆市ID（必须，否则API可能返回空）
                "excludeRegionId": "",
                "publicityStartTime": str(start_ts),
                "publicityEndTime": str(end_ts),
                "pageNum": str(page),
                "pageSize": "10",
                "searchCount": "true",
                "queryAddCount": "true",
                "__platDomain__": "www.ccgp-chongqing.gov.cn",
            }

            try:
                resp = self._safe_get(API_URL, params=params, headers=headers, timeout=8)
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

                    # 地区筛选（简单关键词匹配，精确地理归属由上层处理）
                    if region and region not in item_region:
                        # 地区不匹配但不直接跳过，因为有些项目regionName可能是"重庆市"
                        # 精确的区县归属由 region_geo 模块在搜索后处理
                        pass

                    pub_time = rec.get("publishTime")
                    if pub_time:
                        pub_date = datetime.fromtimestamp(pub_time / 1000).strftime("%Y-%m-%d")
                    else:
                        pub_date = ""

                    # 客户端日期过滤
                    if pub_date and client_start and client_end:
                        try:
                            item_date = datetime.strptime(pub_date, "%Y-%m-%d")
                            range_start = datetime.strptime(client_start, "%Y-%m-%d")
                            range_end = datetime.strptime(client_end, "%Y-%m-%d")
                            if not (range_start <= item_date <= range_end):
                                continue
                        except ValueError:
                            pass

                    # 构建详情链接
                    # 用户指定的URL格式:
                    # https://www.ccgp-chongqing.gov.cn/stock-resources/front/intentionView?id={bizId}/front?__platDomain__=www.ccgp-chongqing.gov.cn
                    biz_id = rec.get("bizId", "")
                    detail_url = ""
                    if biz_id:
                        detail_url = (
                            f"{BASE_URL}/stock-resources/front/intentionView"
                            f"?id={biz_id}/front"
                            f"?__platDomain__=www.ccgp-chongqing.gov.cn"
                        )

                    # 优先使用API返回的URL字段
                    api_url = rec.get("url", "") or rec.get("detailUrl", "") or rec.get("linkUrl", "")
                    if api_url:
                        detail_url = api_url

                    item = BidItem(
                        title=rec.get("title", ""),
                        url=detail_url,
                        publish_date=pub_date,
                        region=item_region or "重庆市",
                        category="采购意向",
                        buyer=rec.get("orgName", ""),
                        agency="",
                        source=self.name,
                        project_code=rec.get("projectCode", ""),
                        summary=rec.get("projectName", ""),
                    )
                    all_items.append(item)

                logger.info(f"[{self.name}] 第{page}页获取 {len(records)} 条采购意向")
                time.sleep(0.3)

            except Exception as e:
                logger.error(f"[{self.name}] 第{page}页解析失败: {e}")
                self.last_error = str(e)
                break

        if not all_items and self.last_error:
            logger.warning(f"[{self.name}] 无结果，最后错误: {self.last_error}")
        return all_items
