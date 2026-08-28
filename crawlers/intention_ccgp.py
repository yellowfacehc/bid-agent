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
  1. 海外服务器直接访问可能被403，需要通过CORS代理中转
  2. 使用BaseCrawler的_safe_get()方法自动处理代理降级
  3. 搜索表单有验证码，但直接调用分页API不需要验证码
  4. 详情页URL使用groupId参数（用户提到的projId是另一种详情页格式）
"""

import logging
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, BidItem, CORS_PROXY_URL

logger = logging.getLogger(__name__)

BASE_URL = "http://cgyx.ccgp.gov.cn"
LIST_URL = f"{BASE_URL}/cgyx/pub/pubSearch"
API_URL = f"{BASE_URL}/cgyx/pub/pubSearchData"


class CCGPIntentionCrawler(BaseCrawler):
    """中国政府采购网 - 采购意向爬虫"""

    def __init__(self):
        super().__init__(name="中国政府采购意向")
        self._session_init = False

    def _ensure_session(self):
        """确保session已初始化（获取cookie）"""
        if self._session_init:
            return True
        try:
            # 使用_safe_get访问列表页，自动处理代理
            resp = self._safe_get(LIST_URL, timeout=10)
            if resp is not None and resp.status_code == 200:
                self._session_init = True
                logger.info(f"[{self.name}] Session初始化成功")
                return True
            logger.warning(f"[{self.name}] Session初始化失败: {self.last_error}")
            return False
        except Exception as e:
            logger.warning(f"[{self.name}] Session初始化异常: {e}")
            return False

    def _post_via_proxy(self, url: str, data: dict, timeout: int = 15) -> Optional[requests.Response]:
        """
        带代理支持的POST请求。
        优先使用self.session（已配置CRAWL_PROXY），失败时尝试CORS代理。
        注意：CORS代理通常只支持GET，所以POST主要依赖CRAWL_PROXY。
        """
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

        # 第一步：直接POST（通过self.session的CRAWL_PROXY）
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.post(
                    url, data=data, headers=headers,
                    timeout=timeout, verify=False,
                )
                if resp.status_code == 200 and resp.text:
                    return resp
                logger.warning(f"[{self.name}] POST返回HTTP {resp.status_code} (尝试{attempt})")
                # 403/451通常是地域限制或防火墙拦截，直接触发代理转发
                if resp.status_code in (403, 451, 400):
                    self.last_error = f"HTTP {resp.status_code} (可能是地域限制)"
                    break
            except requests.exceptions.ConnectionError as e:
                err_str = str(e)
                if "Network is unreachable" in err_str or "Name or service not known" in err_str:
                    self.last_error = "网络不可达(可能是地域限制)"
                    logger.error(f"[{self.name}] 网络不可达: {url}")
                    break
                self.last_error = f"连接错误: {err_str[:100]}"
                logger.warning(f"[{self.name}] 第{attempt}次连接错误: {err_str[:100]}")
            except requests.exceptions.Timeout:
                self.last_error = f"请求超时({timeout}s)"
                logger.warning(f"[{self.name}] 第{attempt}次请求超时")
            except requests.RequestException as e:
                self.last_error = f"请求异常: {e}"
                logger.warning(f"[{self.name}] 第{attempt}次请求异常: {e}")
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)

        # 第二步：通过CORS代理用真正的POST请求转发
        # Cloudflare Worker支持POST转发，会将请求体转发到目标URL
        if self.last_error and ("网络不可达" in self.last_error or "Connection" in self.last_error
                                 or "超时" in self.last_error or "HTTP" in self.last_error or "403" in self.last_error):
            logger.info(f"[{self.name}] 直接POST失败，尝试CORS代理POST中转...")
            try:
                if CORS_PROXY_URL:
                    from urllib.parse import quote_plus
                    # 目标URL作为url参数传递给Worker，POST数据作为请求体
                    proxy_url = f"{CORS_PROXY_URL.rstrip('/')}/?url={quote_plus(url)}"
                    proxy_headers = {
                        "User-Agent": self._get_random_ua(),
                        "Accept": "application/json, text/plain, */*",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    }
                    resp = requests.post(
                        proxy_url, data=data, headers=proxy_headers,
                        timeout=15, verify=False,
                    )
                    if resp.status_code == 200 and resp.text:
                        logger.info(f"[{self.name}] CORS代理POST成功! 响应长度: {len(resp.text)}")
                        self.last_error = ""
                        return resp
                    else:
                        logger.warning(f"[{self.name}] CORS代理POST返回HTTP {resp.status_code}, 响应长度: {len(resp.text) if resp.text else 0}")
            except Exception as e:
                logger.warning(f"[{self.name}] CORS代理POST失败: {e}")

        return None

    def _fetch_page(self, page_no: int, keyword: str = "",
                    start_date: str = "", end_date: str = "") -> Optional[str]:
        """
        获取指定页的采购意向列表HTML。
        优先使用POST API，失败时回退到GET列表页。
        """
        # 确保session已初始化
        self._ensure_session()

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

        # 尝试POST API
        resp = self._post_via_proxy(API_URL, form_data, timeout=15)
        if resp and resp.text and "Internal Server Error" not in resp.text[:500]:
            return resp.text

        logger.info(f"[{self.name}] POST API不可用，回退到GET列表页")

        # 回退：GET列表页（只获取第一页）
        if page_no == 1:
            params = {
                "title": keyword,
                "releaseStar": start_date,
                "releaseEnd": end_date,
                "pageNo": str(page_no),
            }
            resp = self._safe_get(LIST_URL, params=params, timeout=15)
            if resp and resp.text:
                return resp.text

        return None

    def _parse_intention_list(self, html: str) -> List[dict]:
        """
        解析采购意向列表HTML，提取项目信息。
        支持完整列表页和API返回的HTML片段。
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
                table_text = table.get_text()
                if "序号" in table_text or "标题" in table_text or "发布单位" in table_text:
                    rows = table.find_all("tr")
                    break

            # 如果没找到表格，查找所有包含详情链接的行
            if not rows:
                links = soup.find_all("a", href=True)
                for link in links:
                    href = link.get("href", "")
                    if "groupId=" in href or "projId=" in href or "details" in href:
                        title = link.get_text(strip=True)
                        if title and len(title) > 5:
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
            for row in rows[1:]:
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
        days: int = 30,
        max_pages: int = 5,
        region: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[BidItem]:
        """
        搜索中国政府采购网的采购意向。

        Args:
            keyword: 搜索关键词（标题匹配，空字符串返回所有）
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

        for page in range(1, max_pages + 1):
            html = self._fetch_page(page, keyword, start_str, end_str)

            if not html:
                logger.warning(f"[{self.name}] 第{page}页获取失败")
                break

            # 检查是否是错误页面
            if "Internal Server Error" in html[:500]:
                logger.warning(f"[{self.name}] 第{page}页返回服务器错误")
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
