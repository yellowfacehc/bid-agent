#!/usr/bin/env python3
"""
招投标信息快速获取 Agent
==========================
功能：
  1. 自动爬取主流招投标官方网站（中国政府采购网、全国公共资源交易平台、中国招标投标公共服务平台）
  2. 按关键词搜索，仅列出最近 N 天内的相关招投标项目
  3. 输出项目真实链接，支持控制台表格 / JSON / HTML 报告

用法:
  python bid_agent.py --keyword "信息化" --days 20
  python bid_agent.py -k "信息化" -d 20 --output json
  python bid_agent.py -k "信息化" -d 20 --output html --output-file report.html
  python bid_agent.py -k "信息化" --platforms ccgp,ggzy
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

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawlers import CCGPCrawler, GGZYCrawler, CEBPubCrawler, BidItem


# ============================================================
# 日志配置
# ============================================================
def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ============================================================
# 核心 Agent
# ============================================================
class BidAgent:
    """招投标信息获取 Agent - 多平台并行搜索"""

    # 平台注册表
    PLATFORM_REGISTRY = {
        "ccgp": ("中国政府采购网", CCGPCrawler),
        "ggzy": ("全国公共资源交易平台", GGZYCrawler),
        "cebpub": ("中国招标投标公共服务平台", CEBPubCrawler),
    }

    def __init__(self, platforms: Optional[List[str]] = None):
        """
        初始化 Agent

        Args:
            platforms: 指定启用的平台列表 (如 ["ccgp", "ggzy"])，
                       None 表示启用全部平台
        """
        if platforms:
            self.platforms = {
                k: v for k, v in self.PLATFORM_REGISTRY.items() if k in platforms
            }
        else:
            self.platforms = dict(self.PLATFORM_REGISTRY)

        if not self.platforms:
            raise ValueError("没有可用的爬虫平台，请检查 platforms 参数")

        # 初始化爬虫实例
        self.crawlers: Dict[str, object] = {}
        for key, (name, crawler_cls) in self.platforms.items():
            self.crawlers[key] = crawler_cls()
            logging.info(f"已加载平台: {name} ({key})")

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
        并行搜索所有平台的招投标信息

        Args:
            keyword: 搜索关键词，如 "信息化"
            days: 搜索最近多少天的数据
            max_pages: 每个平台最大爬取页数
            region: 地区名称 (如 "广东"), 空字符串表示全国
            start_date: 自定义开始日期 (YYYY-MM-DD), 优先于 days
            end_date: 自定义结束日期 (YYYY-MM-DD)

        Returns:
            合并去重后的 BidItem 列表，按日期降序排列
        """
        all_items: List[BidItem] = []
        stats: Dict[str, int] = {}

        # 并行搜索各平台
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_platform = {}
            for key, crawler in self.crawlers.items():
                future = executor.submit(
                    crawler.search, keyword, days, max_pages,
                    region, start_date, end_date,
                )
                future_to_platform[future] = key

            for future in as_completed(future_to_platform):
                platform_key = future_to_platform[future]
                platform_name = self.platforms[platform_key][0]
                try:
                    items = future.result()
                    stats[platform_name] = len(items)
                    all_items.extend(items)
                    logging.info(f"平台 [{platform_name}] 返回 {len(items)} 条结果")
                except Exception as e:
                    stats[platform_name] = 0
                    logging.error(f"平台 [{platform_name}] 搜索失败: {e}")

        # 日期过滤 (确保所有结果都在指定范围内)
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
                    # 日期格式异常的也保留
                    filtered_items.append(item)
            else:
                # 没有日期的也保留
                filtered_items.append(item)

        # 去重 (按标题+URL)
        seen = set()
        unique_items = []
        for item in filtered_items:
            key = (item.title.strip(), item.url.strip())
            if key not in seen and item.title:
                seen.add(key)
                unique_items.append(item)

        # 按日期降序排列 (有日期的在前，无日期的在后)
        unique_items.sort(
            key=lambda x: x.publish_date or "0000-00-00",
            reverse=True,
        )

        # 打印统计信息
        self._print_stats(stats, len(unique_items), keyword, days)

        return unique_items

    def _print_stats(
        self, stats: Dict[str, int], total: int, keyword: str, days: int
    ):
        """打印搜索统计"""
        print("\n" + "=" * 70)
        print(f"  招投标信息搜索结果")
        print(f"  关键词: {keyword}  |  时间范围: 最近 {days} 天")
        print("=" * 70)
        for name, count in stats.items():
            print(f"  {name}: {count} 条")
        print(f"  ─────────────────────────────")
        print(f"  去重后总计: {total} 条")
        print("=" * 70 + "\n")


# ============================================================
# 输出格式化
# ============================================================
def print_console_table(items: List[BidItem]):
    """控制台表格输出"""
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
        if item.agency:
            print(f"│ 代理机构: {item.agency}")
        print(f"│ 来源: {item.source}")
        print(f"│ 链接: {item.url}")
        print(f"└─────────────────────────────────────────────────\n")


def save_json(items: List[BidItem], filepath: str):
    """保存为 JSON 文件"""
    data = {
        "search_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(items),
        "items": [item.to_dict() for item in items],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存至: {filepath}")


def save_html(items: List[BidItem], filepath: str, keyword: str = "", days: int = 20):
    """保存为 HTML 报告"""
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
        .stats {{ display: flex; gap: 20px; padding: 20px 40px; background: #f8f9fa; border-bottom: 1px solid #e0e0e0; }}
        .stat-box {{ text-align: center; }}
        .stat-box .num {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
        .stat-box .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f5f7fa; padding: 12px 16px; text-align: left; font-size: 13px; color: #666; border-bottom: 2px solid #e0e0e0; white-space: nowrap; }}
        td {{ padding: 12px 16px; border-bottom: 1px solid #f0f0f0; font-size: 14px; vertical-align: top; }}
        tr:hover {{ background: #f8f9ff; }}
        td.num {{ color: #999; text-align: center; width: 40px; }}
        td.title {{ max-width: 400px; }}
        td.title a {{ color: #1a73e8; text-decoration: none; }}
        td.title a:hover {{ text-decoration: underline; }}
        td.date {{ white-space: nowrap; color: #666; }}
        .footer {{ padding: 20px 40px; text-align: center; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>招投标信息搜索报告</h1>
            <div class="meta">关键词: {html_lib.escape(keyword)} | 时间范围: 最近 {days} 天 | 搜索时间: {search_time}</div>
        </div>
        <div class="stats">
            <div class="stat-box"><div class="num">{len(items)}</div><div class="label">总项目数</div></div>
            <div class="stat-box"><div class="num">{len(set(i.source for i in items))}</div><div class="label">数据来源</div></div>
            <div class="stat-box"><div class="num">{len(set(i.region for i in items if i.region))}</div><div class="label">涉及地区</div></div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>项目标题</th>
                    <th>发布日期</th>
                    <th>地区</th>
                    <th>公告类型</th>
                    <th>采购人/平台</th>
                    <th>来源</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="7" style="text-align:center;padding:40px;color:#999;">未找到相关招投标信息</td></tr>'}
            </tbody>
        </table>
        <div class="footer">
            本报告由招投标信息获取 Agent 自动生成 | 数据来源: 中国政府采购网、全国公共资源交易平台、中国招标投标公共服务平台
        </div>
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
    parser = argparse.ArgumentParser(
        description="招投标信息快速获取 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python bid_agent.py -k "信息化" -d 20
  python bid_agent.py -k "信息化" -d 20 --output json
  python bid_agent.py -k "信息化" -d 20 --output html -o report.html
  python bid_agent.py -k "网络安全" -d 30 --platforms ccgp,ggzy
        """,
    )
    parser.add_argument(
        "-k", "--keyword", required=True, help="搜索关键词，如 '信息化'"
    )
    parser.add_argument(
        "-d", "--days", type=int, default=20, help="搜索最近多少天的数据 (默认: 20)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=5, help="每个平台最大爬取页数 (默认: 5)"
    )
    parser.add_argument(
        "--platforms",
        type=str,
        default=None,
        help="指定平台，逗号分隔 (ccgp,ggzy,cebpub)。默认全部启用",
    )
    parser.add_argument(
        "--output",
        choices=["console", "json", "html", "all"],
        default="console",
        help="输出格式 (默认: console)",
    )
    parser.add_argument(
        "-o", "--output-file", default=None, help="输出文件路径 (JSON/HTML)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="显示详细日志"
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    # 解析平台列表
    platforms = None
    if args.platforms:
        platforms = [p.strip() for p in args.platforms.split(",")]

    # 创建 Agent 并搜索
    agent = BidAgent(platforms=platforms)
    items = agent.search(args.keyword, args.days, args.max_pages)

    # 输出结果
    base_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.output in ("console", "all"):
        print_console_table(items)

    if args.output in ("json", "all"):
        if args.output == "all":
            filepath = os.path.join(base_dir, f"bid_results_{args.keyword}_{timestamp}.json")
        else:
            filepath = args.output_file or os.path.join(base_dir, f"bid_results_{args.keyword}_{timestamp}.json")
        save_json(items, filepath)

    if args.output in ("html", "all"):
        if args.output == "all":
            filepath = os.path.join(base_dir, f"bid_report_{args.keyword}_{timestamp}.html")
        else:
            filepath = args.output_file or os.path.join(base_dir, f"bid_report_{args.keyword}_{timestamp}.html")
        save_html(items, filepath, args.keyword, args.days)

    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
