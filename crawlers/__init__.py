"""招投标爬虫模块"""

from crawlers.base import BaseCrawler, BidItem
from crawlers.cqccgp import CQCCGPCrawler
from crawlers.gec123 import GEC123Crawler
from crawlers.cqypt import CQYPTCrawler
from crawlers.intention_cq import CQIntentionCrawler
from crawlers.intention_ccgp import CCGPIntentionCrawler

__all__ = [
    "BaseCrawler",
    "BidItem",
    "CQCCGPCrawler",
    "GEC123Crawler",
    "CQYPTCrawler",
    "CQIntentionCrawler",
    "CCGPIntentionCrawler",
]
