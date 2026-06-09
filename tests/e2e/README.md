# E2E 测试（Playwright）

## 关键路径

1. 登录 `admin@cenkor.cn` / `admin123`
2. 创建产品 → 公开 API `/api/v1/public/site` 可见新产品
3. 编辑站点配置 → 公开 API `site_config` 更新
4. 创建 API Key → 验证 token 仅展示一次
5. 触发通知创建 → 铃铛角标更新

## 本地运行

```bash
# 1. 启动后端
cd backend
DATABASE_URL=sqlite+aiosqlite:///./e2e.db \
  python -m alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./e2e.db \
  python -m cenkor_admin.scripts.seed
uvicorn cenkor_admin.main:app --port 8000

# 2. 启动 admin-web
cd frontend/admin-web
npm run dev   # http://localhost:5173

# 3. 跑测试
pip install playwright pytest
playwright install chromium
pytest tests/e2e -v
```

## 关键配置

| 环境变量 | 默认值 | 说明 |
|---------|-------|------|
| `E2E_BASE_URL` | `http://localhost:5173` | admin-web 地址 |
| `E2E_API_URL` | `http://localhost:8000` | 后端 API 地址 |
| `E2E_USER` | `admin@cenkor.cn` | 测试账号 |
| `E2E_PASSWORD` | `admin123` | 测试密码 |

## CI 集成（推荐）

见 `.github/workflows/ci.yml`：
- 单元 + 集成测试：每个 PR
- E2E 测试：仅 main 分支 nightly（启动容器慢）

## 当前状态

- ✅ 关键路径脚本 `test_smoke.py` 已实现（登录 + Dashboard 验证）
- ⏳ 完整 5 路径覆盖：下一阶段
- ⏳ 视觉回归：未计划
