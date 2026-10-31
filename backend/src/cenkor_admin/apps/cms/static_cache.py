"""公开页静态落盘（模板系统 P2）

nginx 先 `try_files` 找静态文件，命中直接出、不再回源；
未命中才 proxy_pass 到后端渲染，后端渲染成功时就地写盘 —— 下一次就是静态。

设计取舍
--------
1. **只落「规范 URL」**：详情页 `/{article|product|news|case}/{slug}.html`。
   列表页带分页/搜索参数，URL 空间不可枚举，交给后端缓存头，不落盘。
2. **只在规范域名下写盘**：请求 Host 必须等于站点 `Site.domain`，否则跳过。
   否则从 IP / 内网 / 备用域名访问一次，就会把错误的 canonical 写进静态文件，
   之后所有爬虫拿到的都是错域名 —— 这类脏数据极难回滚。
3. **原子写**：先写同目录 `.tmp` 再 `os.replace`，并发请求不会读到半截文件。
4. **路径白名单**：段名只允许 `[A-Za-z0-9._-]`，显式拒 `.` / `..`，
   最终路径必须落在 `<root>/<host>/` 之下，杜绝任何注入。
5. **默认关闭**：`CMS_STATIC_CACHE=1` 才启用。上线先观察，出问题一条命令关掉
   （关掉后 nginx 的 try_files 全部 miss，自动回落动态渲染，等于没开过）。
6. **失效靠双保险**：写入口显式 purge（见 content_engine_router）
   + `scripts/build_static_cache.py --purge` 全量清空。
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import select

from cenkor_admin.apps.cms import models

logger = logging.getLogger(__name__)

__all__ = [
    "DETAIL_KINDS",
    "cache_enabled",
    "cache_root",
    "purge",
    "purge_all",
    "purge_entry",
    "purge_entry_by_site",
    "purge_site",
    "purge_site_domain",
    "record_public_page",
    "site_domain",
    "stats",
    "store",
]

ENABLE_ENV = "CMS_STATIC_CACHE"
ROOT_ENV = "CMS_STATIC_CACHE_ROOT"

# 单页上限。正常详情页 30~80KB，3MB 只是防「一条内容塞了 base64 图片」把盘写爆。
MAX_PAGE_BYTES = 3 * 1024 * 1024

# 走静态化的内容类型（与 render.KIND_TEMPLATE 的详情页一致）
DETAIL_KINDS: tuple[str, ...] = ("article", "product", "news", "case")

_SEG_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_HOST_RE = re.compile(r"^[a-z0-9.-]+$")

# site_id -> (过期 monotonic 时间, 域名)
_domain_cache: dict[int, tuple[float, str | None]] = {}
_domain_lock = threading.Lock()
_DOMAIN_TTL = 60.0


# ---------------------------------------------------------------- 开关与路径


def _setting(name: str) -> Any:
    """读配置：环境变量优先，其次 Settings（.env），最后 None。

    Settings 的 `extra="ignore"` 意味着**没在 config.Settings 里声明字段的 .env 项
    不会进 os.environ**。所以两边都要看：声明字段给宝塔/.env 用，环境变量留给
    命令行临时覆盖（脚本、一次性排障）。
    """
    if name in os.environ:
        return os.environ[name]
    try:
        from cenkor_admin.core.config import get_settings

        return getattr(get_settings(), name, None)
    except Exception:
        logger.debug("读取 Settings 失败，按默认值处理", exc_info=True)
        return None


def cache_enabled() -> bool:
    raw = _setting(ENABLE_ENV)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def cache_root() -> Path:
    raw = _setting(ROOT_ENV)
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip()).expanduser().resolve()
    # backend/src/cenkor_admin/apps/cms/static_cache.py -> backend/var/htmlcache
    return Path(__file__).resolve().parents[4] / "var" / "htmlcache"


def _rel_of(url_path: str) -> str | None:
    """`/article/foo.html?v=1` -> `article/foo.html`；不合法返回 None。"""
    path = (url_path or "").split("?", 1)[0].split("#", 1)[0].strip()
    # `//host/x.html` 这种协议相对写法、`/\x00` 之类一律拒掉：
    # 虽然拼出来仍落在 base 目录下，但不该被当成合法页面路径。
    if not path.startswith("/") or path.startswith("//"):
        return None
    segs = [s for s in path.split("/") if s]
    if not segs or len(segs) > 4:
        return None
    for seg in segs:
        if seg in (".", "..") or not _SEG_RE.match(seg):
            return None
    if not segs[-1].endswith(".html"):
        return None
    return "/".join(segs)


def target_path(host: str, url_path: str) -> Path | None:
    """URL -> 磁盘绝对路径。任一段不合法就返回 None（调用方跳过，不报错）。"""
    host = (host or "").strip().lower()
    if not host or not _HOST_RE.match(host):
        return None
    rel = _rel_of(url_path)
    if rel is None:
        return None

    base = cache_root() / host
    path = (base / rel).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        logger.warning("静态缓存路径越界已拒绝：host=%s path=%s", host, url_path)
        return None
    return path


# ---------------------------------------------------------------- 站点域名


async def site_domain(db, site_id: int) -> str | None:
    """站点规范域名（60s 缓存）。

    两级来源：
    1. `cms_sites.domain` —— 多站点绑定的正式域名
    2. `cms_site_config['brand.domain']` —— 单站历史数据里域名只配在这里，
       线上主站（site id=1）的 `domain` 字段就是 NULL，只认第一条会永远落不了盘
    查不到返回 None，调用方据此跳过落盘。
    """
    now = time.monotonic()
    with _domain_lock:
        hit = _domain_cache.get(site_id)
        if hit and hit[0] > now:
            return hit[1]

    domain: str | None = None
    try:
        row = (await db.execute(select(models.Site).where(models.Site.id == site_id))).scalars().first()
        raw = getattr(row, "domain", None) if row is not None else None
        if raw:
            domain = str(raw).strip().lower()
    except Exception:
        logger.debug("查询站点域名失败 site_id=%s", site_id, exc_info=True)

    if not domain:
        try:
            cfg = (
                await db.execute(
                    select(models.SiteConfig).where(models.SiteConfig.key == "brand.domain")
                )
            ).scalars().first()
            raw = getattr(cfg, "value", None)
            if raw:
                domain = str(raw).strip().lower()
        except Exception:
            logger.debug("查询 brand.domain 失败", exc_info=True)

    with _domain_lock:
        _domain_cache[site_id] = (now + _DOMAIN_TTL, domain)
    return domain


def _same_site(domain: str, host: str) -> bool:
    """请求 Host 是否属于该站点。

    只容忍 `www.` 前缀差异 —— 品牌域名常配成裸域（`cenkor.cn`），实际访问走
    `www.cenkor.cn`。**不**容忍完全不同的域名：多一个别名就多一份
    把错误 canonical 写进静态文件的风险，宁可跳过不落盘。
    """
    a = (domain or "").strip().lower()
    b = (host or "").strip().lower()
    if a.startswith("www."):
        a = a[4:]
    if b.startswith("www."):
        b = b[4:]
    return bool(a) and a == b


def _candidate_hosts(domain: str | None) -> list[str]:
    """一个域名可能对应的磁盘目录名（含 www 变体）。"""
    d = (domain or "").strip().lower()
    if not d:
        return []
    bare = d[4:] if d.startswith("www.") else d
    return sorted({bare, f"www.{bare}"})


def _known_hosts() -> list[str]:
    """已落盘的全部站点目录名。purge 时兜底用，避免因域名写法不同漏删。"""
    root = cache_root()
    if not root.is_dir():
        return []
    try:
        return [p.name for p in root.iterdir() if p.is_dir()]
    except OSError:
        return []


def _forget_domain(site_id: int | None = None) -> None:
    with _domain_lock:
        if site_id is None:
            _domain_cache.clear()
        else:
            _domain_cache.pop(site_id, None)


# ---------------------------------------------------------------- 写


def store(host: str, url_path: str, html: str) -> bool:
    """把一个渲染好的页面写到静态目录。永不抛异常 —— 缓存失败不能影响响应。"""
    if not cache_enabled():
        return False
    if not html:
        return False

    data = html.encode("utf-8")
    if len(data) > MAX_PAGE_BYTES:
        logger.info("页面超过静态缓存上限 %d 字节，跳过 %s", MAX_PAGE_BYTES, url_path)
        return False

    path = target_path(host, url_path)
    if path is None:
        return False

    tmp: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        logger.warning("静态缓存写入失败 %s: %s", path, exc)
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        return False


async def record_public_page(
    db,
    *,
    site_id: int,
    host: str,
    url_path: str,
    html: str,
) -> bool:
    """落盘入口：先确认请求走的是站点规范域名，再写。

    目录名用**请求 Host** 而不是配置里的 domain：nginx 的 root 写的是实际访问
    域名，两者必须完全一致，否则文件写了但 try_files 找不到（静默 miss，
    表现是「开了缓存但一点没快」）。

    非规范域名（IP、localhost、内网、别的备用域名）一律跳过 —— 这些请求渲染出的
    canonical / og:url 是错的，写进静态文件会把全站 SEO 打脏。
    """
    if not cache_enabled():
        return False
    host = (host or "").strip().lower()
    domain = await site_domain(db, site_id)
    if not _same_site(domain or "", host):
        return False
    return store(host, url_path, html)


# ---------------------------------------------------------------- 失效


def purge(host: str, url_path: str) -> bool:
    """删掉一个静态文件。文件本来就不存在时返回 False（不是错误）。"""
    path = target_path(host, url_path)
    if path is None or not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.warning("静态缓存删除失败 %s: %s", path, exc)
        return False


def purge_entry(host: str | None, slug: str, kinds: Iterable[str] = DETAIL_KINDS) -> int:
    """删掉一个条目在所有内容类型下的详情页。

    host 为 None 时扫全部站点目录 —— 磁盘目录名是「实际访问的 Host」，
    而配置里的 domain 可能是裸域，两边写法不一定一致，扫一遍最保险
    （多删一个不存在的文件代价为零，漏删才是脏数据）。

    同一个 slug 可能同时存在于 `/article/x.html` 和 `/case/x.html`
    （case 走内容引擎后两种 URL 都能开，canonical 自愈），全部清掉最省心。
    """
    slug = (slug or "").strip()
    if not slug or not _SEG_RE.match(slug) or slug in (".", ".."):
        return 0
    hosts = [host] if host else _known_hosts()
    return sum(1 for h in hosts for k in kinds if purge(h, f"/{k}/{slug}.html"))


async def purge_entry_by_site(db, site_id: int, slug: str) -> int:
    """按站点清一个条目（钩子用）。扫全站目录，避免域名写法不一致漏删。"""
    if not cache_enabled():
        return 0
    return purge_entry(None, slug)


def purge_site(host: str) -> int:
    """清空一个站点的全部静态文件（模板/站点设置变更后调用）。返回删除文件数。"""
    host = (host or "").strip().lower()
    if not host or not _HOST_RE.match(host):
        return 0
    root = cache_root()
    folder = root / host
    try:
        folder.resolve().relative_to(root.resolve())
    except ValueError:
        return 0
    if not folder.is_dir():
        return 0
    count = sum(1 for _ in folder.rglob("*.html"))
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        logger.warning("清空站点静态目录失败 %s: %s", folder, exc)
        return 0
    return count


def purge_site_domain(domain: str | None) -> int:
    """按配置里的域名清目录，自动补齐 www 变体（两者可能各有一份）。"""
    return sum(purge_site(h) for h in _candidate_hosts(domain))


async def purge_site_by_id(db, site_id: int) -> int:
    """清空一个站点的静态目录。

    按「域名 + www 变体」两个候选目录清；域名查不到就直接全清 ——
    模板改了却因为域名缺失没清掉，线上会一直显示旧版式，
    这比多清几个文件严重得多。
    """
    if not cache_enabled():
        return 0
    hosts = _candidate_hosts(await site_domain(db, site_id))
    if not hosts:
        return purge_all()
    return sum(purge_site(h) for h in hosts)


def purge_all() -> int:
    """清空所有站点的静态文件。"""
    root = cache_root()
    if not root.is_dir():
        return 0
    count = sum(1 for _ in root.rglob("*.html"))
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            shutil.rmtree(child)
        except OSError as exc:
            logger.warning("清空静态目录失败 %s: %s", child, exc)
    _forget_domain()
    return count


# ---------------------------------------------------------------- 观测


def stats(host: str | None = None) -> dict[str, Any]:
    root = cache_root()
    target = root / host if host else root
    files = 0
    total = 0
    if target.is_dir():
        for p in target.rglob("*.html"):
            files += 1
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return {
        "enabled": cache_enabled(),
        "root": str(target),
        "files": files,
        "bytes": total,
        "mounted": target.is_dir(),
    }
