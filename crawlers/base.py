"""
基类模块 - 定义统一的数据结构和爬虫接口
"""

import random
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

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
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 3  # 重试延迟(秒)

    def _get_random_headers(self, host: str = "", referer: str = "") -> dict:
        """生成随机请求头"""
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

    def _sleep_random(self, min_sec: float = 2.0, max_sec: float = 5.0):
        """随机延迟，避免触发反爬"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def _request_with_retry(
        self,
        url: str,
        method: str = "GET",
        params: dict = None,
        data: dict = None,
        headers: dict = None,
        encoding: str = "utf-8",
    ) -> Optional[requests.Response]:
        """带重试机制的HTTP请求"""
        for attempt in range(1, self.max_retries + 1):
            try:
                self._sleep_random()
                if method.upper() == "GET":
                    resp = self.session.get(
                        url, params=params, headers=headers, timeout=self.timeout
                    )
                else:
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

        Args:
            keyword: 搜索关键词，如 "信息化"
            days: 搜索最近多少天的数据
            max_pages: 最大爬取页数
            region: 地区名称 (如 "广东"), 空字符串表示全国
            start_date: 自定义开始日期 (YYYY-MM-DD), 优先于 days
            end_date: 自定义结束日期 (YYYY-MM-DD)

        Returns:
            BidItem 列表
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
