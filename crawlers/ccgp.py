"""
中国政府采购网爬虫 (ccgp.gov.cn)

接口: http://search.ccgp.gov.cn/bxsearch
方式: GET
返回: HTML (需 BeautifulSoup 解析)
反爬: 低 (需设置 Host/Referer 头 + 随机延迟)
"""

import re
import logging
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler, BidItem

logger = logging.getLogger(__name__)

SEARCH_URL = "http://search.ccgp.gov.cn/bxsearch"
HOST = "search.ccgp.gov.cn"
REFERER = "http://search.ccgp.gov.cn/"

# 省份名称 -> CCGP zoneId 映射
PROVINCE_ZONE_MAP = {
    "北京": "11", "天津": "12", "河北": "13", "山西": "14", "内蒙古": "15",
    "辽宁": "21", "吉林": "22", "黑龙江": "23", "上海": "31", "江苏": "32",
    "浙江": "33", "安徽": "34", "福建": "35", "江西": "36", "山东": "37",
    "河南": "41", "湖北": "42", "湖南": "43", "广东": "44", "广西": "45",
    "海南": "46", "重庆": "50", "四川": "51", "贵州": "52", "云南": "53",
    "西藏": "54", "陕西": "61", "甘肃": "62", "青海": "63", "宁夏": "64",
    "新疆": "65", "中央国家机关": "99",
}


class CCGPCrawler(BaseCrawler):
    """中国政府采购网爬虫"""

    def __init__(self):
        super().__init__(name="中国政府采购网")

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
        搜索政府采购公告

        Args:
            keyword: 搜索关键词
            days: 最近N天 (当 start_date/end_date 未指定时使用)
            max_pages: 最大页数
            region: 地区名称 (如 "广东"), 空字符串表示全国
            start_date: 自定义开始日期 (YYYY-MM-DD), 优先于 days
            end_date: 自定义结束日期 (YYYY-MM-DD)
        """
        # 日期处理: 优先使用自定义日期
        if start_date and end_date:
            from datetime import datetime as dt
            start_dt = dt.strptime(start_date, "%Y-%m-%d")
            end_dt = dt.strptime(end_date, "%Y-%m-%d")
        else:
            start_dt, end_dt = self.get_date_range(days)

        # CCGP 日期格式: YYYY:MM:DD
        start_str = start_dt.strftime("%Y:%m:%d")
        end_str = end_dt.strftime("%Y:%m:%d")

        # 地区处理
        zone_id = PROVINCE_ZONE_MAP.get(region, "") if region else ""

        all_items: List[BidItem] = []

        for page in range(1, max_pages + 1):
            params = {
                "searchtype": "1",
                "page_index": str(page),
                "bidSort": "0",
                "buyerName": "",
                "projectId": "",
                "pinMu": "0",
                "bidType": "0",
                "dbselect": "bidx",
                "kw": keyword,
                "start_time": start_str,
                "end_time": end_str,
                "timeType": "6",
                "displayZone": region,
                "zoneId": zone_id,
                "pppStatus": "0",
                "agentName": "",
            }

            headers = self._get_random_headers(host=HOST, referer=REFERER)
            logger.info(f"[{self.name}] 正在搜索第 {page} 页, 关键词='{keyword}'")
            resp = self._request_with_retry(SEARCH_URL, params=params, headers=headers)

            if not resp:
                break

            items = self._parse_list_page(resp.text, keyword)
            if not items:
                logger.info(f"[{self.name}] 第 {page} 页无数据，停止翻页")
                break

            all_items.extend(items)

            # 检查是否还有下一页
            if len(items) < 20:
                logger.info(f"[{self.name}] 第 {page} 页不足20条，已是最后一页")
                break

        logger.info(f"[{self.name}] 共获取 {len(all_items)} 条记录")
        return all_items

    def _parse_list_page(self, html: str, keyword: str = "") -> List[BidItem]:
        """
        解析搜索结果列表页

        HTML 结构:
          <li>
            <a href="...">标题 (含 <font> 高亮关键词)</a>
            <p>摘要内容</p>
            <span>
              2026.08.13 10:44:32 | 采购人：xxx | 代理机构：xxx
              <br/><strong>中标公告</strong> | 广东 | <strong> </strong>
            </span>
          </li>
        """
        items: List[BidItem] = []
        soup = BeautifulSoup(html, "lxml")

        ul = soup.find("ul", class_="vT-srch-result-list-bid")
        if not ul:
            logger.debug(f"[{self.name}] 未找到结果列表容器")
            return items

        for li in ul.find_all("li"):
            try:
                item = BidItem(source=self.name)

                # 1. 标题和链接 (从 <a> 标签)
                a_tag = li.find("a")
                if a_tag:
                    item.title = a_tag.get_text(strip=True)
                    href = a_tag.get("href", "")
                    if href:
                        item.url = urljoin("http://www.ccgp.gov.cn/", href)

                # 2. 摘要 (从 <p> 标签)
                p_tag = li.find("p")
                if p_tag:
                    summary = p_tag.get_text(strip=True)
                    if summary:
                        item.summary = summary[:200]  # 截断

                # 3. 元数据 (从 <span> 标签解析)
                span_tag = li.find("span")
                if span_tag:
                    # 提取公告类型 (在 <strong> 标签中)
                    strong_tags = span_tag.find_all("strong")
                    for strong in strong_tags:
                        strong_text = strong.get_text(strip=True)
                        if strong_text and strong_text not in ("", " "):
                            item.category = strong_text
                            break

                    # 获取 span 的完整文本用于解析其他字段
                    span_text = span_tag.get_text(separator="|", strip=False)
                    # 清理多余的换行和空格
                    span_text = re.sub(r"\s+", " ", span_text).strip()

                    # 提取日期 (格式: 2026.08.13 10:44:32)
                    date_match = re.search(
                        r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", span_text
                    )
                    if date_match:
                        date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                        parsed = self._parse_date(date_str)
                        if parsed:
                            item.publish_date = parsed

                    # 按 | 分割提取各字段
                    parts = [p.strip() for p in span_text.split("|")]
                    for part in parts:
                        if not part:
                            continue
                        if "采购人" in part or "招标人" in part:
                            m = re.search(r"[：:](.+)", part)
                            if m:
                                item.buyer = m.group(1).strip()
                        elif "代理机构" in part:
                            m = re.search(r"[：:](.+)", part)
                            if m:
                                item.agency = m.group(1).strip()
                        elif (
                            re.match(r"^[\u4e00-\u9fa5]{2,8}$", part)
                            and not item.region
                            and part != item.category  # 跳过公告类型
                        ):
                            # 纯中文2-8字 → 地区名 (排除已匹配的公告类型)
                            item.region = part

                # 补充: 如果公告类型未从 strong 提取到，从标题推断
                if not item.category:
                    if "中标" in item.title or "成交" in item.title:
                        item.category = "中标公告"
                    elif "更正" in item.title or "变更" in item.title:
                        item.category = "更正公告"
                    elif "招标" in item.title or "采购" in item.title:
                        item.category = "招标公告"
                    elif "废标" in item.title:
                        item.category = "废标公告"
                    else:
                        item.category = "政府采购公告"

                if item.title and item.url:
                    items.append(item)

            except Exception as e:
                logger.debug(f"[{self.name}] 解析单条记录异常: {e}")
                continue

        return items
