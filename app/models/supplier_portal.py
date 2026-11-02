from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class ShopBranch(Base):

    __tablename__ = "shop_branches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    manager_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    active_low_stock_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0
    )


class SupplierProduct(Base):

    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_id", "sku", name="uq_supplier_product_sku"),
        CheckConstraint("wholesale_price >= 0", name="ck_product_wholesale"),
        CheckConstraint("retail_msrp >= 0", name="ck_product_msrp"),
        CheckConstraint("available_stock >= 0", name="ck_product_stock"),
        CheckConstraint("min_order_qty >= 1", name="ck_product_moq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(150), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    wholesale_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )
    retail_msrp: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    available_stock: Mapped[int] = mapped_column(nullable=False, default=0)
    min_order_qty: Mapped[int] = mapped_column(nullable=False, default=1)
    warranty_period: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default=""
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="In Stock"
    )


class RestockRequest(Base):

    __tablename__ = "restock_requests"
    __table_args__ = (
        CheckConstraint(
            "urgency IN ('Critical (Out of Stock)', 'High (Low Stock)', "
            "'Normal Restock')",
            name="ck_restock_urgency"
        ),
        CheckConstraint(
            "status IN ('Pending Supplier Approval', 'Accepted & Preparing', "
            "'Dispatched', 'Declined')",
            name="ck_restock_status"
        ),
        CheckConstraint("total_est_value >= 0", name="ck_request_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("shop_branches.id"),
        nullable=False
    )
    request_no: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False
    )
    shop_manager: Mapped[str] = mapped_column(String(150), nullable=False)
    shop_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    request_date: Mapped[date] = mapped_column(Date, default=date.today)
    urgency: Mapped[str] = mapped_column(String(40), nullable=False)
    total_est_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Pending Supplier Approval"
    )
    shop_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["RestockRequestItem"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan"
    )


class RestockRequestItem(Base):

    __tablename__ = "restock_request_items"
    __table_args__ = (
        CheckConstraint("current_shop_stock >= 0", name="ck_item_shop_stock"),
        CheckConstraint("min_threshold >= 0", name="ck_item_min_threshold"),
        CheckConstraint("requested_qty >= 1", name="ck_item_requested_qty"),
        CheckConstraint("wholesale_price >= 0", name="ck_item_wholesale"),
        CheckConstraint("line_total >= 0", name="ck_item_line_total"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("restock_requests.id", ondelete="CASCADE"),
        nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_products.id", ondelete="SET NULL"),
        nullable=True
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    current_shop_stock: Mapped[int] = mapped_column(nullable=False)
    min_threshold: Mapped[int] = mapped_column(nullable=False)
    requested_qty: Mapped[int] = mapped_column(nullable=False)
    wholesale_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    request: Mapped[RestockRequest] = relationship(back_populates="items")


class DeliveryDispatch(Base):

    __tablename__ = "delivery_dispatches"
    __table_args__ = (
        CheckConstraint("total_units >= 0", name="ck_dispatch_units"),
        CheckConstraint("total_value >= 0", name="ck_dispatch_value"),
        CheckConstraint(
            "status IN ('Preparing Dispatch', 'Dispatched', 'In-Transit', "
            "'Delivered & Verified')",
            name="ck_dispatch_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("shop_branches.id"),
        nullable=False
    )
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("restock_requests.id", ondelete="SET NULL"),
        nullable=True
    )
    dispatch_no: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False
    )
    request_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    carrier: Mapped[str] = mapped_column(String(150), nullable=False)
    tracking_number: Mapped[str] = mapped_column(String(100), nullable=False)
    dispatch_date: Mapped[str] = mapped_column(String(30), nullable=False)
    estimated_arrival: Mapped[str] = mapped_column(String(100), nullable=False)
    total_units: Mapped[int] = mapped_column(nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="Preparing Dispatch"
    )
    driver_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    driver_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ReturnedProduct(Base):

    __tablename__ = "returned_products"
    __table_args__ = (
        CheckConstraint(
            "return_reason IN ('Dead On Arrival (DOA)', "
            "'GPU Artifacting / Freezing', 'VRM Power Defect', "
            "'Transit Physical Damage')",
            name="ck_return_reason"
        ),
        CheckConstraint(
            "status IN ('Pending Inspection', 'Replacement Dispatched', "
            "'Credit Note Issued', 'Rejected (Physical Damage)')",
            name="ck_return_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("shop_branches.id"),
        nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_products.id", ondelete="SET NULL"),
        nullable=True
    )
    rma_number: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(150), nullable=False)
    customer_issue: Mapped[str] = mapped_column(Text, nullable=False)
    return_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    return_date: Mapped[date] = mapped_column(Date, default=date.today)
    warranty_valid: Mapped[bool] = mapped_column(nullable=False, default=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Pending Inspection"
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
