"""
招投标信息爬虫模块
支持平台：
  - 中国政府采购网 (ccgp.gov.cn)
  - 全国公共资源交易平台 (ggzy.gov.cn)
  - 中国招标投标公共服务平台 (cebpubservice.com)
"""

from .base import BaseCrawler, BidItem
from .ccgp import CCGPCrawler
from .ggzy import GGZYCrawler
from .cebpub import CEBPubCrawler

__all__ = [
    "BaseCrawler",
    "BidItem",
    "CCGPCrawler",
    "GGZYCrawler",
    "CEBPubCrawler",
]
