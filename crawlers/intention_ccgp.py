#!/usr/bin/env python3
"""
中国政府采购网 - 采购意向爬虫
===============================
网站: http://cgyx.ccgp.gov.cn/
列表页: /cgyx/pub/pubSearch
分页API: POST /cgyx/pub/pubSearchData
详情页: /cgyx/pub/details?groupId={groupId}

数据来源: 全国各省市采购意向汇总（包含重庆）

关键参数（POST表单）:
  - releaseStar: 开始日期 (YYYY-MM-DD)
  - releaseEnd: 结束日期 (YYYY-MM-DD)
  - title: 标题关键词
  - releaseUnitName: 发布单位名称
  - zoneId: 地区ID
  - type: 类型 (0=全部, 1=中央, 2=地方)
  - pageSize: 每页数量 (默认10)
  - pageNo: 页码

注意:
  1. 需要先GET访问列表页获取session/cookie
  2. 搜索表单有验证码，但直接调用分页API不需要验证码
  3. API返回HTML片段，需要用BeautifulSoup解析
  4. 详情页URL使用groupId参数（用户提到的projId是另一种详情页格式）
"""

import logging
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

BASE_URL = "http://cgyx.ccgp.gov.cn"
LIST_URL = f"{BASE_URL}/cgyx/pub/pubSearch"
API_URL = f"{BASE_URL}/cgyx/pub/pubSearchData"


class CCGPIntentionCrawler(BaseCrawler):
    """中国政府采购网 - 采购意向爬虫"""

    def __init__(self):
        super().__init__(name="中国政府采购意向")
        # 独立的session用于维护cookie
        self._intention_session = requests.Session()
        self._session_initialized = False

    def _init_session(self) -> bool:
        """
        初始化session：先GET访问列表页获取cookie。

        Returns:
            True if session initialized successfully
        """
        if self._session_initialized:
            return True

        try:
            headers = self._get_full_headers(
                referer="http://www.ccgp.gov.cn/",
                accept_json=False,
            )
            resp = self._intention_session.get(
                LIST_URL,
                headers=headers,
                timeout=10,
                verify=False,
            )
            if resp.status_code == 200:
                self._session_initialized = True
                logger.info(f"[{self.name}] Session初始化成功，获取到{len(self._intention_session.cookies)}个cookie")
                return True
            else:
                logger.warning(f"[{self.name}] 列表页返回HTTP {resp.status_code}")
                return False
        except Exception as e:
            logger.warning(f"[{self.name}] Session初始化失败: {e}")
            return False

    def _fetch_page_via_api(self, page_no: int, keyword: str = "",
                             start_date: str = "", end_date: str = "") -> Optional[str]:
        """
        通过POST API获取指定页的采购意向列表HTML。

        Args:
            page_no: 页码
            keyword: 标题关键词
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            HTML字符串，失败返回None
        """
        if not self._init_session():
            return None

        # 构建表单数据
        form_data = {
            "releaseStar": start_date,
            "releaseEnd": end_date,
            "title": keyword,
            "releaseUnitName": "",
            "zoneId": "",
            "type": "0",
            "pageSize": "10",
            "pageNo": str(page_no),
        }

        headers = {
            "User-Agent": self._get_random_ua(),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LIST_URL,
            "Origin": BASE_URL,
            "Connection": "keep-alive",
        }

        try:
            resp = self._intention_session.post(
                API_URL,
                data=form_data,
                headers=headers,
                timeout=15,
                verify=False,
            )
            if resp.status_code == 200 and resp.text:
                return resp.text
            else:
                logger.warning(f"[{self.name}] API第{page_no}页返回HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"[{self.name}] API第{page_no}页请求失败: {e}")
            return None

    def _fetch_page_via_html(self, page_no: int, keyword: str = "",
                               start_date: str = "", end_date: str = "") -> Optional[str]:
        """
        回退方案：直接GET列表页并解析（第一页），或通过URL参数翻页。

        Args:
            page_no: 页码
            keyword: 关键词
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            HTML字符串
        """
        try:
            params = {
                "title": keyword,
                "releaseStar": start_date,
                "releaseEnd": end_date,
                "pageNo": str(page_no),
            }
            headers = self._get_full_headers(
                referer="http://www.ccgp.gov.cn/",
                accept_json=False,
            )
            resp = self._intention_session.get(
                LIST_URL,
                params=params,
                headers=headers,
                timeout=15,
                verify=False,
            )
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception as e:
            logger.warning(f"[{self.name}] HTML回退方案失败: {e}")
            return None

    def _parse_intention_list(self, html: str) -> List[dict]:
        """
        解析采购意向列表HTML，提取项目信息。

        支持两种格式：
        1. 完整列表页（包含<table>）
        2. API返回的HTML片段

        Args:
            html: HTML字符串

        Returns:
            字典列表，每个字典包含 title, url, publish_date, buyer, region
        """
        items = []
        if not html:
            return items

        try:
            soup = BeautifulSoup(html, "html.parser")

            # 查找列表表格
            tables = soup.find_all("table")
            rows = []

            for table in tables:
                # 找到包含"采购意向列表"或"序号"的表格
                table_text = table.get_text()
                if "序号" in table_text or "标题" in table_text or "发布单位" in table_text:
                    rows = table.find_all("tr")
                    break

            # 如果没找到表格，尝试查找所有包含详情链接的行
            if not rows:
                # 查找所有包含groupId的链接
                links = soup.find_all("a", href=True)
                for link in links:
                    href = link.get("href", "")
                    if "groupId=" in href or "projId=" in href or "details" in href:
                        title = link.get_text(strip=True)
                        if title and len(title) > 5:
                            # 构建完整URL
                            full_url = urljoin(BASE_URL, href)
                            items.append({
                                "title": title,
                                "url": full_url,
                                "publish_date": "",
                                "buyer": "",
                                "region": "",
                            })
                return items

            # 解析表格行（跳过表头）
            for row in rows[1:]:  # 跳过表头
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue

                # 提取标题和链接
                title_cell = cells[1] if len(cells) > 1 else None
                title = ""
                detail_url = ""
                if title_cell:
                    link = title_cell.find("a", href=True)
                    if link:
                        title = link.get_text(strip=True)
                        href = link.get("href", "")
                        detail_url = urljoin(BASE_URL, href)
                    else:
                        title = title_cell.get_text(strip=True)

                if not title:
                    continue

                # 提取发布单位
                buyer = ""
                if len(cells) > 2:
                    buyer = cells[2].get_text(strip=True)

                # 提取发布日期
                publish_date = ""
                if len(cells) > 3:
                    date_text = cells[3].get_text(strip=True)
                    parsed = self._parse_date(date_text)
                    publish_date = parsed or date_text

                # 提取地区
                region = ""
                if len(cells) > 4:
                    region = cells[4].get_text(strip=True)

                items.append({
                    "title": title,
                    "url": detail_url,
                    "publish_date": publish_date,
                    "buyer": buyer,
                    "region": region,
                })

        except Exception as e:
            logger.error(f"[{self.name}] 解析HTML失败: {e}")

        return items

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
        搜索中国政府采购网的采购意向。

        Args:
            keyword: 搜索关键词（标题匹配）
            days: 最近多少天
            max_pages: 最大爬取页数
            region: 地区筛选（如"重庆"）
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

        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")

        all_items: List[BidItem] = []
        use_api_fallback = False

        for page in range(1, max_pages + 1):
            # 优先使用API
            html = None
            if not use_api_fallback:
                html = self._fetch_page_via_api(page, keyword, start_str, end_str)

            # 如果API失败，回退到HTML方案
            if not html:
                use_api_fallback = True
                logger.info(f"[{self.name}] API不可用，切换到HTML回退方案")
                html = self._fetch_page_via_html(page, keyword, start_str, end_str)

            if not html:
                logger.warning(f"[{self.name}] 第{page}页获取失败")
                break

            # 检查是否是错误页面
            if "Internal Server Error" in html or "500" in html[:500]:
                logger.warning(f"[{self.name}] 第{page}页返回服务器错误")
                if page == 1:
                    use_api_fallback = True
                    continue
                break

            # 解析列表
            raw_items = self._parse_intention_list(html)
            if not raw_items:
                logger.info(f"[{self.name}] 第{page}页无数据，停止")
                break

            page_count = 0
            for raw in raw_items:
                title = raw.get("title", "")
                if not title:
                    continue

                # 地区筛选（简单匹配）
                item_region = raw.get("region", "")
                if region and region not in item_region and region not in title:
                    # 不直接跳过，精确地理归属由上层处理
                    pass

                # 关键词过滤（API可能不支持title搜索，在客户端过滤）
                if keyword and keyword not in title:
                    # 也检查采购人名称
                    buyer = raw.get("buyer", "")
                    if keyword not in buyer:
                        continue

                item = BidItem(
                    title=title,
                    url=raw.get("url", ""),
                    publish_date=raw.get("publish_date", ""),
                    region=item_region or "全国",
                    category="采购意向",
                    buyer=raw.get("buyer", ""),
                    agency="",
                    source=self.name,
                    project_code="",
                    summary="",
                )
                all_items.append(item)
                page_count += 1

            logger.info(f"[{self.name}] 第{page}页获取 {page_count} 条采购意向")
            time.sleep(0.5)

        if not all_items:
            logger.info(f"[{self.name}] 无结果")
        return all_items
