import unittest

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.admin import Role, User
from app.models.category import Category
from app.security import require_admin, require_order_access


class AdminApiTests(unittest.TestCase):

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
        app.dependency_overrides[require_order_access] = self.override_admin
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
                User(
                    role_id=1,
                    name="Admin User",
                    email="admin@example.com",
                    password_hash="not-a-valid-password-hash",
                )
            )
            db.add(Category(name="Graphics Cards", slug="graphics-cards"))
            db.commit()

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(require_order_access, None)
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def override_get_db(self):
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_admin(self, db: Session = Depends(get_db)):
        return db.get(User, 1)

    def test_dashboard_and_user_customer_crud_use_database(self):
        dashboard = self.client.get("/api/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertEqual(dashboard.json()["total_customers"], 0)

        created = self.client.post(
            "/api/users",
            json={
                "name": "Cashier One",
                "email": "cashier@example.com",
                "phone": "0771234567",
                "role": "Cashier",
                "role_id": 3,
                "tempPassword": "SafePass123",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["role"], "Cashier")
        self.assertNotIn("password_hash", created.json())

        updated = self.client.patch(
            f"/api/users/{created.json()['id']}",
            json={"name": "Updated Cashier", "status": "Inactive"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "Inactive")

        toggled = self.client.patch(f"/api/users/{created.json()['id']}/toggle-status")
        self.assertEqual(toggled.json()["status"], "Active")
        self.assertEqual(len(self.client.get("/api/users").json()), 2)

        customer = self.client.post(
            "/api/customers",
            json={
                "name": "Customer One",
                "email": "customer@example.com",
                "phone": "0711234567",
                "city": "Kandy",
                "tempPassword": "CustomerPass123",
            },
        )
        self.assertEqual(customer.status_code, 201, customer.text)
        self.assertEqual(customer.json()["city"], "Kandy")
        self.assertEqual(len(self.client.get("/api/customers").json()), 1)

    def test_orders_pos_sales_stock_audit_and_reports(self):
        order = self.client.post(
            "/api/orders",
            json={
                "customer_email": None,
                "payment_method": "Cash",
                "payment_status": "Paid",
                "status": "Pending",
                "shipping_address": {
                    "recipient_name": "Guest",
                    "phone": "0770000000",
                    "street": "Main Street",
                    "city": "Colombo",
                    "postal_code": "00100",
                },
                "items": [],
                "total_amount": 125000,
                "items_summary": "Manual GPU order",
            },
        )
        self.assertEqual(order.status_code, 201, order.text)
        order_number = order.json()["id"]
        self.assertEqual(order.json()["items"][0]["name"], "Manual GPU order")

        updated = self.client.patch(
            f"/api/orders/{order_number}/status",
            json={"status": "Processing"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "Processing")

        sale = self.client.post(
            "/api/admin/pos/sales",
            json={
                "cashier_name": "Counter Operator",
                "items_count": 2,
                "subtotal": 450000,
                "payment_method": "Cash",
            },
        )
        self.assertEqual(sale.status_code, 201, sale.text)
        self.assertEqual(float(sale.json()["discount"]), 9000)
        self.assertEqual(len(self.client.get("/api/admin/pos/sales").json()), 1)

        self.assertEqual(
            self.client.patch(
                f"/api/admin/pos/sales/{sale.json()['id']}",
                json={"items_count": 3},
            ).status_code,
            200,
        )
        voided = self.client.post(f"/api/admin/pos/sales/{sale.json()['id']}/void")
        self.assertEqual(voided.status_code, 200, voided.text)
        self.assertEqual(self.client.get("/api/admin/pos/sales").json(), [])

        category = self.client.get("/api/categories").json()[0]
        product = self.client.post(
            "/api/products",
            json={
                "name": "Audit Product",
                "category_id": category["id"],
                "sku": "AUDIT-001",
                "price": 1000,
                "stock_count": 5,
                "min_stock_level": 2,
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        adjustment = self.client.patch(
            f"/api/products/{product.json()['id']}/stock",
            params={"stock_delta": -1, "reason": "Audit test"},
        )
        self.assertEqual(adjustment.status_code, 200, adjustment.text)
        history = self.client.get("/api/admin/inventory/transactions")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["change"], -1)

        summary = self.client.get("/api/admin/reports/summary")
        self.assertEqual(summary.status_code, 200, summary.text)
        report = self.client.post(
            "/api/admin/reports",
            json={
                "title": "Test Summary",
                "report_type": "Sales Revenue Breakdown",
                "period": "Month-to-Date (MTD)",
                "channel": "Blended (POS & Online)",
                "notes": "Test",
            },
        )
        self.assertEqual(report.status_code, 201, report.text)
        report_id = report.json()["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/admin/reports/{report_id}",
                json={"status": "Archived"},
            ).status_code,
            200,
        )

    def test_ai_profile_supplier_and_purchase_order_persistence(self):
        settings = self.client.put(
            "/api/admin/ai/settings",
            json={
                "budget_tolerance_pct": 12,
                "creativity_mode": "Strict Catalogue Matches",
                "stock_constraint": "Strict In-Stock Only",
                "min_confidence_score": 90,
                "is_active": False,
            },
        )
        self.assertEqual(settings.status_code, 200, settings.text)
        self.assertFalse(settings.json()["is_active"])

        log = self.client.post(
            "/api/admin/ai/logs",
            json={
                "budget": 100000,
                "intent": "Gaming",
                "recommended": "GPU",
                "outcome": "Viewed product",
                "status": "Engaged",
            },
        )
        self.assertEqual(log.status_code, 201, log.text)
        self.assertEqual(len(self.client.get("/api/admin/ai/logs").json()), 1)

        profile = self.client.put(
            "/api/admin/profile",
            json={
                "name": "Admin Updated",
                "email": "admin.updated@example.com",
                "phone": "0775555555",
                "street": "One Main Road",
                "city": "Galle",
                "postal_code": "80000",
                "avatar_url": "",
            },
        )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["city"], "Galle")

        category = self.client.get("/api/categories").json()[0]
        supplier = self.client.post(
            "/api/admin/suppliers",
            json={
                "company_name": "Supplier One",
                "contact_person": "Contact One",
                "email": "supplier@example.com",
                "phone": "0111234567",
                "supplied_categories": [category["name"]],
            },
        )
        self.assertEqual(supplier.status_code, 201, supplier.text)
        self.assertEqual(supplier.json()["supplied_categories"], [category["name"]])

        po = self.client.post(
            "/api/admin/purchase-orders",
            json={
                "supplier_id": supplier.json()["id"],
                "product_name": "Graphics Cards",
                "quantity": 3,
                "unit_cost": 50000,
                "urgency": "Normal",
                "notes": "Test order",
            },
        )
        self.assertEqual(po.status_code, 201, po.text)
        self.assertEqual(len(self.client.get("/api/admin/purchase-orders").json()), 1)


if __name__ == "__main__":
    unittest.main()
