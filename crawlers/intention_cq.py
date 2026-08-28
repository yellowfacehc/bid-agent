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

关键改进（v5.2）:
  1. 增加详情页并发抓取 - 提取采购项目名称、采购需求概况等详情内容
  2. 支持全文关键词匹配 - 不仅匹配标题，还匹配详情页中的项目名称和需求概况
     （解决"数字化"搜不到"大坪监狱基础设施数字化项目"的问题，因为该词在详情页不在标题）
  3. 空关键词搜索 - 不传title参数，返回日期范围内所有采购意向
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

API_URL = "https://www.ccgp-chongqing.gov.cn/yw-gateway/zcjquery/v1/website-content-aggregations/front"
BASE_URL = "https://www.ccgp-chongqing.gov.cn"

# 采购意向的 typeCode
INTENTION_TYPE_CODE = "aggregation-purchaseintention"

# 详情页抓取并发数
DETAIL_CONCURRENCY = 5
# 最多抓取多少条详情页（避免超时）
MAX_DETAIL_FETCH = 10
# 区名关键词列表（这些关键词在标题中已包含，不需要抓详情页做全文匹配）
DISTRICT_KEYWORDS = ["九龙坡", "大渡口"]


class CQIntentionCrawler(BaseCrawler):
    """重庆市政府采购网 - 采购意向爬虫"""

    def __init__(self):
        super().__init__(name="重庆政府采购意向")

    def _build_detail_url(self, biz_id: str) -> str:
        """构建详情页URL"""
        return (
            f"{BASE_URL}/stock-resources/front/intentionView"
            f"?id={biz_id}/front"
            f"?__platDomain__=www.ccgp-chongqing.gov.cn"
        )

    def _fetch_detail_content(self, item: BidItem) -> str:
        """
        抓取采购意向详情页，提取采购项目名称和采购需求概况。

        Returns:
            详情内容字符串（项目名称 + 需求概况），失败返回空字符串
        """
        if not item.url:
            return ""

        try:
            headers = self._get_full_headers(
                referer=f"{BASE_URL}/",
                origin=BASE_URL,
                accept_json=False,
            )
            resp = self._safe_get(item.url, headers=headers, timeout=8)
            if resp is None or resp.status_code != 200:
                return ""

            soup = BeautifulSoup(resp.text, "html.parser")
            content_parts = []

            # 提取表格中的采购项目名称和采购需求概况
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 3:
                        # 通常第2列是采购项目名称，第3列是采购需求概况
                        project_name = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                        requirement = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                        if project_name and len(project_name) > 2:
                            content_parts.append(project_name)
                        if requirement and len(requirement) > 10:
                            content_parts.append(requirement)

            # 也提取页面中的所有文本作为补充
            if not content_parts:
                page_text = soup.get_text(separator=" ", strip=True)
                # 去掉导航和页脚，只取中间内容
                if "采购意向详情" in page_text:
                    idx = page_text.find("采购意向详情")
                    page_text = page_text[idx:idx+2000]
                content_parts.append(page_text)

            return " ".join(content_parts)

        except Exception as e:
            logger.debug(f"[{self.name}] 抓取详情页失败: {e}")
            return ""

    def _fetch_details_batch(self, items: List[BidItem], max_count: int = MAX_DETAIL_FETCH) -> None:
        """
        并发抓取一批项目的详情页内容，存入item.summary字段。

        Args:
            items: 项目列表
            max_count: 最多抓取多少条
        """
        if not items:
            return

        # 只抓取前max_count条（避免超时）
        items_to_fetch = items[:max_count]
        logger.info(f"[{self.name}] 开始抓取 {len(items_to_fetch)} 条详情页内容...")

        with ThreadPoolExecutor(max_workers=DETAIL_CONCURRENCY) as executor:
            future_to_item = {}
            for item in items_to_fetch:
                future = executor.submit(self._fetch_detail_content, item)
                future_to_item[future] = item

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    content = future.result()
                    if content:
                        # 将详情内容追加到summary（保留原有summary）
                        existing = item.summary or ""
                        item.summary = f"{existing} {content}".strip() if existing else content
                except Exception as e:
                    logger.debug(f"[{self.name}] 详情页抓取异常: {e}")

        logger.info(f"[{self.name}] 详情页抓取完成")

    def search(
        self,
        keyword: str,
        days: int = 20,
        max_pages: int = 5,
        region: str = "",
        start_date: str = "",
        end_date: str = "",
        fetch_details: bool = True,
    ) -> List[BidItem]:
        """
        搜索重庆市政府采购网的采购意向。

        Args:
            keyword: 搜索关键词（空字符串返回所有）
            days: 最近多少天
            max_pages: 最大爬取页数
            region: 地区筛选
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            fetch_details: 是否抓取详情页内容（用于全文关键词匹配）
                           空关键词时建议设为False以节省时间

        Returns:
            BidItem 列表
        """
        # 日期处理
        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            start_dt, end_dt = self.get_date_range(days)

        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)

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
                "title": keyword,  # 空字符串时API返回所有结果
                "typeCode": INTENTION_TYPE_CODE,
                "bizType": "3",
                "regionId": "130117562645086249",  # 重庆市ID（必须）
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
                    biz_id = rec.get("bizId", "")
                    detail_url = self._build_detail_url(biz_id) if biz_id else ""

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

        # 抓取详情页内容（用于全文关键词匹配）
        # 注意：区名关键词（如"九龙坡"、"大渡口"）在标题中已包含，不需要抓详情页
        is_district_kw = keyword.strip() in DISTRICT_KEYWORDS
        if fetch_details and all_items and keyword and not is_district_kw:
            self._fetch_details_batch(all_items)

            # 在客户端做全文关键词过滤（标题 + 详情内容）
            filtered = []
            for item in all_items:
                search_text = f"{item.title} {item.summary} {item.buyer}"
                if keyword in search_text:
                    filtered.append(item)
            logger.info(f"[{self.name}] 全文关键词过滤: {len(all_items)} -> {len(filtered)} 条")
            all_items = filtered

        if not all_items and self.last_error:
            logger.warning(f"[{self.name}] 无结果，最后错误: {self.last_error}")
        return all_items
