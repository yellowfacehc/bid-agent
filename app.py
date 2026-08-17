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
      keywords:   关键词列表 (如 ["公安局", "生态环境"])
      start_date: 开始日期 YYYY-MM-DD
      end_date:   结束日期 YYYY-MM-DD
      region:     重庆区县 (可选)
      max_pages:  最大爬取页数 (默认3)
    """
    try:
        data = request.get_json(force=True, silent=True)
        if data is None:
            data = {}
    except Exception:
        return jsonify({"success": False, "error": "无效的JSON数据", "items": [], "total": 0}), 400

    # 关键词处理 - 同时支持列表和字符串
    keywords = data.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split("\n") if k.strip()]
    elif not isinstance(keywords, list):
        keywords = []
    keywords = [str(k).strip() for k in keywords if k and str(k).strip()]

    if not keywords:
        return jsonify({"success": False, "error": "关键词不能为空", "items": [], "total": 0}), 400

    start_date = str(data.get("start_date", "")).strip()
    end_date = str(data.get("end_date", "")).strip()
    region = str(data.get("region", "")).strip()

    # 多关键词时自动减少页数，避免超时
    if len(keywords) >= 3:
        max_pages = 2
    elif len(keywords) == 2:
        max_pages = 3
    else:
        max_pages = min(int(data.get("max_pages", 5)), 5)

    # 如果没有日期，默认最近20天
    if not start_date or not end_date:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=20)
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")

    logger.info(
        f"搜索请求: keywords={keywords}, region='{region}', "
        f"start_date='{start_date}', end_date='{end_date}', max_pages={max_pages}"
    )

    try:
        agent = get_agent()
        items = agent.search(
            keywords=keywords,
            days=20,
            max_pages=max_pages,
            region=region,
            start_date=start_date,
            end_date=end_date,
        )

        regions_set = set(i.region for i in items if i.region)
        categories_set = set(i.category for i in items if i.category)
        sources_set = set(i.source for i in items if i.source)

        # 安全序列化
        try:
            items_data = [item.to_dict() for item in items]
        except Exception as se:
            logger.error(f"序列化失败: {se}")
            items_data = []

        # 获取平台状态
        platform_status = {}
        try:
            platform_status = agent.platform_status
        except Exception:
            pass

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
            "platforms": platform_status,
            "items": items_data,
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
    <title>重庆招投标信息查询平台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --green-dark: #0f5132;
            --green: #198754;
            --green-light: #e8f5e9;
            --green-hover: #157347;
            --gray-border: #e0e0e0;
            --gray-bg: #f8f9fa;
            --text: #333;
            --text-light: #666;
            --text-muted: #999;
            --shadow: 0 2px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 8px 32px rgba(0,0,0,0.12);
            --radius: 12px;
        }
        html { -webkit-text-size-adjust: 100%; }
        body {
            font-family: "Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif;
            background: linear-gradient(135deg, #0f5132 0%, #198754 100%);
            min-height: 100vh;
            color: var(--text);
        }

        /* ===== 导航栏 ===== */
        .navbar {
            background: rgba(255,255,255,0.97);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .navbar .logo {
            font-size: 18px; font-weight: 700; color: var(--text);
            display: flex; align-items: center; gap: 8px;
        }
        .navbar .logo .icon {
            width: 32px; height: 32px;
            background: linear-gradient(135deg, var(--green-dark), var(--green));
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            color: #fff; font-size: 14px; flex-shrink: 0;
        }
        .navbar .badge {
            background: var(--green-light); color: var(--green);
            padding: 4px 10px; border-radius: 20px;
            font-size: 11px; font-weight: 600; white-space: nowrap;
        }

        /* ===== 容器 ===== */
        .container { max-width: 1000px; margin: 0 auto; padding: 16px; }

        /* ===== 搜索卡片 ===== */
        .search-card {
            background: #fff; border-radius: var(--radius); padding: 24px;
            box-shadow: var(--shadow-lg); margin-bottom: 16px;
        }
        .section-title {
            font-size: 15px; color: var(--text); margin-bottom: 14px;
            display: flex; align-items: center; gap: 8px; font-weight: 600;
        }
        .section-title::before {
            content: ""; width: 4px; height: 16px;
            background: linear-gradient(180deg, var(--green-dark), var(--green));
            border-radius: 2px; flex-shrink: 0;
        }

        /* ===== 关键词输入区 ===== */
        .kw-section { margin-bottom: 18px; }
        .kw-label {
            font-size: 13px; color: var(--text-light); margin-bottom: 8px;
            font-weight: 500;
        }
        .kw-inputs { display: flex; flex-direction: column; gap: 8px; }
        .kw-row {
            display: flex; align-items: center; gap: 8px;
        }
        .kw-row input {
            flex: 1; padding: 10px 14px; border: 2px solid var(--gray-border);
            border-radius: 10px; font-size: 15px; font-family: inherit;
            transition: border-color 0.2s; min-width: 0;
            -webkit-appearance: none;
        }
        .kw-row input:focus { outline: none; border-color: var(--green); }
        .kw-btn {
            width: 40px; height: 40px; border: none; border-radius: 10px;
            font-size: 22px; font-weight: 600; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0; transition: all 0.15s; line-height: 1;
        }
        .kw-btn-add {
            background: var(--green-light); color: var(--green);
        }
        .kw-btn-add:hover { background: var(--green); color: #fff; }
        .kw-btn-del {
            background: #fff0f0; color: #dc3545;
        }
        .kw-btn-del:hover { background: #dc3545; color: #fff; }

        /* ===== 筛选行 ===== */
        .filter-row {
            display: grid; grid-template-columns: 1fr 1fr 1fr;
            gap: 12px; margin-bottom: 18px;
        }
        .form-group { display: flex; flex-direction: column; }
        .form-group label {
            font-size: 13px; color: var(--text-light); margin-bottom: 6px; font-weight: 500;
        }
        .form-group input, .form-group select {
            padding: 10px 14px; border: 2px solid var(--gray-border);
            border-radius: 10px; font-size: 14px; font-family: inherit;
            transition: border-color 0.2s; width: 100%;
            -webkit-appearance: none;
            background: #fff;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none; border-color: var(--green);
        }

        /* ===== 快捷关键词 ===== */
        .quick-tags-section { margin-bottom: 18px; }
        .quick-tags {
            display: flex; gap: 6px; flex-wrap: wrap;
        }
        .quick-tag {
            padding: 5px 12px; background: var(--green-light); color: var(--green);
            border-radius: 20px; font-size: 13px; cursor: pointer;
            border: 1px solid transparent; transition: all 0.2s;
            user-select: none; white-space: nowrap;
        }
        .quick-tag:hover { background: var(--green); color: #fff; }
        .quick-tag:active { transform: scale(0.95); }

        /* ===== 搜索按钮 ===== */
        .search-btn {
            width: 100%; padding: 13px;
            background: linear-gradient(135deg, var(--green-dark), var(--green));
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

        /* ===== 统计卡片 ===== */
        .stats-row {
            display: grid; grid-template-columns: repeat(5, 1fr);
            gap: 8px; margin-bottom: 16px;
        }
        .stat-card {
            background: #fff; border-radius: 10px; padding: 12px 6px;
            text-align: center; box-shadow: var(--shadow);
        }
        .stat-card .num {
            font-size: 22px; font-weight: 700;
            background: linear-gradient(135deg, var(--green-dark), var(--green));
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .stat-card .label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

        /* ===== 结果区域 ===== */
        .results-card {
            background: #fff; border-radius: var(--radius); overflow: hidden;
            box-shadow: var(--shadow);
        }
        .results-header {
            padding: 14px 20px; border-bottom: 2px solid #f0f0f0;
            display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; gap: 6px;
        }
        .results-header h3 { font-size: 15px; color: var(--text); }
        .results-header .meta { font-size: 12px; color: var(--text-muted); }

        /* ===== 桌面端表格 ===== */
        .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        table { width: 100%; border-collapse: collapse; }
        th {
            background: var(--gray-bg); padding: 10px 14px; text-align: left;
            font-size: 13px; color: var(--text-light); font-weight: 600;
            border-bottom: 2px solid #e8e8e8; white-space: nowrap;
        }
        td {
            padding: 12px 14px; border-bottom: 1px solid #f0f0f0;
            font-size: 14px; vertical-align: top;
        }
        tr:hover { background: #f0f7f0; }
        td.idx { color: #bbb; text-align: center; width: 40px; }
        td.title { max-width: 380px; }
        td.title a {
            color: var(--text); text-decoration: none; font-weight: 500; line-height: 1.5;
        }
        td.title a:hover { color: var(--green); }
        td.date { white-space: nowrap; color: var(--text-light); font-size: 13px; }
        .tag {
            display: inline-block; padding: 2px 10px;
            border-radius: 4px; font-size: 12px; font-weight: 500; white-space: nowrap;
        }
        .tag-zb { background: #e3f2fd; color: #1976d2; }
        .tag-zb2 { background: #e8f5e9; color: #388e3c; }
        .tag-gz { background: #fff3e0; color: #e65100; }
        .tag-other { background: #f3e5f5; color: #7b1fa2; }
        .tag-region { background: #e0f7fa; color: #00838f; }

        /* ===== 移动端卡片式结果 ===== */
        .mobile-results { display: none; }
        .m-result-card {
            padding: 14px 16px; border-bottom: 1px solid #f0f0f0;
        }
        .m-result-card:active { background: #f0f7f0; }
        .m-result-card .m-title {
            font-size: 15px; font-weight: 500; line-height: 1.5;
            margin-bottom: 8px;
        }
        .m-result-card .m-title a {
            color: var(--text); text-decoration: none;
        }
        .m-result-card .m-title a:active { color: var(--green); }
        .m-result-card .m-info {
            display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px;
        }
        .m-result-card .m-meta {
            font-size: 12px; color: var(--text-muted);
            display: flex; gap: 12px; flex-wrap: wrap;
        }
        .m-result-card .m-meta span { white-space: nowrap; }

        /* ===== 加载/空状态 ===== */
        .loading-overlay { display: none; text-align: center; padding: 50px 20px; }
        .spinner {
            width: 44px; height: 44px; border: 4px solid #e0e0e0;
            border-top-color: var(--green); border-radius: 50%;
            animation: spin 0.8s linear infinite; margin: 0 auto 14px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading-text { color: var(--text-light); font-size: 14px; }
        .empty-state { text-align: center; padding: 50px 20px; color: var(--text-muted); }
        .empty-state .icon { font-size: 44px; margin-bottom: 10px; }

        /* ===== 平台状态 ===== */
        .platform-status {
            background: #fff; border-radius: var(--radius); padding: 14px 20px;
            box-shadow: var(--shadow); margin-bottom: 16px;
        }
        .platform-status .ps-title {
            font-size: 13px; color: var(--text-light); margin-bottom: 10px; font-weight: 500;
        }
        .platform-status .ps-list {
            display: flex; flex-wrap: wrap; gap: 8px;
        }
        .ps-item {
            display: flex; align-items: center; gap: 6px;
            padding: 5px 12px; border-radius: 20px; font-size: 13px;
        }
        .ps-ok { background: #e8f5e9; color: #2e7d32; }
        .ps-fail { background: #ffebee; color: #c62828; }
        .ps-item .dot {
            width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
        }
        .ps-ok .dot { background: #4caf50; }
        .ps-fail .dot { background: #f44336; }
        .ps-item .count { font-weight: 600; }

        /* ===== 移动端响应式 ===== */
        @media (max-width: 768px) {
            .navbar { padding: 10px 14px; }
            .navbar .logo { font-size: 15px; gap: 6px; }
            .navbar .logo .icon { width: 28px; height: 28px; font-size: 12px; border-radius: 6px; }
            .navbar .badge { font-size: 10px; padding: 3px 8px; }

            .container { padding: 10px 8px; }
            .search-card { padding: 16px 14px; border-radius: 10px; }
            .section-title { font-size: 14px; margin-bottom: 12px; }

            .kw-row input { font-size: 16px; padding: 9px 12px; }
            .kw-btn { width: 38px; height: 38px; font-size: 20px; }

            .filter-row { grid-template-columns: 1fr; gap: 10px; }
            .form-group input, .form-group select { font-size: 16px; padding: 9px 12px; }

            .quick-tag { font-size: 12px; padding: 4px 10px; }

            .search-btn { font-size: 15px; padding: 12px; }

            .stats-row { grid-template-columns: repeat(3, 1fr); gap: 6px; }
            .stat-card { padding: 10px 4px; }
            .stat-card .num { font-size: 18px; }
            .stat-card .label { font-size: 10px; }

            .results-header { padding: 12px 14px; }
            .results-header h3 { font-size: 14px; }
            .results-header .meta { font-size: 11px; }

            /* 移动端使用卡片式结果，隐藏表格 */
            .table-wrap { display: none; }
            .mobile-results { display: block; }
        }

        @media (max-width: 480px) {
            .navbar .badge { display: none; }
            .navbar .logo { font-size: 14px; }
            .stats-row { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="logo">
            <div class="icon">CQ</div>
            <span>重庆招投标信息查询</span>
        </div>
        <div class="badge">4大平台 · 全重庆</div>
    </nav>

    <div class="container">
        <!-- 搜索表单 -->
        <div class="search-card">
            <div class="section-title">搜索条件</div>

            <!-- 关键词输入区 -->
            <div class="kw-section">
                <div class="kw-label">关键词（点击 + 添加更多，结果取并集）</div>
                <div class="kw-inputs" id="kwInputs">
                    <div class="kw-row">
                        <input type="text" class="kw-input" placeholder="输入关键词，如：信息化" value="信息化">
                        <button class="kw-btn kw-btn-add" onclick="addKwRow(this)" title="添加关键词">+</button>
                    </div>
                </div>
            </div>

            <!-- 筛选条件 -->
            <div class="filter-row">
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
                <div class="form-group">
                    <label>结束日期</label>
                    <input type="date" id="endDate">
                </div>
            </div>

            <!-- 快捷关键词 -->
            <div class="quick-tags-section">
                <div class="kw-label">快捷关键词（点击填入输入框）</div>
                <div class="quick-tags" id="quickTags">
                    {% for kw in gov_keywords %}
                    <span class="quick-tag" onclick="fillQuickKw('{{ kw }}')">{{ kw }}</span>
                    {% endfor %}
                </div>
            </div>

            <!-- 搜索按钮 -->
            <button class="search-btn" id="searchBtn" onclick="doSearch()">搜索</button>
        </div>

        <!-- 统计 -->
        <div class="stats-row" id="statsRow" style="display:none;">
            <div class="stat-card"><div class="num" id="statTotal">0</div><div class="label">项目总数</div></div>
            <div class="stat-card"><div class="num" id="statRegions">0</div><div class="label">涉及区县</div></div>
            <div class="stat-card"><div class="num" id="statCategories">0</div><div class="label">公告类型</div></div>
            <div class="stat-card"><div class="num" id="statSources">0</div><div class="label">数据来源</div></div>
            <div class="stat-card"><div class="num" id="statToday">0</div><div class="label">今日发布</div></div>
        </div>

        <!-- 平台状态 -->
        <div class="platform-status" id="platformStatus" style="display:none;"></div>

        <!-- 加载中 -->
        <div class="results-card" id="loadingCard" style="display:none;">
            <div class="loading-overlay">
                <div class="spinner"></div>
                <div class="loading-text" id="loadingText">正在搜索...</div>
            </div>
        </div>

        <!-- 结果区域 -->
        <div class="results-card" id="resultsCard" style="display:none;">
            <div class="results-header">
                <h3>搜索结果</h3>
                <div class="meta" id="resultsMeta"></div>
            </div>
            <!-- 桌面端表格 -->
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
            <!-- 移动端卡片式结果 -->
            <div class="mobile-results" id="mobileResults"></div>
        </div>

        <!-- 空状态 -->
        <div class="results-card" id="emptyCard" style="display:none;">
            <div class="empty-state">
                <div class="icon">📋</div>
                <div>未找到相关招投标信息，请尝试更换关键词或调整搜索条件</div>
            </div>
        </div>
    </div>

    <script>
        // ===== 日期初始化 =====
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

        // ===== 关键词输入框管理 =====
        function addKwRow(btn) {
            var container = document.getElementById('kwInputs');
            var rows = container.querySelectorAll('.kw-row');
            if (rows.length >= 5) {
                alert('最多支持5个关键词联查');
                return;
            }
            // 把当前+按钮改为删除按钮
            btn.className = 'kw-btn kw-btn-del';
            btn.textContent = '\u2212';
            btn.title = '删除此关键词';
            btn.onclick = function() { delKwRow(this); };

            // 添加新行
            var newRow = document.createElement('div');
            newRow.className = 'kw-row';
            newRow.innerHTML =
                '<input type="text" class="kw-input" placeholder="输入关键词">' +
                '<button class="kw-btn kw-btn-add" onclick="addKwRow(this)" title="添加关键词">+</button>';
            container.appendChild(newRow);
            newRow.querySelector('input').focus();
        }

        function delKwRow(btn) {
            var row = btn.parentElement;
            var container = document.getElementById('kwInputs');
            // 至少保留一行
            if (container.querySelectorAll('.kw-row').length <= 1) return;
            row.remove();
            // 确保最后一行是+按钮
            var lastRow = container.querySelector('.kw-row:last-child');
            if (lastRow) {
                var lastBtn = lastRow.querySelector('.kw-btn');
                if (lastBtn && lastBtn.classList.contains('kw-btn-del')) {
                    lastBtn.className = 'kw-btn kw-btn-add';
                    lastBtn.textContent = '+';
                    lastBtn.title = '添加关键词';
                    lastBtn.onclick = function() { addKwRow(this); };
                }
            }
        }

        function fillQuickKw(kw) {
            // 填入第一个空的输入框，如果没有空的就填第一个
            var inputs = document.querySelectorAll('.kw-input');
            for (var i = 0; i < inputs.length; i++) {
                if (!inputs[i].value.trim()) {
                    inputs[i].value = kw;
                    return;
                }
            }
            // 所有框都有值，如果第一个框不是这个关键词就填入第一个
            if (inputs[0].value.trim() !== kw) {
                inputs[0].value = kw;
            }
        }

        function getKeywords() {
            var inputs = document.querySelectorAll('.kw-input');
            var keywords = [];
            for (var i = 0; i < inputs.length; i++) {
                var val = inputs[i].value.trim();
                if (val && keywords.indexOf(val) === -1) {
                    keywords.push(val);
                }
            }
            return keywords;
        }

        // ===== 搜索功能 =====
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
            var keywords = getKeywords();
            if (keywords.length === 0) {
                alert('请输入至少一个关键词');
                return;
            }

            var region = document.getElementById('region').value;
            var startDate = document.getElementById('startDate').value;
            var endDate = document.getElementById('endDate').value;

            var btn = document.getElementById('searchBtn');
            btn.disabled = true;
            btn.textContent = '搜索中...';
            document.getElementById('statsRow').style.display = 'none';
            document.getElementById('platformStatus').style.display = 'none';
            document.getElementById('resultsCard').style.display = 'none';
            document.getElementById('emptyCard').style.display = 'none';
            document.getElementById('loadingCard').style.display = 'block';
            document.getElementById('loadingText').textContent =
                '正在搜索 ' + keywords.length + ' 个关键词，查询4个平台...（约需10-40秒）';

            fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keywords: keywords,
                    region: region,
                    start_date: startDate,
                    end_date: endDate,
                    max_pages: 5
                })
            })
            .then(function(r) {
                if (!r.ok) {
                    return r.json().then(function(d) {
                        throw new Error(d.error || '服务器错误 (HTTP ' + r.status + ')');
                    }).catch(function(e) {
                        if (e instanceof Error && e.message) throw e;
                        throw new Error('服务器错误 (HTTP ' + r.status + ')，可能是请求超时');
                    });
                }
                return r.json();
            })
            .then(function(data) {
                document.getElementById('loadingCard').style.display = 'none';
                btn.disabled = false;
                btn.textContent = '搜索';

                if (data.success === false || data.error) {
                    alert('搜索失败: ' + (data.error || '未知错误'));
                    return;
                }
                renderResults(data);
            })
            .catch(function(err) {
                document.getElementById('loadingCard').style.display = 'none';
                btn.disabled = false;
                btn.textContent = '搜索';
                var msg = err.message || '网络请求失败';
                if (msg.indexOf('Failed to fetch') >= 0 || msg.indexOf('NetworkError') >= 0) {
                    msg = '请求超时或网络错误，请稍后重试（多关键词搜索可能需要更长时间）';
                }
                alert('请求失败: ' + msg);
            });
        }

        function renderResults(data) {
            var items = data.items || [];
            var total = data.total || 0;

            // 显示平台状态
            renderPlatformStatus(data.platforms);

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

            // 桌面端表格
            var html = '';
            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                var tagClass = getTagClass(item.category);
                html += '<tr>';
                html += '<td class="idx">' + (i + 1) + '</td>';
                html += '<td class="title"><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + escapeHtml(item.title) + '</a></td>';
                html += '<td class="date">' + escapeHtml(item.publish_date || '-') + '</td>';
                html += '<td>' + (item.region ? '<span class="tag tag-region">' + escapeHtml(item.region) + '</span>' : '-') + '</td>';
                html += '<td>' + (item.category ? '<span class="tag ' + tagClass + '">' + escapeHtml(item.category) + '</span>' : '-') + '</td>';
                html += '<td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escapeHtml(item.buyer) + '">' + escapeHtml(item.buyer || '-') + '</td>';
                html += '<td style="font-size:12px;color:#999;white-space:nowrap;">' + escapeHtml(item.source) + '</td>';
                html += '</tr>';
            }
            document.getElementById('resultsBody').innerHTML = html;

            // 移动端卡片式结果
            var mHtml = '';
            for (var j = 0; j < items.length; j++) {
                var mItem = items[j];
                var mTagClass = getTagClass(mItem.category);
                mHtml += '<div class="m-result-card">';
                mHtml += '<div class="m-title"><a href="' + escapeHtml(mItem.url) + '" target="_blank" rel="noopener">' + escapeHtml(mItem.title) + '</a></div>';
                mHtml += '<div class="m-info">';
                if (mItem.region) mHtml += '<span class="tag tag-region">' + escapeHtml(mItem.region) + '</span>';
                if (mItem.category) mHtml += '<span class="tag ' + mTagClass + '">' + escapeHtml(mItem.category) + '</span>';
                mHtml += '</div>';
                mHtml += '<div class="m-meta">';
                mHtml += '<span>' + escapeHtml(mItem.publish_date || '日期未知') + '</span>';
                if (mItem.buyer) mHtml += '<span>' + escapeHtml(mItem.buyer) + '</span>';
                mHtml += '<span>' + escapeHtml(mItem.source) + '</span>';
                mHtml += '</div>';
                mHtml += '</div>';
            }
            document.getElementById('mobileResults').innerHTML = mHtml;

            document.getElementById('resultsCard').style.display = 'block';
            // 滚动到结果区域
            document.getElementById('resultsCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        function renderPlatformStatus(platforms) {
            var container = document.getElementById('platformStatus');
            if (!platforms || Object.keys(platforms).length === 0) {
                container.style.display = 'none';
                return;
            }
            var html = '<div class="ps-title">平台查询状态</div><div class="ps-list">';
            for (var name in platforms) {
                if (!platforms.hasOwnProperty(name)) continue;
                var ps = platforms[name];
                var isOk = ps.ok || ps.count > 0;
                var cls = isOk ? 'ps-ok' : 'ps-fail';
                var dot = isOk ? '✓' : '✗';
                html += '<div class="ps-item ' + cls + '">';
                html += '<span class="dot"></span>';
                html += '<span>' + escapeHtml(name) + '</span>';
                if (isOk) {
                    html += '<span class="count">' + ps.count + '条</span>';
                } else {
                    html += '<span style="font-size:11px;opacity:0.7;">' + (ps.error ? '失败' : '无数据') + '</span>';
                }
                html += '</div>';
            }
            html += '</div>';
            container.innerHTML = html;
            container.style.display = 'block';
        }

        // 支持回车搜索
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && e.target.classList.contains('kw-input')) {
                e.preventDefault();
                doSearch();
            }
        });
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
