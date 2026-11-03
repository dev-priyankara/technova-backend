
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):

    name: str = Field(min_length=1, max_length=120)

    slug: str | None = Field(default=None, min_length=1, max_length=140)
    description: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class CategoryUpdate(BaseModel):

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120
    )

    slug: str | None = Field(default=None, min_length=1, max_length=140)
    description: str | None = None

    model_config = ConfigDict(
        str_strip_whitespace=True
    )


class CategoryResponse(BaseModel):

    id: int
    name: str
    slug: str
    description: str | None
    created_at: datetime
    item_count: int = 0

    model_config = ConfigDict(from_attributes=True)
