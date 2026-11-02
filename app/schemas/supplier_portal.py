from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RestockUrgency = Literal[
    "Critical (Out of Stock)",
    "High (Low Stock)",
    "Normal Restock",
]
RestockStatus = Literal[
    "Pending Supplier Approval",
    "Accepted & Preparing",
    "Dispatched",
    "Declined",
]
DeliveryStatus = Literal[
    "Preparing Dispatch",
    "Dispatched",
    "In-Transit",
    "Delivered & Verified",
]
ReturnReason = Literal[
    "Dead On Arrival (DOA)",
    "GPU Artifacting / Freezing",
    "VRM Power Defect",
    "Transit Physical Damage",
]
ReturnStatus = Literal[
    "Pending Inspection",
    "Replacement Dispatched",
    "Credit Note Issued",
    "Rejected (Physical Damage)",
]


class SupplierProfileUpdate(BaseModel):

    company_name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    street: str | None = None
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    tax_id: str | None = Field(default=None, max_length=100)
    bank_name: str | None = Field(default=None, max_length=150)
    bank_branch: str | None = Field(default=None, max_length=150)
    bank_account_no: str | None = Field(default=None, max_length=100)
    authorized_brands: list[str] | None = None
    avatar_url: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplierProfileResponse(BaseModel):

    id: int
    vendor_code: str | None
    company_name: str
    contact_person: str | None
    email: str | None
    phone: str | None
    street: str | None
    city: str | None
    postal_code: str | None
    tax_id: str | None
    contract_status: str
    bank_name: str | None
    bank_branch: str | None
    bank_account_no: str | None
    authorized_brands: list[str]
    avatar_url: str | None

    model_config = ConfigDict(from_attributes=True)


class SupplierProductCreate(BaseModel):

    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=150)
    sku: str = Field(min_length=1, max_length=100)
    wholesale_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    retail_msrp: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    available_stock: int = Field(ge=0)
    min_order_qty: int = Field(default=1, ge=1)
    warranty_period: str = Field(default="", max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplierProductUpdate(BaseModel):

    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=150)
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    wholesale_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2
    )
    retail_msrp: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2
    )
    available_stock: int | None = Field(default=None, ge=0)
    min_order_qty: int | None = Field(default=None, ge=1)
    warranty_period: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplierProductResponse(SupplierProductCreate):

    id: int
    supplier_id: int
    status: Literal["In Stock", "Low Supply", "Out of Stock"]

    model_config = ConfigDict(from_attributes=True)


class ShopBranchResponse(BaseModel):

    id: int
    name: str
    city: str
    address: str
    manager_name: str
    phone: str
    active_low_stock_count: int

    model_config = ConfigDict(from_attributes=True)


class ShopBranchCreate(BaseModel):

    name: str = Field(min_length=1, max_length=150)
    city: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1)
    manager_name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=1, max_length=32)
    active_low_stock_count: int = Field(default=0, ge=0)

    model_config = ConfigDict(str_strip_whitespace=True)


class RestockRequestItemCreate(BaseModel):

    product_id: int
    current_shop_stock: int = Field(ge=0)
    min_threshold: int = Field(ge=0)
    requested_qty: int = Field(ge=1)


class RestockRequestItemResponse(BaseModel):

    id: int
    product_id: int | None
    product_name: str
    sku: str
    current_shop_stock: int
    min_threshold: int
    requested_qty: int
    wholesale_price: Decimal
    line_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class RestockRequestCreate(BaseModel):

    branch_id: int
    request_no: str = Field(min_length=1, max_length=80)
    shop_manager: str = Field(min_length=1, max_length=150)
    shop_phone: str = Field(min_length=1, max_length=32)
    urgency: RestockUrgency
    items: list[RestockRequestItemCreate] = Field(min_length=1)
    shop_notes: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class RestockRequestStatusUpdate(BaseModel):

    status: RestockStatus


class RestockRequestResponse(BaseModel):

    id: int
    supplier_id: int
    branch_id: int
    request_no: str
    shop_manager: str
    shop_phone: str
    request_date: date
    urgency: RestockUrgency
    total_est_value: Decimal
    status: RestockStatus
    shop_notes: str | None
    items: list[RestockRequestItemResponse]

    model_config = ConfigDict(from_attributes=True)


class DeliveryItemCreate(BaseModel):

    product_id: int
    quantity: int = Field(ge=1)


class DeliveryCreate(BaseModel):

    branch_id: int
    dispatch_no: str = Field(min_length=1, max_length=80)
    carrier: str = Field(min_length=1, max_length=150)
    tracking_number: str = Field(min_length=1, max_length=100)
    dispatch_date: str = Field(min_length=1, max_length=30)
    estimated_arrival: str = Field(min_length=1, max_length=100)
    driver_name: str | None = Field(default=None, max_length=150)
    driver_phone: str | None = Field(default=None, max_length=32)
    request_id: int | None = None
    items: list[DeliveryItemCreate] = Field(default_factory=list)
    total_units: int | None = Field(default=None, ge=0)
    total_value: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class DeliveryStatusUpdate(BaseModel):

    status: DeliveryStatus


class DeliveryResponse(BaseModel):

    id: int
    supplier_id: int
    branch_id: int
    request_id: int | None
    dispatch_no: str
    request_no: str | None
    carrier: str
    tracking_number: str
    dispatch_date: str
    estimated_arrival: str
    total_units: int
    total_value: Decimal
    status: DeliveryStatus
    driver_name: str | None
    driver_phone: str | None

    model_config = ConfigDict(from_attributes=True)


class ReturnedProductCreate(BaseModel):

    branch_id: int
    product_id: int
    rma_number: str = Field(min_length=1, max_length=80)
    serial_number: str = Field(min_length=1, max_length=150)
    customer_issue: str = Field(min_length=1)
    return_reason: ReturnReason
    warranty_valid: bool = True

    model_config = ConfigDict(str_strip_whitespace=True)


class ReturnedProductStatusUpdate(BaseModel):

    status: ReturnStatus
    resolution_notes: str | None = None


class ReturnedProductResponse(BaseModel):

    id: int
    supplier_id: int
    branch_id: int
    product_id: int | None
    rma_number: str
    product_name: str
    sku: str
    serial_number: str
    customer_issue: str
    return_reason: ReturnReason
    return_date: date
    warranty_valid: bool
    status: ReturnStatus
    resolution_notes: str | None

    model_config = ConfigDict(from_attributes=True)


class SupplierOverviewResponse(BaseModel):

    supplier_id: int
    total_products: int
    pending_requests: int
    pending_request_value: Decimal
    active_deliveries: int
    total_returns: int
    pending_inspections: int
    recent_requests: list[RestockRequestResponse]
    recent_deliveries: list[DeliveryResponse]
