"""ERP App manifest — 注册到 cenkor-admin 应用中心"""
from __future__ import annotations

from cenkor_admin.apps.base import AppManifest


MANIFEST = AppManifest(
    key="erp",
    name="ERP管理系统",
    version="1.0.0",
    author="Cenkor Team",
    description=(
        "客户/供应商/商品/采购/销售/仓库/财务 一体化业务应用。"
        "全新设计 26 张表 + 39 个 API + 9 个前端页面。"
    ),
    icon="📊",
    category="business",
    min_platform_version="0.1.0",
    dependencies=[],
    permissions_required=[
        # 客户管理
        "erp:customer:read",
        "erp:customer:write",
        "erp:customer:delete",
        # 供应商 + 商品
        "erp:supplier:read",
        "erp:supplier:write",
        "erp:product:read",
        "erp:product:write",
        # 销售订单
        "erp:quotation:read",
        "erp:quotation:write",
        "erp:sales_order:read",
        "erp:sales_order:write",
        "erp:sales_order:confirm",
        # 采购
        "erp:purchase:read",
        "erp:purchase:write",
        # 仓库
        "erp:warehouse:read",
        "erp:warehouse:write",
        # 财务
        "erp:finance:read",
        "erp:finance:write",
        # 管理
        "erp:admin",
    ],
    menus=[
        {
            "key": "erp",
            "title": "ERP 管理",
            "icon": "calculator",
            "sort": 50,
            "children": [
                {"key": "erp:customer",   "title": "客户管理",   "path": "/erp/customers",      "icon": "user"},
                {"key": "erp:supplier",   "title": "供应商",     "path": "/erp/suppliers",      "icon": "office-building"},
                {"key": "erp:product",    "title": "商品",       "path": "/erp/products",       "icon": "goods"},
                {"key": "erp:sales",      "title": "销售订单",   "path": "/erp/sales-orders",   "icon": "document"},
                {"key": "erp:purchase",   "title": "采购订单",   "path": "/erp/purchase-orders","icon": "shopping-cart"},
                {"key": "erp:warehouse",  "title": "仓库",       "path": "/erp/warehouses",     "icon": "box"},
                {"key": "erp:finance",    "title": "财务",       "path": "/erp/finance",        "icon": "money"},
            ],
        },
    ],
    content_types=[],  # 本期不引入 CMS 引擎，主数据全部走自建表
    field_definitions=[],
    field_groups=[],
    categories_seed=[],
    public_routes_prefix="/api/v1/erp",
    hooks=[
        # 预留：后期接 customer.on_change 之类的事件钩子
        # "cenkor_admin.apps.erp.hooks",
    ],
)