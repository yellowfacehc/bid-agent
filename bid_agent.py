#!/usr/bin/env python3
"""
招投标信息快速获取 Agent (重庆版)
====================================
功能：
  1. 自动爬取重庆市4个采购平台
  2. 按关键词/多关键词搜索，仅列出最近 N 天内的相关招投标项目
  3. 支持按重庆区县筛选
  4. 输出项目真实链接，支持控制台表格 / JSON / HTML 报告

数据来源:
  - 重庆市政府采购网 (www.ccgp-chongqing.gov.cn)
  - 政企行业采购网 (www.gec123.com)
  - 九龙坡区小额平台 (cqjlp.gec123.com)
  - 重庆市政府采购云平台 (xj.ccgp-chongqing.gov.cn)

用法:
  python bid_agent.py -k "公安局" -d 20
  python bid_agent.py -k "公安局" -k "生态环境" -d 20
  python bid_agent.py -k "公安局" -d 20 --region "沙坪坝区"
"""

import argparse
import json
import logging
import os
import sys
import html as html_lib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawlers import CQCCGPCrawler, GEC123Crawler, CQYPTCrawler, BidItem


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# 重庆区县列表
CHONGQING_DISTRICTS = [
    # 主城九区
    "渝中区", "江北区", "沙坪坝区", "九龙坡区", "大渡口区",
    "南岸区", "北碚区", "渝北区", "巴南区",
    # 其他区县
    "万州区", "涪陵区", "长寿区", "綦江区", "永川区", "合川区",
    "南川区", "璧山区", "铜梁区", "潼南区", "大足区",
    "黔江区", "开州区", "梁平区", "武隆区",
    # 县
    "城口县", "丰都县", "垫江县", "忠县", "云阳县", "奉节县",
    "巫山县", "巫溪县", "石柱县", "秀山县", "酉阳县", "彭水县",
]


class BidAgent:
    """招投标信息获取 Agent - 重庆多平台并行搜索"""

    def __init__(self):
        """初始化重庆4个采购平台爬虫"""
        self.crawlers: Dict[str, object] = {
            "cqccgp": CQCCGPCrawler(),
            "gec123": GEC123Crawler(
                site_name="政企行业采购网",
                plat_domain="www.gec123.com",
                publish_site="1",
                api_base="https://www.gec123.com",
            ),
            "jlp": GEC123Crawler(
                site_name="九龙坡区小额平台",
                plat_domain="cqjlp.gec123.com",
                publish_site="2",
                api_base="https://qypt.gec123.com",
            ),
            "cqypt": CQYPTCrawler(),
        }
        for key, crawler in self.crawlers.items():
            logging.info(f"已加载平台: {crawler.name} ({key})")

    def search_single(
        self,
        keyword: str,
        days: int = 20,
        max_pages: int = 5,
        region: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[BidItem]:
        """搜索单个关键词，并行查询所有平台"""
        all_items: List[BidItem] = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_platform = {}
            for key, crawler in self.crawlers.items():
                future = executor.submit(
                    crawler.search, keyword, days, max_pages,
                    region, start_date, end_date,
                )
                future_to_platform[future] = (key, crawler.name)

            for future in as_completed(future_to_platform):
                key, name = future_to_platform[future]
                try:
                    items = future.result()
                    all_items.extend(items)
                    logging.info(f"平台 [{name}] 关键词'{keyword}' 返回 {len(items)} 条")
                except Exception as e:
                    logging.error(f"平台 [{name}] 关键词'{keyword}' 失败: {e}")

        return all_items

    def search(
        self,
        keywords: List[str],
        days: int = 20,
        max_pages: int = 5,
        region: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[BidItem]:
        """
        多关键词联查 - 返回所有关键词结果的并集

        Args:
            keywords: 关键词列表 (如 ["公安局", "生态环境"])
            days: 搜索最近多少天
            max_pages: 每个平台最大爬取页数
            region: 重庆区县名称, 空字符串表示全重庆
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD

        Returns:
            合并去重后的 BidItem 列表，按日期降序排列
        """
        all_items: List[BidItem] = []

        # 逐个关键词搜索
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            logging.info(f"=== 开始搜索关键词: {kw} ===")
            items = self.search_single(kw, days, max_pages, region, start_date, end_date)
            all_items.extend(items)

        # 日期过滤
        if start_date and end_date:
            filter_start = datetime.strptime(start_date, "%Y-%m-%d")
            filter_end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            filter_end = datetime.now()
            filter_start = filter_end - timedelta(days=days)

        filtered_items = []
        for item in all_items:
            if item.publish_date:
                try:
                    item_date = datetime.strptime(item.publish_date, "%Y-%m-%d")
                    if filter_start <= item_date <= filter_end:
                        filtered_items.append(item)
                except ValueError:
                    filtered_items.append(item)
            else:
                filtered_items.append(item)

        # 去重 (按标题+URL)
        seen = set()
        unique_items = []
        for item in filtered_items:
            key = (item.title.strip(), item.url.strip())
            if key not in seen and item.title:
                seen.add(key)
                unique_items.append(item)

        # 按日期降序
        unique_items.sort(
            key=lambda x: x.publish_date or "0000-00-00",
            reverse=True,
        )

        kw_str = " + ".join(keywords)
        self._print_stats(len(unique_items), kw_str, days, region)
        return unique_items

    def _print_stats(self, total: int, keyword: str, days: int, region: str):
        print("\n" + "=" * 70)
        print(f"  招投标信息搜索结果 (重庆)")
        print(f"  关键词: {keyword}  |  时间范围: 最近 {days} 天  |  地区: {region or '全重庆'}")
        print("=" * 70)
        for key, crawler in self.crawlers.items():
            print(f"  {crawler.name}: 已查询")
        print(f"  ─────────────────────────────")
        print(f"  去重后总计: {total} 条")
        print("=" * 70 + "\n")


# ============================================================
# 输出格式化
# ============================================================
def print_console_table(items: List[BidItem]):
    if not items:
        print("  未找到相关招投标信息。")
        return
    for i, item in enumerate(items, 1):
        print(f"┌─ [{i}] ─────────────────────────────────────────")
        print(f"│ 标题: {item.title}")
        print(f"│ 日期: {item.publish_date or '未知'}")
        print(f"│ 地区: {item.region or '未知'}")
        print(f"│ 类型: {item.category or '未知'}")
        if item.buyer:
            print(f"│ 采购人: {item.buyer}")
        print(f"│ 来源: {item.source}")
        print(f"│ 链接: {item.url}")
        print(f"└─────────────────────────────────────────────────\n")


def save_json(items: List[BidItem], filepath: str):
    data = {
        "search_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(items),
        "items": [item.to_dict() for item in items],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存至: {filepath}")


def save_html(items: List[BidItem], filepath: str, keyword: str = "", days: int = 20):
    search_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_html = ""
    for i, item in enumerate(items, 1):
        rows_html += f"""
        <tr>
            <td class="num">{i}</td>
            <td class="title"><a href="{html_lib.escape(item.url)}" target="_blank">{html_lib.escape(item.title)}</a></td>
            <td class="date">{html_lib.escape(item.publish_date or '未知')}</td>
            <td>{html_lib.escape(item.region or '未知')}</td>
            <td>{html_lib.escape(item.category or '未知')}</td>
            <td>{html_lib.escape(item.buyer or '-')}</td>
            <td>{html_lib.escape(item.source)}</td>
        </tr>"""

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>招投标信息搜索报告 - {html_lib.escape(keyword)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; background: #f0f2f5; color: #333; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; padding: 30px 40px; }}
        .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
        .header .meta {{ font-size: 14px; opacity: 0.85; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f5f7fa; padding: 12px 16px; text-align: left; font-size: 13px; color: #666; border-bottom: 2px solid #e0e0e0; white-space: nowrap; }}
        td {{ padding: 12px 16px; border-bottom: 1px solid #f0f0f0; font-size: 14px; vertical-align: top; }}
        tr:hover {{ background: #f8f9ff; }}
        td.num {{ color: #999; text-align: center; width: 40px; }}
        td.title {{ max-width: 400px; }}
        td.title a {{ color: #1a73e8; text-decoration: none; }}
        td.date {{ white-space: nowrap; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>招投标信息搜索报告 (重庆)</h1>
            <div class="meta">关键词: {html_lib.escape(keyword)} | 时间范围: 最近 {days} 天 | 搜索时间: {search_time}</div>
        </div>
        <table>
            <thead>
                <tr><th>#</th><th>项目标题</th><th>发布日期</th><th>地区</th><th>公告类型</th><th>采购人</th><th>来源</th></tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="7" style="text-align:center;padding:40px;color:#999;">未找到相关招投标信息</td></tr>'}
            </tbody>
        </table>
    </div>
</body>
</html>"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"\n  HTML报告已保存至: {filepath}")


# ============================================================
# 命令行入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="招投标信息快速获取 Agent (重庆版)")
    parser.add_argument("-k", "--keyword", action="append", required=True, help="搜索关键词 (可多次指定实现联查)")
    parser.add_argument("-d", "--days", type=int, default=20, help="搜索最近多少天 (默认: 20)")
    parser.add_argument("--max-pages", type=int, default=5, help="每个平台最大爬取页数 (默认: 5)")
    parser.add_argument("--region", type=str, default="", help="重庆区县 (如 '沙坪坝区'), 默认全重庆")
    parser.add_argument("--output", choices=["console", "json", "html", "all"], default="console")
    parser.add_argument("-o", "--output-file", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    setup_logging(args.verbose)

    agent = BidAgent()
    items = agent.search(
        keywords=args.keyword,
        days=args.days,
        max_pages=args.max_pages,
        region=args.region,
    )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    kw_str = "_".join(args.keyword)

    if args.output in ("console", "all"):
        print_console_table(items)
    if args.output in ("json", "all"):
        filepath = args.output_file or os.path.join(base_dir, f"bid_results_{kw_str}_{timestamp}.json")
        save_json(items, filepath)
    if args.output in ("html", "all"):
        filepath = args.output_file or os.path.join(base_dir, f"bid_report_{kw_str}_{timestamp}.html")
        save_html(items, filepath, kw_str, args.days)

    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
