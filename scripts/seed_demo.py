"""Seed TECHNOVA with demo data for local development.

Safe to run more than once: existing rows are looked up by their unique keys
before anything is inserted.

Usage (from the backend directory):

    .venv/bin/python scripts/seed_demo.py
"""

from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import SessionLocal
from app.models.admin import Role, User
from app.models.category import Category
from app.models.product import Product
from app.models.supplier import Supplier
from app.security import hash_password

DEMO_PASSWORD = "Technova@123"

CATEGORIES = [
    ("Laptops", "laptops", "Notebooks and ultrabooks from leading brands."),
    ("Desktop PCs", "desktop-pcs", "Pre-built and custom desktop computers."),
    ("Components", "components", "CPUs, motherboards, RAM, GPUs and storage."),
    ("Monitors", "monitors", "Gaming and productivity displays."),
    ("Peripherals", "peripherals", "Keyboards, mice, headsets and webcams."),
    ("Networking", "networking", "Routers, switches and network adapters."),
]

PRODUCTS = [
    ("Laptops", "ASUS ROG Strix G16", "LAP-ROG-G16", 385000, 429000, 12, 4,
     "2 Years", ["Intel Core i7-13650HX", "16GB DDR5", "1TB NVMe SSD", "RTX 4060 8GB", "16\" FHD+ 165Hz"]),
    ("Laptops", "HP Pavilion 15", "LAP-HP-PAV15", 168000, 189500, 20, 5,
     "1 Year", ["Intel Core i5-1335U", "8GB DDR4", "512GB NVMe SSD", "15.6\" FHD"]),
    ("Laptops", "Lenovo IdeaPad Slim 3", "LAP-LEN-IP3", 132000, 149000, 3, 5,
     "1 Year", ["AMD Ryzen 5 7520U", "8GB LPDDR5", "512GB SSD", "15.6\" FHD"]),
    ("Laptops", "Apple MacBook Air M3", "LAP-APP-MBA-M3", 395000, 439900, 6, 3,
     "1 Year", ["Apple M3 8-core", "8GB Unified Memory", "256GB SSD", "13.6\" Liquid Retina"]),
    ("Desktop PCs", "TECHNOVA Gaming Tower RTX 4060", "DSK-TN-G4060", 298000, 339000, 8, 3,
     "2 Years", ["Intel Core i5-13400F", "16GB DDR5", "1TB NVMe SSD", "RTX 4060 8GB"]),
    ("Desktop PCs", "TECHNOVA Office Mini PC", "DSK-TN-MINI", 96000, 112000, 15, 5,
     "1 Year", ["Intel Core i3-12100", "8GB DDR4", "256GB SSD", "Windows 11 Pro"]),
    ("Components", "NVIDIA GeForce RTX 4070 Super", "CMP-GPU-4070S", 172000, 199500, 5, 3,
     "3 Years", ["12GB GDDR6X", "PCIe 4.0", "DLSS 3.5", "Triple-fan cooling"]),
    ("Components", "Corsair Vengeance 16GB DDR5 5600", "CMP-RAM-CV16", 21500, 26500, 40, 10,
     "Lifetime", ["16GB (2x8GB)", "DDR5 5600MHz", "CL36", "XMP 3.0"]),
    ("Components", "Samsung 980 PRO 1TB NVMe", "CMP-SSD-980P1T", 34500, 41500, 2, 6,
     "5 Years", ["1TB PCIe 4.0 NVMe", "7000MB/s read", "M.2 2280"]),
    ("Monitors", "Dell UltraSharp 27\" 4K", "MON-DEL-U2723", 118000, 138000, 9, 3,
     "3 Years", ["27\" IPS 4K UHD", "USB-C 90W", "60Hz", "Height adjustable"]),
    ("Monitors", "LG UltraGear 24\" 165Hz", "MON-LG-24G165", 52000, 62500, 14, 4,
     "2 Years", ["24\" IPS FHD", "165Hz", "1ms GtG", "AMD FreeSync Premium"]),
    ("Peripherals", "Logitech MX Master 3S", "PER-LOG-MX3S", 24500, 29500, 25, 8,
     "1 Year", ["8000 DPI", "Quiet clicks", "USB-C charging", "Bluetooth + Logi Bolt"]),
    ("Peripherals", "Keychron K2 Mechanical Keyboard", "PER-KEY-K2", 19800, 24500, 0, 5,
     "1 Year", ["75% layout", "Hot-swappable", "RGB backlight", "Bluetooth 5.1"]),
    ("Peripherals", "HyperX Cloud III Headset", "PER-HX-CLOUD3", 27500, 32900, 11, 4,
     "2 Years", ["53mm drivers", "DTS Spatial Audio", "Detachable mic"]),
    ("Networking", "TP-Link Archer AX55 Wi-Fi 6", "NET-TPL-AX55", 22500, 27500, 18, 5,
     "3 Years", ["Wi-Fi 6 AX3000", "Dual band", "4x Gigabit LAN", "OneMesh"]),
    ("Networking", "Ubiquiti UniFi 6 Lite AP", "NET-UBI-U6L", 31500, 36900, 7, 3,
     "1 Year", ["Wi-Fi 6", "2x2 MIMO", "PoE powered", "Ceiling mount"]),
]

USERS = [
    ("Cashier", "Nimal Perera", "cashier@technova.lk", "0771234567"),
    ("Customer", "Sanduni Fernando", "customer@technova.lk", "0779876543"),
    ("Supplier", "Kasun Jayasinghe", "supplier@technova.lk", "0775551234"),
]

SUPPLIERS = [
    {
        "company_name": "Lanka Computer Distributors (Pvt) Ltd",
        "contact_person": "Kasun Jayasinghe",
        "email": "supplier@technova.lk",
        "phone": "0775551234",
        "address": "112 Galle Road, Colombo 03",
        "tax_id": "114567890",
        "vendor_code": "VEN-LCD-001",
        "rating": Decimal("4.60"),
        "contract_status": "Active",
        "bank_name": "Commercial Bank of Ceylon",
        "bank_branch": "Colombo 03",
        "bank_account_number": "8001234567",
    },
    {
        "company_name": "Metro Tech Imports",
        "contact_person": "Dilani Silva",
        "email": "dilani@metrotech.lk",
        "phone": "0112345678",
        "address": "45 Nawala Road, Nugegoda",
        "tax_id": "114567891",
        "vendor_code": "VEN-MTI-002",
        "rating": Decimal("4.20"),
        "contract_status": "Active",
        "bank_name": "Sampath Bank",
        "bank_branch": "Nugegoda",
        "bank_account_number": "0023456789",
    },
]


def main() -> None:
    with SessionLocal() as db:
        category_ids: dict[str, int] = {}
        for name, slug, description in CATEGORIES:
            category = db.scalar(select(Category).where(Category.slug == slug))
            if category is None:
                category = Category(name=name, slug=slug, description=description)
                db.add(category)
                db.flush()
            category_ids[name] = category.id

        for (
            category_name,
            name,
            sku,
            cost_price,
            price,
            stock,
            min_stock,
            warranty,
            specs,
        ) in PRODUCTS:
            if db.scalar(select(Product.id).where(Product.sku == sku)):
                continue
            db.add(
                Product(
                    category_id=category_ids[category_name],
                    name=name,
                    sku=sku,
                    description=f"{name} available at TECHNOVA Computers.",
                    specs=specs,
                    cost_price=Decimal(cost_price),
                    price=Decimal(price),
                    stock_count=stock,
                    min_stock_level=min_stock,
                    warranty=warranty,
                    status="Active",
                )
            )

        for role_name, name, email, phone in USERS:
            role = db.scalar(select(Role).where(Role.name == role_name))
            if role is None:
                raise SystemExit(f"Missing role: {role_name}")
            if db.scalar(select(User.id).where(User.email == email)):
                continue
            db.add(
                User(
                    role_id=role.id,
                    name=name,
                    email=email,
                    phone=phone,
                    password_hash=hash_password(DEMO_PASSWORD),
                    status="Active",
                )
            )

        db.flush()

        for payload in SUPPLIERS:
            if db.scalar(select(Supplier.id).where(Supplier.email == payload["email"])):
                continue
            supplier_user = db.scalar(
                select(User).where(User.email == payload["email"])
            )
            db.add(
                Supplier(
                    user_id=supplier_user.id if supplier_user else None,
                    **payload,
                )
            )

        db.commit()

    print("Demo data ready.")
    print(f"  Admin    admin@technova.lk / Admin@12345")
    print(f"  Cashier  cashier@technova.lk / {DEMO_PASSWORD}")
    print(f"  Customer customer@technova.lk / {DEMO_PASSWORD}")
    print(f"  Supplier supplier@technova.lk / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
