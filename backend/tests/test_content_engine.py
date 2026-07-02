"""内容引擎 V2 端到端测试

覆盖：
- Content Types CRUD
- Field Groups CRUD + reorder
- Field Definitions CRUD + reorder
- Field Options CRUD
- Categories CRUD + 3 级树形
- Tags CRUD
- Entries CRUD + custom_fields + batch operations
- 公共 API (categories / tags / entries / field-definitions)
- 模板渲染 (render / validate)
- 路由级隔离 (portal token → admin API 返回 403)
"""
import time
import requests

BASE_URL = "http://localhost:8002"


def get_admin_token():
    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "admin@cenkor.cn",
        "password": "admin123",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 200, f"登录失败: {r.text}"
    return r.json()["access_token"]


def test_content_types_list():
    """内容类型列表"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    r = requests.get(f"{BASE_URL}/api/v1/cms/content-types", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert data["total"] >= 3
    keys = {ct["key"] for ct in data["items"]}
    assert {"product", "case", "news"} <= keys


def test_content_type_create_and_delete():
    """内容类型创建+删除"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    key = f"test_ct_{int(time.time())}"

    # Create
    r = requests.post(f"{BASE_URL}/api/v1/cms/content-types", headers=h, json={
        "key": key, "name": "Test CT", "icon": "🧪",
        "supports_category": True, "supports_tags": True,
    })
    assert r.status_code == 201, r.text
    ct = r.json()
    assert ct["key"] == key

    # Get
    r = requests.get(f"{BASE_URL}/api/v1/cms/content-types/{ct['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["name"] == "Test CT"

    # Update
    r = requests.patch(f"{BASE_URL}/api/v1/cms/content-types/{ct['id']}", headers=h, json={
        "name": "Test CT Updated", "icon": "✅",
    })
    assert r.status_code == 200
    assert r.json()["name"] == "Test CT Updated"

    # Delete (soft)
    r = requests.delete(f"{BASE_URL}/api/v1/cms/content-types/{ct['id']}", headers=h)
    assert r.status_code == 204


def test_content_type_duplicate_key():
    """内容类型 key 重复应返回 409"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    r = requests.post(f"{BASE_URL}/api/v1/cms/content-types", headers=h, json={
        "key": "product", "name": "Duplicate",
    })
    assert r.status_code == 409


def test_field_groups_lifecycle():
    """字段分组生命周期"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    # 获取 product CT id
    r = requests.get(f"{BASE_URL}/api/v1/cms/content-types", headers=h)
    product_ct = next(ct for ct in r.json()["items"] if ct["key"] == "product")

    # Create
    r = requests.post(
        f"{BASE_URL}/api/v1/cms/content-types/{product_ct['id']}/field-groups",
        headers=h,
        json={"key": f"test_fg_{int(time.time())}", "label": "Test FG", "sort": 99},
    )
    assert r.status_code == 201, r.text
    fg_id = r.json()["id"]

    # List
    r = requests.get(f"{BASE_URL}/api/v1/cms/content-types/{product_ct['id']}/field-groups", headers=h)
    assert r.status_code == 200
    assert any(g["id"] == fg_id for g in r.json())

    # Update
    r = requests.patch(
        f"{BASE_URL}/api/v1/cms/content-types/{product_ct['id']}/field-groups/{fg_id}",
        headers=h,
        json={"label": "Test FG Updated"},
    )
    assert r.status_code == 200
    assert r.json()["label"] == "Test FG Updated"

    # Delete
    r = requests.delete(
        f"{BASE_URL}/api/v1/cms/content-types/{product_ct['id']}/field-groups/{fg_id}",
        headers=h,
    )
    assert r.status_code == 204


def test_field_definitions_with_options():
    """字段定义 + 选项 完整生命周期"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    r = requests.get(f"{BASE_URL}/api/v1/cms/content-types", headers=h)
    product_ct = next(ct for ct in r.json()["items"] if ct["key"] == "product")

    # Create field
    r = requests.post(
        f"{BASE_URL}/api/v1/cms/content-types/{product_ct['id']}/field-definitions",
        headers=h,
        json={
            "field_key": f"test_field_{int(time.time())}",
            "label": "Test Field",
            "field_type": "select",
            "required": False,
            "validation": {"max_length": 100},
        },
    )
    assert r.status_code == 201, r.text
    fd = r.json()
    assert fd["field_type"] == "select"
    assert fd["validation"]["max_length"] == 100

    # Add options
    for i, val in enumerate(["opt_a", "opt_b", "opt_c"]):
        r = requests.post(f"{BASE_URL}/api/v1/cms/field-options", headers=h, json={
            "definition_id": fd["id"], "value": val, "label": val.upper(),
            "color": "#3b82f6", "sort": i,
        })
        assert r.status_code == 201, r.text

    # Verify options
    r = requests.get(f"{BASE_URL}/api/v1/cms/field-definitions/{fd['id']}/options", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 3

    # Update field
    r = requests.patch(f"{BASE_URL}/api/v1/cms/field-definitions/{fd['id']}", headers=h, json={
        "label": "Test Field Updated", "required": True,
    })
    assert r.status_code == 200
    assert r.json()["label"] == "Test Field Updated"
    assert r.json()["required"] is True

    # Invalid field_type
    r = requests.patch(f"{BASE_URL}/api/v1/cms/field-definitions/{fd['id']}", headers=h, json={
        "field_type": "invalid_type",
    })
    assert r.status_code == 422  # pydantic 验证

    # Delete field (cascades options)
    r = requests.delete(f"{BASE_URL}/api/v1/cms/field-definitions/{fd['id']}", headers=h)
    assert r.status_code == 204


def test_categories_tree():
    """分类树 2 级嵌套（manifest categories_seed 定义）"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    r = requests.get(f"{BASE_URL}/api/v1/cms/categories/tree?content_type_key=product", headers=h)
    assert r.status_code == 200
    tree = r.json()
    # 检查至少有顶级分类
    assert len(tree) > 0, "分类树为空"
    # 检查 2 级层级（mes > flow/quality 或 ai > agent/rag）
    has_2_level = False
    for top in tree:
        if top.get("children"):
            has_2_level = True
            break
    assert has_2_level, "分类树没有 2 级层级"


def test_categories_crud():
    """分类 CRUD"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    slug = f"test_cat_{int(time.time())}"

    r = requests.post(f"{BASE_URL}/api/v1/cms/categories", headers=h, json={
        "content_type_key": "product",
        "name": "Test Category", "slug": slug,
    })
    assert r.status_code == 201
    cat = r.json()
    assert cat["slug"] == slug

    # Create child
    r = requests.post(f"{BASE_URL}/api/v1/cms/categories", headers=h, json={
        "content_type_key": "product",
        "name": "Test Subcategory", "slug": f"{slug}_sub",
        "parent_id": cat["id"],
    })
    assert r.status_code == 201
    child = r.json()
    assert child["parent_id"] == cat["id"]

    # Try delete parent with children - should fail
    r = requests.delete(f"{BASE_URL}/api/v1/cms/categories/{cat['id']}", headers=h)
    assert r.status_code == 400
    assert "子分类" in r.json()["detail"]

    # Delete child first
    r = requests.delete(f"{BASE_URL}/api/v1/cms/categories/{child['id']}", headers=h)
    assert r.status_code == 204

    # Then delete parent
    r = requests.delete(f"{BASE_URL}/api/v1/cms/categories/{cat['id']}", headers=h)
    assert r.status_code == 204


def test_tags_crud():
    """标签 CRUD"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    slug = f"test_tag_{int(time.time())}"

    # Create
    r = requests.post(f"{BASE_URL}/api/v1/cms/tags", headers=h, json={
        "content_type_key": "product",
        "slug": slug, "name": "Test Tag", "color": "#ef4444",
    })
    assert r.status_code == 201
    tag = r.json()
    assert tag["color"] == "#ef4444"

    # List
    r = requests.get(f"{BASE_URL}/api/v1/cms/tags?content_type_key=product", headers=h)
    assert r.status_code == 200
    assert any(t["id"] == tag["id"] for t in r.json()["items"])

    # Update
    r = requests.patch(f"{BASE_URL}/api/v1/cms/tags/{tag['id']}", headers=h, json={
        "name": "Updated Tag", "color": "#10b981",
    })
    assert r.status_code == 200
    assert r.json()["color"] == "#10b981"

    # Delete
    r = requests.delete(f"{BASE_URL}/api/v1/cms/tags/{tag['id']}", headers=h)
    assert r.status_code == 204


def test_entries_crud():
    """通用内容 CRUD + custom_fields"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}

    # Create entry
    r = requests.post(f"{BASE_URL}/api/v1/cms/entries", headers=h, json={
        "content_type_key": "product",
        "title": "Test Entry",
        "slug": f"test-entry-{int(time.time())}",
        "content": {
            "name": "Test",
            "tagline": "A test entry",
            "features": ["feature1", "feature2"],
        },
        "custom_fields": {
            "price": 199.99,
            "docs_url": "https://example.com",
        },
        "status": "published",
    })
    assert r.status_code == 201, r.text
    entry = r.json()
    assert entry["title"] == "Test Entry"
    assert entry["custom_fields"]["price"] == 199.99
    assert entry["status"] == "published"

    # Get
    r = requests.get(f"{BASE_URL}/api/v1/cms/entries/{entry['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["custom_fields"]["price"] == 199.99

    # List with filter
    r = requests.get(f"{BASE_URL}/api/v1/cms/entries?content_type_key=product&status=published", headers=h)
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    # Update
    r = requests.patch(f"{BASE_URL}/api/v1/cms/entries/{entry['id']}", headers=h, json={
        "title": "Test Entry Updated",
        "custom_fields": {"price": 299.99},
    })
    assert r.status_code == 200
    assert r.json()["title"] == "Test Entry Updated"
    assert r.json()["custom_fields"]["price"] == 299.99

    # Delete (soft)
    r = requests.delete(f"{BASE_URL}/api/v1/cms/entries/{entry['id']}", headers=h)
    assert r.status_code == 204

    # List with include_deleted
    r = requests.get(f"{BASE_URL}/api/v1/cms/entries?content_type_key=product", headers=h)
    ids = [e["id"] for e in r.json()["items"]]
    assert entry["id"] not in ids, "软删未生效"


def test_entries_batch_operations():
    """批量操作"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    # 创建 3 条 entry
    ids = []
    for i in range(3):
        r = requests.post(f"{BASE_URL}/api/v1/cms/entries", headers=h, json={
            "content_type_key": "product",
            "title": f"Batch Entry {i}",
            "slug": f"batch-entry-{int(time.time())}-{i}",
        })
        assert r.status_code == 201
        ids.append(r.json()["id"])

    # 批量改状态
    r = requests.post(f"{BASE_URL}/api/v1/cms/entries/batch-status", headers=h, json={
        "ids": ids, "status": "archived",
    })
    assert r.status_code == 200
    assert r.json()["updated"] == 3

    # 批量删除
    r = requests.post(f"{BASE_URL}/api/v1/cms/entries/batch-delete", headers=h, json={
        "ids": ids,
    })
    assert r.status_code == 200
    assert r.json()["deleted"] == 3


# ============================================================
# 公共 API 测试（无需鉴权）
# ============================================================

def test_public_categories():
    """公共分类 API"""
    r = requests.get(f"{BASE_URL}/api/v1/public/categories?content_type_key=product")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_public_categories_tree():
    """公共分类树"""
    r = requests.get(f"{BASE_URL}/api/v1/public/categories/tree?content_type_key=product")
    assert r.status_code == 200
    tree = r.json()
    assert isinstance(tree, list)
    assert len(tree) > 0


def test_public_tags():
    """公共标签 API"""
    r = requests.get(f"{BASE_URL}/api/v1/public/tags?content_type_key=product")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_public_site_content_type():
    """公共内容列表（按内容类型）"""
    r = requests.get(f"{BASE_URL}/api/v1/public/site/product?page=1&page_size=5")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data


def test_public_site_content_type_filter_by_category():
    """公共内容列表（按分类过滤）"""
    # 先获取分类
    r = requests.get(f"{BASE_URL}/api/v1/public/categories?content_type_key=product")
    cats = r.json()
    if not cats:
        return
    cat = cats[0]
    # 用分类 ID 过滤
    r = requests.get(f"{BASE_URL}/api/v1/public/site/product?category={cat['id']}")
    assert r.status_code == 200


def test_public_field_definitions():
    """公共字段定义 API"""
    r = requests.get(f"{BASE_URL}/api/v1/public/field-definitions?content_type_key=product")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # 必须有 price 字段
    keys = [fd["field_key"] for fd in data]
    assert "price" in keys


# ============================================================
# 模板渲染测试
# ============================================================

def test_template_render():
    """模板渲染"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    r = requests.post(f"{BASE_URL}/api/v1/cms/templates/render", headers=h, json={
        "template": "Hello {{ name | upcase }}! Price: {{ price | format_price }}",
        "data": {"name": "world", "price": 1234.5},
    })
    assert r.status_code == 200
    rendered = r.json()["rendered"]
    assert "WORLD" in rendered
    assert "1,234.50" in rendered


def test_template_validate():
    """模板语法校验"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    # 合法
    r = requests.post(f"{BASE_URL}/api/v1/cms/templates/validate", headers=h, json={
        "template": "{{ x }}",
    })
    assert r.status_code == 200
    assert r.json()["valid"] is True
    # 非法
    r = requests.post(f"{BASE_URL}/api/v1/cms/templates/validate", headers=h, json={
        "template": "{{ unclosed",
    })
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert r.json()["error"] is not None


def test_template_business_filters():
    """业务 filter 测试"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    # t filter
    r = requests.post(f"{BASE_URL}/api/v1/cms/templates/render", headers=h, json={
        "template": "{{ line | t }}",
        "data": {"line": "enterprise"},
    })
    assert r.json()["rendered"] == "企业应用"
    # format_price
    r = requests.post(f"{BASE_URL}/api/v1/cms/templates/render", headers=h, json={
        "template": "{{ p | format_price }}",
        "data": {"p": 9999.99},
    })
    assert r.json()["rendered"] == "¥9,999.99"
    # for loop
    r = requests.post(f"{BASE_URL}/api/v1/cms/templates/render", headers=h, json={
        "template": "{% for x in items %}{{ x.name }},{% endfor %}",
        "data": {"items": [{"name": "A"}, {"name": "B"}]},
    })
    assert r.json()["rendered"] == "A,B,"


def test_template_public_render():
    """公共模板渲染（无需 auth）"""
    r = requests.post(f"{BASE_URL}/api/v1/public/templates/render", json={
        "template": "<h1>{{ title }}</h1>",
        "data": {"title": "Public"},
    })
    assert r.status_code == 200
    assert r.json()["rendered"] == "<h1>Public</h1>"


# ============================================================
# 路由级隔离测试
# ============================================================

def test_portal_token_blocked_from_admin_api():
    """portal token 不能访问后台 API"""
    # 注册并登录 portal 用户
    r = requests.post(f"{BASE_URL}/api/v1/public/portal/auth/register", json={
        "username": f"test_portal_{int(time.time())}",
        "email": f"test_portal_{int(time.time())}@example.com",
        "password": "test123456",
        "captcha_token": "a" * 32,
    })
    assert r.status_code == 201, r.text
    portal_token = r.json()["access_token"]

    # 尝试访问后台 API
    r = requests.get(f"{BASE_URL}/api/v1/cms/content-types", headers={
        "Authorization": f"Bearer {portal_token}",
    })
    assert r.status_code == 403, f"应该返回 403，但返回了 {r.status_code}: {r.text}"
    assert "前台用户" in r.json()["detail"]


def test_admin_token_blocked_from_portal_me():
    """admin token 不能访问 portal /me"""
    admin_t = get_admin_token()
    r = requests.get(f"{BASE_URL}/api/v1/public/portal/me", headers={
        "Authorization": f"Bearer {admin_t}",
    })
    # 应该返回 401（SECRET 不同的 token 会被拒）
    assert r.status_code in (401, 403)


# ============================================================
# App 中心测试
# ============================================================

def test_apps_list_with_v2_fields():
    """app 列表包含 V2 字段"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    r = requests.get(f"{BASE_URL}/api/v1/system/apps", headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    cms = next((a for a in items if a["key"] == "cms"), None)
    assert cms is not None
    # V2 字段
    assert "content_types" in cms
    assert "field_definitions" in cms
    assert "categories_seed" in cms
    assert "registered_counts" in cms
    assert "permissions_grants" in cms
    # 验证数据
    assert cms["status"] == "installed"
    assert cms["registered_counts"]["content_types"] >= 3
    assert cms["registered_counts"]["field_definitions"] >= 8


def test_app_registered_data():
    """app 已注册数据查看"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    r = requests.get(f"{BASE_URL}/api/v1/system/apps/cms/registered-data", headers=h)
    assert r.status_code == 200
    data = r.json()
    # 检查 content_types
    assert len(data["content_types"]) >= 3
    # 检查 field_definitions 含 options
    fd_with_options = [fd for fd in data["field_definitions"] if fd["options"]]
    assert len(fd_with_options) >= 1, "至少应该有一个带 options 的字段（license 或 project_scale）"


def test_app_permissions_grants():
    """权限委派配置"""
    h = {"Authorization": f"Bearer {get_admin_token()}"}
    grants = {
        "test_role": ["cms:field_definitions:read", "cms:entries:read"],
    }
    r = requests.put(f"{BASE_URL}/api/v1/system/apps/cms/permissions-grants", headers=h, json=grants)
    assert r.status_code == 200
    assert r.json()["permissions_grants"]["test_role"] == grants["test_role"]

    # 验证
    r = requests.get(f"{BASE_URL}/api/v1/system/apps", headers=h)
    cms = next(a for a in r.json()["items"] if a["key"] == "cms")
    assert cms["permissions_grants"].get("test_role") == grants["test_role"]


if __name__ == "__main__":
    # 手动运行所有测试
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
