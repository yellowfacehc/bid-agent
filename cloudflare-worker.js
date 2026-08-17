/**
 * Cloudflare Worker - 政府网站API代理
 * ================================
 * 作用: 当海外服务器(如Render)无法直接访问中国政府网站时，
 *       通过Cloudflare Worker中转请求。
 *
 * Cloudflare拥有全球边缘网络(包括中国大陆节点)，可以访问中国政府网站。
 *
 * 部署步骤:
 * 1. 注册/登录 Cloudflare 账号 (https://dash.cloudflare.com)
 * 2. 左侧菜单选择 "Workers & Pages"
 * 3. 点击 "Create application" → "Create Worker"
 * 4. 给Worker起名(如 "gov-proxy")，点击 "Deploy"
 * 5. 点击 "Edit code"，将本文件内容粘贴进去
 * 6. 点击 "Save and deploy"
 * 7. 复制Worker URL (如 https://gov-proxy.your-name.workers.dev)
 * 8. 在Render环境变量中设置:
 *    CORS_PROXY_URL = https://gov-proxy.your-name.workers.dev
 *
 * 免费额度: 每天 100,000 次请求，足够使用。
 */

export default {
  async fetch(request) {
    // 处理 CORS 预检请求
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': '*',
        },
      });
    }

    const url = new URL(request.url);

    // 获取目标URL参数
    const targetUrl = url.searchParams.get('url');
    if (!targetUrl) {
      return new Response(JSON.stringify({
        error: 'Missing "url" parameter',
        usage: 'Append ?url=<target_url> to proxy requests'
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    try {
      // 转发请求到目标URL
      const headers = new Headers();
      // 模拟浏览器请求头
      headers.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36');
      headers.set('Accept', 'application/json, text/plain, */*');
      headers.set('Accept-Language', 'zh-CN,zh;q=0.9,en;q=0.8');

      // 如果有额外的查询参数，添加到目标URL
      const targetUrlObj = new URL(targetUrl);
      for (const [key, value] of url.searchParams.entries()) {
        if (key !== 'url') {
          targetUrlObj.searchParams.set(key, value);
        }
      }

      const response = await fetch(targetUrlObj.toString(), {
        method: request.method,
        headers: headers,
      });

      const data = await response.text();

      return new Response(data, {
        status: response.status,
        headers: {
          'Content-Type': response.headers.get('Content-Type') || 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      });
    } catch (error) {
      return new Response(JSON.stringify({
        error: 'Proxy request failed',
        message: error.message,
        targetUrl: targetUrl,
      }), {
        status: 502,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      });
    }
  },
};
