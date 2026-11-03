import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.admin import InventoryTransaction, Role, User
from app.models.product import Product
from app.security import hash_password, require_admin, require_authenticated_user


class AuthenticationApiTests(unittest.TestCase):

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
        with self.session_factory() as db:
            db.add_all(
                [
                    Role(id=1, name="Admin"),
                    Role(id=2, name="Supplier"),
                    Role(id=3, name="Cashier"),
                    Role(id=4, name="Customer"),
                ]
            )
            db.add(
                Product(
                    name="RTX Graphics Card",
                    sku="GPU-001",
                    price=100,
                    cost_price=75,
                    stock_count=3,
                    min_stock_level=1,
                )
            )
            db.commit()

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(require_authenticated_user, None)
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def override_get_db(self):
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def register_customer(self):
        return self.client.post(
            "/api/auth/register",
            json={
                "name": "Customer One",
                "email": "customer@example.com",
                "phone": "0771234567",
                "password": "SafePassword123",
            },
        )

    def test_customer_registration_login_csrf_and_logout(self):
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        registered = self.register_customer()
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertEqual(registered.json()["role"], "Customer")
        self.assertNotIn("access_token", registered.json())
        self.assertIn("httponly", registered.headers["set-cookie"].lower())
        self.assertEqual(
            self.client.get("/api/auth/profile").json()["email"],
            "customer@example.com",
        )

        rejected = self.client.put(
            "/api/auth/profile",
            json={"name": "Customer One", "phone": "", "city": "Kandy"},
        )
        self.assertEqual(rejected.status_code, 403)

        profile = self.client.put(
            "/api/auth/profile",
            headers={"X-Requested-With": "TECHNOVA"},
            json={
                "name": "Updated Customer",
                "phone": "0710000000",
                "street": "Main Street",
                "city": "Kandy",
                "postal_code": "20000",
            },
        )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["name"], "Updated Customer")

        logged_out = self.client.post(
            "/api/auth/logout",
            headers={"X-Requested-With": "TECHNOVA"},
        )
        self.assertEqual(logged_out.status_code, 200, logged_out.text)
        self.assertEqual(self.client.get("/api/orders").status_code, 401)

        logged_in = self.client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "SafePassword123"},
        )
        self.assertEqual(logged_in.status_code, 200, logged_in.text)
        self.assertEqual(logged_in.json()["name"], "Updated Customer")

    def test_admin_routes_require_admin_and_customer_cannot_access_them(self):
        self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/products",
                headers={"X-Requested-With": "TECHNOVA"},
                json={
                    "name": "Unauthorized Product",
                    "sku": "NO-AUTH",
                    "price": 100,
                },
            ).status_code,
            401,
        )

        self.assertEqual(self.register_customer().status_code, 201)
        self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 403)
        self.assertEqual(self.client.get("/api/users").status_code, 403)

    def test_admin_login_grants_admin_routes(self):
        with self.session_factory() as db:
            db.add(
                User(
                    role_id=1,
                    name="Admin One",
                    email="admin@example.com",
                    password_hash=hash_password("AdminPassword123"),
                )
            )
            db.commit()

        login = self.client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "AdminPassword123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["role"], "Admin")
        self.assertEqual(self.client.get("/api/admin/profile").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 200)

    def test_customer_order_uses_database_price_and_updates_stock(self):
        registered = self.register_customer()
        self.assertEqual(registered.status_code, 201, registered.text)
        order = self.client.post(
            "/api/orders",
            headers={"X-Requested-With": "TECHNOVA"},
            json={
                "payment_method": "PayHere",
                "shipping_address": {
                    "recipient_name": "Spoofed Name",
                    "phone": "000",
                    "street": "Delivery Street",
                    "city": "Colombo",
                },
                "items": [{"product_id": 1, "quantity": 2}],
            },
        )
        self.assertEqual(order.status_code, 201, order.text)
        payload = order.json()
        self.assertEqual(float(payload["total"]), 1700)
        self.assertEqual(payload["payment_status"], "Pending")
        self.assertEqual(payload["recipient_name"], "Customer One")

        with self.session_factory() as db:
            product = db.get(Product, 1)
            self.assertEqual(product.stock_count, 1)
            transaction = db.scalar(select(InventoryTransaction))
            self.assertEqual(transaction.change_qty, -2)
            self.assertEqual(transaction.reason, "Order sale")

        self.assertEqual(len(self.client.get("/api/orders").json()), 1)
        self.assertEqual(
            self.client.get(f"/api/orders/{payload['id']}").status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
