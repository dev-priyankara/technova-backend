from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


UserRole = Literal["Admin", "Supplier", "Cashier", "Customer"]
OrderStatus = Literal["Pending", "Processing", "Delivered", "Cancelled"]
PaymentStatus = Literal[
    "Pending",
    "Pending Verification",
    "Paid",
    "Failed",
    "Refunded",
]
AIStatus = Literal["Success", "Engaged", "Safety Fallback"]


class AdminUserCreate(BaseModel):

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    role: UserRole = "Customer"
    role_id: int | None = Field(default=None, ge=1, le=255)
    tempPassword: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminUserUpdate(BaseModel):

    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    role: UserRole | None = None
    role_id: int | None = Field(default=None, ge=1, le=255)
    status: Literal["Active", "Inactive", "Pending"] | None = None
    city: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminCustomerCreate(BaseModel):

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    city: str = Field(min_length=1, max_length=100)
    tempPassword: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminUserResponse(BaseModel):

    id: int
    role_id: int
    role: str
    name: str
    email: str
    phone: str | None
    status: str
    created_at: datetime
    city: str | None = None
    orders_count: int = 0
    total_spent: Decimal = Decimal("0.00")


class AdminOrderItemCreate(BaseModel):

    product_id: int | None = Field(default=None, gt=0)
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class AdminOrderCreate(BaseModel):

    customer_email: str | None = None
    payment_method: str = Field(default="Cash", max_length=60)
    payment_status: PaymentStatus = "Pending"
    status: OrderStatus = "Pending"
    shipping_address: dict[str, str | None]
    items: list[AdminOrderItemCreate] = Field(default_factory=list)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    items_summary: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_order_items_or_total(self):
        if not self.items and self.total_amount is None:
            raise ValueError("Provide at least one item or a total amount")
        return self


class AdminOrderStatusUpdate(BaseModel):

    status: OrderStatus
    payment_status: PaymentStatus | None = None


class AdminOrderUpdate(BaseModel):

    customer_name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    items_summary: str | None = Field(default=None, min_length=1, max_length=200)
    total_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    status: OrderStatus | None = None
    payment_status: PaymentStatus | None = None


class POSSaleCreate(BaseModel):

    cashier_name: str = Field(min_length=1, max_length=150)
    items_count: int = Field(ge=1)
    subtotal: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    payment_method: str = Field(min_length=1, max_length=60)


class POSSaleUpdate(BaseModel):

    cashier_name: str | None = Field(default=None, min_length=1, max_length=150)
    items_count: int | None = Field(default=None, ge=1)
    payment_method: str | None = Field(default=None, min_length=1, max_length=60)


class AIEngineSettingsUpdate(BaseModel):

    budget_tolerance_pct: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    creativity_mode: str = Field(min_length=1, max_length=80)
    stock_constraint: str = Field(min_length=1, max_length=80)
    min_confidence_score: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    is_active: bool = True


class AIRecommendationCreate(BaseModel):

    budget: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    intent: str | None = None
    recommended: str | None = None
    outcome: str | None = Field(default=None, max_length=150)
    status: AIStatus
    reasoning: str | None = None


class AIRecommendationUpdate(BaseModel):

    budget: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    intent: str | None = None
    recommended: str | None = None
    outcome: str | None = Field(default=None, max_length=150)
    status: AIStatus | None = None
    reasoning: str | None = None


class AdminProfileUpdate(BaseModel):

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    street: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    avatar_url: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class AdminPasswordUpdate(BaseModel):

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AdminSupplierCreate(BaseModel):

    company_name: str = Field(min_length=1, max_length=180)
    contact_person: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=255)
    status: Literal["Active", "Pending Verification"] = "Active"
    supplied_categories: list[str] = Field(default_factory=list)


class AdminSupplierUpdate(BaseModel):

    company_name: str | None = Field(default=None, min_length=1, max_length=180)
    contact_person: str | None = Field(default=None, min_length=1, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=255)
    status: Literal["Active", "Pending Verification"] | None = None
    supplied_categories: list[str] | None = None


class PurchaseOrderCreate(BaseModel):

    supplier_id: int = Field(gt=0)
    product_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    urgency: Literal["Normal", "Urgent Expedited"] = "Normal"
    notes: str | None = None


class SavedReportCreate(BaseModel):

    title: str = Field(min_length=1, max_length=200)
    report_type: str = Field(min_length=1, max_length=100)
    period: str = Field(min_length=1, max_length=100)
    channel: str = Field(min_length=1, max_length=100)
    status: Literal["Finalized", "Draft", "Archived"] = "Finalized"
    notes: str | None = None


class SavedReportUpdate(BaseModel):

    title: str | None = Field(default=None, min_length=1, max_length=200)
    report_type: str | None = Field(default=None, min_length=1, max_length=100)
    period: str | None = Field(default=None, min_length=1, max_length=100)
    channel: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["Finalized", "Draft", "Archived"] | None = None
    notes: str | None = None
    gross_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
