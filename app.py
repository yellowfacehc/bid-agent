#!/usr/bin/env python3
"""
招投标信息查询 Web 应用 (重庆版)
==================================
提供 Web 界面，用户可通过日期、多关键词、区县等条件快速查询重庆招投标信息。

数据来源:
  - 重庆市政府采购网
  - 政企行业采购网
  - 九龙坡区小额平台
  - 重庆市政府采购云平台

启动: python app.py
访问: http://localhost:5000
"""

import os
import sys
import logging
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, render_template_string

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bid_agent import BidAgent, CHONGQING_DISTRICTS

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_agent = None


def get_agent() -> BidAgent:
    global _agent
    if _agent is None:
        _agent = BidAgent()
    return _agent


# 政府机关快捷关键词
GOV_KEYWORDS = [
    "公安局", "生态环境", "教育局", "卫健委", "住建委", "交通局",
    "水利局", "农业农村", "民政局", "人社局", "财政局", "自然资源",
    "应急管理", "市场监管", "城市管理", "司法局", "文旅委", "科技局",
    "审计局", "林业局", "气象局", "税务局", "退役军人", "医疗保障",
    "信息化", "网络安全", "智慧城市", "数字政府",
]


@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE,
        districts=CHONGQING_DISTRICTS,
        gov_keywords=GOV_KEYWORDS,
    )


@app.route("/api/districts")
def api_districts():
    return jsonify({"districts": CHONGQING_DISTRICTS})


@app.route("/api/search", methods=["POST"])
def api_search():
    """
    搜索招投标信息

    请求参数 (JSON):
      keywords:   关键词列表 (如 ["公安局", "生态环境"]), 也接受单个字符串
      days:       最近N天 (默认20)
      start_date: 开始日期 YYYY-MM-DD (可选)
      end_date:   结束日期 YYYY-MM-DD (可选)
      region:     重庆区县 (可选, 如 "沙坪坝区")
      max_pages:  最大爬取页数 (默认5)
    """
    data = request.get_json(force=True)

    # 关键词处理: 支持数组或字符串
    keywords = data.get("keywords", [])
    if isinstance(keywords, str):
        # 字符串按换行分割
        keywords = [k.strip() for k in keywords.split("\n") if k.strip()]
    keywords = [k for k in keywords if k.strip()]

    if not keywords:
        return jsonify({"error": "关键词不能为空", "items": [], "total": 0}), 400

    days = int(data.get("days", 20))
    start_date = data.get("start_date", "").strip()
    end_date = data.get("end_date", "").strip()
    region = data.get("region", "").strip()
    max_pages = min(int(data.get("max_pages", 5)), 10)

    logger.info(
        f"搜索请求: keywords={keywords}, days={days}, region='{region}', "
        f"start_date='{start_date}', end_date='{end_date}', max_pages={max_pages}"
    )

    try:
        agent = get_agent()
        items = agent.search(
            keywords=keywords,
            days=days,
            max_pages=max_pages,
            region=region,
            start_date=start_date,
            end_date=end_date,
        )

        regions_set = set(i.region for i in items if i.region)
        categories_set = set(i.category for i in items if i.category)
        sources_set = set(i.source for i in items if i.source)

        return jsonify({
            "success": True,
            "total": len(items),
            "keywords": keywords,
            "region": region,
            "search_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stats": {
                "regions": len(regions_set),
                "categories": len(categories_set),
                "sources": len(sources_set),
            },
            "items": [item.to_dict() for item in items],
        })
    except Exception as e:
        logger.error(f"搜索失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "items": [],
            "total": 0,
        }), 500


# ============================================================
# 前端 HTML 模板
# ============================================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>重庆招投标信息查询平台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: "Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif;
            background: linear-gradient(135deg, #0f5132 0%, #198754 100%);
            min-height: 100vh;
        }
        .navbar {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            padding: 16px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
        }
        .navbar .logo {
            font-size: 22px; font-weight: 700; color: #333;
            display: flex; align-items: center; gap: 10px;
        }
        .navbar .logo .icon {
            width: 36px; height: 36px;
            background: linear-gradient(135deg, #0f5132, #198754);
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            color: #fff; font-size: 18px;
        }
        .navbar .badge {
            background: #e8f5e9; color: #198754;
            padding: 4px 12px; border-radius: 20px;
            font-size: 12px; font-weight: 600;
        }
        .container { max-width: 1200px; margin: 30px auto; padding: 0 20px; }
        .search-card {
            background: #fff; border-radius: 16px; padding: 32px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15); margin-bottom: 24px;
        }
        .search-card h2 {
            font-size: 18px; color: #333; margin-bottom: 20px;
            display: flex; align-items: center; gap: 8px;
        }
        .search-card h2::before {
            content: ""; width: 4px; height: 18px;
            background: linear-gradient(180deg, #0f5132, #198754);
            border-radius: 2px;
        }
        .form-row {
            display: grid; grid-template-columns: 2fr 1fr 1fr 1fr;
            gap: 16px; margin-bottom: 16px;
        }
        .form-group { display: flex; flex-direction: column; }
        .form-group label {
            font-size: 13px; color: #666; margin-bottom: 6px; font-weight: 500;
        }
        .form-group input, .form-group select, .form-group textarea {
            padding: 10px 14px; border: 2px solid #e0e0e0;
            border-radius: 10px; font-size: 14px;
            transition: border-color 0.2s; font-family: inherit;
        }
        .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
            outline: none; border-color: #198754;
        }
        .form-group textarea { resize: vertical; min-height: 80px; }
        .search-btn {
            width: 100%; padding: 12px;
            background: linear-gradient(135deg, #0f5132, #198754);
            color: #fff; border: none; border-radius: 10px;
            font-size: 16px; font-weight: 600; cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }
        .search-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(25,135,84,0.4);
        }
        .search-btn:active { transform: translateY(0); }
        .search-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .quick-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
        .quick-tag {
            padding: 4px 12px; background: #e8f5e9; color: #198754;
            border-radius: 20px; font-size: 12px; cursor: pointer;
            border: 1px solid transparent; transition: all 0.2s;
        }
        .quick-tag:hover { background: #198754; color: #fff; }
        .quick-tag.active { background: #198754; color: #fff; }
        .stats-row {
            display: grid; grid-template-columns: repeat(5, 1fr);
            gap: 12px; margin-bottom: 24px;
        }
        .stat-card {
            background: #fff; border-radius: 12px; padding: 16px;
            text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }
        .stat-card .num {
            font-size: 28px; font-weight: 700;
            background: linear-gradient(135deg, #0f5132, #198754);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .stat-card .label { font-size: 12px; color: #888; margin-top: 4px; }
        .results-card {
            background: #fff; border-radius: 16px; overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }
        .results-header {
            padding: 20px 28px; border-bottom: 2px solid #f0f0f0;
            display: flex; justify-content: space-between; align-items: center;
        }
        .results-header h3 { font-size: 16px; color: #333; }
        .results-header .meta { font-size: 13px; color: #999; }
        .table-wrap { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; }
        th {
            background: #f8f9fa; padding: 12px 16px; text-align: left;
            font-size: 13px; color: #666; font-weight: 600;
            border-bottom: 2px solid #e8e8e8; white-space: nowrap;
        }
        td {
            padding: 14px 16px; border-bottom: 1px solid #f0f0f0;
            font-size: 14px; vertical-align: top;
        }
        tr:hover { background: #f0f7f0; }
        td.idx { color: #bbb; text-align: center; width: 40px; }
        td.title { max-width: 380px; }
        td.title a {
            color: #333; text-decoration: none; font-weight: 500; line-height: 1.5;
        }
        td.title a:hover { color: #198754; }
        td.date { white-space: nowrap; color: #666; font-size: 13px; }
        .tag {
            display: inline-block; padding: 2px 10px;
            border-radius: 4px; font-size: 12px; font-weight: 500; white-space: nowrap;
        }
        .tag-zb { background: #e3f2fd; color: #1976d2; }
        .tag-zb2 { background: #e8f5e9; color: #388e3c; }
        .tag-gz { background: #fff3e0; color: #e65100; }
        .tag-other { background: #f3e5f5; color: #7b1fa2; }
        .tag-region { background: #e0f7fa; color: #00838f; }
        .kw-badge {
            display: inline-block; padding: 2px 8px; background: #fce4ec;
            color: #c62828; border-radius: 4px; font-size: 11px; margin-left: 4px;
        }
        .loading-overlay { display: none; text-align: center; padding: 60px; }
        .spinner {
            width: 48px; height: 48px; border: 4px solid #e0e0e0;
            border-top-color: #198754; border-radius: 50%;
            animation: spin 0.8s linear infinite; margin: 0 auto 16px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading-text { color: #666; font-size: 14px; }
        .empty-state { text-align: center; padding: 60px; color: #999; }
        .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
        @media (max-width: 768px) {
            .form-row { grid-template-columns: 1fr 1fr; }
            .stats-row { grid-template-columns: repeat(2, 1fr); }
            .navbar { padding: 12px 16px; }
            .container { padding: 0 12px; margin: 16px auto; }
            .search-card { padding: 20px; }
            td.title { max-width: 200px; }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="logo">
            <div class="icon">CQ</div>
            <span>重庆招投标信息查询平台</span>
        </div>
        <div class="badge">4大采购平台 · 全重庆覆盖</div>
    </nav>

    <div class="container">
        <div class="search-card">
            <h2>搜索条件</h2>
            <div class="form-row">
                <div class="form-group" style="grid-column: span 2;">
                    <label>关键词（每行一个，支持多关键词联查）</label>
                    <textarea id="keywords" placeholder="公安局&#10;生态环境&#10;（每行输入一个关键词，结果取并集）">公安局</textarea>
                </div>
                <div class="form-group">
                    <label>区县</label>
                    <select id="region">
                        <option value="">全重庆</option>
                        <optgroup label="主城九区">
                            {% for d in districts[:9] %}
                            <option value="{{ d }}">{{ d }}</option>
                            {% endfor %}
                        </optgroup>
                        <optgroup label="其他区县">
                            {% for d in districts[9:] %}
                            <option value="{{ d }}">{{ d }}</option>
                            {% endfor %}
                        </optgroup>
                    </select>
                </div>
                <div class="form-group">
                    <label>开始日期</label>
                    <input type="date" id="startDate">
                </div>
            </div>
            <div class="form-row" style="grid-template-columns: 2fr 1fr 1fr 1fr;">
                <div class="form-group">
                    <label>快捷关键词（点击添加到输入框）</label>
                    <div class="quick-tags" id="quickTags">
                        {% for kw in gov_keywords %}
                        <span class="quick-tag" onclick="addKeyword('{{ kw }}')">{{ kw }}</span>
                        {% endfor %}
                    </div>
                </div>
                <div class="form-group">
                    <label>结束日期</label>
                    <input type="date" id="endDate">
                </div>
                <div class="form-group">
                    <label>最近天数</label>
                    <select id="days">
                        <option value="7">最近 7 天</option>
                        <option value="20" selected>最近 20 天</option>
                        <option value="30">最近 30 天</option>
                        <option value="60">最近 60 天</option>
                        <option value="90">最近 90 天</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>&nbsp;</label>
                    <button class="search-btn" id="searchBtn" onclick="doSearch()">搜索</button>
                </div>
            </div>
        </div>

        <div class="stats-row" id="statsRow" style="display:none;">
            <div class="stat-card"><div class="num" id="statTotal">0</div><div class="label">项目总数</div></div>
            <div class="stat-card"><div class="num" id="statRegions">0</div><div class="label">涉及区县</div></div>
            <div class="stat-card"><div class="num" id="statCategories">0</div><div class="label">公告类型</div></div>
            <div class="stat-card"><div class="num" id="statSources">0</div><div class="label">数据来源</div></div>
            <div class="stat-card"><div class="num" id="statToday">0</div><div class="label">今日发布</div></div>
        </div>

        <div class="results-card" id="resultsCard" style="display:none;">
            <div class="results-header">
                <h3>搜索结果</h3>
                <div class="meta" id="resultsMeta"></div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>项目标题</th>
                            <th>发布日期</th>
                            <th>区县</th>
                            <th>公告类型</th>
                            <th>采购人</th>
                            <th>来源</th>
                        </tr>
                    </thead>
                    <tbody id="resultsBody"></tbody>
                </table>
            </div>
        </div>

        <div class="results-card" id="loadingCard" style="display:none;">
            <div class="loading-overlay">
                <div class="spinner"></div>
                <div class="loading-text" id="loadingText">正在搜索重庆招投标信息，请稍候...（多关键词联查可能需要更长时间）</div>
            </div>
        </div>

        <div class="results-card" id="emptyCard" style="display:none;">
            <div class="empty-state">
                <div class="icon">📋</div>
                <div>未找到相关招投标信息，请尝试更换关键词或调整搜索条件</div>
            </div>
        </div>
    </div>

    <script>
        (function initDates() {
            var today = new Date();
            var start = new Date(today);
            start.setDate(start.getDate() - 20);
            document.getElementById('startDate').value = formatDate(start);
            document.getElementById('endDate').value = formatDate(today);
        })();

        function formatDate(d) {
            var y = d.getFullYear();
            var m = ('0' + (d.getMonth() + 1)).slice(-2);
            var day = ('0' + d.getDate()).slice(-2);
            return y + '-' + m + '-' + day;
        }

        function addKeyword(kw) {
            var ta = document.getElementById('keywords');
            var lines = ta.value.split('\n').map(function(l) { return l.trim(); }).filter(function(l) { return l; });
            if (lines.indexOf(kw) === -1) {
                lines.push(kw);
            }
            ta.value = lines.join('\n');
        }

        function getTagClass(category) {
            if (!category) return 'tag-other';
            if (category.indexOf('招标') >= 0 || category.indexOf('采购') >= 0 || category.indexOf('磋商') >= 0 || category.indexOf('谈判') >= 0)
                return 'tag-zb';
            if (category.indexOf('中标') >= 0 || category.indexOf('成交') >= 0 || category.indexOf('结果') >= 0)
                return 'tag-zb2';
            if (category.indexOf('更正') >= 0 || category.indexOf('变更') >= 0 || category.indexOf('终止') >= 0)
                return 'tag-gz';
            return 'tag-other';
        }

        function escapeHtml(text) {
            if (!text) return '';
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function doSearch() {
            var ta = document.getElementById('keywords');
            var keywords = ta.value.split('\n').map(function(l) { return l.trim(); }).filter(function(l) { return l; });
            if (keywords.length === 0) { alert('请输入至少一个关键词'); return; }

            var region = document.getElementById('region').value;
            var startDate = document.getElementById('startDate').value;
            var endDate = document.getElementById('endDate').value;
            var days = parseInt(document.getElementById('days').value);

            document.getElementById('searchBtn').disabled = true;
            document.getElementById('searchBtn').textContent = '搜索中...';
            document.getElementById('statsRow').style.display = 'none';
            document.getElementById('resultsCard').style.display = 'none';
            document.getElementById('emptyCard').style.display = 'none';
            document.getElementById('loadingCard').style.display = 'block';
            document.getElementById('loadingText').textContent =
                '正在搜索 ' + keywords.length + ' 个关键词，查询4个平台...（约需15-60秒）';

            fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keywords: keywords,
                    region: region,
                    start_date: startDate,
                    end_date: endDate,
                    days: days,
                    max_pages: 5
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                document.getElementById('loadingCard').style.display = 'none';
                document.getElementById('searchBtn').disabled = false;
                document.getElementById('searchBtn').textContent = '搜索';

                if (data.success === false || data.error) {
                    alert('搜索失败: ' + (data.error || '未知错误'));
                    return;
                }
                renderResults(data);
            })
            .catch(function(err) {
                document.getElementById('loadingCard').style.display = 'none';
                document.getElementById('searchBtn').disabled = false;
                document.getElementById('searchBtn').textContent = '搜索';
                alert('请求失败: ' + err.message);
            });
        }

        function renderResults(data) {
            var items = data.items || [];
            var total = data.total || 0;
            if (total === 0) {
                document.getElementById('emptyCard').style.display = 'block';
                return;
            }

            document.getElementById('statTotal').textContent = total;
            document.getElementById('statRegions').textContent = data.stats ? data.stats.regions : 0;
            document.getElementById('statCategories').textContent = data.stats ? data.stats.categories : 0;
            document.getElementById('statSources').textContent = data.stats ? data.stats.sources : 0;

            var today = new Date();
            var todayStr = today.getFullYear() + '-' +
                ('0' + (today.getMonth() + 1)).slice(-2) + '-' +
                ('0' + today.getDate()).slice(-2);
            var todayCount = items.filter(function(i) { return i.publish_date === todayStr; }).length;
            document.getElementById('statToday').textContent = todayCount;
            document.getElementById('statsRow').style.display = 'grid';

            var kwStr = data.keywords.join(' + ');
            document.getElementById('resultsMeta').textContent =
                '关键词: ' + kwStr + ' | 共 ' + total + ' 条 | ' + data.search_time;

            var html = '';
            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                var tagClass = getTagClass(item.category);
                html += '<tr>';
                html += '<td class="idx">' + (i + 1) + '</td>';
                html += '<td class="title"><a href="' + escapeHtml(item.url) + '" target="_blank">' + escapeHtml(item.title) + '</a></td>';
                html += '<td class="date">' + escapeHtml(item.publish_date || '-') + '</td>';
                html += '<td>' + (item.region ? '<span class="tag tag-region">' + escapeHtml(item.region) + '</span>' : '-') + '</td>';
                html += '<td>' + (item.category ? '<span class="tag ' + tagClass + '">' + escapeHtml(item.category) + '</span>' : '-') + '</td>';
                html += '<td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escapeHtml(item.buyer) + '">' + escapeHtml(item.buyer || '-') + '</td>';
                html += '<td style="font-size:12px;color:#999;white-space:nowrap;">' + escapeHtml(item.source) + '</td>';
                html += '</tr>';
            }
            document.getElementById('resultsBody').innerHTML = html;
            document.getElementById('resultsCard').style.display = 'block';
        }
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  重庆招投标信息查询平台")
    print("  访问地址: http://localhost:5000")
    print("  数据来源: 4个重庆采购平台")
    print("=" * 50 + "\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
