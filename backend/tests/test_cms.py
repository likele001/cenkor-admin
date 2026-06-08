import time
"""CMS 模块测试"""


def test_public_site_anonymous(client):
    """公开接口 - 无需鉴权"""
    r = client.get(f"{client.base_url}/api/v1/public/site")
    assert r.status_code == 200
    data = r.json()
    assert "site_config" in data
    assert "products" in data
    assert "cases" in data
    assert len(data["products"]) >= 7
    flagship = [p for p in data["products"] if p.get("isFlagship")]
    assert any(p["key"] == "plantflow" for p in flagship)


def test_public_products_listing(client):
    r = client.get(f"{client.base_url}/api/v1/public/products")
    assert r.status_code == 200
    products = r.json()
    assert isinstance(products, list)
    assert len(products) >= 7


def test_cms_products_requires_auth(client):
    r = client.get(f"{client.base_url}/api/v1/cms/products")
    assert r.status_code == 401


def test_cms_products_list(client, auth_headers, unique_id):
    r = client.get(f"{client.base_url}/api/v1/cms/products?page_size=50", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 7


def test_cms_product_crud(client, auth_headers, unique_id):
    """产品 CRUD 全流程"""
    # Create
    r = client.post(
        f"{client.base_url}/api/v1/cms/products",
        headers=auth_headers,
        json={
            "slug": f"test-product-{unique_id}",
            "name": "Test Product",
            "tagline": "Test tagline",
            "line": "enterprise",
            "stack": "Test stack",
            "desc": "Test desc",
            "features": ["feature 1", "feature 2"],
            "isFlagship": False, "isOpenSource": False,
            "github": None, "demo": None, "license": None,
            "sort": 99, "status": "published",
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    # Read
    r = client.get(f"{client.base_url}/api/v1/cms/products/{pid}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Test Product"

    # Update
    r = client.patch(
        f"{client.base_url}/api/v1/cms/products/{pid}",
        headers=auth_headers,
        json={"name": "Test Product Updated"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Test Product Updated"

    # Delete
    r = client.delete(f"{client.base_url}/api/v1/cms/products/{pid}", headers=auth_headers)
    assert r.status_code == 204

    r = client.get(f"{client.base_url}/api/v1/cms/products/{pid}", headers=auth_headers)
    assert r.status_code == 404


def test_cms_duplicate_slug(client, auth_headers, unique_id):
    """重复 slug 应 409"""
    r = client.post(
        f"{client.base_url}/api/v1/cms/products",
        headers=auth_headers,
        json={
            "slug": "plantflow", "name": "Dup", "tagline": "x",
            "line": "ai", "stack": "x", "desc": "x",
        },
    )
    assert r.status_code == 409


def test_cms_news_crud(client, auth_headers, unique_id):
    """新闻 CRUD"""
    r = client.post(
        f"{client.base_url}/api/v1/cms/news",
        headers=auth_headers,
        json={
            "slug": f"test-news-{unique_id}", "title": "Test News",
            "excerpt": "x", "content_md": "x", "status": "published",
        },
    )
    assert r.status_code == 201, r.text
    nid = r.json()["id"]

    r = client.get(f"{client.base_url}/api/v1/cms/news/{nid}", headers=auth_headers)
    assert r.status_code == 200

    r = client.get(f"{client.base_url}/api/v1/public/news?limit=200")
    assert r.status_code == 200
    slugs = [n["slug"] for n in r.json()]
    assert any(s.startswith("test-news-") for s in slugs)

    # Cleanup
    client.delete(f"{client.base_url}/api/v1/cms/news/{nid}", headers=auth_headers)


def test_audit_log_captures_writes(client, auth_headers, unique_id):
    """写操作被审计"""
    # Make a write
    client.post(f"{client.base_url}/api/v1/cms/news", headers=auth_headers, json={
        "slug": f"audit-news-{unique_id}", "title": "Audit",
        "excerpt": "x", "content_md": "x", "status": "draft",
    })

    r = client.get(f"{client.base_url}/api/v1/system/audit?page_size=20", headers=auth_headers)
    assert r.status_code == 200
    paths = [x["path"] for x in r.json()["items"]]
    assert "/api/v1/cms/news" in paths
