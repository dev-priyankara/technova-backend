
from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):

    name: str = Field(min_length=1, max_length=100)

    description: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)


class CategoryUpdate(BaseModel):

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100
    )

    description: str | None = None

    model_config = ConfigDict(
        str_strip_whitespace=True
    )


class CategoryResponse(BaseModel):

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
