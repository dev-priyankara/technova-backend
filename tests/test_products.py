import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.category import Category
from app.models.admin import User
from app.security import require_admin


class ProductApiTests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.client = TestClient(app)
        app.dependency_overrides[get_db] = self.override_get_db
        app.dependency_overrides[require_admin] = self.override_admin

        with self.session_factory() as db:
            category = Category(name="Graphics Cards", slug="graphics-cards")
            db.add(category)
            db.commit()
            db.refresh(category)
            self.category_id = category.id

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_admin, None)
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def override_get_db(self):
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_admin(self):
        return User(
            id=1,
            role_id=1,
            name="Test Admin",
            email="admin@example.com",
            password_hash="test",
            status="Active",
        )

    def create_product(self, sku="GPU-001"):
        response = self.client.post(
            "/api/products",
            json={
                "name": "RTX Graphics Card",
                "category": "Graphics Cards",
                "sku": sku,
                "price": "150000.00",
                "cost_price": "125000.00",
                "stock_count": 8,
                "min_stock_level": 3,
                "specs": ["12GB VRAM", "PCIe 4.0"],
                "description": "Gaming graphics card",
                "warranty": "3 years",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_create_product_uses_master_table_fields_and_category(self):
        product = self.create_product()

        self.assertEqual(product["category_id"], self.category_id)
        self.assertEqual(product["category"], "Graphics Cards")
        self.assertEqual(product["category_name"], "Graphics Cards")
        self.assertEqual(product["specs"], ["12GB VRAM", "PCIe 4.0"])
        self.assertTrue(product["in_stock"])

    def test_list_search_filter_and_get_product(self):
        product = self.create_product()
        self.create_product("GPU-002")

        listed = self.client.get(
            "/api/products",
            params={"search": "RTX", "category_id": self.category_id},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 2)

        fetched = self.client.get(f"/api/products/{product['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["sku"], "GPU-001")

    def test_duplicate_sku_and_unknown_category(self):
        self.create_product()
        duplicate = self.client.post(
            "/api/products",
            json={
                "name": "Duplicate SKU",
                "sku": "GPU-001",
                "price": 100,
                "category_id": self.category_id,
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        missing_category = self.client.post(
            "/api/products",
            json={
                "name": "Unknown category product",
                "sku": "GPU-003",
                "price": 100,
                "category_id": 999,
            },
        )
        self.assertEqual(missing_category.status_code, 404)

    def test_update_stock_and_delete_product(self):
        product = self.create_product()

        updated = self.client.patch(
            f"/api/products/{product['id']}",
            json={"stock_count": 4, "price": 155000},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["stock_count"], 4)

        adjusted = self.client.patch(
            f"/api/products/{product['id']}/stock",
            params={"stock_delta": -4},
        )
        self.assertEqual(adjusted.status_code, 200)
        self.assertEqual(adjusted.json()["stock_count"], 0)
        self.assertFalse(adjusted.json()["in_stock"])

        negative_stock = self.client.patch(
            f"/api/products/{product['id']}/stock",
            params={"stock_delta": -1},
        )
        self.assertEqual(negative_stock.status_code, 422)

        deleted = self.client.delete(f"/api/products/{product['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/products").json(), [])
