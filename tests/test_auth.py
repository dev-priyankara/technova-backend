import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.admin import InventoryTransaction, Role, User
from app.models.product import Product
from app.services.email import EmailConfigurationError
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

    def test_customer_can_update_password_with_confirmation_and_login(self):
        self.assertEqual(self.register_customer().status_code, 201)
        headers = {"X-Requested-With": "TECHNOVA"}

        mismatch = self.client.put(
            "/api/auth/password",
            headers=headers,
            json={
                "new_password": "NewPassword456",
                "confirm_password": "DifferentPassword456",
            },
        )
        self.assertEqual(mismatch.status_code, 422, mismatch.text)

        updated = self.client.put(
            "/api/auth/password",
            headers=headers,
            json={
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        self.client.post("/api/auth/logout", headers=headers)
        old_password_login = self.client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "SafePassword123"},
        )
        self.assertEqual(old_password_login.status_code, 401)

        new_password_login = self.client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "NewPassword456"},
        )
        self.assertEqual(new_password_login.status_code, 200, new_password_login.text)

    def test_customer_can_change_email_and_login_with_new_email(self):
        self.assertEqual(self.register_customer().status_code, 201)
        updated = self.client.put(
            "/api/auth/profile",
            headers={"X-Requested-With": "TECHNOVA"},
            json={
                "name": "Customer One",
                "email": " NewCustomer@example.com ",
                "phone": "0771234567",
                "street": "",
                "city": "",
                "postal_code": "",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["email"], "newcustomer@example.com")
        password_updated = self.client.put(
            "/api/auth/password",
            headers={"X-Requested-With": "TECHNOVA"},
            json={
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            },
        )
        self.assertEqual(password_updated.status_code, 200, password_updated.text)
        self.client.post(
            "/api/auth/logout",
            headers={"X-Requested-With": "TECHNOVA"},
        )

        old_email_login = self.client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "SafePassword123"},
        )
        self.assertEqual(old_email_login.status_code, 401)
        old_password_login = self.client.post(
            "/api/auth/login",
            json={"email": "newcustomer@example.com", "password": "SafePassword123"},
        )
        self.assertEqual(old_password_login.status_code, 401)
        new_email_login = self.client.post(
            "/api/auth/login",
            json={"email": "newcustomer@example.com", "password": "NewPassword456"},
        )
        self.assertEqual(new_email_login.status_code, 200, new_email_login.text)

    def test_password_reset_requires_email_code_and_revokes_sessions(self):
        self.assertEqual(self.register_customer().status_code, 201)

        with patch("app.routers.auth.send_password_reset_email") as send_email:
            requested = self.client.post(
                "/api/auth/password-reset/request",
                json={"email": "CUSTOMER@example.com"},
            )
        self.assertEqual(requested.status_code, 202, requested.text)
        self.assertEqual(
            requested.json()["message"],
            "If that email is registered, a reset code will be sent.",
        )
        code = send_email.call_args.args[2]
        self.assertRegex(code, r"^\d{6}$")
        incorrect_code = f"{(int(code) + 1) % 1_000_000:06d}"

        invalid = self.client.post(
            "/api/auth/password-reset/confirm",
            json={
                "email": "customer@example.com",
                "verification_code": incorrect_code,
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            },
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.client.get("/api/auth/profile").status_code, 200)

        reset = self.client.post(
            "/api/auth/password-reset/confirm",
            json={
                "email": "customer@example.com",
                "verification_code": code,
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            },
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(self.client.get("/api/auth/profile").status_code, 401)

        old_password_login = self.client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "SafePassword123"},
        )
        self.assertEqual(old_password_login.status_code, 401)
        new_password_login = self.client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "NewPassword456"},
        )
        self.assertEqual(new_password_login.status_code, 200, new_password_login.text)

    def test_password_reset_request_does_not_disclose_unknown_email(self):
        with patch("app.routers.auth.send_password_reset_email") as send_email:
            response = self.client.post(
                "/api/auth/password-reset/request",
                json={"email": "unknown@example.com"},
            )
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(
            response.json()["message"],
            "If that email is registered, a reset code will be sent.",
        )
        send_email.assert_not_called()

    def test_password_reset_reports_missing_email_provider_configuration(self):
        self.assertEqual(self.register_customer().status_code, 201)
        with patch(
            "app.routers.auth.send_password_reset_email",
            side_effect=EmailConfigurationError(
                "Password reset email is not configured. Set EMAILJS_SERVICE_ID, "
                "EMAILJS_TEMPLATE_ID, and EMAILJS_PUBLIC_KEY in the backend "
                "environment, or configure SMTP."
            ),
        ):
            response = self.client.post(
                "/api/auth/password-reset/request",
                json={"email": "customer@example.com"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Set EMAILJS_SERVICE_ID", response.json()["detail"])

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
