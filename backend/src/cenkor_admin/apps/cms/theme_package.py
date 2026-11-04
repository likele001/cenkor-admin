"""模板包规范（``theme.json``）：定义、校验、设置解析。

## 为什么要有这个文件

在它之前，「一套主题」没有可陈述的定义 —— 内置主题没有清单，``templates/export``
只产出一个 ``manifest.json``（``theme`` / ``files`` / ``exported_at`` / ``site_id``），
那是内部导出用的快照，不含任何分发需要的信息：谁写的、什么版本、给谁用、
装完怎么配。于是三件事只能靠约定：作者写 README、审核靠人眼看、站长装完
不知道能改什么，只能去翻 HTML 找色值。

``theme.json`` 把这三件事变成机器可读的：

* **分发** —— 版本 / 作者 / 许可 / 依赖，商店与安装器直接吃
* **审核** —— ``asset_kinds`` 声明与实际文件比对，声明只用 CSS 的包可以自动过审
* **配置** —— ``settings`` 声明让后台自动长出配置表单，无需为每个主题写一个页面

## 与 cms_templates 表的关系

表里存的是**文件**，``theme.json`` 也是其中一条（``kind="meta"``）。也就是说
清单跟着主题走、跟着主题导出、跟着主题换版本 —— 不需要新表、不需要迁移。

## 兼容旧包

上一版 export 的产物没有 ``theme.json``。``validate_package()`` 遇到时按
legacy 处理：给 warning、用 zip 内的信息补一份最小清单，**不拒包**。
装得进去比规矩整齐更重要。

## 设置值存在哪

``Site.settings`` 的扁平 key：``theme.<主题key>.<设置key>``。
复用已有的 key-value 存储，不新建表；``TemplateContext.site_meta()`` 本来
就能读到扁平 key，所以模板侧无需任何新接口。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MANIFEST_NAME",
    "MAX_FILE_BYTES",
    "MAX_PACKAGE_BYTES",
    "MAX_PACKAGE_FILES",
    "SCHEMA_VERSION",
    "SETTING_TYPES",
    "PackageCheck",
    "SettingSpec",
    "ThemeManifest",
    "coerce_setting",
    "manifest_from_json",
    "resolve_settings",
    "setting_storage_key",
    "validate_package",
]

# ---------------------------------------------------------------- 常量

MANIFEST_NAME = "theme.json"
SCHEMA_VERSION = 1

# 包体限制。templates/import 以前自己定义了一份，现在统一从这里取，
# 避免"导入接口 5MB、商店提交 10MB"这种两套口径的经典漂移。
MAX_PACKAGE_BYTES = 5 * 1024 * 1024
MAX_PACKAGE_FILES = 300
MAX_FILE_BYTES = 1024 * 1024

# 主题 key 同时是目录名、URL 片段、设置前缀，收紧到小写字母数字
_THEME_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# 设置 key 要拼进 site.settings 的扁平 key（theme.<主题>.<设置>），
# 所以不能带点（点会被当成层级）、不能大写（导出 SQL 时容易变味）
_SETTING_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")

# 语义化版本。允许 1.2 简写，拒绝 "latest" / "v1" 这类无法比较的写法
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?$")

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# 设置控件类型。前端 ThemeSettingsDialog 按这个 switch 出控件，
# 加新类型要两边一起改（后端校验 + 前端渲染），所以列表只有这一份。
SETTING_TYPES = ("color", "select", "bool", "text", "textarea", "number", "range", "image")

# 资源类型 → 文件扩展名。审核时拿它比对 asset_kinds 声明。
_ASSET_KIND_EXT = {"css": ".css", "js": ".js"}

# 包里允许出现、但不写进 cms_templates 的文件（不参与模板渲染）
# 预览图目前也走商店 AppIntro 上传，所以这里暂无条目；
# 留着这个钩子是因为下一步要支持包内截图。
_ATTACHMENT_PATTERNS: tuple[str, ...] = ()

_UNKNOWN = object()


# ---------------------------------------------------------------- 数据结构


@dataclass(frozen=True)
class SettingSpec:
    """一个可配置项。默认值必须给 —— 模板里读 ``theme.xxx`` 时不能有空。"""

    key: str
    type: str
    label: str
    default: Any = None
    options: tuple[Any, ...] = ()
    help: str = ""
    group: str = "通用"
    # number / range 的取值范围。前端滑杆要知道两端在哪，
    # 后端也不能让 1200px 的内容区开出 5000px 的档
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "key": self.key,
            "type": self.type,
            "label": self.label,
            "default": self.default,
            "group": self.group,
        }
        if self.options:
            out["options"] = list(self.options)
        if self.help:
            out["help"] = self.help
        for attr in ("minimum", "maximum", "step"):
            val = getattr(self, attr)
            if val is not None:
                out[attr] = val
        return out


@dataclass(frozen=True)
class ThemeManifest:
    """``theme.json`` 的解析结果。"""

    schema_version: int
    key: str
    name: str
    version: str
    description: str = ""
    author: dict[str, Any] = field(default_factory=dict)
    license: str = "MIT"
    icon: str = ""
    screenshots: tuple[str, ...] = ()
    demo_url: str = ""
    tags: tuple[str, ...] = ()
    requires: dict[str, Any] = field(default_factory=dict)
    settings: tuple[SettingSpec, ...] = ()
    changelog: str = ""
    files: tuple[str, ...] = ()
    # 包里没有 theme.json 时由文件名补出来的清单，审核口径要区别对待
    legacy: bool = False

    @property
    def author_name(self) -> str:
        return str(self.author.get("name") or "").strip()

    @property
    def asset_kinds(self) -> tuple[str, ...]:
        """声明的资源类型。没声明等于「只用模板 + CSS」，审核据此放行。"""
        kinds = self.requires.get("asset_kinds") or []
        return tuple(k for k in kinds if isinstance(k, str))

    def setting(self, key: str) -> SettingSpec | None:
        for spec in self.settings:
            if spec.key == key:
                return spec
        return None

    def defaults(self) -> dict[str, Any]:
        return {spec.key: spec.default for spec in self.settings}

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "key": self.key,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": dict(self.author),
            "license": self.license,
            "icon": self.icon,
            "tags": list(self.tags),
            "requires": dict(self.requires),
            "settings": [s.as_dict() for s in self.settings],
            "files": list(self.files),
        }
        if self.screenshots:
            data["screenshots"] = list(self.screenshots)
        if self.demo_url:
            data["demo_url"] = self.demo_url
        if self.changelog:
            data["changelog"] = self.changelog
        return data


@dataclass
class PackageCheck:
    """一次包校验的完整结果。errors 非空即拒包。"""

    ok: bool
    manifest: ThemeManifest | None
    files: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    legacy: bool = False

    def error(self, message: str, *, path: str = "", field_name: str = "") -> None:
        item: dict[str, Any] = {"message": message}
        if path:
            item["path"] = path
        if field_name:
            item["field"] = field_name
        self.errors.append(item)

    def warn(self, message: str, *, path: str = "", field_name: str = "") -> None:
        item: dict[str, Any] = {"message": message}
        if path:
            item["path"] = path
        if field_name:
            item["field"] = field_name
        self.warnings.append(item)


# ---------------------------------------------------------------- 解析


def _num_or_none(value: Any) -> float | None:
    """清单里的数字可能写成字符串（作者手写 JSON 常见），统一收成 float。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def manifest_from_json(raw: str | dict[str, Any], *, legacy_key: str | None = None) -> ThemeManifest:
    """把 ``theme.json`` 文本/字典解析成 ``ThemeManifest``。

    只做**结构解析**（缺字段给默认值、类型错了给默认值），不做**合法性判断**
    —— 判断在 ``_check_manifest`` 里，两件事分开写，报错能定位到字段。
    """
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"theme.json 不是合法 JSON：{exc}") from exc
    else:
        obj = dict(raw or {})
    if not isinstance(obj, dict):
        raise ValueError("theme.json 顶层必须是对象")

    key = str(obj.get("key") or legacy_key or "").strip()
    spec_list: list[SettingSpec] = []
    for item in obj.get("settings") or []:
        if not isinstance(item, dict):
            continue
        opts = item.get("options")
        spec_list.append(
            SettingSpec(
                key=str(item.get("key") or "").strip(),
                type=str(item.get("type") or "text").strip().lower(),
                label=str(item.get("label") or item.get("key") or "").strip(),
                default=item.get("default"),
                options=tuple(opts) if isinstance(opts, list) else (),
                help=str(item.get("help") or ""),
                group=str(item.get("group") or "通用"),
                minimum=_num_or_none(item.get("minimum")),
                maximum=_num_or_none(item.get("maximum")),
                step=_num_or_none(item.get("step")),
            )
        )

    author = obj.get("author")
    if isinstance(author, str):
        author = {"name": author}
    elif not isinstance(author, dict):
        author = {}

    requires = obj.get("requires")
    if not isinstance(requires, dict):
        requires = {}

    return ThemeManifest(
        schema_version=int(obj.get("schema_version") or SCHEMA_VERSION),
        key=key,
        name=str(obj.get("name") or key or "未命名主题").strip(),
        version=str(obj.get("version") or "0.0.0").strip(),
        description=str(obj.get("description") or "").strip(),
        author=author,
        license=str(obj.get("license") or "MIT"),
        icon=str(obj.get("icon") or ""),
        screenshots=tuple(str(s) for s in (obj.get("screenshots") or []) if s),
        demo_url=str(obj.get("demo_url") or ""),
        tags=tuple(str(t) for t in (obj.get("tags") or []) if t),
        requires=requires,
        settings=tuple(spec_list),
        changelog=str(obj.get("changelog") or ""),
        files=tuple(str(f) for f in (obj.get("files") or []) if f),
        legacy=bool(obj.get("_legacy")),
    )


def _check_manifest(m: ThemeManifest, check: PackageCheck) -> None:
    """字段级校验。每一条都必须能说清「改哪里」，否则作者只能猜。"""
    if m.schema_version != SCHEMA_VERSION:
        check.error(
            f"schema_version 必须是 {SCHEMA_VERSION}，当前是 {m.schema_version}",
            path=MANIFEST_NAME,
            field_name="schema_version",
        )

    if not _THEME_KEY_RE.match(m.key or ""):
        check.error(
            "key 只能用小写字母、数字、连字符、下划线，且以小写字母或数字开头（1-64 位）",
            path=MANIFEST_NAME,
            field_name="key",
        )

    if not m.name:
        check.error("name 不能为空", path=MANIFEST_NAME, field_name="name")

    if not _VERSION_RE.match(m.version or ""):
        check.error(
            f"version 必须是语义化版本（如 1.2.0），当前是 {m.version!r}",
            path=MANIFEST_NAME,
            field_name="version",
        )

    if not m.description:
        check.warn(
            "description 为空，商店列表里没有简介会显著降低点击",
            path=MANIFEST_NAME,
            field_name="description",
        )

    if not m.author_name:
        check.warn(
            "author.name 为空，审核时无法确认作者身份",
            path=MANIFEST_NAME,
            field_name="author",
        )

    seen: set[str] = set()
    for spec in m.settings:
        where = f"settings[{spec.key or '?'}]"
        if not _SETTING_KEY_RE.match(spec.key or ""):
            check.error(
                f"{where}: key 只能用小写字母、数字、下划线，且以小写字母开头（1-48 位）",
                path=MANIFEST_NAME,
                field_name=where,
            )
            continue
        if spec.key in seen:
            check.error(f"{where}: key 重复", path=MANIFEST_NAME, field_name=where)
            continue
        seen.add(spec.key)

        if spec.type not in SETTING_TYPES:
            check.error(
                f"{where}: type 必须是 {' / '.join(SETTING_TYPES)} 之一，当前是 {spec.type!r}",
                path=MANIFEST_NAME,
                field_name=where,
            )
            continue
        _check_setting_default(spec, where, check)

    if m.requires.get("cms_features") and not isinstance(m.requires["cms_features"], list):
        check.error(
            "requires.cms_features 必须是数组", path=MANIFEST_NAME, field_name="requires.cms_features"
        )

    unknown_kinds = [k for k in m.asset_kinds if k not in _ASSET_KIND_EXT]
    if unknown_kinds:
        check.error(
            f"requires.asset_kinds 只支持 {' / '.join(_ASSET_KIND_EXT)}，出现了 {unknown_kinds}",
            path=MANIFEST_NAME,
            field_name="requires.asset_kinds",
        )


def _check_setting_default(spec: SettingSpec, where: str, check: PackageCheck) -> None:
    """默认值必须与类型自洽 —— 否则模板取到一个错类型的值，渲染时才炸。"""
    default = spec.default

    if spec.type == "bool":
        if not isinstance(default, bool):
            check.error(f"{where}: bool 类型的 default 必须是 true/false", path=MANIFEST_NAME, field_name=where)
        return

    if spec.type in ("number", "range"):
        if not isinstance(default, (int, float)) or isinstance(default, bool):
            check.error(f"{where}: {spec.type} 类型的 default 必须是数字", path=MANIFEST_NAME, field_name=where)
            return
        if spec.type == "range" and (spec.minimum is None or spec.maximum is None):
            check.error(f"{where}: range 必须提供 minimum 和 maximum（滑杆要知道两端在哪）",
                        path=MANIFEST_NAME, field_name=where)
            return
        if spec.minimum is not None and default < spec.minimum:
            check.error(f"{where}: default {default} 小于 minimum {spec.minimum}",
                        path=MANIFEST_NAME, field_name=where)
        if spec.maximum is not None and default > spec.maximum:
            check.error(f"{where}: default {default} 大于 maximum {spec.maximum}",
                        path=MANIFEST_NAME, field_name=where)
        if spec.minimum is not None and spec.maximum is not None and spec.minimum >= spec.maximum:
            check.error(f"{where}: minimum 必须小于 maximum", path=MANIFEST_NAME, field_name=where)
        return

    if spec.type == "color":
        if not isinstance(default, str) or not _HEX_COLOR_RE.match(default):
            check.error(
                f"{where}: color 的 default 必须是 #rgb / #rrggbb / #rrggbbaa",
                path=MANIFEST_NAME,
                field_name=where,
            )
        return

    if spec.type == "select":
        if not spec.options:
            check.error(f"{where}: select 必须提供 options", path=MANIFEST_NAME, field_name=where)
            return
        if default not in spec.options:
            check.error(
                f"{where}: default 必须是 options 之一（{list(spec.options)}），当前是 {default!r}",
                path=MANIFEST_NAME,
                field_name=where,
            )
        return

    if spec.type == "image":
        if default in (None, ""):
            return
        if not isinstance(default, str):
            check.error(f"{where}: image 的 default 必须是 URL 字符串", path=MANIFEST_NAME, field_name=where)
        elif not default.startswith(("http://", "https://", "/")):
            check.error(
                f"{where}: image 的 default 必须是 http(s) 或站内绝对路径，当前是 {default!r}",
                path=MANIFEST_NAME,
                field_name=where,
            )
        return

    # text / textarea
    if default is not None and not isinstance(default, str):
        check.error(f"{where}: {spec.type} 的 default 必须是字符串", path=MANIFEST_NAME, field_name=where)


# ---------------------------------------------------------------- 包校验


def _looks_like_attachment(path: str) -> bool:
    return any(path.endswith(p) or path.startswith(p) for p in _ATTACHMENT_PATTERNS)


def validate_package(
    raw_files: dict[str, str],
    *,
    expected_key: str | None = None,
    require_manifest: bool = False,
) -> PackageCheck:
    """校验一个已解压的主题包。

    ``raw_files`` 是 {包内路径: 文本内容}，由调用方负责解 zip 与体积闸
    （``templates_import`` 和商店提交共用本函数，只是解包来源不同）。

    返回的 ``files`` 是**已通过校验、可以落库**的文件集合；``errors`` 非空
    就必须整体拒绝 —— 半套主题装进去比装不上更糟，线上会白屏。
    """
    from cenkor_admin.core import jinja_env

    check = PackageCheck(ok=False, manifest=None)

    if not raw_files:
        check.error("主题包里没有任何文件")
        return check

    if len(raw_files) > MAX_PACKAGE_FILES:
        check.error(f"文件数上限 {MAX_PACKAGE_FILES}，当前 {len(raw_files)}")
        return check

    manifest_src = raw_files.get(MANIFEST_NAME)
    if manifest_src is None:
        if require_manifest:
            check.error(
                f"缺少 {MANIFEST_NAME}。一份可分发的主题包必须有清单（版本、作者、设置项）",
                path=MANIFEST_NAME,
            )
            return check
        legacy_key = expected_key or ""
        check.legacy = True
        check.warn(
            f"包内没有 {MANIFEST_NAME}，按旧版导出包处理。建议补上清单："
            "没有版本号就无法做更新检测，没有 settings 站长改不了色值",
            path=MANIFEST_NAME,
        )
        try:
            check.manifest = manifest_from_json(
                {"schema_version": SCHEMA_VERSION, "key": legacy_key, "name": legacy_key or "未命名主题",
                 "_legacy": True},
                legacy_key=legacy_key,
            )
        except ValueError as exc:  # pragma: no cover - 兜底
            check.error(str(exc), path=MANIFEST_NAME)
            return check
    else:
        try:
            check.manifest = manifest_from_json(manifest_src, legacy_key=expected_key)
        except ValueError as exc:
            check.error(str(exc), path=MANIFEST_NAME)
            return check
        _check_manifest(check.manifest, check)

    accepted: dict[str, str] = {}
    total_bytes = 0
    for path, content in raw_files.items():
        norm = path.replace("\\", "/")
        if _looks_like_attachment(norm):
            continue
        if not jinja_env.is_safe_template_name(norm):
            check.error("路径非法或扩展名不在白名单", path=norm)
            continue
        size = len(content.encode("utf-8"))
        total_bytes += size
        if size > MAX_FILE_BYTES:
            check.error(f"单文件超过 {MAX_FILE_BYTES // 1024}KB", path=norm)
            continue
        ext = os.path.splitext(norm)[1].lower()
        if ext in (".html", ".xml"):
            ok, err = jinja_env.validate_theme_source(content, name=norm, path=norm)
            if not ok:
                item = dict(err or {"message": "语法错误"})
                item["path"] = norm
                check.errors.append(item)
                continue
        elif ext == ".js":
            # JS 不跑 CSP 检查（文件里出现 <script> 字样是正常的），
            # 但它的存在必须在 asset_kinds 里声明过
            pass
        accepted[norm] = content

    if total_bytes > MAX_PACKAGE_BYTES:
        check.error(f"包解压后超过 {MAX_PACKAGE_BYTES // 1024 // 1024}MB")

    # ---- asset_kinds 声明与实际文件比对（审核自动化的抓手）
    present_kinds = {kind for kind, ext in _ASSET_KIND_EXT.items()
                     if any(p.endswith(ext) for p in accepted)}
    declared = set(check.manifest.asset_kinds) if check.manifest else set()
    undeclared = present_kinds - declared
    if undeclared:
        check.error(
            f"包里带了 {sorted(undeclared)} 文件，但 requires.asset_kinds 没有声明。"
            "声明是审核放行的依据，漏声明一律拒（等同于隐瞒可执行内容）",
            path=MANIFEST_NAME,
            field_name="requires.asset_kinds",
        )
    missing = declared - present_kinds
    if missing:
        check.warn(
            f"声明了 {sorted(missing)} 但包里没有对应文件",
            path=MANIFEST_NAME,
            field_name="requires.asset_kinds",
        )

    # ---- files 清单与实际内容比对。声明清单是为了让安装器知道该期待哪些文件，
    # 对不上通常意味着打包时漏拷，属于作者自己的坑，先提示不拦。
    if check.manifest and check.manifest.files:
        declared_files = {f.replace("\\", "/") for f in check.manifest.files}
        actual = set(accepted) - {MANIFEST_NAME}
        absent = declared_files - actual
        extra = actual - declared_files
        if absent:
            check.warn(f"files 声明里有 {len(absent)} 个文件包内不存在：{sorted(absent)[:5]}",
                       path=MANIFEST_NAME, field_name="files")
        if extra:
            check.warn(f"包内有 {len(extra)} 个文件未在 files 里声明：{sorted(extra)[:5]}",
                       path=MANIFEST_NAME, field_name="files")

    if not accepted:
        check.error("包内没有可导入的模板文件")

    check.files = accepted
    check.ok = not check.errors
    return check


# ---------------------------------------------------------------- 设置解析


def setting_storage_key(theme_key: str, setting_key: str) -> str:
    """设置值在 ``Site.settings`` 里的扁平 key。"""
    return f"theme.{theme_key}.{setting_key}"


def coerce_setting(value: Any, spec: SettingSpec) -> Any:
    """把存下来的原始值转成声明类型。转不了就返回原值，让模板自己兜底。

    刻意不做严格拒绝：站长手改 DB、或模板改了类型后老值还在，这两种情况
    都会出现。渲染时因为一个色值不合法而整页 500，是最不该发生的失败。
    """
    if value is None:
        return spec.default

    if spec.type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    if spec.type in ("number", "range"):
        try:
            num = float(value)
        except (TypeError, ValueError):
            return spec.default
        if spec.minimum is not None:
            num = max(num, spec.minimum)
        if spec.maximum is not None:
            num = min(num, spec.maximum)
        # 整数就别显示成 1.0
        return int(num) if num.is_integer() else num

    if spec.type == "color":
        return value if isinstance(value, str) and _HEX_COLOR_RE.match(value) else spec.default

    if spec.type == "select":
        return value if value in spec.options else spec.default

    return str(value)


def resolve_settings(manifest: ThemeManifest, site_settings: dict[str, Any] | None) -> dict[str, Any]:
    """清单默认值 + 站点覆盖 → 模板里 ``theme`` 对象的最终内容。"""
    resolved = manifest.defaults()
    if not site_settings:
        return resolved
    for spec in manifest.settings:
        key = setting_storage_key(manifest.key, spec.key)
        if key in site_settings:
            resolved[spec.key] = coerce_setting(site_settings[key], spec)
    return resolved
