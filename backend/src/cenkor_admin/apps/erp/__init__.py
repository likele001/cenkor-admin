"""ERP App

key=erp · 客户/供应商/商品/采购/销售/仓库/财务 一体化

首次安装时由 CENKOR Admin 应用中心扫描并自动注册；新表通过本目录
alembic/versions/ 下的迁移文件创建，前端资源通过 frontend/dist/plugin.js
动态注入到 admin-web。
"""