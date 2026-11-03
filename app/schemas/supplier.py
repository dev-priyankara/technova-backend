from pydantic import BaseModel, ConfigDict, Field


class SupplierCreate(BaseModel):

    name: str = Field(min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplierUpdate(BaseModel):

    name: str | None = Field(default=None, min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class SupplierResponse(BaseModel):

    id: int
    name: str
    contact_person: str | None
    email: str | None
    phone: str | None
    address: str | None

    model_config = ConfigDict(from_attributes=True)


class SupplierDashboardResponse(BaseModel):

    total_suppliers: int
    recent_suppliers: list[SupplierResponse]
