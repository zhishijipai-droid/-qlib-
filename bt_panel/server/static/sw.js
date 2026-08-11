/**
 * Service Worker — 拦截 /api/* 请求，返回预生成的 JSON 文件
 * 
 * 策略:
 *   1. /api/strategies/{id}/source  → /api/strategies/{id}_source.json
 *   2. /api/strategies/{id}          → /api/strategies/{id}.json
 *   3. /api/strategies               → /api/strategies.json
 *   4. /api/overview                 → /api/overview.json
 *   5. /api/trades                   → /api/trades.json
 *   6. /api/positions                → /api/positions.json
 *   7. /api/risk/overview            → /api/risk_overview.json
 *   8. /api/portfolios               → /api/portfolios.json
 *   9. /api/health                   → /api/health.json
 *  10. /api/backtests                → /api/backtests.json
 *  11. /api/backtests/{id}/result    → /api/backtests.json (static stub)
 *  12. POST /api/*                   → {"ok": false, "message": "静态网站不支持写入"}
 */

const API_PATTERNS = [
  // source 必须在 strategies/:id 之前匹配
  [/^\/api\/strategies\/([^/]+)\/source$/, (m) => `/api/strategies/${m[1]}_source.json`],
  [/^\/api\/strategies\/([^/]+)$/,        (m) => `/api/strategies/${m[1]}.json`],
  [/^\/api\/strategies$/,                 ()   => '/api/strategies.json'],
  [/^\/api\/overview$/,                   ()   => '/api/overview.json'],
  [/^\/api\/trades$/,                     ()   => '/api/trades.json'],
  [/^\/api\/positions$/,                  ()   => '/api/positions.json'],
  [/^\/api\/risk\/overview$/,            ()   => '/api/risk_overview.json'],
  [/^\/api\/portfolios$/,                ()   => '/api/portfolios.json'],
  [/^\/api\/health$/,                    ()   => '/api/health.json'],
  [/^\/api\/backtests\/[^/]+\/result$/,  ()   => '/api/backtests.json'],
  [/^\/api\/backtests\/[^/]+$/,          ()   => '/api/backtests.json'],
  [/^\/api\/backtests$/,                 ()   => '/api/backtests.json'],
  [/^\/api\//,                            ()   => null],  // 未知 API → 404
];

function apiPathToFile(urlPath, method) {
  // POST 请求统一返回静态提示
  if (method === 'POST') {
    // 去掉开头 /
    const path = urlPath.startsWith('/') ? urlPath.slice(1) : urlPath;
    let file = path.replace(/\//g, '_') + '.json';
    return `/api/${file}`;
  }
  
  for (const [pattern, handler] of API_PATTERNS) {
    const match = urlPath.match(pattern);
    if (match) {
      return handler(match);
    }
  }
  return null;
}

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // 只处理 API 请求
  if (!url.pathname.startsWith('/api/')) {
    return;
  }

  const file = apiPathToFile(url.pathname, event.request.method);
  if (!file) {
    return;
  }

  event.respondWith(
    caches.open('api-data-v1').then(async (cache) => {
      // 先查缓存
      const cached = await cache.match(file);
      if (cached) return cached;
      
      // 从网络加载 → 缓存
      try {
        const response = await fetch(file);
        if (response.ok) {
          cache.put(file, response.clone());
          return response;
        }
      } catch (e) {
        // 网络失败，返回 404 stub
      }
      
      return new Response(JSON.stringify({ error: "data not found" }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    })
  );
});
