# ERP App 开发文档

> **App key**：`erp`
> **版本**：1.0.0
> **基础结构**：`cenkor_admin/apps/erp/`
> **机制**：基于 cenkor-admin 应用中心，manifest.py 声明式注册，可装可卸
> **状态**：Phase 1 脚手架已完成，后续 Phase 按计划推进

---

## 一、目录结构

```
apps/erp/
├── __init__.py                  # 包标识
├── manifest.py                  # 应用清单（核心）
├── alembic/
│   └── versions/
│       └── 20260831_0001_erp_init.py   # 建表迁移（Phase 1 已完成）
├── scripts/
│   ├── build.sh                 # ZIP 打包（路径 B）
│   ├── install.sh               # 本地安装（路径 A）
│   └── dev.sh                   # 开发命令（backend/frontend/migrate）
├── frontend/
│   ├── src/                     # 源代码（待 Phase 7 写入）
│   │   ├── views/
│   │   ├── components/
│   │   └── locales/
│   └── dist/                    # 构建产物（plugin.js）— 待生成
├── docs/
│   └── DEVELOPMENT.md           # 本文档
├── release/                     # ZIP 打包产物目录
└── tests/                       # 测试用例（待写）
```

---

## 二、两种部署路径

### 路径 A：内置（**本地开发用**）

直接修改 `apps/erp/` 下文件，重启后端即可被应用中心自动扫描。

```bash
# 软链到内置 apps 目录（推荐）
bash scripts/install.sh symlink

# 或复制
bash scripts/install.sh copy

# 重启后端
docker compose restart backend
# 或 systemctl restart cenkor-backend
```

### 路径 B：ZIP 打包 + 商店安装（**生产发布用**）

```bash
# 1. 前端构建
cd apps/erp/frontend && npm run build

# 2. 打 ZIP
bash scripts/build.sh 1.0.0
# 产物: release/erp-1.0.0.zip

# 3. 上传到开发者门户
# https://dev.cenkor.cn/ → 提交审核

# 4. 后台审核 → 一键安装
# 应用中心 → 待审核 → 通过 → 自动安装
```

---

## 三、Phase 进度

| Phase | 任务 | 状态 | 完成日期 |
|---|---|---|---|
| **Phase 1** | 脚手架 + alembic init + 脚本 | ✅ 已完成 | 2026-08-31 |
| Phase 2 | 客户管理（6 表 + 5 API） | 🔜 待开始 | - |
| Phase 3 | 供应商 + 商品（4 表 + 10 API） | ⏸ 等待 | - |
| Phase 4 | 销售订单（5 表 + 8 API） | ⏸ 等待 | - |
| Phase 5 | 采购 + 仓库（6 表 + 8 API） | ⏸ 等待 | - |
| Phase 6 | 财务（5 表 + 8 API） | ⏸ 等待 | - |
| Phase 7 | 前端（9 页面 + Vite library） | ⏸ 等待 | - |
| Phase 8 | ZIP 打包 + 商店发布 | ⏸ 等待 | - |

---

## 四、Phase 1 已完成内容

### 4.1 manifest.py

- ✅ App key `erp`
- ✅ 20 个 RBAC 权限点
- ✅ 7 个菜单（客户/供应商/商品/销售订单/采购订单/仓库/财务）
- ✅ category=business
- ✅ public_routes_prefix=/api/v1/erp
- ✅ author/icon/version 齐全

### 4.2 alembic 初始迁移

- ✅ 6 张表：
  - `erp_customers`（客户主数据）
  - `erp_customer_contacts`（客户联系人）
  - `erp_customer_addresses`（客户多地址）
  - `erp_follow_ups`（跟进记录）
  - `erp_attachments`（附件）
  - 暂未建：erp_customer_tags（Phase 2 视情况补）

- ✅ 索引：name / owner / customer_id / business_type+business_id

### 4.3 脚本

- ✅ `scripts/build.sh`：ZIP 打包（路径 B）
- ✅ `scripts/install.sh`：本地安装（路径 A）
- ✅ `scripts/dev.sh`：开发命令

---

## 五、Phase 2 待做：客户管理（5 个 API）

### 5.1 后端文件结构（待创建）

```
apps/erp/
├── models/
│   ├── __init__.py
│   └── customer.py           # ErpCustomer / ErpCustomerContact / ErpCustomerAddress / ErpFollowUp
├── schemas/
│   ├── __init__.py
│   └── customer.py           # Pydantic DTO
├── crud/
│   ├── __init__.py
│   └── customer.py           # 数据库操作
└── router/
    ├── __init__.py
    └── customer.py           # 5 个 API
```

### 5.2 5 个 API（待实现）

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/api/v1/erp/customers` | erp:customer:read |
| GET | `/api/v1/erp/customers/{id}` | erp:customer:read |
| POST | `/api/v1/erp/customers` | erp:customer:write |
| PUT | `/api/v1/erp/customers/{id}` | erp:customer:write |
| DELETE | `/api/v1/erp/customers/{id}` | erp:customer:delete |

### 5.3 模板参考

- **后端路由风格**：参考 `apps/tickets/router.py`（247 行）
- **模型风格**：参考 `apps/tickets/models.py`
- **权限注入**：`from cenkor_admin.api.deps import require_permission`

### 5.4 验收标准

```bash
# 重启后端
docker compose restart backend

# 应用中心能看到 erp App（待 Phase 1 验证）
# 点安装 → 自动建表
# curl 验证 API:
curl -X POST http://localhost:8001/api/v1/erp/customers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"C001","name":"测试客户"}'

# 返回 {"id":1, ...}
```

---

## 六、调试技巧

### 6.1 重启后端（最快验证）

```bash
docker compose restart backend
# 等待 5-10 秒
curl http://localhost:8001/api/v1/system/apps | jq '.items[] | select(.key=="erp")'
```

### 6.2 查看 App 注册日志

```bash
docker compose logs -f backend | grep -i 'erp\|app.*scan\|manifest'
```

### 6.3 单独跑迁移（不走自动安装）

```bash
cd /www/wwwroot/cenkor-admin/backend
alembic upgrade head
# 验证表已建:
docker compose exec postgres psql -U cenkor -d cenkor -c '\dt erp_*'
```

---

## 七、Phase 8 商店发布流程（预留）

### 7.1 注册开发者

访问 https://dev.cenkor.cn/ → 注册 → 等待审核

### 7.2 提交 ZIP

```bash
# 1) 准备 release/erp-1.0.0.zip
bash scripts/build.sh 1.0.0

# 2) 登录 dev.cenkor.cn → 我的应用 → 提交应用
# 上传 zip，填写 manifest 信息
```

### 7.3 后台审核 + 安装

```
1. 应用中心 → 商店 tab → 找到 erp-1.0.0
2. 点击「通过审核」
3. 点击「安装到平台」
4. 系统自动：
   - 解压 ZIP 到 backend/src/apps/erp/
   - 复制 frontend/dist/ 到 static/apps/erp/
   - 复制 alembic 到 alembic/versions/
   - 执行 alembic upgrade head
   - 写 InstalledApp 表
   - 注册权限点
5. 后端重启 → PluginManager 自动加载 plugin.js
6. admin-web 自动出现 ERP 菜单
```

---

## 八、依赖与兼容性

### 8.1 cenkor-admin 版本

- min_platform_version: 0.1.0
- 要求：manifest.py 支持 public_routes_prefix / hooks（V2 特性）
- 当前 dev 环境：cenkor-admin 主分支，应该兼容

### 8.2 数据库

- 默认 PostgreSQL 16（cenkor-admin 默认）
- 兼容 MySQL 5.7+（cenkormes 用 MySQL，但本 App 在 cenkor-admin 内部用 PG）

### 8.3 Python 依赖

- 无新增第三方依赖（用平台已装的 FastAPI / SQLAlchemy / Pydantic）

---

## 九、变更记录

| 日期 | 版本 | 变更 | 作者 |
|---|---|---|---|
| 2026-08-31 | 1.0.0 | Phase 1 脚手架 | AI 助理 |
| TBD | 1.0.0 | Phase 2 客户管理 | - |
| TBD | 1.0.0 | Phase 3 供应商商品 | - |
| TBD | 1.0.0 | Phase 4 销售订单 | - |
| TBD | 1.0.0 | Phase 5 采购仓库 | - |
| TBD | 1.0.0 | Phase 6 财务 | - |
| TBD | 1.0.0 | Phase 7 前端 | - |
| TBD | 1.0.0 | Phase 8 ZIP 发布 | - |