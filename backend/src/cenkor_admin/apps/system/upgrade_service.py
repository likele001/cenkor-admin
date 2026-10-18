"""核心平台在线升级服务（在 FastAPI 进程内完成 备份 拉新代码 替换+迁移 重启+健康检查）。

设计要点（参考 iCMS 的「先备份，失败自动回滚」）：
  1. 全程在 Python 进程内执行（不调外部 upgrade.sh），便于流式写日志。
  2. 升级前先做「升级前快照」到 /www/backup/cenkor-admin/snapshot_<时间>/。
  3. 拉新代码（URL 下载 / tar 上传）后用 rsync 覆盖到 ROOT。
     rsync 不删目标里独有的文件 —— 保证 crm/erp/mes/workflow/payment 这 5 个本地应用不被误删。
  4. 跑 alembic upgrade head 时只跑主架构链（按 revision 文件名前缀 + down 拓扑过滤），
     业务应用链（crm_/erp_/mes_/commerce_/payment_/marketplace_/cloud_/workflow_/promo_/payout_）的迁移绝不自动跑。
  5. 杀 8002 拉起同一命令行；/api/health 检查 200 才算成功。
  6. 任一失败 → 触发「自动回滚」（rsync 整站恢复 + 重启 + health）。
  7. 「开源 vs 商业」边界：只升主架构（dev_method=platform 的内置应用 + 7 个无 manifest 的自带模块）；
     crm/erp/mes/workflow/payment 是 dev_method=extension/standalone 的商业应用，不参与这个升级流程。

安全护栏：is_superuser + confirm_text 双因子；进程内 asyncio.Lock + DB 行 status 双互斥；
          任意步骤失败都写 UpgradeRun(status=failed) 并原样记录后端日志。
"""
from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.system.models import InstalledApp, UpgradeRun
from cenkor_admin.codegen import builder

log = structlog.get_logger()

ROOT = Path("/www/wwwroot/cenkor-admin").resolve()
BACKUP_DIR = Path("/www/backup/cenkor-admin")
LOG_MAX_BYTES = 200 * 1024

BUSINESS_REVISION_PREFIXES = (
    "crm_", "erp_", "mes_",
    "commerce_", "payment_", "marketplace_",
    "cloud_", "workflow_", "promo_", "payout_",
)
BUSINESS_REVISION_HEADS = (
    "20260903_crm_0001",
    "20260831_0001_erp_init",
    "20260904_mes_0001",
    "20260925_0027_workflow",
    "20260922_0020_commerce",
)

PYTHON_BIN = "/www/server/pyporject_evn/cenkor/bin/python3"
BACKEND_PORT = 8002
HEALTH_URL = "http://127.0.0.1:" + str(BACKEND_PORT) + "/api/health"

_RUNNING_LOCK = asyncio.Lock()
_LOG_HOOKS = {}  # type: dict[int, list[Callable[[str], Awaitable[None]]]]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _truncate_log(text):
    if len(text) <= LOG_MAX_BYTES:
        return text
    half = LOG_MAX_BYTES // 2 - 32
    return text[:half] + "\n... [truncated, see backup_dir logs] ...\n" + text[-half:]


async def _append_log(run, db, line):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    entry = "[" + ts + "] " + line + "\n"
    run.log = (run.log or "") + entry
    if run.log and len(run.log) > LOG_MAX_BYTES:
        run.log = _truncate_log(run.log)
    try:
        await db.commit()
    except Exception as exc:  # noqa
        log.warning("upgrade.log_commit_failed", run_id=run.id, error=str(exc))
        try:
            await db.rollback()
        except Exception:  # noqa
            pass
    for hook in _LOG_HOOKS.get(run.id, []):
        try:
            await hook(line)
        except Exception:  # noqa
            pass
    log.info("upgrade.step", run_id=run.id, line=line)


def register_log_hook(run_id, hook):
    _LOG_HOOKS.setdefault(run_id, []).append(hook)


def unregister_log_hook(run_id, hook):
    _LOG_HOOKS.pop(run_id, None)


def _load_migration_index() -> dict:
    V = ROOT / "backend" / "alembic" / "versions"
    out = {}
    for f in builder.all_migration_files(V):
        if f.name.startswith("__"):
            continue
        rev, down = builder.parse_migration(f)
        if rev:
            out[rev] = (f.name, down)
    return out


def _collect_business_revs() -> set:
    """业务应用链 = 全部迁移 - 主架构链（从 0026_app_enabled 走到 root）。

    主架构链：0026 → 0028 → 0030 → 0031 → 0029（汇合点）→ 0032 → 0033 + 它们的父级。
    业务链：crm/erp/mes/workflow/commerce/payment/marketplace/... 在主架构链之外的所有 revision。
    """
    idx = _load_migration_index()
    all_revs = set(idx.keys())
    # 沿 down 链走到 root
    main = set()
    cur = MAIN_REVISION_HEAD
    seen = set()
    while cur and cur in idx and cur not in seen:
        seen.add(cur)
        main.add(cur)
        d = idx[cur][1]
        if isinstance(d, (list, tuple)):
            cur = d[0] if d else None
        else:
            cur = d
    return all_revs - main


async def _wait_health(timeout=30.0, interval=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa
            pass
        await asyncio.sleep(interval)
    return False


async def _kill_8002():
    proc = await asyncio.create_subprocess_exec(
        "bash", "-lc",
        "ss -ltnp 2>/dev/null | grep ':8002 ' | sed -nE 's/.*pid=([0-9]+).*/\\1/p' | head -1",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    pid = out.decode().strip()
    if not (pid and pid.isdigit()):
        return None
    pid_int = int(pid)
    try:
        os.kill(pid_int, signal.SIGTERM)
    except ProcessLookupError:
        return pid_int
    for _ in range(20):
        try:
            os.kill(pid_int, 0)
        except (ProcessLookupError, ValueError):
            return pid_int
        await asyncio.sleep(0.5)
    try:
        os.kill(pid_int, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return pid_int


async def _spawn_8002():
    log_path = ROOT / "backend" / "cenkor_admin_8002.log"
    pid_path = ROOT / "backend" / ".uvicorn_8002.pid"
    cmd = [
        PYTHON_BIN, "-m", "uvicorn",
        "cenkor_admin.main:app",
        "--host", "127.0.0.1", "--port", str(BACKEND_PORT),
        "--log-config", str(ROOT / "backend" / "logconf" / "hub_logging.yaml"),
    ]
    log_fp = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT / "backend"),
        stdout=log_fp, stderr=log_fp, stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    pid_path.write_text(str(proc.pid), encoding="utf-8")


async def _restart_8002():
    pid = await _kill_8002()
    await asyncio.sleep(1)
    await _spawn_8002()
    return pid


def _read_version() -> str:
    p = ROOT / "backend/src/cenkor_admin/VERSION"
    if p.exists():
        return p.read_text(encoding="utf-8", errors="ignore").strip()
    return "0.1.0"


def _read_env_prod() -> dict:
    p = ROOT / ".env.prod"
    out = {}
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


async def _do_backup(run, db):
    stamp = _now_stamp()
    snap = BACKUP_DIR / ("snapshot_" + stamp)
    snap.mkdir(parents=True, exist_ok=True)
    await _append_log(run, db, "▸ 升级前快照 → " + str(snap))
    # 1. env.prod
    src = ROOT / ".env.prod"
    if src.exists():
        shutil.copy2(src, snap / "env.prod")
    else:
        src2 = ROOT / ".env"
        if src2.exists():
            shutil.copy2(src2, snap / "env")
    # 2. pg_dump
    pg_dump_bin = shutil.which("pg_dump") or "/www/server/pgsql/bin/pg_dump"
    if not os.path.exists(pg_dump_bin):
        await _append_log(run, db, "  ! pg_dump 未找到（" + pg_dump_bin + "），跳过 DB 快照")
    else:
        envs = _read_env_prod()
        db_user = envs.get("POSTGRES_USER", "cenkor")
        db_name = envs.get("POSTGRES_DB", "cenkor")
        db_pass = envs.get("POSTGRES_PASSWORD", "")
        db_port = envs.get("DB_HOST_PORT") or envs.get("POSTGRES_PORT", "5432")
        pg_file = snap / ("pg_" + stamp + ".sql.gz")
        proc = await asyncio.create_subprocess_exec(
            pg_dump_bin, "-h", "127.0.0.1", "-p", db_port,
            "-U", db_user, "-d", db_name, "-n", "public",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PGPASSWORD": db_pass},
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            with gzip.open(pg_file, "wb") as fh:
                fh.write(stdout)
            await _append_log(run, db, "  ✓ pg_dump " + str(len(stdout)) + " 字节 → " + pg_file.name)
        else:
            await _append_log(run, db, "  ! pg_dump 失败：" + (stderr.decode()[:200] if stderr else ""))
    # 3. tar.gz
    tar_path = snap / ("project_" + stamp + ".tar.gz")
    excludes = [
        "--exclude=./.env", "--exclude=./.env.prod",
        "--exclude=./backend/src/uploads", "--exclude=./backend/logs",
        "--exclude=./.git", "--exclude=./node_modules",
        "--exclude=./__pycache__", "--exclude=./backend/**/__pycache__",
        "--exclude=./frontend/**/node_modules", "--exclude=./frontend/**/dist",
        "--exclude=./release", "--exclude=./_rollback_bak_*",
        "--exclude=*.pyc", "--exclude=*.tar.gz", "--exclude=*.zip",
    ]
    cmd = ["tar", "-czf", str(tar_path)] + excludes + ["-C", str(ROOT.parent), ROOT.name]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("tar 失败：" + (stderr.decode()[:300] if stderr else ""))
    sz = tar_path.stat().st_size
    await _append_log(run, db, "  ✓ 项目文件 → " + tar_path.name + " (" + str(round(sz/1024/1024, 1)) + " MB)")
    # 4. chown root:www
    try:
        subprocess.run(["chown", "-R", "root:www", str(snap)], check=False)
        subprocess.run(["chmod", "-R", "u+rwX,g+rX", str(snap)], check=False)
    except Exception:  # noqa
        pass
    # 5. manifest.json
    manifest = {
        "snapshot_at": stamp,
        "from_version": _read_version(),
        "backup_path": str(snap),
        "project_tar": str(tar_path),
        "pg_dump": str(pg_file) if (snap / ("pg_" + stamp + ".sql.gz")).exists() else None,
    }
    (snap / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap

def _local_release() -> dict | None:
    """读本地 release.json（仓库自带 / 上一版升级后留下的）作为资源库「降级」数据源。"""
    p = Path(__file__).resolve().parents[3] / "release.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa
        return None


_RESOURCES_CACHE: dict = {"fetched_at": 0.0, "items": [], "error": None}


def _settings():
    try:
        from cenkor_admin.core.config import get_settings  # noqa
        return get_settings()
    except Exception:  # noqa
        return None


async def list_resources(force_refresh: bool = False) -> dict:
    """合并：远程 releases.json（带 token 鉴权）+ 本地 release.json + 本地已下载文件。

    返回 {source, items:[{version, channel, released_at, pkg_url, size, notes, source, local_path?, installed?}], remote_error?}
    """
    s = _settings()
    url = (s.CORE_RELEASES_URL if s else "").strip() or "https://cenkor.cn/api/releases.json"
    token = (s.CORE_RELEASES_TOKEN if s else "").strip()
    ttl = (s.CORE_RELEASES_TTL_SECONDS if s else 300)
    download_dir = Path((s.CORE_RELEASES_DOWNLOAD_DIR if s else "/www/wwwroot/cenkor-admin/release"))
    download_dir.mkdir(parents=True, exist_ok=True)

    now = time.time()
    items: list[dict] = []
    remote_error = None

    # 1) 远程（带 token 鉴权 + 缓存）
    if not force_refresh and _RESOURCES_CACHE["items"] and (now - _RESOURCES_CACHE["fetched_at"]) < ttl:
        items.extend(_RESOURCES_CACHE["items"])
        remote_error = _RESOURCES_CACHE.get("error")
    else:
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "cenkor-admin-upgrade/0.2.0")
            if token:
                req.add_header("Authorization", "Bearer " + token)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            # 兼容 {releases:[...]} 与 直接数组
            if isinstance(data, dict) and "releases" in data:
                arr = data["releases"]
            elif isinstance(data, list):
                arr = data
            else:
                arr = []
            for it in arr:
                if not isinstance(it, dict):
                    continue
                v = str(it.get("version") or "").strip()
                if not v:
                    continue
                items.append({
                    "version": v,
                    "channel": str(it.get("channel") or "stable"),
                    "released_at": str(it.get("released_at") or ""),
                    "pkg_url": str(it.get("pkg_url") or "").strip(),
                    "size": int(it.get("size") or 0),
                    "notes": str(it.get("notes") or "")[:2000],
                    "source": "remote",
                })
            _RESOURCES_CACHE["fetched_at"] = now
            _RESOURCES_CACHE["items"] = list(items)
            _RESOURCES_CACHE["error"] = None
        except Exception as exc:  # noqa
            remote_error = str(exc)
            _RESOURCES_CACHE["fetched_at"] = now
            _RESOURCES_CACHE["error"] = remote_error
            log.warning("upgrade.resources.remote_failed", url=url, error=remote_error)

    # 2) 本地 release.json（永远在，避免远端挂时空白）
    local = _local_release()
    if local:
        items.append({
            "version": str(local.get("version") or ""),
            "channel": str(local.get("channel") or "stable"),
            "released_at": str(local.get("released_at") or ""),
            "pkg_url": str(local.get("core_pkg_url") or "").strip(),
            "size": 0,
            "notes": str(local.get("notes") or "")[:2000],
            "source": "local",
        })

    # 3) 本地已下载 tar.gz（按 version 标 installed/local_path）
    cur = _read_version()
    downloaded: dict[str, Path] = {}
    if download_dir.exists():
        for f in sorted(download_dir.glob("cenkor-admin-core-*.tar.gz"), key=lambda x: x.stat().st_mtime, reverse=True):
            # 文件名：cenkor-admin-core-<version>-<date>.tar.gz
            name = f.name
            # 提取 -<version>- 部分
            v = ""
            m = re.match(r"cenkor-admin-core-([\d.]+)-", name)
            if m:
                v = m.group(1)
            if not v:
                v = name
            downloaded.setdefault(v, f)
    for it in items:
        if it["version"] in downloaded:
            it["local_path"] = str(downloaded[it["version"]])
            it["local_size"] = downloaded[it["version"]].stat().st_size
            it["installed"] = (it["version"] == cur)
            # 标记「此资源已下载到本地」
            it["downloaded"] = True
    for v, p in downloaded.items():
        if not any(it["version"] == v for it in items):
            items.append({
                "version": v,
                "channel": "stable",
                "released_at": "",
                "pkg_url": "",
                "size": 0,
                "notes": "（仅本地文件，未在资源清单中）",
                "source": "local_file",
                "local_path": str(p),
                "local_size": p.stat().st_size,
                "installed": (v == cur),
                "downloaded": True,
            })

    # 去重（同 version 优先 remote），按 version 倒序
    seen: set[str] = set()
    out: list[dict] = []
    rank = {"remote": 0, "local": 1, "local_file": 2}
    for it in sorted(items, key=lambda x: (rank.get(x.get("source", ""), 9), x.get("version", "")), reverse=False):
        if it["version"] in seen:
            continue
        seen.add(it["version"])
        out.append(it)
    out.sort(key=lambda x: x.get("version", ""), reverse=True)

    return {
        "current_version": cur,
        "remote_url": url,
        "remote_cached_at": _RESOURCES_CACHE["fetched_at"],
        "remote_error": remote_error,
        "download_dir": str(download_dir),
        "items": out,
    }


async def download_resource(version: str, db) -> dict:
    """把指定 version 的 pkg_url 拉到本地 download_dir。返回 {ok, version, local_path, size}。

    软失败：URL 不可达 / 无 URL / 鉴权失败都返回 {ok:false, error}。
    """
    s = _settings()
    token = (s.CORE_RELEASES_TOKEN if s else "").strip()
    download_dir = Path((s.CORE_RELEASES_DOWNLOAD_DIR if s else "/www/wwwroot/cenkor-admin/release"))
    download_dir.mkdir(parents=True, exist_ok=True)

    # 在缓存里找
    info = await list_resources(force_refresh=False)
    target = next((x for x in info["items"] if x.get("version") == version), None)
    if not target:
        return {"ok": False, "error": "未找到版本 " + version, "version": version}
    pkg_url = (target.get("pkg_url") or "").strip()
    if not pkg_url:
        return {"ok": False, "error": "该版本没有 pkg_url", "version": version, "item": target}

    # 推断文件名（URL 末段 → cenkor-admin-core-<version>.tar.gz）
    fn = pkg_url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] or ("cenkor-admin-core-" + version + ".tar.gz")
    if not fn.endswith(".tar.gz"):
        fn = "cenkor-admin-core-" + version + ".tar.gz"
    dst = download_dir / fn
    # 防止 path 穿越
    if not str(dst.resolve()).startswith(str(download_dir.resolve())):
        return {"ok": False, "error": "非法的目标路径", "version": version}

    proc = await asyncio.create_subprocess_exec(
        "curl", "-fL", "--retry", "3",
        "-H", "User-Agent: cenkor-admin-upgrade/0.2.0",
        *(["-H", "Authorization: Bearer " + token] if token else []),
        "-o", str(dst), pkg_url,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        try:
            dst.unlink(missing_ok=True)
        except Exception:  # noqa
            pass
        return {
            "ok": False, "version": version,
            "error": "curl exit " + str(proc.returncode) + ": " + err.decode("utf-8", errors="replace").strip()[:500],
        }
    size = dst.stat().st_size if dst.exists() else 0
    if size == 0:
        try:
            dst.unlink(missing_ok=True)
        except Exception:  # noqa
            pass
        return {"ok": False, "version": version, "error": "下载文件为空"}

    return {"ok": True, "version": version, "local_path": str(dst), "size": size}


async def _fetch_pkg(run, db, source, payload):
    stamp = _now_stamp()
    pkg_path = Path("/tmp/upgrade_" + stamp + ".tar.gz")
    if source == "url":
        url = (payload.get("url") or "").strip()
        if not url:
            raise RuntimeError("source=url 但未传 url")
        await _append_log(run, db, "▸ 下载 " + url)
        proc = await asyncio.create_subprocess_exec(
            "curl", "-fL", "--retry", "3", "-o", str(pkg_path), url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError("下载失败：" + (stderr.decode()[:300] if stderr else ""))
    elif source == "tar_upload":
        local = (payload.get("local_path") or "").strip()
        if not local or not Path(local).exists():
            raise RuntimeError("source=tar_upload 但未传 local_path 或文件不存在")
        shutil.copy2(local, pkg_path)
    else:
        raise RuntimeError("不支持的 source：" + str(source) + "（仅 url / tar_upload）")
    sz = pkg_path.stat().st_size
    if sz < 1024:
        raise RuntimeError("核心包太小（" + str(sz) + " B），疑似下载失败")
    await _append_log(run, db, "  ✓ 核心包就绪：" + str(pkg_path) + " (" + str(round(sz/1024/1024, 2)) + " MB)")
    return pkg_path

async def _apply_pkg(run, db, pkg_path):
    stage = Path(tempfile.mkdtemp(prefix="upgrade_stage_"))
    await _append_log(run, db, "▸ 解压 " + pkg_path.name + " → " + str(stage))
    proc = await asyncio.create_subprocess_exec(
        "tar", "-xzf", str(pkg_path), "-C", str(stage),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("解压失败：" + (stderr.decode()[:300] if stderr else ""))
    subs = [d for d in stage.iterdir() if d.is_dir()]
    if len(subs) != 1:
        raise RuntimeError("核心包结构异常：stage 顶层 " + str(len(subs)) + " 个目录")
    pkg_root = subs[0]
    await _append_log(run, db, "  ✓ 解压完成，包根：" + pkg_root.name)
    await _append_log(run, db, "▸ rsync 覆盖到 /www/wwwroot/cenkor-admin/")
    if shutil.which("rsync"):
        cmd = [
            "rsync", "-a",
            "--exclude=.env", "--exclude=.env.prod",
            "--exclude=backend/src/uploads", "--exclude=backend/logs",
            "--exclude=node_modules", "--exclude=__pycache__",
            "--exclude=.git",
            str(pkg_root) + "/", str(ROOT) + "/",
        ]
    else:
        cmd = ["bash", "-lc", "cp -a " + str(pkg_root) + "/. " + str(ROOT) + "/."]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("rsync/cp 失败：" + (stderr.decode()[:300] if stderr else ""))
    await _append_log(run, db, "  ✓ 文件已覆盖")
    try:
        subprocess.run(
            ["chown", "-R", "www:www",
             str(ROOT / "backend/src"),
             str(ROOT / "backend/alembic"),
             str(ROOT / "backend/alembic.ini"),
             str(ROOT / "backend/logconf"),
             str(ROOT / "backend/src/cenkor_admin/VERSION"),
            ], check=False,
        )
    except Exception:  # noqa
        pass
    await _append_log(run, db, "  ✓ chown www:www（关键路径）")
    subprocess.run(
        ["find", str(ROOT / "backend"), "-name", "__pycache__",
         "-type", "d", "-exec", "rm", "-rf", "{}", "+"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    await _append_log(run, db, "  ✓ 清 __pycache__")
    return pkg_root

async def _alembic_upgrade_main_only(run, db):
    """只升级主架构链迁移，跳过业务应用链。

    列出当前 head 链上待跑的所有 revision；
    对每条业务链 revision 用 alembic stamp 标记为已应用（不执行 DDL）；
    再 alembic upgrade head 跑剩下的主架构链。
    """
    business = _collect_business_revs()
    await _append_log(run, db, "  · 业务链白名单（跳过）：" + str(len(business)) + " 个 revision")
    idx = _load_migration_index()
    rows = (await db.execute(text("select version_num from alembic_version"))).all()
    current = {r[0] for r in rows}
    if not current:
        await _append_log(run, db, "  ! alembic_version 表为空，跳过 alembic")
        return []
    referenced = set()
    for rev, (_fn, down) in idx.items():
        if down is None:
            continue
        if isinstance(down, (list, tuple)):
            for x in down:
                referenced.add(x)
        else:
            referenced.add(down)
    heads = {r for r in idx if r not in referenced}
    await _append_log(run, db, "  · 迁移图 head(s)：" + str(sorted(heads)))
    reachable = set()
    for head in heads:
        cur = head
    seen = set()
    while cur and cur in idx and cur not in seen:
            seen.add(cur)
            reachable.add(cur)
            d = idx[cur][1]
            if isinstance(d, (list, tuple)):
                cur = d[0] if d else None
            else:
                cur = d
    to_run = reachable - current
    business_to_skip = to_run & business
    main_to_run = to_run - business
    await _append_log(run, db, "  · 待跑 " + str(len(to_run)) + " 个（主架构 " + str(len(main_to_run)) + " / 业务 " + str(len(business_to_skip)) + "）")
    if business_to_skip:
        sample = sorted(business_to_skip)[:5]
        more = " 等" if len(business_to_skip) > 5 else ""
        await _append_log(run, db, "  · 业务链跳过：" + str(sample) + more)
    if business_to_skip:
        leaf_revs = set()
        for rev in business_to_skip:
            down = idx.get(rev, (None, None))[1]
            if down is None:
                continue
            childs = down if isinstance(down, (list, tuple)) else [down]
            for c in childs:
                if c in business_to_skip:
                    break
            else:
                leaf_revs.add(rev)
        for rev in leaf_revs:
            await _append_log(run, db, "  · stamp 跳过业务链：" + rev)
            proc = await asyncio.create_subprocess_exec(
                PYTHON_BIN, "-m", "alembic", "stamp", rev,
                cwd=str(ROOT / "backend"),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                await _append_log(run, db, "    ! stamp 失败：" + (stderr.decode()[:200] if stderr else "") + "（继续）")
    await _append_log(run, db, "▸ alembic upgrade head（仅主架构链）")
    proc = await asyncio.create_subprocess_exec(
        PYTHON_BIN, "-m", "alembic", "upgrade", "head",
        cwd=str(ROOT / "backend"),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = (stdout + stderr).decode()
    for ln in out.splitlines()[-20:]:
        await _append_log(run, db, "  · " + ln)
    if proc.returncode != 0:
        raise RuntimeError("alembic upgrade 失败：" + (stderr.decode()[:300] if stderr else ""))
    return sorted(main_to_run)

async def _rollback_from_snapshot(run, db, snap):
    """从 snapshot 恢复：用 tar 反向覆盖 ROOT，chown。

    不做 alembic downgrade —— 业务链迁移没跑、没必要降级；
    主架构链的迁移，新版代码退回去后，新迁移的 schema 是兼容的。
    """
    await _append_log(run, db, "⟲ 自动回滚：" + str(snap))
    tar_files = list(snap.glob("project_*.tar.gz"))
    if not tar_files:
        raise RuntimeError("snapshot " + str(snap) + " 找不到 project_*.tar.gz")
    tar_path = tar_files[0]
    stage = Path(tempfile.mkdtemp(prefix="rollback_stage_"))
    proc = await asyncio.create_subprocess_exec(
        "tar", "-xzf", str(tar_path), "-C", str(stage),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    subs = [d for d in stage.iterdir() if d.isdir()]
    if len(subs) != 1:
        raise RuntimeError("rollback tar 解压结构异常")
    snap_root = subs[0]
    if shutil.which("rsync"):
        cmd = [
            "rsync", "-a",
            str(snap_root) + "/", str(ROOT) + "/",
        ]
    else:
        cmd = ["bash", "-lc", "cp -a " + str(snap_root) + "/. " + str(ROOT) + "/."]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await proc.communicate()
    await _append_log(run, db, "  ✓ 文件已从快照恢复")
    subprocess.run(
        ["chown", "-R", "www:www", str(ROOT / "backend/src"),
         str(ROOT / "backend/alembic"), str(ROOT / "backend/alembic.ini"),
         str(ROOT / "backend/logconf"), str(ROOT / "backend/src/cenkor_admin/VERSION"),
        ], check=False,
    )
    subprocess.run(
        ["find", str(ROOT / "backend"), "-name", "__pycache__",
         "-type", "d", "-exec", "rm", "-rf", "{}", "+"],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    await _append_log(run, db, "  ✓ chown + 清 __pycache__")

def _run_brief(r):
    if r is None:
        return None
    return {
        "id": r.id,
        "source": r.source,
        "channel": r.channel,
        "from_version": r.from_version,
        "to_version": r.to_version,
        "status": r.status,
        "backup_path": r.backup_path,
        "duration_ms": r.duration_ms,
        "operator_id": r.operator_id,
        "rollback_from_id": r.rollback_from_id,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def _announcement_class():
    """软依赖 announcements App —— 升级时如果装了，写一条置顶公告（30 天过期）。

    软依赖：没装 / 导入失败都返回 None，调用方降级。
    announcements 模型字段：title / content / category / is_pinned / is_published /
    publish_at / expire_at / author_id。
    """
    try:
        from cenkor_admin.apps.announcements.models import Announcement  # noqa
    except Exception:  # noqa
        return None
    return Announcement


async def _publish_announcement(db, run, notes, user):
    """把 notes 写进 announcements 表（如果 announcements App 存在）。

    - category='system'  priority='normal'  is_pinned=True
    - publish_at=现在    expire_at=30 天后（30 天后自动 unpin）
    """
    if not notes or not notes.strip():
        return
    Ann = _announcement_class()
    if Ann is None:
        log.info("upgrade.publish_announcement.skipped", run_id=run.id, reason="announcements_app_missing")
        return
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=30)
    title = f"系统升级 v{run.from_version or '?'} → v{run.to_version or '?'}"
    content = notes.strip()
    extra = (
        "\n\n---\n"
        f"升级耗时：{(run.duration_ms or 0) // 1000} 秒"
        f"　操作人：user#{user.id if user else 'system'}"
        f"　升级记录：#{run.id}"
    )
    a = Ann(
        title=title,
        content=content + extra,
        category="system",
        priority="normal",
        is_pinned=True,
        is_published=True,
        publish_at=now,
        expire_at=expire,
        author_id=user.id if user else None,
    )
    db.add(a)
    await db.commit()
    log.info("upgrade.publish_announcement.ok", run_id=run.id, title=title)


async def run_upgrade(db, user, source, payload, dry_run=False, rollback_from_id=None, notes=None):
    """跑一次升级。返回 UpgradeRun（status=pending/running/success/failed/rolled_back）。

    入参：source=url/tar_upload, payload={url|local_path, channel=stable|beta}, dry_run=True 只 plan 不动。
          notes=更新日志（升级成功后既写进 run.notes，也尝试发一条 announcements 公告）。
    """
    if _RUNNING_LOCK.locked():
        raise RuntimeError("已有升级任务在跑，请稍后再试")
    async with _RUNNING_LOCK:
        from_version = _read_version()
        run = UpgradeRun(
            mode="core",
            source=source,
            channel=(payload.get("channel") or "stable"),
            from_version=from_version,
            to_version="unknown",
            status="pending",
            operator_id=user.id if user else None,
            rollback_from_id=rollback_from_id,
            notes=notes,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        if dry_run:
            await _append_log(run, db, "== dry-run 仅规划，不动文件 / DB ==")
            await _append_log(run, db, "  当前版本：" + from_version)
            business = _collect_business_revs()
            await _append_log(run, db, "  业务链（升级时跳过）：" + str(len(business)) + " 个 revision")
            await _append_log(run, db, "  将执行：备份 → 拉核心包 → 解压覆盖 → alembic upgrade head（仅主架构） → 重启 8002 → 健康检查")
            await _append_log(run, db, "  失败时自动回滚：rsync 整站恢复 + 重启 + health")
            run.status = "success"
            await db.commit()
            return run

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()
        snap = None
        try:
            await _append_log(run, db, "=== 升级开始（" + str(source) + "）===")
            snap = await _do_backup(run, db)
            run.backup_path = str(snap)
            await db.commit()
            pkg_path = await _fetch_pkg(run, db, source, payload)
            run.pkg_path = str(pkg_path)
            await db.commit()
            await _apply_pkg(run, db, pkg_path)
            await _alembic_upgrade_main_only(run, db)
            to_version = _read_version()
            run.to_version = to_version
            await _append_log(run, db, "✓ 代码+迁移已应用 " + from_version + " → " + to_version)
            await db.commit()
            await _append_log(run, db, "▸ 重启 8002 + 健康检查")
            await _restart_8002()
            if not await _wait_health(timeout=30.0):
                raise RuntimeError("健康检查失败（30s 内 /api/health 未 200）")
            await _append_log(run, db, "✓ /api/health 200")
            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            if run.started_at:
                run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
            await db.commit()
            # 升级成功 → 自动发布「系统更新公告」（软依赖 announcements App）
            try:
                await _publish_announcement(db, run, run.notes, user)
            except Exception as pub_exc:  # noqa
                log.warning("upgrade.publish_announcement.failed", run_id=run.id, error=str(pub_exc))
                await _append_log(run, db, "  · 发布升级公告失败（不影响升级结果）: " + str(pub_exc))
                try:
                    await db.rollback()
                except Exception:  # noqa
                    pass
        except Exception as exc:  # noqa
            run.error = type(exc).__name__ + ": " + str(exc)
            await _append_log(run, db, "✗ 升级失败：" + str(exc))
            await db.commit()
            if snap:
                try:
                    await _rollback_from_snapshot(run, db, snap)
                    await _append_log(run, db, "▸ 回滚后重启 8002 + 健康检查")
                    await _restart_8002()
                    if await _wait_health(timeout=30.0):
                        await _append_log(run, db, "✓ 自动回滚后 /api/health 200")
                        run.status = "rolled_back"
                    else:
                        await _append_log(run, db, "✗ 回滚后健康检查仍失败 —— 需人工救火")
                        run.status = "failed"
                except Exception as rexc:  # noqa
                    await _append_log(run, db, "✗ 自动回滚也失败：" + str(rexc))
                    run.error = (run.error or "") + " | rollback_failed: " + str(rexc)
                    run.status = "failed"
            else:
                run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            if run.started_at:
                run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        await db.commit()
        await db.refresh(run)
        return run

async def manual_rollback(db, user, run_id):
    """对「已 success」的 run 手动回滚（用它的 backup_path 恢复）。

    不会动 DB schema（业务链迁移没跑、没必要降级；主架构链的迁移是新版的，
    把代码退回去后，新迁移的 schema 是兼容的）。
    """
    if _RUNNING_LOCK.locked():
        raise RuntimeError("已有升级任务在跑，请稍后再试")
    target = await db.get(UpgradeRun, run_id)
    if target is None:
        raise RuntimeError("找不到 run #" + str(run_id))
    if not target.backup_path:
        raise RuntimeError("run #" + str(run_id) + " 没有 backup_path，无法回滚")
    snap = Path(target.backup_path)
    if not snap.exists():
        raise RuntimeError("备份目录不存在：" + str(snap))
    new_run = UpgradeRun(
        mode="core", source=target.source, channel=target.channel,
        from_version=target.to_version or "unknown",
        to_version=target.from_version or "unknown",
        status="running",
        backup_path=target.backup_path,
        operator_id=user.id if user else None,
        rollback_from_id=target.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)
    try:
        await _append_log(new_run, db, "⟲ 手动回滚 → run #" + str(target.id))
        await _rollback_from_snapshot(new_run, db, snap)
        await _restart_8002()
        if not await _wait_health(timeout=30.0):
            raise RuntimeError("回滚后健康检查失败")
        new_run.status = "rolled_back"
        await _append_log(new_run, db, "✓ 手动回滚完成")
    except Exception as exc:  # noqa
        new_run.error = type(exc).__name__ + ": " + str(exc)
        new_run.status = "failed"
        await _append_log(new_run, db, "✗ 手动回滚失败：" + str(exc))
    new_run.finished_at = datetime.now(timezone.utc)
    if new_run.started_at:
        new_run.duration_ms = int((new_run.finished_at - new_run.started_at).total_seconds() * 1000)
    await db.commit()
    await db.refresh(new_run)
    return new_run


async def current_status(db):
    """GET /api/v1/system/upgrade/status 用的快照。

    返回：当前版本 / 通道 / alembic head / 是否有 running 中的升级 / 最近一次结果。
    """
    cur_v = _read_version()
    alembic_cur = "unknown"
    try:
        proc = await asyncio.create_subprocess_exec(
            PYTHON_BIN, "-m", "alembic", "current",
            cwd=str(ROOT / "backend"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        for ln in stdout.decode().splitlines():
            s = ln.strip()
            if s and "Rev:" not in s and "INFO" not in s and "Context" not in s:
                alembic_cur = s.split()[0]
                break
    except Exception:  # noqa
        pass
    running = (await db.execute(
        select(UpgradeRun).where(UpgradeRun.status == "running").order_by(UpgradeRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    last = (await db.execute(
        select(UpgradeRun).order_by(UpgradeRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    return {
        "current_version": cur_v,
        "alembic_current": alembic_cur,
        "running": running is not None,
        "running_run_id": running.id if running else None,
        "last_run": _run_brief(last) if last else None,
        "business_revisions": len(_collect_business_revs()),
    }

MAIN_REVISION_HEAD = "20260925_0026_app_enabled"
