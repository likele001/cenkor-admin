# 通用 CRUD 运行时插件（runtime_plugin）

这一份源码在平台上只构建 **一次**，产物落到
`backend/src/cenkor_admin/codegen/assets/plugin_head.js`。

每个由「代码生成器」生成的 App 的 `frontend/dist/plugin.js` =
**内嵌该 App 元数据的前言** + **本文件构建出的 bundle**。
因此生成 App 时**零 npm 构建**，所有 App 复用同一份通用 CRUD 运行时。

## 为什么这样做

- 生成的 App 走「开发者中心 / 应用中心」分发，包内必须有 `frontend/dist/plugin.js`。
  若每个 App 都跑一次 `npm install && vite build`（`scripts/package-app.sh` 的做法），
  代价极高且不可控。
- 通用运行时的路由/表格/表单完全由内嵌的 spec 元数据驱动，无需按实体生成前端代码。

## 构建（仅需在插件源码变更时执行一次）

```bash
cd backend/src/cenkor_admin/codegen/runtime_plugin
npm install
npm run build
cp dist/plugin_head.js ../assets/plugin_head.js
```

生成 App 的源码视图（`frontend/src/**`）仍然保留：需要定制某个 App 的界面时，
可以在该 App 的 `frontend/` 下 `npm install && npm run build` 覆写 `dist/plugin.js`。
