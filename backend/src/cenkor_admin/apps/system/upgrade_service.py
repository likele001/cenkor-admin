"""核心平台在线升级服务（git 模式）。

设计：
  1. 检查更新：git fetch origin → 对比 HEAD..origin/main → 返回待更新提交列表
  2. 执行升级：git pull --ff-only origin main → alembic upgrade head → 提示用户手动重启
  3. 不自动重启后端（部署方式各异：宝塔/systemd/docker/supervisor，重启命令不同）
  4. 回滚：git reset --hard <旧commit> → 提示用户手动重启
  5. 升级前自动备份数据库（pg_dump），代码回滚靠 git
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.system.models import UpgradeRun

log = structlog.get_logger()

ROOT = Path("/www/wwwroot/cenkor-admin").resolve()
BACKUP_DIR = Path("/www/backup/cenkor-admin")
PYTHON_BIN = "/www/server/pyporject_evn/cenkor/bin/python3"
PGDUMP_BIN = "/www/server/pgsql/bin/pg_dump"
BACKEND_PORT = 8002

_RUNNING_LOCK = asyncio.Lock()
_LOG_HOOKS: dict[int, list] = {}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _truncate_log(text: str, max_bytes: int = 200 * 1024) -> str:
    if not text:
        return ""
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    return text[-max_bytes:]


async def _append_log(run, db, line: str):
    run.log = _truncate_log((run.log or "") + line + "\n")
    try:
        await db.commit()
    except Exception:
        await db.rollback()
    hooks = _LOG_HOOKS.get(run.id, [])
    for h in hooks:
        try:
            await h(line)
        except Exception:
            pass


def register_log_hook(run_id, hook):
    _LOG_HOOKS.setdefault(run_id, []).append(hook)


def unregister_log_hook(run_id, hook):
    if run_id in _LOG_HOOKS:
        _LOG_HOOKS[run_id] = [h for h in _LOG_HOOKS[run_id] if h != hook]


# ── Git 辅助 ────────────────────────────────────────────────────────────────

async def _git(*args: str) -> tuple[int, str, str]:
    """执行 git 命令，返回 (returncode, stdout, stderr)。"""
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode("utf-8", errors="replace").strip(), err.decode("utf-8", errors="replace").strip()


async def _git_current_sha() -> str | None:
    code, out, _ = await _git("rev-parse", "HEAD")
    return out if code == 0 and out else None


async def _git_current_version() -> str:
    vf = ROOT / "backend/src/cenkor_admin/VERSION"
    if vf.exists():
        return vf.read_text().strip()
    sha = await _git_current_sha()
    return sha[:8] if sha else "unknown"


async def _git_fetch_origin() -> tuple[bool, str]:
    code, out, err = await _git("fetch", "origin", "main")
    if code != 0:
        return False, f"git fetch 失败：{err or out}"
    return True, out or "fetch ok"


async def _git_new_commits() -> list[dict]:
    """返回 origin/main 领先 HEAD 的提交列表。"""
    code, out, _ = await _git(
        "log", "HEAD..origin/main",
        "--format=%h|%ad|%s", "--date=short",
    )
    if code != 0 or not out:
        return []
    commits = []
    for line in out.split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"sha": parts[0], "date": parts[1], "message": parts[2]})
    return commits


async def _git_pull_fast_forward() -> tuple[bool, str]:
    code, out, err = await _git("pull", "--ff-only", "origin", "main")
    msg = (out + "\n" + err).strip()
    return code == 0, msg


async def _git_reset_hard(sha: str) -> tuple[bool, str]:
    code, out, err = await _git("reset", "--hard", sha)
    msg = (out + "\n" + err).strip()
    return code == 0, msg


async def _git_status_clean() -> tuple[bool, str]:
    code, out, _ = await _git("status", "--porcelain")
    if code != 0:
        return False, "无法检查 git 状态"
    if out:
        return False, "工作区有未提交改动：\n" + out
    return True, ""


# ── 数据库备份 ──────────────────────────────────────────────────────────────

def _read_env_value(key: str) -> str:
    for fname in (".env.prod", ".env"):
        p = ROOT / fname
        if not p.exists():
            continue
        try:
            for line in p.read_text().splitlines():
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    return ""


async def _do_db_backup(run, db) -> str | None:
    """pg_dump 备份数据库，返回备份文件路径。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    out_path = BACKUP_DIR / f"pg_{stamp}.sql.gz"

    db_user = _read_env_value("POSTGRES_USER") or "cenkor"
    db_name = _read_env_value("POSTGRES_DB") or "cenkor"
    db_pass = _read_env_value("POSTGRES_PASSWORD")
    db_port = _read_env_value("POSTGRES_PORT") or "5432"

    await _append_log(run, db, f"▸ 备份数据库 {db_name} → {out_path}")

    # 尝试 docker exec
    try:
        ps = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        if ps.returncode == 0 and "cenkor-postgres" in ps.stdout:
            dump = subprocess.run(
                ["docker", "exec", "-i", "cenkor-postgres", "pg_dump", "-U", db_user, db_name],
                capture_output=True, timeout=300,
            )
            if dump.returncode == 0:
                import gzip
                out_path.write_bytes(gzip.compress(dump.stdout))
                await _append_log(run, db, f"  ✓ 数据库备份完成（docker）")
                return str(out_path)
    except Exception:
        pass

    # 直连 pg_dump
    try:
        env = os.environ.copy()
        env["PGPASSWORD"] = db_pass
        dump = subprocess.run(
            [PGDUMP_BIN, "-h", "127.0.0.1", "-p", db_port, "-U", db_user, db_name],
            capture_output=True, timeout=300, env=env,
        )
        if dump.returncode == 0:
            import gzip
            out_path.write_bytes(gzip.compress(dump.stdout))
            await _append_log(run, db, f"  ✓ 数据库备份完成（直连）")
            return str(out_path)
        else:
            await _append_log(run, db, f"  ⚠ pg_dump 失败：{dump.stderr.decode()[:200]}")
    except FileNotFoundError:
        await _append_log(run, db, "  ⚠ pg_dump 未安装，跳过数据库备份")
    except Exception as e:
        await _append_log(run, db, f"  ⚠ 数据库备份异常：{e}")

    return None


# ── Alembic 迁移 ────────────────────────────────────────────────────────────

async def _alembic_upgrade(run, db) -> tuple[bool, str]:
    """跑 alembic upgrade head。"""
    await _append_log(run, db, "▸ alembic upgrade head（数据库迁移）")
    proc = await asyncio.create_subprocess_exec(
        PYTHON_BIN, "-m", "alembic", "upgrade", "head",
        cwd=str(ROOT / "backend"),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    out, _ = await proc.communicate()
    text = out.decode("utf-8", errors="replace")
    for line in text.strip().split("\n")[-20:]:
        if line.strip():
            await _append_log(run, db, "  " + line.strip())
    if proc.returncode == 0:
        await _append_log(run, db, "  ✓ 数据库迁移完成")
        return True, text
    else:
        await _append_log(run, db, f"  ✗ 数据库迁移失败（exit={proc.returncode}）")
        return False, text


# ── 对外接口 ────────────────────────────────────────────────────────────────

async def current_status(db: AsyncSession) -> dict:
    """当前版本 / 是否有 running 升级。"""
    cur_version = await _git_current_version()
    cur_sha = await _git_current_sha()

    # 找 running 的 run
    stmt = select(UpgradeRun).where(UpgradeRun.status == "running").order_by(UpgradeRun.id.desc()).limit(1)
    result = await db.execute(stmt)
    running = result.scalar_one_or_none()

    return {
        "current_version": cur_version,
        "current_sha": cur_sha,
        "backend_port": BACKEND_PORT,
        "running_run_id": running.id if running else None,
        "running_status": running.status if running else None,
    }


async def list_resources(force_refresh: bool = False) -> dict:
    """检查远程有没有新版本。返回提交列表。"""
    fetched_ok, msg = await _git_fetch_origin()
    if not fetched_ok:
        return {
            "has_update": False,
            "current_version": await _git_current_version(),
            "commits": [],
            "error": msg,
            "note": "git fetch 失败，无法检查更新",
        }

    commits = await _git_new_commits()
    cur_sha = await _git_current_sha()

    return {
        "has_update": len(commits) > 0,
        "current_version": await _git_current_version(),
        "current_sha": cur_sha,
        "commits": commits,
        "commits_count": len(commits),
        "note": f"远程有 {len(commits)} 个新提交" if commits else "已是最新",
    }


async def download_resource(version: str, db) -> dict:
    """git 模式不需要单独下载包，直接返回提示。"""
    return {
        "ok": True,
        "note": "git 模式无需预下载，升级时直接 git pull",
    }


def _run_brief(r: UpgradeRun) -> dict:
    return {
        "id": r.id,
        "mode": r.mode,
        "source": r.source,
        "channel": r.channel,
        "from_version": r.from_version,
        "to_version": r.to_version,
        "status": r.status,
        "backup_path": r.backup_path,
        "pkg_path": r.pkg_path,
        "error": r.error,
        "notes": r.notes,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_ms": r.duration_ms,
        "operator_id": r.operator_id,
        "rollback_from_id": r.rollback_from_id,
    }


async def _publish_announcement(db, run, notes, user):
    """升级成功后尝试发公告（软依赖，失败不影响升级）。"""
    try:
        from cenkor_admin.apps.announcements.models import Announcement
        title = f"系统升级 {run.from_version} → {run.to_version}"
        body = notes or "系统已更新"
        ann = Announcement(
            title=title,
            body=body,
            level="info",
            is_published=True,
        )
        db.add(ann)
        await db.commit()
    except Exception as e:
        log.warning("upgrade.announcement.failed", error=str(e))


async def run_upgrade(db, user, source: str = "git", payload: dict | None = None,
                      dry_run: bool = False, rollback_from_id: int | None = None,
                      notes: str | None = None) -> UpgradeRun:
    """执行升级：git pull + alembic + 提示重启。"""
    payload = payload or {}
    async with _RUNNING_LOCK:
        from_version = await _git_current_version()
        from_sha = await _git_current_sha()

        run = UpgradeRun(
            mode="core",
            source="git",
            channel=payload.get("channel", "stable"),
            from_version=from_version,
            to_version="unknown",
            status="pending",
            operator_id=user.id if user else None,
            rollback_from_id=rollback_from_id,
            notes=notes,
            pkg_path=from_sha,  # 记录回滚点
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        if dry_run:
            await _append_log(run, db, "== dry-run 预演 ==")
            await _append_log(run, db, f"  当前版本：{from_version} ({from_sha})")
            ok, msg = await _git_fetch_origin()
            if ok:
                commits = await _git_new_commits()
                await _append_log(run, db, f"  远程有 {len(commits)} 个新提交：")
                for c in commits[:20]:
                    await _append_log(run, db, f"    {c['sha']} {c['date']} {c['message']}")
            else:
                await _append_log(run, db, f"  fetch 失败：{msg}")
            await _append_log(run, db, "  将执行：git pull --ff-only → alembic upgrade head → 提示手动重启")
            run.status = "success"
            await db.commit()
            return run

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            await _append_log(run, db, "=== 开始 git 升级 ===")
            await _append_log(run, db, f"  当前：{from_version} ({from_sha})")

            # 1. 检查工作区干净
            clean, clean_msg = await _git_status_clean()
            if not clean:
                raise RuntimeError("git 工作区不干净，请先提交或 stash 本地改动：\n" + clean_msg)
            await _append_log(run, db, "  ✓ 工作区干净")

            # 2. fetch
            ok, msg = await _git_fetch_origin()
            if not ok:
                raise RuntimeError(msg)
            await _append_log(run, db, "  ✓ git fetch origin/main")

            # 3. 检查有没有新提交
            commits = await _git_new_commits()
            if not commits:
                await _append_log(run, db, "  已是最新，无需升级")
                run.to_version = from_version
                run.status = "success"
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
                return run

            await _append_log(run, db, f"  待更新 {len(commits)} 个提交：")
            for c in commits[:30]:
                await _append_log(run, db, f"    {c['sha']} {c['date']} {c['message']}")

            # 4. 备份数据库
            backup_path = await _do_db_backup(run, db)
            if backup_path:
                run.backup_path = backup_path
                await db.commit()

            # 5. git pull
            await _append_log(run, db, "▸ git pull --ff-only origin main")
            ok, msg = await _git_pull_fast_forward()
            if not ok:
                raise RuntimeError(f"git pull 失败：{msg}")
            for line in msg.split("\n")[-10:]:
                if line.strip():
                    await _append_log(run, db, "  " + line.strip())
            await _append_log(run, db, "  ✓ 代码已更新")

            # 6. alembic 迁移
            mig_ok, _ = await _alembic_upgrade(run, db)
            if not mig_ok:
                raise RuntimeError("数据库迁移失败，请查看日志")

            # 7. 读取新版本
            to_version = await _git_current_version()
            to_sha = await _git_current_sha()
            run.to_version = to_version
            await _append_log(run, db, f"✓ 升级完成：{from_version} ({from_sha[:8] if from_sha else '?'}) → {to_version} ({to_sha[:8] if to_sha else '?'})")

            # 8. 提示手动重启
            await _append_log(run, db, "")
            await _append_log(run, db, "════════════════════════════════════════")
            await _append_log(run, db, "⚠ 代码和数据库已更新，请手动重启后端服务：")
            await _append_log(run, db, "  - 宝塔面板：重启 Python 项目 / Gunicorn")
            await _append_log(run, db, "  - systemd：systemctl restart cenkor-admin")
            await _append_log(run, db, "  - Docker：docker compose restart backend")
            await _append_log(run, db, "════════════════════════════════════════")

            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            if run.started_at:
                run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
            await db.commit()

            # 发公告
            try:
                await _publish_announcement(db, run, run.notes, user)
            except Exception as pub_exc:
                log.warning("upgrade.announcement.failed", error=str(pub_exc))

        except Exception as exc:
            run.error = type(exc).__name__ + ": " + str(exc)
            await _append_log(run, db, f"✗ 升级失败：{exc}")
            await db.commit()

            # 尝试 git 回滚到旧 sha
            if from_sha:
                try:
                    await _append_log(run, db, f"▸ 自动回滚 git 到 {from_sha[:8]}")
                    ok, msg = await _git_reset_hard(from_sha)
                    if ok:
                        await _append_log(run, db, "  ✓ git 已回滚")
                        # 迁移也尝试回滚？不自动 downgrade，太危险
                        await _append_log(run, db, "  ⚠ 数据库迁移未自动回滚，请检查备份")
                    else:
                        await _append_log(run, db, f"  ✗ git 回滚失败：{msg}")
                        run.status = "failed"
                        await db.commit()
                        return run
                except Exception as rexc:
                    await _append_log(run, db, f"  ✗ 自动回滚异常：{rexc}")
                    run.status = "failed"
                    await db.commit()
                    return run

            run.status = "rolled_back"
            run.finished_at = datetime.now(timezone.utc)
            if run.started_at:
                run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
            await db.commit()

        await db.refresh(run)
        return run


async def manual_rollback(db, user, run_id: int) -> UpgradeRun:
    """手动回滚到指定 run 的 from_version。"""
    target = await db.get(UpgradeRun, run_id)
    if target is None:
        raise RuntimeError("升级记录不存在")

    async with _RUNNING_LOCK:
        # target.pkg_path 记录的是 from_sha
        old_sha = target.pkg_path
        if not old_sha or len(old_sha) < 7:
            raise RuntimeError("该记录没有有效的回滚点（pkg_path 为空）")

        run = UpgradeRun(
            mode="core",
            source="git",
            channel="stable",
            from_version=await _git_current_version(),
            to_version=old_sha[:8],
            status="running",
            operator_id=user.id if user else None,
            rollback_from_id=run_id,
            notes=f"手动回滚到 {old_sha[:8]}",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        try:
            await _append_log(run, db, f"=== 手动回滚到 {old_sha} ===")

            ok, msg = await _git_reset_hard(old_sha)
            if not ok:
                raise RuntimeError(f"git reset --hard 失败：{msg}")
            await _append_log(run, db, "  ✓ git 已回滚")

            await _append_log(run, db, "")
            await _append_log(run, db, "⚠ 请手动重启后端服务使回滚生效")

            run.status = "success"
            run.to_version = await _git_current_version()
        except Exception as exc:
            run.error = str(exc)
            run.status = "failed"
            await _append_log(run, db, f"✗ 回滚失败：{exc}")

        run.finished_at = datetime.now(timezone.utc)
        if run.started_at:
            run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
        await db.commit()
        await db.refresh(run)
        return run
