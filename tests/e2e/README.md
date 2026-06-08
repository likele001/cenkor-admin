# E2E 测试（Playwright）

## 关键路径

1. 登录 `admin@cenkor.cn` / `admin123`
2. 创建产品 → 公开 API `/api/v1/public/site` 可见新产品
3. 编辑站点配置 → 公开 API `site_config` 更新

## 运行（待接入 CI）

```bash
# 需先启动 docker compose 并完成 seed
cd tests/e2e
npm init -y && npx playwright install
npx playwright test
```

当前为手工验证清单；CI 集成见 `.github/workflows/ci.yml` integration job。
