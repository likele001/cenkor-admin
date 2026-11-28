"""域名绑定状态检测 + 一键命令生成（方案 A：半自动）。

## 为什么不做全自动

绑定一个域名到这台服务器需要四步，其中两步必须在服务器上以 root 执行：

1. **DNS 解析** → 域名注册商，任何程序都替不了（DNS 的物理边界）
2. **nginx server_name + 证书** → 服务器 root
3. **反代保留 Host 头** → 服务器 root
4. **写 cms_sites.domain** → 后台（这一步现在就能做）

后端跑在 www 用户下，sudo 白名单只有三条（restart celery/beat、btpy-project-start），
没有改 nginx、reload、签证书的权限。所以 2、3 步必须由具备权限的人执行一次。

方案 A 的定位：把「要做什么」从隐性知识变成显式指引 ——
后台判断域名当前处于哪个状态，并生成可直接粘贴的命令。运维复制一次即可，
不需要理解 nginx 配置结构。

## 状态判定

- `unset`        未绑定域名
- `dns_missing`  DNS 未解析到本机（或解析到别处）
- `dns_www_only` 裸域没解析，但 www 版指向本机（常见写法，提示改填 www）
- `ip_mismatch`  填的是 IP 但不是本机 IP（改 DNS 无用，只能改填的值）
- `dns_ok`       解析正确，但 nginx 还没有该域名的 server 块
- `nginx_ok`     nginx 已配置，但证书缺失/未配置
- `live`         全部就绪

## 探测方式

不用读 `/www/server/panel/vhost/{nginx,cert}`：宝塔把这两个目录设成
`root:root 700`，后端进程跑在 `www` 下，`stat` 直接 PermissionError。
改为从本机访问该域名（HTTP 通 → nginx 已配；HTTPS 握手成功 → 证书已装），
这恰好也是最贴近「用户能不能打开」的判据。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any

import structlog

from cenkor_admin.core.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

# 本机公网 IP。写死不如每次探测：服务器迁机后自动跟着变。
_IP_CACHE: dict[str, Any] = {"at": 0.0, "ip": None}
_IP_TTL = 300.0


async def _resolve_a(host: str, timeout: float = 3.0) -> list[str]:
    """查 A 记录。失败返回空列表（不改抛，调用方按「解析不到」处理）。"""
    try:
        import dns.asyncresolver
        import dns.resolver

        resolver = dns.asyncresolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        ans = await resolver.resolve(host, "A")
        return sorted({str(r) for r in ans})
    except Exception as exc:  # noqa: BLE001 —— 各种 DNS 异常都归为「查不到」
        log.debug("dns.resolve_failed", host=host, err=str(exc))
        return []


def _local_ip_sync() -> str | None:
    """本机对外的源 IP。用 UDP connect 探测，不发包。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


async def local_ip() -> str | None:
    import time

    now = time.monotonic()
    if _IP_CACHE["ip"] and (now - _IP_CACHE["at"]) < _IP_TTL:
        return _IP_CACHE["ip"]
    ip = await asyncio.get_running_loop().run_in_executor(None, _local_ip_sync)
    _IP_CACHE["ip"] = ip
    _IP_CACHE["at"] = now
    return ip


def _normalize(domain: str | None) -> str:
    d = (domain or "").strip().lower()
    d = d.removeprefix("https://").removeprefix("http://")
    return d.split("/")[0].split(":")[0]


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


async def domain_status(
    domain: str | None,
    *,
    nginx_has_server: bool | None = None,
    cert_exists: bool | None = None,
) -> dict[str, Any]:
    """综合判断域名当前状态。

    ``nginx_has_server`` / ``cert_exists`` 可传入，也可留空由本函数自己
    从本机 HTTP 探测（``probe_http``）。留空是默认路径 —— 后端没有读
    宝塔 vhost 目录的权限，文件系统探测在这台机上不可用。
    """
    d = _normalize(domain)
    if not d:
        return {"status": "unset", "domain": None, "resolved": [], "expected": None}

    expected = await local_ip()
    resolved = [] if _is_ip(d) else await _resolve_a(d)

    if _is_ip(d):
        # 直接填 IP 的场景：不需要 DNS，但必须等于本机
        dns_ok = expected is not None and d == expected
    else:
        dns_ok = bool(resolved) and expected is not None and expected in resolved

    # 裸域没配、但 www 有解析，是极常见的写法（还常被 CDN/证书一起处理）。
    # 这种情况下报「DNS 未指向本机」会把人带偏：真正要做的是把域名改成 www 版，
    # 或者去补一条裸域 A 记录。单独标出来，前端才能给出正确指引。
    alt_ok: str | None = None
    if not dns_ok and not _is_ip(d) and not d.startswith("www."):
        alt = f"www.{d}"
        alt_resolved = await _resolve_a(alt)
        if alt_resolved and expected is not None and expected in alt_resolved:
            alt_ok = alt

    probe: dict[str, Any] = {}
    if dns_ok and (nginx_has_server is None or cert_exists is None):
        probe = await probe_http(d)
        if nginx_has_server is None:
            nginx_has_server = bool(probe.get("nginx_ok"))
        if cert_exists is None:
            cert_exists = bool(probe.get("https_ok"))

    if not dns_ok and _is_ip(d):
        # 填的是 IP 但不是本机 IP：改 DNS 没用，只能改填的地址
        status = "ip_mismatch"
    elif not dns_ok and alt_ok:
        status = "dns_www_only"
    elif not dns_ok:
        status = "dns_missing"
    elif not nginx_has_server:
        status = "dns_ok"
    elif not cert_exists:
        status = "nginx_ok"
    else:
        status = "live"

    out = {
        "status": status,
        "domain": d,
        "resolved": resolved,
        "expected": expected,
        "http_status": probe.get("http_status"),
        # 明确告知这两个值是「探测结果」而非「读目录得知」，前端文案据此措辞
        "probe": "http" if probe else "caller",
    }
    if alt_ok:
        out["alt_domain"] = alt_ok
    return out


async def probe_http(domain: str, timeout: float = 5.0) -> dict[str, Any]:
    """从本机访问该域名，判断 nginx 与证书是否已就绪。

    为什么不读 ``/www/server/panel/vhost/{nginx,cert}``：
    宝塔把这两个目录设成 ``root:root 700``，后端进程跑在 ``www`` 下，
    ``stat`` 直接 PermissionError；加 sudo 又要把后端提权，风险更大。
    本机访问自己的域名反而是最贴近「用户能不能打开」的判据：
      - 80 有响应  → nginx 已有该域名的 server 块
      - 443 握手成功 → 证书已装好
    连不通就是没配好，与文件是否存在无关。
    """
    import asyncio
    import ssl as _ssl

    d = _normalize(domain)
    out: dict[str, Any] = {"nginx_ok": False, "https_ok": False, "http_status": None}
    if not d:
        return out

    def _http() -> int | None:
        import http.client

        try:
            conn = http.client.HTTPConnection(d, 80, timeout=timeout)
            conn.request("HEAD", "/", headers={"User-Agent": "cenkor-domain-check"})
            code = conn.getresponse().status
            conn.close()
            return code
        except Exception:
            return None

    def _https() -> bool:
        import http.client

        try:
            ctx = _ssl.create_default_context()
            # 自签/链不全也算「证书已装」——要查的是装没装，不是合不合规。
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            conn = http.client.HTTPSConnection(d, 443, timeout=timeout, context=ctx)
            conn.request("HEAD", "/", headers={"User-Agent": "cenkor-domain-check"})
            conn.getresponse()
            conn.close()
            return True
        except Exception:
            return False

    code, https_ok = await asyncio.gather(
        asyncio.to_thread(_http), asyncio.to_thread(_https)
    )
    out["http_status"] = code
    out["nginx_ok"] = code is not None
    out["https_ok"] = https_ok
    return out


_STATUS_HINT = {
    "unset": "尚未绑定域名，该站点只能通过后台或默认站点访问。",
    "ip_mismatch": "填的是 IP，但不是本机 IP。域名请填解析到本机的域名，或改成上面显示的本机 IP。",
    "dns_www_only": "裸域没有解析，但带 www 的域名已指向本机。建议把域名改成带 www 的那个，或去域名服务商补一条裸域 A 记录。",
    "dns_missing": "DNS 未指向本机。先去域名服务商把 A 记录指向上面的 IP，等生效后再回来。",
    "dns_ok": "DNS 已就绪，但 nginx 还没有这个域名的配置。复制下面的命令在服务器执行。",
    "nginx_ok": "nginx 已配置，但证书还没就绪。执行下面的命令签发证书。",
    "live": "全部就绪，域名已可正常访问。",
}


def build_commands(
    domain: str,
    *,
    site_key: str,
    backend_port: int,
    status: str,
) -> list[dict[str, str]]:
    """生成可直接粘贴的运维命令。

    只针对「下一步该做什么」，不把无关步骤堆上去 —— 一次只给一个动作，
    运维不需要判断该执行哪条。
    """
    d = _normalize(domain)
    if not d or status == "live":
        return []

    # 宝塔面板的站点配置目录。放常量而非散落字符串，便于裸机部署时改一处。
    nginx_dir = settings.CMS_NGINX_VHOST_DIR
    conf = f"{nginx_dir}/{d}.conf"
    cmds: list[dict[str, str]] = []

    if status == "ip_mismatch":
        ip = _IP_CACHE.get("ip") or "<本机公网IP>"
        return [
            {
                "title": "改用本机 IP",
                "lang": "text",
                "code": ip,
                "note": "填这个值才能通到本机。注意：用 IP 访问拿不到证书，正式站点仍应绑域名。",
            },
        ]

    if status == "dns_www_only":
        www = f"www.{d}"
        return [
            {
                "title": "方案一：改用带 www 的域名（最省事）",
                "lang": "text",
                "code": www,
                "note": "把这个值填到上面的「绑定域名」里保存即可 —— 它已经解析到本机。",
            },
            {
                "title": "方案二：给裸域补一条 A 记录",
                "lang": "text",
                "code": f"{d}    A    {(_IP_CACHE.get('ip') or '<本机公网IP>')}",
                "note": "域名服务商处添加，生效通常 1~10 分钟。",
            },
        ]

    if status in ("dns_missing",):
        return [
            {
                "title": "到域名服务商添加解析",
                "lang": "text",
                "code": f"{d}    A    {(_IP_CACHE.get('ip') or '<本机公网IP>')}",
                "note": "DNS 生效通常 1~10 分钟，可用下面的命令自查。",
            },
            {
                "title": "自查解析是否生效",
                "lang": "bash",
                "code": f"dig +short {d}",
                "note": "返回上面的 IP 就说明生效了，刷新本页可看到状态变化。",
            },
        ]

    if status == "dns_ok":
        conf_body = _nginx_conf(d, site_key, backend_port, with_ssl=False)
        cmds.append(
            {
                "title": "第一步：写入 nginx 配置",
                "lang": "bash",
                "code": f"cat > {conf} <<'NGINX'\n{conf_body}NGINX",
                "note": "该段会先只监听 80，证书签发成功后再补 443。",
            }
        )
        cmds.append(
            {
                "title": "第二步：reload nginx",
                "lang": "bash",
                "code": "nginx -t && nginx -s reload",
                "note": "先 -t 校验语法，通过才 reload。",
            }
        )
        cmds.append(
            {
                "title": "第三步：申请证书",
                "lang": "bash",
                "code": _cert_cmd(d),
                "note": "证书申请要求 80 端口可达；若用了 CDN，需先回源或改用 DNS 验证。",
            }
        )
        return cmds

    if status == "nginx_ok":
        cmds.append(
            {
                "title": "申请证书",
                "lang": "bash",
                "code": _cert_cmd(d),
                "note": "签发后把 443 相关配置补进同一个 conf 文件再 reload。",
            }
        )
        return cmds

    return cmds


def _cert_cmd(d: str) -> str:
    """证书命令。优先用 acme.sh（这台机器没有 certbot），走 webroot 模式
    不碰 80 端口占用问题。"""
    return (
        "~/.acme.sh/acme.sh --issue -d {d} -w /www/wwwroot/cenkor-site-v2 "
        "--keylength ec-256\n"
        "~/.acme.sh/acme.sh --install-cert -d {d} --ecc \\\n"
        "  --key-file {cert}/" + "{d}/privkey.pem \\\n"
        "  --fullchain-file {cert}/" + "{d}/fullchain.pem \\\n"
        "  --reloadcmd \"nginx -s reload\""
    ).format(d=d, cert=settings.CMS_CERT_DIR)


def _nginx_conf(d: str, site_key: str, port: int, *, with_ssl: bool) -> str:
    """最小可用的 cms 反代配置。

    刻意不复制 www.cenkor.cn.conf 的全部内容：那份配置里有大量针对官网静态站
    的 location 规则（GEO 落地页、伪静态兜底），套到新站上反而会互相打架。
    这里只保留「所有路径都转给后端按站点渲染」这一条主线 —— 新站的伪静态规则
    由后端 url_resolver 决定，不需要 nginx 参与。
    """
    ssl_block = ""
    if with_ssl:
        ssl_block = """    listen 443 ssl;
    http2 on;
    ssl_certificate     {cert}/{d}/fullchain.pem;
    ssl_certificate_key {cert}/{d}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
""".format(d=d, cert=settings.CMS_CERT_DIR)

    return """server {{
    listen 80;
{ssl}    server_name {d};

    charset utf-8;
    client_max_body_size 50m;

    # 所有请求交给后端，由后端按 Host 解析站点（cms_sites.domain）后渲染。
    # Host 头必须原样传下去，否则后端认不出是哪个站。
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }}

    # 证书签发用的验证路径（acme webroot 模式需要）
    location ^~ /.well-known/acme-challenge/ {{
        root /www/wwwroot/cenkor-site-v2;
        default_type text/plain;
    }}
}}
""".format(ssl=ssl_block, d=d, port=port)


def hint_for(status: str) -> str:
    return _STATUS_HINT.get(status, "")