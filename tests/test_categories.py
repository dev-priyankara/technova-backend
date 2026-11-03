import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.admin import User
from app.security import require_admin


class CategoryApiTests(unittest.TestCase):

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

    def create_category(self, name="Graphics Cards", **fields):
        response = self.client.post(
            "/api/categories",
            json={"name": name, **fields},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_create_list_and_read_categories_with_product_counts(self):
        category = self.create_category(
            description="GPU catalogue",
        )
        for sku in ("GPU-001", "GPU-002"):
            product = self.client.post(
                "/api/products",
                json={
                    "name": f"Graphics Card {sku}",
                    "category_id": category["id"],
                    "sku": sku,
                    "price": 100,
                },
            )
            self.assertEqual(product.status_code, 201, product.text)

        self.assertEqual(category["slug"], "graphics-cards")
        self.assertEqual(category["description"], "GPU catalogue")

        listed = self.client.get("/api/categories")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["item_count"], 2)

        fetched = self.client.get(f"/api/categories/{category['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["slug"], "graphics-cards")
        self.assertEqual(fetched.json()["item_count"], 2)

    def test_slug_conflicts_and_auto_generated_unique_slugs(self):
        first = self.create_category("Wi-Fi Routers")
        second = self.create_category("Wi Fi Routers")

        self.assertEqual(first["slug"], "wi-fi-routers")
        self.assertEqual(second["slug"], "wi-fi-routers-2")

        duplicate_slug = self.client.post(
            "/api/categories",
            json={"name": "Network Gear", "slug": first["slug"]},
        )
        self.assertEqual(duplicate_slug.status_code, 409)

    def test_patch_updates_name_slug_and_description(self):
        category = self.create_category()

        response = self.client.patch(
            f"/api/categories/{category['id']}",
            json={
                "name": "Video Cards",
                "slug": "video-cards",
                "description": "Updated description",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "Video Cards")
        self.assertEqual(response.json()["slug"], "video-cards")
        self.assertEqual(response.json()["description"], "Updated description")

        duplicate_name = self.client.patch(
            f"/api/categories/{category['id']}",
            json={"name": "Video Cards"},
        )
        self.assertEqual(duplicate_name.status_code, 200)

    def test_validation_duplicate_names_and_not_found(self):
        category = self.create_category()
        self.create_category("Processors")

        duplicate_name = self.client.post(
            "/api/categories",
            json={"name": "Graphics Cards"},
        )
        self.assertEqual(duplicate_name.status_code, 409)

        duplicate_update = self.client.patch(
            f"/api/categories/{category['id']}",
            json={"name": "Processors"},
        )
        self.assertEqual(duplicate_update.status_code, 409)

        empty_update = self.client.patch(
            f"/api/categories/{category['id']}",
            json={},
        )
        self.assertEqual(empty_update.status_code, 400)
        self.assertEqual(self.client.get("/api/categories/999").status_code, 404)
        self.assertEqual(self.client.delete("/api/categories/999").status_code, 404)

    def test_delete_category(self):
        category = self.create_category()

        response = self.client.delete(f"/api/categories/{category['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["category_id"], category["id"])
        self.assertEqual(self.client.get("/api/categories").json(), [])
