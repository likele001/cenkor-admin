# 参与贡献

感谢你愿意把改动提回来。这个项目的核心平台以 MIT 开源，你可以自由 fork 自用；
如果改动对别人也有用，欢迎提 PR。

本文只写**提交前必须知道的硬约束**。深入细节都在 `docs/` 里，正文末尾给了索引，不在这里重复抄一遍。

---

## 一、先确认你要改的是哪一层

| 你想做的事 | 位置 | 能否提 PR |
|---|---|---|
| 改核心平台（API、RBAC、内容引擎、CMS、AI、存储…） | `backend/src/cenkor_admin/` | ✅ 欢迎 |
| 改管理后台 / 用户中心 / 官网前端 | `frontend/{admin-web,portal-web,landing-web}/` | ✅ 欢迎 |
| 新增一个应用（App） | `backend/src/cenkor_admin/apps/<key>/` | ✅ 欢迎，用生成器起步 |
| 新增存储驱动、登录方式、通知渠道 | 对应 app 的 `drivers/`、`providers/` | ✅ 欢迎，这类扩展最容易合并 |
| 改 ERP / CRM / MES / 支付 / 开发者门户 | — | ❌ **不在本仓库内** |

最后一行不是态度问题，是事实：那些目录在 `.gitignore` 里，公开仓库中没有它们的代码，
你也看不到。如果你拿到的是混合部署包，请只提交 `git status` 能看到的文件。

> **一个容易踩的坑**：改核心的 App 契约（`apps/base.py` 的 `AppManifest` 字段、
> hook 签名、权限码注册机制）会影响到**仓库外的商业应用**。这类改动请在 PR 里
> 单独说明「对既有 app 的兼容性影响」，必要时加默认值保持向后兼容。

---

## 二、开发环境

要求：**Python 3.11+**、**Node 20+**、PostgreSQL 16、Redis 7（对象存储可选）。

```bash
cp .env.example .env          # 填 DB / Redis / 对象存储等配置
docker compose up -d          # 一键起全套（后端 --reload + 前端 dev server）
```

不想用 Docker 时，后端和前端可以各自单跑：

```bash
# 后端
cd backend
pip install -r requirements.txt
PYTHONPATH=src uvicorn cenkor_admin.main:app --reload --port 8002

# 前端（另开终端）
cd frontend/admin-web
npm install
npm run dev                   # 默认 5173；用户中心在 portal-web，默认 5175
```

后端启动时 lifespan 会自动执行 `alembic upgrade heads` 建表，**一般不需要手动跑迁移**。
种子数据：`python -m cenkor_admin.scripts.seed`（未设 `CENKOR_ADMIN_PASSWORD` 时随机生成口令，
只打印一次）。

> **版本号唯一来源是 `backend/src/cenkor_admin/VERSION`。**
> `backend/pyproject.toml` 里的 `version` 字段不参与发版流程，贡献时不用改它。

---

## 三、提交前必须过的门禁

下面每一条都对应 CI 里的一个步骤，本地跑一遍能省一轮往返：

```bash
# 1) 依赖声明自洽
pip check

# 2) 代码风格（line-length=100，target py311）
cd backend && ruff check .

# 3) 迁移图：无断链、单 head
python3 scripts/check-migration-graph.py --tracked-only

# 4) 迁移能真跑通
cd backend && alembic upgrade heads

# 5) ORM ↔ 迁移对账（最容易漏，见第四节）
cd backend && PYTHONPATH=src python3 ../scripts/check-orm-drift.py --strict

# 6) 单元测试（CI 跑的就是这批）
cd backend && PYTHONPATH=src python -m pytest tests/ -q \
  --ignore=tests/test_auth.py \
  --ignore=tests/test_cms.py \
  --ignore=tests/test_content_engine.py \
  --ignore=tests/test_notification.py \
  --ignore=tests/test_portal.py \
  --ignore=tests/test_rbac.py

# 7) 前端类型检查与构建
cd frontend/admin-web && npm run type-check && npm run build
```

补充两点：

- **集成测试**（上面 `--ignore` 的 6 个文件）需要真实的 `uvicorn:8002` + 种子数据，
  本地不具备时会 skip 或报错，**属于正常**，不用为它改测试。
- `mypy src/ --ignore-missing-imports` 在 CI 里是 `|| true`（不阻断），
  但请不要**新增**类型错误。

---

## 四、动数据库迁移是最容易出错的地方

改动涉及 `models` 时，**必须同时有一条建表 / 加列的迁移**。否则：

- `alembic` 不会报错
- 单元测试也测不到
- 只有第 5 步那个「ORM ↔ 迁移对账」会红

这个检查不是形式主义：历史上出现过两次「ORM 有表 / 有列、迁移没建」的缺口
（12 张 AI 表、6 张 CMS 表 + 18 个字段），都是它抓出来的。

迁移相关的硬规则（放哪个目录、`down_revision` 指向哪个 head、挂载点顺延、
`upgrade`/`downgrade` 都要写、revision 字符串长度等）请直接读：

- [`docs/migrations.md`](docs/migrations.md) —— 迁移规则权威文档
- [`docs/database-migrations.md`](docs/database-migrations.md) §12.1 —— 提交 PR 前的勾选清单

---

## 五、提交信息

用 **Conventional Commits + 中文描述**：`type(scope): 说明`。

取自本仓库的真实提交示例：

```
fix(auth): bcrypt 4.1+ 兼容——口令上下文收敛到 core/pwd 并放宽依赖约束
deps(s3): 拆掉 boto3 僵尸声明，S3 链路升到 aiobotocore 2.26，pip check 归零
docs(architecture): 更新密码哈希说明——bcrypt 4.1+ 兼容与唯一入口 core/pwd.py
feat(apps): 产品核心能力归入底座，内置清单 6 个
refactor(sso): 统一登录归入底座能力，应用中心不可卸载
ci: 依赖门禁——CI 加 pip check，upgrade.sh 加依赖快照与对账
```

三条要求：

1. **一个提交只做一件事。** 逻辑改动和格式化改动分开，否则 review 时真正的改动会被淹没。
2. **别整文件改写行尾。** 仓库里有部分文件是 CRLF（历史原因），把你的编辑器设成
   「保留原有行尾」，否则一个改 3 行的提交会变成 2000 行 diff。
3. 正文里说清**为什么**改。只写「修复 bug」等于没写。

---

## 六、PR

- 从 `main` 开分支，PR 目标也是 `main`（CI 同时监听 `develop`、`feat/**` 的 push）
- 描述里写四件事：**改了什么、为什么、怎么验证的、有没有兼容性影响**
- CI 必须全绿
- 涉及界面的改动请附截图或录屏

---

## 七、贡献的授权

提交 PR 即表示你确认两件事：

1. 该贡献由你原创，或你有权按本项目的许可证提交；
2. **你同意该贡献按 MIT License 授权**，与其他代码同等对待（即 inbound = outbound）。

项目的核心平台以 MIT 开源。**商业应用**（ERP / CRM / MES / 支付 / 开发者门户）
作为独立产品单独授权，不在本仓库内、不适用本许可 —— 这是产品边界，不是授权限制。

本项目**不要求签署 CLA**（贡献者许可协议）：上面两条确认就够了。

---

## 八、不要提交这些

| 禁止 | 原因 |
|---|---|
| `.env`、`*.pem`、`*.key`、真实口令 / Token | 一旦进历史就再也删不干净，只能全链重写 |
| 生产数据导出、真实用户信息、客户名单 | 隐私与合规 |
| 构建产物（`dist/`、`node_modules/`） | 已在 `.gitignore` 里，不需要你手动处理 |
| 仓库外商业应用的代码 | 即使在你本地目录里，也会被忽略；提交前看一眼 `git status` |
| 无关的格式化 / import 重排 | 制造 review 噪音 |

如果不小心提交了密钥：**先当它已经泄漏**，立刻轮换该凭据，再来处理 git 历史。

---

## 九、文档从哪看

| 文档 | 内容 |
|---|---|
| [`docs/index.md`](docs/index.md) | 文档总索引（推荐从这里进） |
| [`docs/dev_guide.md`](docs/dev_guide.md) | 开发者指南：五分钟起一个 App、manifest 全字段、前端插件机制、模板标签 |
| [`docs/apps/development_guide.md`](docs/apps/development_guide.md) | 应用开发规范：结构 / 字段类型 / 路由 / 迁移 / 打包 / 安全 |
| [`docs/migrations.md`](docs/migrations.md) | 数据库迁移规则 |
| [`architecture.md`](architecture.md) | 架构设计（内容引擎 / 双用户体系 / 模板引擎 / App 中心 / 安全） |
| [`docs/packaging.md`](docs/packaging.md) | 打包交付 |

遇到问题请开 issue，并附上：**版本号**（`GET /api/health` 返回的 `version`）、
复现步骤、相关日志片段。
