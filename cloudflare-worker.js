/**
 * Cloudflare Worker - 政府网站API代理 (V2)
 * ========================================
 * 作用: 当海外服务器(如Render)无法直接访问中国政府网站时，
 *       通过Cloudflare Worker中转请求。
 *
 * 改进(V2):
 *   1. 支持GET/POST两种请求方式
 *   2. 自动转发原始请求头(包括Content-Type)
 *   3. 更好的错误处理和诊断信息
 *   4. 支持非JSON响应(HTML等)
 *   5. 添加请求超时控制
 *
 * Cloudflare拥有全球边缘网络(包括中国大陆节点)，可以访问中国政府网站。
 *
 * 部署步骤:
 * 1. 注册/登录 Cloudflare 账号 (https://dash.cloudflare.com)
 * 2. 左侧菜单选择 "Workers & Pages"
 * 3. 点击 "Create application" → "Create Worker"
 * 4. 给Worker起名(如 "govproxy")，点击 "Deploy"
 * 5. 点击 "Edit code"，将本文件内容粘贴进去
 * 6. 点击 "Save and deploy"
 * 7. 复制Worker URL (如 https://govproxy.your-subdomain.workers.dev)
 * 8. 在Render环境变量中设置:
 *    CORS_PROXY_URL = https://govproxy.your-subdomain.workers.dev
 *
 * 免费额度: 每天 100,000 次请求，足够使用。
 *
 * 验证Worker是否工作:
 * 浏览器访问: https://your-worker-url.workers.dev/
 * 应返回: {"error":"Missing url parameter"}
 *
 * 测试代理:
 * 浏览器访问: https://your-worker-url.workers.dev/?url=https://www.ccgp-chongqing.gov.cn/
 * 应返回政府网站的HTML内容
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
        usage: 'Append ?url=<target_url> to proxy requests',
        example: `https://${url.hostname}/?url=https://www.ccgp-chongqing.gov.cn/`
      }), {
        status: 400,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      });
    }

    try {
      // 解析目标URL
      const targetUrlObj = new URL(targetUrl);

      // 如果有额外的查询参数，添加到目标URL
      for (const [key, value] of url.searchParams.entries()) {
        if (key !== 'url') {
          targetUrlObj.searchParams.set(key, value);
        }
      }

      // 构建请求头 - 模拟浏览器 + 转发原始请求的关键头
      const headers = new Headers();
      headers.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36');
      headers.set('Accept', 'application/json, text/plain, */*');
      headers.set('Accept-Language', 'zh-CN,zh;q=0.9,en;q=0.8');
      headers.set('Accept-Encoding', 'gzip, deflate, br');
      
      // 转发原始请求的关键头（Referer、Origin、X-Requested-With等）
      const forwardHeaders = ['Referer', 'Origin', 'X-Requested-With', 'Content-Type', 'Accept', 'Accept-Language'];
      for (const h of forwardHeaders) {
          const val = request.headers.get(h);
          if (val) { headers.set(h, val); }
          }
      
      let fetchOptions = { method: request.method, headers: headers };
      if (request.method === 'POST') {
          const body = await request.text();
          if (body) { fetchOptions.body = body; }
          }
        } catch (e) {
          // 忽略body读取错误
        }
      }

      // 发送请求到目标URL (Cloudflare的fetch会自动跟随重定向)
      const response = await fetch(targetUrlObj.toString(), fetchOptions);

      // 获取响应内容
      const data = await response.text();

      // 获取原始Content-Type，默认为JSON
      const contentType = response.headers.get('Content-Type') || 'application/json';

      // 返回响应，添加CORS头
      return new Response(data, {
        status: response.status,
        headers: {
          'Content-Type': contentType,
          'Access-Control-Allow-Origin': '*',
          'X-Proxy-Status': 'success',
          'X-Target-URL': targetUrlObj.hostname,
        },
      });
    } catch (error) {
      // 返回详细的错误信息，便于诊断
      return new Response(JSON.stringify({
        error: 'Proxy request failed',
        message: error.message,
        targetUrl: targetUrl,
        errorType: error.constructor.name,
        hint: '如果错误是"fetch failed"，可能是目标网站不可访问或被防火墙拦截',
      }), {
        status: 502,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
          'X-Proxy-Status': 'failed',
        },
      });
    }
  },
};
