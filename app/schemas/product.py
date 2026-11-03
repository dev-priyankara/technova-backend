from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):

    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    specs: list[str] | None = None
    cost_price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock_count: int = Field(default=0, ge=0)
    min_stock_level: int = Field(default=3, ge=0)
    warranty: str | None = Field(default=None, max_length=150)

    model_config = ConfigDict(str_strip_whitespace=True)


class ProductUpdate(BaseModel):

    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    specs: list[str] | None = None
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock_count: int | None = Field(default=None, ge=0)
    min_stock_level: int | None = Field(default=None, ge=0)
    warranty: str | None = Field(default=None, max_length=150)

    model_config = ConfigDict(str_strip_whitespace=True)


class ProductResponse(BaseModel):

    id: int
    category_id: int | None
    category: str
    category_name: str
    name: str
    sku: str
    description: str | None
    specs: list[str] | None
    cost_price: Decimal
    price: Decimal
    stock_count: int
    min_stock_level: int
    warranty: str | None
    status: str
    in_stock: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
