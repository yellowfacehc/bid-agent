"""
基类模块 - 定义统一的数据结构和爬虫接口

关键改进:
  1. _get_full_headers() - 生成完整浏览器请求头，绕过WAF
  2. _safe_get() - 带SSL降级、重试、代理支持的安全请求方法
  3. last_error - 记录最后一次错误，便于调试
  4. 代理支持 - 通过环境变量 HTTP_PROXY/HTTPS_PROXY 或 CRAWL_PROXY 配置
     用于解决海外服务器无法访问中国政府网站的问题
"""

import os
import random
import time
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus, urlencode

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

# 从环境变量获取代理配置
# 支持两种方式: CRAWL_PROXY (专用) 或 HTTP_PROXY/HTTPS_PROXY (标准)
CRAWL_PROXY = os.environ.get("CRAWL_PROXY", "") or os.environ.get("HTTPS_PROXY", "") or os.environ.get("https_proxy", "")

# Cloudflare Worker 代理URL (用于海外服务器访问中国政府网站)
# 部署方法见 cloudflare-worker.js 文件说明
CORS_PROXY_URL = os.environ.get("CORS_PROXY_URL", "")


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
        # 降低超时和重试次数，避免海外服务器长时间等待不可达的政府网站
        self.timeout = 8
        self.max_retries = 2
        self.retry_delay = 1  # 重试延迟(秒)
        self.last_error: str = ""  # 记录最后一次错误，用于调试

        # 配置代理
        if CRAWL_PROXY:
            self.session.proxies = {
                "http": CRAWL_PROXY,
                "https": CRAWL_PROXY,
            }
            logger.info(f"[{self.name}] 已配置代理: {CRAWL_PROXY}")

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
        安全的 GET 请求，带 SSL 降级、重试、代理和CORS中转支持。

        政府网站常见问题:
        1. 海外服务器网络不可达 → 快速失败(5秒超时)，然后尝试CORS中转
        2. SSL证书不受信任 → 先 verify=True，失败后降级为 verify=False
        3. WAF拦截 → 完整浏览器请求头绕过
        4. 地域限制 → 通过 CRAWL_PROXY 环境变量配置代理

        Returns:
            requests.Response 或 None（全部重试失败时）
        """
        if timeout is None:
            timeout = self.timeout
        self.last_error = ""

        # 第一步：尝试直接连接（带SSL降级和重试）
        result = self._direct_get(url, params, headers, timeout)
        if result is not None:
            return result

        # 第二步：如果直接连接失败且错误是"网络不可达"，尝试通过CORS中转
        # 注意: 代理请求需要更长的超时时间(25秒)，因为代理服务器需要额外时间访问目标网站
        if "网络不可达" in self.last_error or "Connection" in self.last_error:
            logger.info(f"[{self.name}] 直接连接失败，尝试CORS中转(超时25秒)...")
            result = self._get_via_cors_proxy(url, params, timeout=25)
            if result is not None:
                return result

        logger.error(f"[{self.name}] 请求失败: {url} | 错误: {self.last_error}")
        return None

    def _direct_get(
        self,
        url: str,
        params: dict = None,
        headers: dict = None,
        timeout: int = None,
    ) -> Optional[requests.Response]:
        """直接连接请求（带SSL降级和重试）"""
        for attempt in range(1, self.max_retries + 1):
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
                    self.last_error = f"HTTP {resp.status_code}"
                    logger.warning(
                        f"[{self.name}] 第{attempt}次请求(verify={verify_ssl}) "
                        f"返回 {resp.status_code}: {url}"
                    )
                    break
                except requests.exceptions.SSLError as e:
                    if verify_ssl:
                        logger.warning(f"[{self.name}] SSL验证失败，降级为不验证: {e}")
                        self.last_error = f"SSL错误: {e}"
                        continue
                    else:
                        self.last_error = f"SSL错误(已降级): {e}"
                        break
                except requests.exceptions.ConnectionError as e:
                    error_str = str(e)
                    if "Network is unreachable" in error_str or "Name or service not known" in error_str:
                        self.last_error = "网络不可达(可能是地域限制)"
                        logger.error(f"[{self.name}] 网络不可达: {url}")
                        return None
                    self.last_error = f"连接错误: {error_str[:100]}"
                    logger.warning(f"[{self.name}] 第{attempt}次连接错误: {error_str[:100]}")
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

        return None

    def _get_via_cors_proxy(
        self,
        url: str,
        params: dict = None,
        timeout: int = None,
    ) -> Optional[requests.Response]:
        """
        通过代理中转服务访问目标URL。
        当海外服务器无法直接访问中国政府网站时，通过中转服务转发请求。

        优先使用用户配置的 Cloudflare Worker (CORS_PROXY_URL 环境变量)，
        其次尝试公共CORS代理服务。

        部署自己的Cloudflare Worker: 见 cloudflare-worker.js 文件
        """
        if timeout is None:
            timeout = 25

        # 构建完整URL（含查询参数）
        full_url = url
        if params:
            query_string = urlencode(params)
            full_url = f"{url}?{query_string}"

        # 构建代理URL列表
        proxy_urls = []

        # 优先: 用户配置的 Cloudflare Worker
        if CORS_PROXY_URL:
            base = CORS_PROXY_URL.rstrip("/")
            proxy_urls.append({
                "url": f"{base}/?url={quote_plus(full_url)}",
                "source": "Cloudflare Worker",
                "proxy_base": CORS_PROXY_URL,
            })

        # 备用: 公共CORS代理（可能不稳定）
        proxy_urls.append({
            "url": f"https://api.allorigins.win/raw?url={quote_plus(full_url)}",
            "source": "公共CORS代理(allorigins)",
            "proxy_base": "https://api.allorigins.win",
        })
        proxy_urls.append({
            "url": f"https://corsproxy.io/?url={quote_plus(full_url)}",
            "source": "公共CORS代理(corsproxy)",
            "proxy_base": "https://corsproxy.io",
        })

        for proxy_info in proxy_urls:
            proxy_url = proxy_info["url"]
            source = proxy_info["source"]
            try:
                logger.info(
                    f"[{self.name}] 尝试{source}中转... "
                    f"代理地址={proxy_info['proxy_base']}"
                )
                simple_headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "application/json, text/plain, */*",
                }
                resp = requests.get(
                    proxy_url,
                    headers=simple_headers,
                    timeout=timeout,
                    verify=False,
                )
                if resp.status_code == 200 and resp.text:
                    # 尝试验证响应是否为有效JSON
                    is_json = False
                    try:
                        resp.json()
                        is_json = True
                    except ValueError:
                        pass

                    if is_json:
                        logger.info(f"[{self.name}] {source}中转成功! (JSON响应)")
                        self.last_error = ""
                        return resp
                    else:
                        # 即使不是JSON也返回，可能是HTML或其他格式
                        logger.info(f"[{self.name}] {source}中转成功! (非JSON, 长度={len(resp.text)})")
                        self.last_error = ""
                        return resp
                else:
                    logger.warning(
                        f"[{self.name}] {source}返回 HTTP {resp.status_code}, "
                        f"响应长度={len(resp.text) if resp.text else 0}"
                    )
                    if resp.text:
                        logger.warning(f"[{self.name}] 响应内容预览: {resp.text[:200]}")
                    continue
            except requests.exceptions.ConnectionError as e:
                err_str = str(e)[:200]
                logger.warning(f"[{self.name}] {source}连接失败: {err_str}")
                if "Name or service not known" in err_str or "Failed to resolve" in err_str:
                    logger.error(
                        f"[{self.name}] {source} DNS解析失败! "
                        f"代理地址={proxy_info['proxy_base']} "
                        f"请检查CORS_PROXY_URL环境变量是否正确"
                    )
                continue
            except requests.exceptions.Timeout:
                logger.warning(f"[{self.name}] {source}请求超时({timeout}s)")
                continue
            except Exception as e:
                logger.warning(f"[{self.name}] {source}中转失败: {e}")
                continue

        if CORS_PROXY_URL:
            self.last_error = f"网络不可达(代理{CORS_PROXY_URL}无法连接，请检查CORS_PROXY_URL配置)"
        else:
            self.last_error = "网络不可达(需配置CORS_PROXY_URL或CRAWL_PROXY)"
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
        """搜索招投标信息 (子类必须实现)"""
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
