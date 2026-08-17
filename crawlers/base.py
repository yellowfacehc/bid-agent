"""
基类模块 - 定义统一的数据结构和爬虫接口
"""

import random
import time
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

# 抑制 SSL 验证警告（政府网站证书可能不受信任）
try:
    from urllib3.exceptions import InsecureRequestWarning
    warnings.simplefilter("ignore", InsecureRequestWarning)
except ImportError:
    pass

logger = logging.getLogger(__name__)

# 随机 User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


@dataclass
class BidItem:
    """统一的招投标信息数据结构"""
    title: str = ""               # 项目标题
    publish_date: str = ""        # 发布日期 (YYYY-MM-DD)
    region: str = ""              # 地区
    category: str = ""            # 公告类型 (招标公告/中标公告等)
    buyer: str = ""               # 采购人/招标人
    agency: str = ""              # 代理机构
    url: str = ""                 # 公告真实链接
    source: str = ""              # 数据来源平台
    summary: str = ""             # 摘要信息
    project_code: str = ""        # 项目编号

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "publish_date": self.publish_date,
            "region": self.region,
            "category": self.category,
            "buyer": self.buyer,
            "agency": self.agency,
            "url": self.url,
            "source": self.source,
            "summary": self.summary,
            "project_code": self.project_code,
        }

    def __str__(self) -> str:
        lines = [
            f"  标题: {self.title}",
            f"  日期: {self.publish_date}",
            f"  地区: {self.region}",
            f"  类型: {self.category}",
            f"  采购人: {self.buyer}",
            f"  代理机构: {self.agency}",
            f"  链接: {self.url}",
            f"  来源: {self.source}",
        ]
        return "\n".join(lines)


class BaseCrawler:
    """爬虫基类 - 提供通用的HTTP请求和解析工具方法"""

    def __init__(self, name: str = "base"):
        self.name = name
        self.session = requests.Session()
        self.timeout = 15
        self.max_retries = 3
        self.retry_delay = 2  # 重试延迟(秒)
        self.last_error: str = ""  # 记录最后一次错误，用于调试

    def _get_full_headers(self, referer: str = "", origin: str = "", accept_json: bool = True) -> dict:
        """
        生成完整的浏览器请求头，模拟真实浏览器访问。
        包含 Accept-Encoding、Accept-Language、Sec-Fetch-* 等字段，
        绕过政府网站 WAF 对简单请求的拦截。
        """
        ua = random.choice(USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*" if accept_json else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if referer:
            headers["Referer"] = referer
        if origin:
            headers["Origin"] = origin
        return headers

    def _get_random_headers(self, host: str = "", referer: str = "") -> dict:
        """生成随机请求头（兼容旧代码）"""
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        if host:
            headers["Host"] = host
        if referer:
            headers["Referer"] = referer
        return headers

    @staticmethod
    def _get_random_ua() -> str:
        """获取随机 User-Agent"""
        return random.choice(USER_AGENTS)

    def _sleep_random(self, min_sec: float = 0.3, max_sec: float = 1.0):
        """随机延迟，避免触发反爬"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def _safe_get(
        self,
        url: str,
        params: dict = None,
        headers: dict = None,
        timeout: int = None,
    ) -> Optional[requests.Response]:
        """
        安全的 GET 请求，带重试和 SSL 降级。

        1. 先用标准方式请求（verify=True）
        2. 如果 SSL 失败，降级为 verify=False
        3. 带重试逻辑（最多 max_retries 次）
        """
        if timeout is None:
            timeout = self.timeout
        self.last_error = ""

        for attempt in range(1, self.max_retries + 1):
            # 第一次用 verify=True，SSL 失败后降级为 verify=False
            for verify_ssl in [True, False]:
                try:
                    resp = self.session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=timeout,
                        verify=verify_ssl,
                    )
                    if resp.status_code == 200:
                        return resp
                    # 非200状态码，记录但继续重试
                    self.last_error = f"HTTP {resp.status_code}"
                    logger.warning(
                        f"[{self.name}] 第{attempt}次请求(verify={verify_ssl}) "
                        f"返回 {resp.status_code}: {url}"
                    )
                    break  # 跳出 verify 循环，进入下一次重试
                except requests.exceptions.SSLError as e:
                    if verify_ssl:
                        # SSL 错误，降级到 verify=False 重试
                        logger.warning(f"[{self.name}] SSL验证失败，降级为不验证: {e}")
                        self.last_error = f"SSL错误: {e}"
                        continue  # 继续下一次 verify=False
                    else:
                        self.last_error = f"SSL错误(已降级): {e}"
                        break
                except requests.exceptions.ConnectionError as e:
                    self.last_error = f"连接错误: {e}"
                    logger.warning(f"[{self.name}] 第{attempt}次连接错误: {e}")
                    break
                except requests.exceptions.Timeout:
                    self.last_error = f"请求超时({timeout}s)"
                    logger.warning(f"[{self.name}] 第{attempt}次请求超时({timeout}s)")
                    break
                except requests.RequestException as e:
                    self.last_error = f"请求异常: {e}"
                    logger.warning(f"[{self.name}] 第{attempt}次请求异常: {e}")
                    break

            if attempt < self.max_retries:
                time.sleep(self.retry_delay)

        logger.error(f"[{self.name}] 请求失败，已达最大重试次数({self.max_retries}): {url} | 错误: {self.last_error}")
        return None

    def _request_with_retry(
        self,
        url: str,
        method: str = "GET",
        params: dict = None,
        data: dict = None,
        headers: dict = None,
        encoding: str = "utf-8",
    ) -> Optional[requests.Response]:
        """带重试机制的HTTP请求（兼容旧代码，内部调用 _safe_get）"""
        if method.upper() == "GET":
            return self._safe_get(url, params=params, headers=headers)
        else:
            for attempt in range(1, self.max_retries + 1):
                try:
                    resp = self.session.post(
                        url, params=params, data=data, headers=headers, timeout=self.timeout
                    )
                    resp.encoding = encoding
                    if resp.status_code == 200:
                        return resp
                    logger.warning(
                        f"[{self.name}] 第{attempt}次请求返回 {resp.status_code}: {url}"
                    )
                except requests.RequestException as e:
                    logger.warning(f"[{self.name}] 第{attempt}次请求异常: {e}")
                    self.last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)
        logger.error(f"[{self.name}] 请求失败，已达最大重试次数: {url}")
        return None

    def search(
        self, keyword: str, days: int = 20, max_pages: int = 5,
        region: str = "", start_date: str = "", end_date: str = "",
    ) -> List[BidItem]:
        """
        搜索招投标信息 (子类必须实现)
        """
        raise NotImplementedError("子类必须实现 search 方法")

    @staticmethod
    def _parse_date(date_str: str) -> Optional[str]:
        """尝试将各种日期格式统一为 YYYY-MM-DD"""
        if not date_str:
            return None
        date_str = date_str.strip()
        formats = [
            "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
            "%Y年%m月%d日", "%Y:%m:%d", "%Y%m%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    @staticmethod
    def get_date_range(days: int) -> tuple:
        """获取最近 N 天的日期范围 (start_date, end_date)"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return start_date, end_date
