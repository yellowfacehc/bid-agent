"""
中国招标投标公共服务平台爬虫 (cebpubservice.com)

平台搜索接口:
  - getSearch.do: 返回搜索表单 HTML 页面, 实际搜索结果通过 JS 加密请求加载
  - 新版接口使用 DES 加密 + JS 混淆, 逆向难度大

本模块尝试 getSearch.do 接口, 若返回的是表单页面而非搜索结果,
则记录警告并返回空列表。
"""

import re
import logging
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

# 搜索接口端点
SEARCH_URL = "http://www.cebpubservice.com/ctpsp_iiss/searchbusinesstypebeforedooraction/getSearch.do"
BASE_URL = "http://www.cebpubservice.com"


class CEBPubCrawler(BaseCrawler):
    """中国招标投标公共服务平台爬虫"""

    def __init__(self):
        super().__init__(name="中国招标投标公共服务平台")

    def search(self, keyword: str, days: int = 20, max_pages: int = 5, region: str = "", start_date: str = "", end_date: str = "") -> List[BidItem]:
        """
        搜索招标投标公告

        尝试通过 getSearch.do 接口获取搜索结果。
        注意: 该平台新版接口使用 DES 加密 + JS 混淆,
        若接口返回表单页面而非结果, 将返回空列表。
        """
        start_date, end_date = self.get_date_range(days)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        all_items: List[BidItem] = []

        for page in range(1, max_pages + 1):
            params = {
                "searchType": "1",
                "keyword": keyword,
                "startDate": start_str,
                "endDate": end_str,
                "pageNo": str(page),
                "pageSize": "20",
            }

            headers = self._get_random_headers()
            headers["Referer"] = BASE_URL + "/"

            logger.info(
                f"[{self.name}] 正在搜索第 {page} 页, 关键词='{keyword}'"
            )
            resp = self._request_with_retry(
                SEARCH_URL, method="POST", data=params, headers=headers
            )

            if not resp:
                break

            items = self._parse_list_page(resp.text)
            if not items:
                # 检查是否是表单页面 (而非搜索结果)
                if self._is_form_page(resp.text):
                    logger.warning(
                        f"[{self.name}] 接口返回搜索表单页面, 非搜索结果。"
                        f"该平台新版接口使用DES加密+JS混淆, 暂不支持自动爬取。"
                    )
                break

            all_items.extend(items)
            if len(items) < 15:
                break

        logger.info(f"[{self.name}] 共获取 {len(all_items)} 条记录")
        return all_items

    def _is_form_page(self, html: str) -> bool:
        """检测是否是搜索表单页面 (而非搜索结果)"""
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        if title_tag and "信息公开" in title_tag.get_text():
            return True
        # 检查是否有搜索表单字段
        if soup.find("input", {"name": re.compile("time|date|status", re.I)}):
            return True
        return False

    def _parse_list_page(self, html: str) -> List[BidItem]:
        """解析搜索结果列表页 HTML"""
        items: List[BidItem] = []
        soup = BeautifulSoup(html, "lxml")

        # 查找表格行中的公告链接
        for tr in soup.find_all("tr"):
            try:
                a_tag = tr.find("a")
                if not a_tag:
                    continue
                title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                if not title or not href or "javascript" in href:
                    continue
                if len(title) < 5:
                    continue

                item = BidItem(source=self.name, title=title)
                item.url = href if href.startswith("http") else urljoin(BASE_URL, href)

                # 从行中提取日期
                row_text = tr.get_text()
                date_match = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", row_text)
                if date_match:
                    parsed = self._parse_date(date_match.group(1))
                    if parsed:
                        item.publish_date = parsed

                # 从行中提取地区
                for td in tr.find_all("td"):
                    td_text = td.get_text(strip=True)
                    if re.match(r"^[\u4e00-\u9fa5]{2,6}$", td_text):
                        item.region = td_text
                        break

                item.category = "招标公告"
                items.append(item)
            except Exception:
                continue

        # 备用: 查找列表中的公告链接
        if not items:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                title = a.get_text(strip=True)
                if (
                    title
                    and len(title) > 8
                    and href
                    and "javascript" not in href
                    and ("bulletin" in href or "ctpsp" in href or "notice" in href)
                ):
                    item = BidItem(source=self.name, title=title, category="招标公告")
                    item.url = href if href.startswith("http") else urljoin(BASE_URL, href)
                    items.append(item)

        return items
