/**
 * 可选 · 外部官网 CMS 数据桥
 * 优先从同域 /api/v1/public/site 拉取，失败降级本地 site-data.js
 *
 * 用法：
 * <script src="/js/cms-bridge.js"></script>
 * <script>CenkorCMS.load().then(data => { ... });</script>
 */
(function (global) {
  const DEFAULT_API = '/api/v1/public/site';
  const FALLBACK_SCRIPT = '/assets/site-data.js';

  async function load(apiUrl) {
    const url = apiUrl || DEFAULT_API;
    try {
      const res = await fetch(url, { credentials: 'omit' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return await res.json();
    } catch (e) {
      console.warn('[CenkorCMS] API 失败，尝试降级:', e);
      if (global.SITE_DATA) return global.SITE_DATA;
      return new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = FALLBACK_SCRIPT;
        s.onload = () => resolve(global.SITE_DATA || {});
        s.onerror = () => reject(new Error('降级 site-data.js 也失败'));
        document.head.appendChild(s);
      });
    }
  }

  global.CenkorCMS = { load, DEFAULT_API };
})(window);
