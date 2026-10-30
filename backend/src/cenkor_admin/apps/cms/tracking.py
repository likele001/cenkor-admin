"""内容埋点采集。

设计上的三个取舍：

1. **不要求前端改业务代码**。埋点脚本是自托管的，一行 ``<script>`` 接入。
   更进一步：上报只带 URL path，服务端用 ``slug`` 反查 entry_id，所以
   连「在模板里塞 meta 标签」这一步都省了。前端改动越少，接入越可能真发生。

2. **不用 CORS 预检**。埋点走 ``Content-Type: text/plain`` + ``sendBeacon``，
   这是 CORS 的 safelisted 类型，不触发预检，跨域直接能发。服务端手动
   解析 body。否则每个官网域名都得配一遍 CORS，漏一个就静默丢数据。

3. **防刷不靠拦，靠兜底**。埋点接口是公开的，任何拦法都能绕过。所以
   按 ``ip_hash`` 做日配额，超了静默丢弃（返回 200，不让刷的人知道被挡），
   同时把异常量记日志。真被刷了至少数据库不会被写爆。
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import analytics_models as am

log = structlog.get_logger()

BIZ_TZ = ZoneInfo("Asia/Shanghai")

# 允许的事件类型。白名单而不是黑名单：埋点接口对外开放，
# 任何没见过的类型都视为噪音，不写库。
EVENT_TYPES = ("pv", "heartbeat", "scroll", "conversion")

# 单 IP 单日事件上限。正常访客一天几十条，公司 NAT 后面几百人共享一个
# 出口 IP 也就几千条。给到 20000 是留足余量的同时挡住刷量。
IP_DAILY_QUOTA = 20000

# 单次上报最多携带的事件数
MAX_BATCH = 50

# 单条字段长度上限，防止有人塞超长字符串把索引撑爆
_MAX_PATH = 500
_MAX_REFERRER = 500

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_]{0,119}$")

# slug → entry_id 的进程内缓存。条目 slug 改动很少，缓存 5 分钟足够，
# 且能避免每个 PV 都查一次库。
_slug_cache: dict[str, tuple[int | None, float]] = {}
_SLUG_TTL = 300.0


def biz_today() -> date:
    """按业务时区取当前自然日。"""
    return datetime.now(BIZ_TZ).date()


def biz_date_of(ts: datetime | None = None) -> date:
    """把任意时间点换算成业务时区的自然日。"""
    if ts is None:
        return biz_today()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(BIZ_TZ).date()


def _digest(value: str, salt: str = "cms-track") -> str:
    """不可逆摘要。埋点表不放明文 IP / UA。"""
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:32]


def hash_client(ip: str | None, ua: str | None) -> tuple[str, str]:
    return _digest(ip or "", "ip"), _digest(ua or "", "ua")


def _clean_str(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "")[:limit]


def _clean_int(value: Any, *, low: int = 0, high: int = 86_400_000) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(low, min(high, n))


def _slug_from_path(path: str) -> str | None:
    """从 URL 路径里猜出 slug。

    只看最后一段，并排除纯数字（详情页 id 形式）和带扩展名的静态资源。
    猜不出来就返回 None，不硬凑 —— 关联错了比关联不上更糟。
    """
    if not path:
        return None
    seg = path.split("?")[0].split("#")[0].rstrip("/").rsplit("/", 1)[-1]
    if not seg or "." in seg:
        return None
    if not _SLUG_RE.match(seg):
        return None
    return seg


async def _resolve_entry_ids(db: AsyncSession, paths: list[str]) -> dict[str, int]:
    """把 slug 批量翻译成 entry_id。

    前端没给 entry_id 时，用 URL 最后一段当 slug 反查。这一步是「零前端改动
    也能关联内容」的关键 —— 官网模板不需要动，slug 本来就是给人看的。
    """
    wanted: set[str] = set()
    for p in paths:
        s = _slug_from_path(p)
        if s:
            wanted.add(s)
    if not wanted:
        return {}

    now = datetime.now(UTC).timestamp()
    out: dict[str, int] = {}
    todo: list[str] = []
    for slug in wanted:
        hit = _slug_cache.get(slug)
        if hit and now - hit[1] < _SLUG_TTL:
            if hit[0] is not None:
                out[slug] = hit[0]
        else:
            todo.append(slug)

    if todo:
        from cenkor_admin.apps.cms import models as cms_models

        res = await db.execute(
            select(cms_models.Entry.slug, cms_models.Entry.id).where(
                cms_models.Entry.slug.in_(todo),
                cms_models.Entry.deleted_at.is_(None),
            )
        )
        found = {r[0]: r[1] for r in res.all() if r[0]}
        for slug in todo:
            eid = found.get(slug)
            _slug_cache[slug] = (eid, now)
            if eid is not None:
                out[slug] = eid

    return out


def _normalize_event(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    et = _clean_str(raw.get("event_type"), 20)
    if et not in EVENT_TYPES:
        return None
    meta = raw.get("meta")
    if not isinstance(meta, dict):
        meta = None
    return {
        "event_type": et,
        "entry_id": _clean_int(raw.get("entry_id"), high=2_000_000_000) or None,
        "path": _clean_str(raw.get("path"), _MAX_PATH),
        "referrer": _clean_str(raw.get("referrer"), _MAX_REFERRER),
        "device": _clean_str(raw.get("device"), 16),
        "duration_ms": _clean_int(raw.get("duration_ms")),
        "scroll_pct": _clean_int(raw.get("scroll_pct"), high=100),
        "meta": meta,
    }


async def record_batch(
    db: AsyncSession,
    *,
    site_id: int,
    visitor_id: str,
    session_id: str,
    events: list[Any],
    ip: str | None,
    ua: str | None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
) -> dict[str, int]:
    """写入一批埋点事件，返回「收了 / 丢了」的计数。

    永远返回 200 给前端：埋点失败不该影响访客浏览页面。被限流或校验不过的
    事件静默丢弃，但计数进日志，方便排查「为什么数据少了」。
    """
    if not events:
        return {"accepted": 0, "dropped": 0}

    ip_hash, ua_hash = hash_client(ip, ua)
    today = biz_today()

    # 1) 日配额检查：超了就整批丢
    used = await db.scalar(
        select(func.count())
        .select_from(am.CmsTrackEvent)
        .where(am.CmsTrackEvent.ip_hash == ip_hash, am.CmsTrackEvent.stat_date == today)
    )
    if (used or 0) >= IP_DAILY_QUOTA:
        log.warning("cms.track.quota_exceeded", ip_hash=ip_hash, used=used, stat_date=str(today))
        return {"accepted": 0, "dropped": len(events)}

    # 2) 规整 + 白名单过滤
    cleaned: list[dict[str, Any]] = []
    for raw in events[:MAX_BATCH]:
        ev = _normalize_event(raw)
        if ev is not None:
            cleaned.append(ev)
    dropped = min(len(events), MAX_BATCH) - len(cleaned)
    if not cleaned:
        return {"accepted": 0, "dropped": dropped}

    # 3) 没带 entry_id 的，用 slug 反查
    need = [e["path"] for e in cleaned if not e["entry_id"]]
    slug_map = await _resolve_entry_ids(db, need) if need else {}
    for e in cleaned:
        if not e["entry_id"]:
            s = _slug_from_path(e["path"])
            if s and s in slug_map:
                e["entry_id"] = slug_map[s]

    vid = _clean_str(visitor_id, 64)
    sid = _clean_str(session_id, 64)
    if not vid:
        # 没有 visitor_id 的请求无法做 UV 统计，也不算有效流量
        return {"accepted": 0, "dropped": dropped + len(cleaned)}

    rows = [
        {
            "site_id": site_id or 1,
            "entry_id": e["entry_id"],
            "event_type": e["event_type"],
            "visitor_id": vid,
            "session_id": sid,
            "path": e["path"],
            "referrer": e["referrer"],
            "utm_source": _clean_str(utm_source, 80) or None,
            "utm_medium": _clean_str(utm_medium, 80) or None,
            "utm_campaign": _clean_str(utm_campaign, 120) or None,
            "device": e["device"],
            "ip_hash": ip_hash,
            "ua_hash": ua_hash,
            "duration_ms": e["duration_ms"],
            "scroll_pct": e["scroll_pct"],
            "stat_date": today,
            "meta": e["meta"],
        }
        for e in cleaned
    ]
    await db.execute(am.CmsTrackEvent.__table__.insert(), rows)
    await db.commit()
    return {"accepted": len(rows), "dropped": dropped}


async def purge_old_events(db: AsyncSession, keep_days: int = 90) -> int:
    """清理过期的原始事件。

    原始事件只用于「换个口径重算」，留 90 天足够。汇总表永久保留，
    所以删除原始事件不会丢掉历史趋势。不清理的话这张表一年能长到千万行。
    """
    cutoff = biz_today() - timedelta(days=max(1, keep_days))
    res = await db.execute(
        text("DELETE FROM cms_track_events WHERE stat_date < :cutoff"), {"cutoff": cutoff}
    )
    await db.commit()
    return int(getattr(res, "rowcount", 0) or 0)


async def track_storage_stats(db: AsyncSession) -> dict[str, Any]:
    """埋点数据自身的健康度：今天收了多少、总共多少、最老一天是哪天。"""
    total = await db.scalar(select(func.count()).select_from(am.CmsTrackEvent)) or 0
    today = biz_today()
    today_n = (
        await db.scalar(
            select(func.count())
            .select_from(am.CmsTrackEvent)
            .where(am.CmsTrackEvent.stat_date == today)
        )
        or 0
    )
    oldest = await db.scalar(select(func.min(am.CmsTrackEvent.stat_date)))
    unlinked = (
        await db.scalar(
            select(func.count())
            .select_from(am.CmsTrackEvent)
            .where(am.CmsTrackEvent.stat_date == today, am.CmsTrackEvent.entry_id.is_(None))
        )
        or 0
    )
    return {
        "total": int(total),
        "today": int(today_n),
        "oldest": oldest.isoformat() if oldest else None,
        "today_unlinked": int(unlinked),
        "quota_per_ip": IP_DAILY_QUOTA,
    }


CLIENT_SCRIPT = r"""
/* CMS 埋点脚本 · 自托管，无需构建工具
 * 接入：<script src="{api}/api/v1/public/track.js" data-site="1" defer></script>
 * 可选：data-entry="1214" 指定内容 ID（不填则用 URL slug 反查）
 * 转化：window.cmsTrack.convert('lead', 1)
 */
(function () {
  'use strict';
  var s = document.currentScript;
  if (!s) return;
  var api = (s.getAttribute('data-api') || '{api}').replace(/\/+$/, '');
  var siteId = parseInt(s.getAttribute('data-site') || '1', 10) || 1;
  var fixedEntry = parseInt(s.getAttribute('data-entry') || '', 10) || null;
  if (window.__cmsTrackLoaded) return;
  window.__cmsTrackLoaded = true;

  function uuid() {
    var t = new Date().getTime().toString(16);
    var r = '';
    for (var i = 0; i < 16; i++) r += Math.floor(Math.random() * 16).toString(16);
    return (t + r).slice(0, 32);
  }
  var vid = '';
  try {
    vid = localStorage.getItem('_cms_vid') || '';
    if (!vid) { vid = uuid(); localStorage.setItem('_cms_vid', vid); }
  } catch (e) { vid = uuid(); }
  var sid = uuid();
  var start = Date.now();
  var maxScroll = 0;
  var queue = [];

  function entryId() {
    if (fixedEntry) return fixedEntry;
    var m = document.querySelector('meta[name="cms-entry-id"]');
    if (m && m.getAttribute('content')) return parseInt(m.getAttribute('content'), 10) || null;
    var b = document.body;
    if (b && b.getAttribute) {
      var v = b.getAttribute('data-entry-id');
      if (v) return parseInt(v, 10) || null;
    }
    return null;
  }
  function device() {
    var w = window.innerWidth || 0;
    return w < 768 ? 'mobile' : (w < 1200 ? 'tablet' : 'desktop');
  }
  function utm(k) {
    try { return new URLSearchParams(location.search).get(k) || null; } catch (e) { return null; }
  }
  function push(type, meta) {
    var ev = {
      event_type: type,
      entry_id: entryId(),
      path: (location.pathname || '').slice(0, 500),
      referrer: (document.referrer || '').slice(0, 500),
      device: device(),
      duration_ms: Date.now() - start,
      scroll_pct: maxScroll
    };
    if (meta) ev.meta = meta;
    if (queue.length < 50) queue.push(ev);
  }
  function flush() {
    if (!queue.length || !vid) return;
    var body = JSON.stringify({
      site_id: siteId, visitor_id: vid, session_id: sid,
      utm_source: utm('utm_source'), utm_medium: utm('utm_medium'),
      utm_campaign: utm('utm_campaign'), events: queue
    });
    queue = [];
    var url = api + '/api/v1/public/track';
    /* text/plain 是 CORS safelisted 类型，不触发预检，跨域必达。
       服务端手动解析 body，不依赖 Content-Type。 */
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([body], { type: 'text/plain;charset=UTF-8' }));
      } else {
        fetch(url, { method: 'POST', body: body, mode: 'no-cors', keepalive: true });
      }
    } catch (e) { /* 埋点失败不影响页面 */ }
  }
  function onScroll() {
    var h = document.documentElement;
    var total = (h.scrollHeight - h.clientHeight) || 1;
    var pct = Math.round(((h.scrollTop || 0) / total) * 100);
    if (pct > maxScroll) maxScroll = pct > 100 ? 100 : pct;
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  push('pv');
  flush();

  var hb = setInterval(function () { push('heartbeat'); flush(); }, 15000);

  function bye() { clearInterval(hb); onScroll(); push('scroll'); flush(); }
  window.addEventListener('pagehide', bye);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flush();
  });

  window.cmsTrack = {
    convert: function (name, value) {
      push('conversion', { name: String(name || '').slice(0, 60), value: value === undefined ? null : value });
      flush();
    },
    entry: function (id) { fixedEntry = parseInt(id, 10) || null; },
    flush: flush
  };
})();
"""


def render_client_script(api_base: str) -> str:
    base = (api_base or "").rstrip("/")
    return CLIENT_SCRIPT.replace("{api}", base)
