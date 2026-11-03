import unittest
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.supplier import Supplier
from app.models.admin import User
from app.security import require_admin, require_supplier_access


class SupplierDashboardApiTests(unittest.TestCase):

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
        app.dependency_overrides[require_supplier_access] = self.override_admin

        with self.session_factory() as db:
            supplier = Supplier(
                name="Acme Distribution",
                contact_person="Sam Perera",
                email="sam@example.com",
                phone="0111234567",
            )
            db.add(supplier)
            db.commit()
            db.refresh(supplier)
            self.supplier_id = supplier.id

        self.branch_id = self.create_branch()

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(require_supplier_access, None)
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

    @property
    def supplier_url(self) -> str:
        return f"/api/suppliers/{self.supplier_id}"

    def create_branch(self) -> int:
        response = self.client.post(
            "/api/shop-branches",
            json={
                "name": "Colombo Flagship",
                "city": "Colombo",
                "address": "142 Galle Road",
                "manager_name": "Kasun Silva",
                "phone": "0771234567",
                "active_low_stock_count": 2,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def create_product(self, sku: str = "GPU-001", stock: int = 20) -> dict:
        response = self.client.post(
            f"{self.supplier_url}/products",
            json={
                "name": "RTX Graphics Card",
                "brand": "ASUS ROG",
                "category": "Graphics Cards",
                "sku": sku,
                "wholesale_price": "125000.00",
                "retail_msrp": "150000.00",
                "available_stock": stock,
                "min_order_qty": 2,
                "warranty_period": "3 years",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_profile_get_and_update_all_editable_fields(self):
        response = self.client.get(f"{self.supplier_url}/profile")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["company_name"], "Acme Distribution")

        response = self.client.put(
            f"{self.supplier_url}/profile",
            json={
                "company_name": "Acme Tech Distribution",
                "contact_person": "Nimal Perera",
                "email": "nimal@example.com",
                "phone": "0775551234",
                "street": "10 Main Street",
                "city": "Kandy",
                "postal_code": "20000",
                "tax_id": "VAT-123",
                "bank_name": "Commercial Bank",
                "bank_branch": "Kandy",
                "bank_account_no": "000123456",
                "authorized_brands": ["ASUS", "MSI"],
                "avatar_url": "https://example.test/logo.png",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["company_name"], "Acme Tech Distribution")
        self.assertEqual(response.json()["authorized_brands"], ["ASUS", "MSI"])
        self.assertEqual(response.json()["bank_account_no"], "000123456")

        empty_update = self.client.put(f"{self.supplier_url}/profile", json={})
        self.assertEqual(empty_update.status_code, 400)
        null_name = self.client.put(
            f"{self.supplier_url}/profile",
            json={"company_name": None},
        )
        self.assertEqual(null_name.status_code, 422)

    def test_product_catalog_create_search_filter_update_and_delete(self):
        product = self.create_product(stock=3)
        self.assertEqual(product["status"], "Low Supply")

        response = self.client.get(
            f"{self.supplier_url}/products",
            params={"search": "graphics", "brand": "ASUS ROG"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [product["id"]])

        duplicate = self.client.post(
            f"{self.supplier_url}/products",
            json={
                "name": "Duplicate SKU",
                "brand": "MSI",
                "category": "GPU",
                "sku": "GPU-001",
                "wholesale_price": 100,
                "retail_msrp": 120,
                "available_stock": 4,
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        updated = self.client.put(
            f"{self.supplier_url}/products/{product['id']}",
            json={"available_stock": 0},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "Out of Stock")

        deleted = self.client.delete(
            f"{self.supplier_url}/products/{product['id']}"
        )
        self.assertEqual(deleted.status_code, 204)
        missing = self.client.get(
            f"{self.supplier_url}/products/{product['id']}"
        )
        self.assertEqual(missing.status_code, 404)

    def test_branch_lookup_and_duplicate_branch(self):
        response = self.client.get("/api/shop-branches")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], self.branch_id)

        duplicate = self.client.post(
            "/api/shop-branches",
            json={
                "name": "Colombo Flagship",
                "city": "Colombo",
                "address": "142 Galle Road",
                "manager_name": "Kasun Silva",
                "phone": "0771234567",
            },
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_restock_request_pricing_filters_and_status_transitions(self):
        product = self.create_product()
        response = self.client.post(
            f"{self.supplier_url}/requests",
            json={
                "branch_id": self.branch_id,
                "request_no": "REQ-001",
                "shop_manager": "Kasun Silva",
                "shop_phone": "0771234567",
                "urgency": "Critical (Out of Stock)",
                "items": [
                    {
                        "product_id": product["id"],
                        "current_shop_stock": 0,
                        "min_threshold": 5,
                        "requested_qty": 3,
                    }
                ],
                "shop_notes": "Urgent replenishment",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        request = response.json()
        self.assertEqual(Decimal(request["total_est_value"]), Decimal("375000.00"))
        self.assertEqual(request["items"][0]["sku"], "GPU-001")

        filtered = self.client.get(
            f"{self.supplier_url}/requests",
            params={"status": "Pending Supplier Approval"},
        )
        self.assertEqual(len(filtered.json()), 1)

        accepted = self.client.patch(
            f"{self.supplier_url}/requests/{request['id']}/status",
            json={"status": "Accepted & Preparing"},
        )
        self.assertEqual(accepted.status_code, 200)

        dispatched = self.client.patch(
            f"{self.supplier_url}/requests/{request['id']}/status",
            json={"status": "Dispatched"},
        )
        self.assertEqual(dispatched.status_code, 200)

        invalid_transition = self.client.patch(
            f"{self.supplier_url}/requests/{request['id']}/status",
            json={"status": "Declined"},
        )
        self.assertEqual(invalid_transition.status_code, 409)

        duplicate_number = self.client.post(
            f"{self.supplier_url}/requests",
            json={
                "branch_id": self.branch_id,
                "request_no": "REQ-001",
                "shop_manager": "Kasun Silva",
                "shop_phone": "0771234567",
                "urgency": "Normal Restock",
                "items": [
                    {
                        "product_id": product["id"],
                        "current_shop_stock": 2,
                        "min_threshold": 5,
                        "requested_qty": 1,
                    }
                ],
            },
        )
        self.assertEqual(duplicate_number.status_code, 409)

    def test_delivery_creation_decrements_stock_and_updates_status(self):
        product = self.create_product(stock=8)
        response = self.client.post(
            f"{self.supplier_url}/deliveries",
            json={
                "branch_id": self.branch_id,
                "dispatch_no": "DSP-001",
                "carrier": "Pronto Lanka",
                "tracking_number": "TRK-001",
                "dispatch_date": "2026-11-02 09:00",
                "estimated_arrival": "Tomorrow",
                "driver_name": "Kamal",
                "driver_phone": "0770000000",
                "items": [{"product_id": product["id"], "quantity": 3}],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        delivery = response.json()
        self.assertEqual(delivery["total_units"], 3)
        self.assertEqual(Decimal(delivery["total_value"]), Decimal("375000.00"))

        product_after_delivery = self.client.get(
            f"{self.supplier_url}/products/{product['id']}"
        ).json()
        self.assertEqual(product_after_delivery["available_stock"], 5)
        self.assertEqual(product_after_delivery["status"], "Low Supply")

        updated = self.client.patch(
            f"{self.supplier_url}/deliveries/{delivery['id']}/status",
            json={"status": "Delivered & Verified"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "Delivered & Verified")

        insufficient_stock = self.client.post(
            f"{self.supplier_url}/deliveries",
            json={
                "branch_id": self.branch_id,
                "dispatch_no": "DSP-002",
                "carrier": "Pronto Lanka",
                "tracking_number": "TRK-002",
                "dispatch_date": "2026-11-02 10:00",
                "estimated_arrival": "Tomorrow",
                "items": [{"product_id": product["id"], "quantity": 6}],
            },
        )
        self.assertEqual(insufficient_stock.status_code, 409)

        second_product = self.create_product(sku="GPU-002", stock=1)
        multi_item_failure = self.client.post(
            f"{self.supplier_url}/deliveries",
            json={
                "branch_id": self.branch_id,
                "dispatch_no": "DSP-003",
                "carrier": "Pronto Lanka",
                "tracking_number": "TRK-003",
                "dispatch_date": "2026-11-02 11:00",
                "estimated_arrival": "Tomorrow",
                "items": [
                    {"product_id": product["id"], "quantity": 2},
                    {"product_id": second_product["id"], "quantity": 2},
                ],
            },
        )
        self.assertEqual(multi_item_failure.status_code, 409)
        unchanged_stock = self.client.get(
            f"{self.supplier_url}/products/{product['id']}"
        ).json()["available_stock"]
        self.assertEqual(unchanged_stock, 5)

    def test_return_log_filter_and_resolution(self):
        product = self.create_product()
        response = self.client.post(
            f"{self.supplier_url}/returns",
            json={
                "branch_id": self.branch_id,
                "product_id": product["id"],
                "rma_number": "RMA-001",
                "serial_number": "SN-123",
                "customer_issue": "GPU artifacts under load",
                "return_reason": "GPU Artifacting / Freezing",
                "warranty_valid": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        returned = response.json()
        self.assertEqual(returned["product_name"], "RTX Graphics Card")

        filtered = self.client.get(
            f"{self.supplier_url}/returns",
            params={"status": "Pending Inspection"},
        )
        self.assertEqual(len(filtered.json()), 1)

        resolved = self.client.patch(
            f"{self.supplier_url}/returns/{returned['id']}/status",
            json={
                "status": "Replacement Dispatched",
                "resolution_notes": "DOA confirmed; replacement sent.",
            },
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(resolved.json()["status"], "Replacement Dispatched")
        self.assertEqual(
            resolved.json()["resolution_notes"],
            "DOA confirmed; replacement sent.",
        )

        resolved_again = self.client.patch(
            f"{self.supplier_url}/returns/{returned['id']}/status",
            json={"status": "Credit Note Issued"},
        )
        self.assertEqual(resolved_again.status_code, 409)

    def test_overview_aggregates_all_dashboard_sections(self):
        product = self.create_product()
        request = self.client.post(
            f"{self.supplier_url}/requests",
            json={
                "branch_id": self.branch_id,
                "request_no": "REQ-OVERVIEW",
                "shop_manager": "Kasun Silva",
                "shop_phone": "0771234567",
                "urgency": "High (Low Stock)",
                "items": [
                    {
                        "product_id": product["id"],
                        "current_shop_stock": 1,
                        "min_threshold": 5,
                        "requested_qty": 2,
                    }
                ],
            },
        )
        self.assertEqual(request.status_code, 201)
        delivery = self.client.post(
            f"{self.supplier_url}/deliveries",
            json={
                "branch_id": self.branch_id,
                "dispatch_no": "DSP-OVERVIEW",
                "carrier": "Pronto Lanka",
                "tracking_number": "TRK-OVERVIEW",
                "dispatch_date": "2026-11-02",
                "estimated_arrival": "Tomorrow",
                "total_units": 4,
                "total_value": "500000.00",
            },
        )
        self.assertEqual(delivery.status_code, 201)
        active_delivery = self.client.patch(
            f"{self.supplier_url}/deliveries/{delivery.json()['id']}/status",
            json={"status": "In-Transit"},
        )
        self.assertEqual(active_delivery.status_code, 200)
        returned = self.client.post(
            f"{self.supplier_url}/returns",
            json={
                "branch_id": self.branch_id,
                "product_id": product["id"],
                "rma_number": "RMA-OVERVIEW",
                "serial_number": "SN-OVERVIEW",
                "customer_issue": "Unit will not power on",
                "return_reason": "Dead On Arrival (DOA)",
            },
        )
        self.assertEqual(returned.status_code, 201)

        response = self.client.get(f"{self.supplier_url}/overview")
        self.assertEqual(response.status_code, 200, response.text)
        overview = response.json()
        self.assertEqual(overview["total_products"], 1)
        self.assertEqual(overview["pending_requests"], 1)
        self.assertEqual(
            Decimal(overview["pending_request_value"]),
            Decimal("250000.00"),
        )
        self.assertEqual(overview["active_deliveries"], 1)
        self.assertEqual(overview["total_returns"], 1)
        self.assertEqual(overview["pending_inspections"], 1)

    def test_supplier_data_is_scoped_and_unknown_supplier_is_not_found(self):
        other_supplier = self.client.post(
            "/api/suppliers",
            json={"name": "Another Supplier"},
        )
        self.assertEqual(other_supplier.status_code, 201)
        other_id = other_supplier.json()["id"]
        product = self.create_product()

        other_products = self.client.get(
            f"/api/suppliers/{other_id}/products"
        )
        self.assertEqual(other_products.status_code, 200)
        self.assertEqual(other_products.json(), [])

        missing = self.client.get("/api/suppliers/99999/overview")
        self.assertEqual(missing.status_code, 404)

        cross_supplier_product = self.client.get(
            f"/api/suppliers/{other_id}/products/{product['id']}"
        )
        self.assertEqual(cross_supplier_product.status_code, 404)

    def test_supplier_dashboard_api_routes_are_registered(self):
        paths = app.openapi()["paths"]
        prefix = f"/api/suppliers/{{supplier_id}}"
        expected_paths = {
            f"{prefix}/overview",
            f"{prefix}/profile",
            f"{prefix}/products",
            f"{prefix}/products/{{product_id}}",
            f"{prefix}/requests",
            f"{prefix}/requests/{{request_id}}/status",
            f"{prefix}/deliveries",
            f"{prefix}/deliveries/{{delivery_id}}/status",
            f"{prefix}/returns",
            f"{prefix}/returns/{{return_id}}/status",
            "/api/shop-branches",
        }
        self.assertTrue(expected_paths.issubset(paths))


if __name__ == "__main__":
    unittest.main()
