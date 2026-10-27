#!/usr/bin/env python3
"""把 mes-extensions 里的扩展包发布到 hub（写 app_submissions + 拷 zip）。

为什么要有这个脚本
------------------
2026-10-12 取证结论：**打包已经不是缺口**。24 个包的源码与同名 zip 都是 1.0.1、都带
product、sha256 两两一致（`mes-extensions/pack.py --check` 全绿）；缺的是发布这一步——
hub 的 `app_submissions` 里仍是 1.0.0，实例侧因此永远显示「已是最新」，`/market/status`
的「可更新 N 个」永远是 0，升级链路也从来没被走过一次。

本脚本把「发布」变成一条可重复执行、默认不写库的命令。

安全设计
--------
- **默认 dry-run**：不加 `--apply` 只打印将要发生的事，一个字节都不写。
- **只新增版本行**：永不 UPDATE/DELETE 别的 version 的行；同一 (product, app_key, version)
  已存在且 hash 相同 → 跳过（幂等，重复执行无害）。
- **产品轴继承基线行**：developer_id/name/icon/category/dev_method 取自该 app_key 现有的
  最新行，避免手填错产品把包发到别的宿主下。
- **先体检再落盘**：zip 缺失或内容与源码不一致时调 `pack.py --build` 重建，过不了闸门就不发布。
- 打印 DSN 一律脱敏；不改任何正在运行的进程（生效需 hub 重启或下一次请求自然读到新行）。

用法
----
    PY=/www/server/pyporject_evn/cenkor/bin/python
    $PY scripts/publish_extension.py --keys mold_management              # 干跑，看要做什么
    $PY scripts/publish_extension.py --keys mold_management --apply      # 真发布
    $PY scripts/publish_extension.py --all --apply                        # 批量（先演练通过再用）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime

SRC_DEFAULT = "/www/wwwroot/mes-extensions"
UPLOADS_DEFAULT = "/www/wwwroot/cenkor-admin/backend/src/uploads/apps"
ENV_FILES = [
    "/www/wwwroot/cenkor-admin/backend/.env",
    "/www/wwwroot/cenkor-admin/.env",
]


def mask(url: str) -> str:
    return re.sub(r"://[^@/]*@", "://***@", url)


def find_dsn() -> str:
    """优先取正在服务的 8002 进程环境，其次 .env（与 commerce_report.py 同一口径）。

    线上库是 8002 进程连的那一套，`.env` 可能指向别处；读错库会把包发到没人看的实例上。
    """
    try:
        out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "cenkor_admin" in line and "--port 8002" in line:
                pid = line.strip().split()[0]
                try:
                    raw = open(f"/proc/{pid}/environ", "rb").read().decode("utf8", "ignore")
                except OSError:
                    continue
                for kv in raw.split("\0"):
                    if kv.startswith("DATABASE_URL="):
                        return kv.split("=", 1)[1]
    except Exception as e:
        print(f"  读进程环境失败：{e}", file=sys.stderr)
    for f in ENV_FILES:
        if os.path.isfile(f):
            for line in open(f, encoding="utf8", errors="ignore"):
                if line.strip().startswith("DATABASE_URL="):
                    return line.strip().split("=", 1)[1]
    return ""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(pkg_dir: str) -> dict:
    p = os.path.join(pkg_dir, "manifest.json")
    if not os.path.isfile(p):
        raise SystemExit(f"缺少 manifest.json：{p}")
    with open(p, encoding="utf8") as fh:
        return json.load(fh)


def ensure_zip(src: str, key: str, version: str, apply: bool) -> str:
    """返回 zip 路径；zip 不在或与源码不一致时，先跑 pack.py 重建。"""
    zip_path = os.path.join(src, f"{key}-{version}.zip")
    pack = os.path.join(src, "pack.py")
    stale = True
    if os.path.isfile(zip_path):
        # 用 pack.py 的体检判定是否一致（它逐文件比对 sha256，比 mtime 可靠）
        if os.path.isfile(pack):
            r = subprocess.run(
                [sys.executable, pack, "--check", key], capture_output=True, text=True
            )
            stale = r.returncode != 0
        else:
            stale = False
    if stale:
        if not os.path.isfile(pack):
            raise SystemExit(f"{key}: zip 需要重建，但找不到 {pack}")
        if not apply:
            print(f"  [dry-run] 会执行：python3 {pack} --build {key}")
            return zip_path
        r = subprocess.run([sys.executable, pack, "--build", key], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"{key}: 打包闸门未通过，不发布。\n{r.stdout}\n{r.stderr}")
        print(f"  已重建 {key}-{version}.zip")
    return zip_path


def resolve_developer_id(cur, product: str, hint: int | None) -> int:
    """首发应用时定归属开发者：显式 --developer-id 优先，其次沿用该产品历史行的归属。

    app_submissions.developer_id 是外键，指向 app_developers(id)。首发时库里没有同
    app_key 的基线行可继承，若不显式定这个值，就只能瞎填一个 —— 归属错了会连带影响
    分账与开发者中心「我的应用」列表，所以宁可报错也不要猜。
    """
    if hint:
        cur.execute("select id from app_developers where id=%s", (hint,))
        row = cur.fetchone()
        return int(row[0]) if row else 0
    cur.execute(
        """select developer_id from app_submissions
           where product=%s order by id desc limit 1""",
        (product,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def baseline_row(cur, product: str, key: str):
    cur.execute(
        """select developer_id, product, dev_method, app_key, name, description, icon, category,
                  version, status, file_hash
           from app_submissions
           where product=%s and app_key=%s
           order by id desc limit 1""",
        (product, key),
    )
    return cur.fetchone()


def existing_row(cur, product: str, key: str, version: str):
    cur.execute(
        """select id, status, file_hash, file_path, developer_id,
                  published_at, schema_version, min_core_version, changelog
           from app_submissions where product=%s and app_key=%s and version=%s""",
        (product, key, version),
    )
    return cur.fetchone()


def publish_one(conn, src: str, key: str, apply: bool, uploads_dir: str,
              allow_new: bool = False, developer_id_hint: int | None = None) -> str:
    pkg_dir = os.path.join(src, key)
    if not os.path.isdir(pkg_dir):
        return f"SKIP {key}: 源码目录不存在 {pkg_dir}"
    man = read_manifest(pkg_dir)
    if man.get("key") != key:
        return f"SKIP {key}: manifest.key={man.get('key')!r} 与目录名不符"
    version = str(man.get("version") or "")
    product = str(man.get("product") or "")
    if not version or not product:
        return f"SKIP {key}: manifest 缺 version 或 product（先补包，别急着发）"

    zip_path = ensure_zip(src, key, version, apply)
    if not os.path.isfile(zip_path):
        return f"SKIP {key}: 没有 {os.path.basename(zip_path)}"
    file_hash = sha256(zip_path)
    target_zip = os.path.join(uploads_dir, f"{key}-{version}.zip")

    cur = conn.cursor()
    base = baseline_row(cur, product, key)
    if not base:
        # 首发路径：hub 上从来没出现过这个 app_key。老逻辑一律 SKIP，是因为它要靠基线行
        # 继承 developer_id / name / icon 这些「不属于包体」的归属信息，猜错会把包发到别的
        # 宿主或别的开发者名下。加 --allow-new 后改从 manifest 取，归属人仍必须查得到。
        if not allow_new:
            return (f"SKIP {key}: hub 上该产品({product})没有该 app_key 的任何行，缺发布基线"
                    f"（首次上架需 --allow-new，或走开发者中心上传）")
        developer_id = resolve_developer_id(cur, product, developer_id_hint)
        if not developer_id:
            return (f"SKIP {key}: 首发定不出 developer_id（{product} 下无任何历史行，"
                    f"且 app_developers 查不到指定值），请显式传 --developer-id")
        base = (developer_id, product, str(man.get("dev_method") or "extension"), key,
                str(man.get("name") or key), man.get("description"),
                str(man.get("icon") or "📦"), str(man.get("category") or "system"),
                version, "pending", None)
        print(f"  [首发] {key}: 基线行不存在，developer_id={developer_id} "
              f"dev_method={base[2]} icon={base[6]} category={base[7]}")
    developer_id = base[0]

    schema_version = man.get("schema_version")
    min_core_version = man.get("min_core_version")
    changelog = man.get("changelog")

    row = existing_row(cur, product, key, version)
    # 0035 起「审核通过」与「上架」分离：目录只认 published_at 非空的行。
    # 老版本脚本只写 status=approved，新包会审核通过却不出现在商店，所以这里连同
    # manifest v2 契约字段一起补齐；已上架且内容一致的才跳过。
    if (
        row
        and row[2] == file_hash
        and row[1] in ("approved", "installed")
        and row[5] is not None
        and row[6] == schema_version
        and row[7] == min_core_version
        and row[8] == changelog
    ):
        return f"OK   {key} {product}@{version} 已上架且内容一致（id={row[0]}），跳过"

    if not apply:
        action = "更新已有行" if row else "新增行"
        print(
            f"  [dry-run] {key} {product}@{version} → {action}"
            f"（developer_id={developer_id}, zip→{target_zip}, sha256={file_hash[:12]}…,"
            f" status=approved）"
        )
        if row:
            print(f"           现有行 id={row[0]} status={row[1]} hash={str(row[2])[:12]}…")
        return f"PLANNED {key} {product}@{version}"

    # 落盘 zip（同一内容重复写无害；内容不同则覆盖，因为 DB 行会跟着记新 hash）
    os.makedirs(uploads_dir, exist_ok=True)
    shutil.copy2(zip_path, target_zip)

    manifest_json = json.dumps(man, ensure_ascii=False)
    now = datetime.now(UTC)
    try:
        if row:
            cur.execute(
                """update app_submissions
                   set file_path=%s, file_hash=%s, manifest_data=%s::json,
                       status='approved', reviewed_at=now(), review_note=%s,
                       schema_version=%s, min_core_version=%s, changelog=%s,
                       published_at=COALESCE(published_at, now()),
                       updated_at=now()
                   where id=%s""",
                (
                    target_zip, file_hash, manifest_json,
                    f"publish_extension.py 于 {now:%Y-%m-%d %H:%M} 同步发布",
                    schema_version, min_core_version, changelog, row[0],
                ),
            )
            note = f"UPDATE id={row[0]}"
        else:
            cur.execute(
                """insert into app_submissions
                   (developer_id, product, dev_method, app_key, name, version, description,
                    icon, category, manifest_data, file_path, file_hash, status,
                    schema_version, min_core_version, changelog, published_at,
                    review_note, reviewed_at, updated_at)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::json,%s,%s,'approved',
                           %s,%s,%s,now(),%s,now(),now())""",
                (
                    developer_id, product, base[2], key, base[4] or man.get("name", key), version,
                    base[5] if base[5] is not None else man.get("description"),
                    base[6] or man.get("icon", "📦"), base[7] or man.get("category", "system"),
                    manifest_json, target_zip, file_hash,
                    schema_version, min_core_version, changelog,
                    f"publish_extension.py 于 {now:%Y-%m-%d %H:%M} 发布",
                ),
            )
            note = "INSERT"
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"FAIL {key}: {type(e).__name__}: {e}"
    finally:
        cur.close()
    return f"DONE {key} {product}@{version} {note} zip={os.path.basename(target_zip)}"


def main() -> int:
    ap = argparse.ArgumentParser(description="发布扩展包到 hub（默认 dry-run）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--keys", nargs="+", metavar="KEY", help="要发布的 app_key（可多个）")
    g.add_argument("--all", action="store_true", help="src 下全部包")
    ap.add_argument("--apply", action="store_true", help="真正写库与拷 zip；不加只打印")
    ap.add_argument("--allow-new", action="store_true",
                    help="允许首发：hub 上没有该 app_key 基线行时，按 manifest 建新行")
    ap.add_argument("--developer-id", type=int, default=None,
                    help="首发时的归属开发者 id（默认沿用同产品历史行）")
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--uploads", default=UPLOADS_DEFAULT)
    args = ap.parse_args()

    try:
        import psycopg2
    except ImportError:
        print("需要 psycopg2：用 /www/server/pyporject_evn/cenkor/bin/python 跑本脚本", file=sys.stderr)
        return 2

    dsn = find_dsn()
    if not dsn:
        print("取不到 DATABASE_URL（8002 进程与 .env 都没有）", file=sys.stderr)
        return 2
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", dsn)
    print(f"连接：{mask(url)}")
    conn = psycopg2.connect(url)

    if args.all:
        keys = sorted(
            d for d in os.listdir(args.src)
            if os.path.isfile(os.path.join(args.src, d, "manifest.json"))
        )
    else:
        keys = args.keys

    print(f"{'[DRY-RUN] ' if not args.apply else ''}目标：{len(keys)} 个包，发布目录 {args.uploads}\n")
    results = [publish_one(conn, args.src, k, args.apply, args.uploads,
                           allow_new=args.allow_new, developer_id_hint=args.developer_id)
               for k in keys]
    print("\n".join(results))
    planned = sum(1 for r in results if r.startswith("PLANNED"))
    done = sum(1 for r in results if r.startswith("DONE"))
    skipped = sum(1 for r in results if r.startswith("SKIP"))
    failed = sum(1 for r in results if r.startswith("FAIL"))
    print(f"\n汇总：新增/更新 {done}，一致跳过 {len(results) - done - planned - skipped - failed}，"
          f"待发布 {planned}，跳过 {skipped}，失败 {failed}")
    conn.close()
    if args.apply and done:
        print("\n下一步：实例侧 `POST /api/v1/market/install`（或市场页点安装）即可拿到新版本；"
              "重装会按 mtime:size 指纹重跑 migrations.sql，所以升级演练前先导一份 mold_* 表 dump。")
    if failed:
        return 1
    if not args.apply and planned:
        print("（以上只是计划，加 --apply 才写库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
