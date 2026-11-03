import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.category import Category
from app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from app.security import require_admin


router = APIRouter(
    prefix="/api/categories",
    tags=["Categories"],
)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug[:140].rstrip("-") or "category"


def _slug_exists(
    db: Session,
    slug: str,
    exclude_category_id: int | None = None,
) -> bool:
    statement = select(Category.id).where(Category.slug == slug)
    if exclude_category_id is not None:
        statement = statement.where(Category.id != exclude_category_id)
    return db.scalar(statement) is not None


def _available_slug(
    db: Session,
    value: str,
    is_custom: bool,
    exclude_category_id: int | None = None,
) -> str:
    base_slug = _slugify(value)
    candidate = base_slug
    suffix = 2

    while _slug_exists(db, candidate, exclude_category_id):
        if is_custom:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category slug already exists",
            )
        suffix_text = f"-{suffix}"
        candidate = f"{base_slug[:140 - len(suffix_text)].rstrip('-')}{suffix_text}"
        suffix += 1

    return candidate


def _item_count(db: Session, category_id: int) -> int:
    count = db.scalar(
        text("SELECT COUNT(*) FROM products WHERE category_id = :category_id"),
        {"category_id": category_id},
    )
    return int(count or 0)


def _category_response(db: Session, category: Category) -> CategoryResponse:
    return CategoryResponse(
        id=category.id,
        name=category.name,
        slug=category.slug,
        description=category.description,
        created_at=category.created_at,
        item_count=_item_count(db, category.id),
    )


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db),
):
    existing_category = db.scalar(
        select(Category.id).where(Category.name == category_data.name)
    )
    if existing_category is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category name already exists",
        )

    slug_value = category_data.slug or category_data.name
    slug = _available_slug(
        db,
        slug_value,
        is_custom=category_data.slug is not None,
    )
    new_category = Category(
        name=category_data.name,
        slug=slug,
        description=category_data.description or None,
    )
    db.add(new_category)

    try:
        db.commit()
        db.refresh(new_category)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category name or slug already exists",
        ) from None

    return _category_response(db, new_category)


@router.get("", response_model=list[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    categories = db.scalars(select(Category).order_by(Category.id)).all()
    item_counts = dict(
        db.execute(
            text(
                "SELECT category_id, COUNT(*) "
                "FROM products "
                "WHERE category_id IS NOT NULL "
                "GROUP BY category_id"
            )
        ).all()
    )

    return [
        CategoryResponse(
            id=category.id,
            name=category.name,
            slug=category.slug,
            description=category.description,
            created_at=category.created_at,
            item_count=int(item_counts.get(category.id, 0)),
        )
        for category in categories
    ]


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return _category_response(db, category)


@router.put("/{category_id}", response_model=CategoryResponse)
@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    update_data = category_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one field to update",
        )

    if "name" in update_data:
        new_name = update_data["name"]
        if new_name is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Category name cannot be empty",
            )
        existing_name = db.scalar(
            select(Category.id).where(
                Category.name == new_name,
                Category.id != category_id,
            )
        )
        if existing_name is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category name already exists",
            )
        category.name = new_name

    if "slug" in update_data:
        slug_value = update_data["slug"] or category.name
        category.slug = _available_slug(
            db,
            slug_value,
            is_custom=update_data["slug"] is not None,
            exclude_category_id=category_id,
        )
    elif "name" in update_data:
        category.slug = _available_slug(
            db,
            category.name,
            is_custom=False,
            exclude_category_id=category_id,
        )

    if "description" in update_data:
        category.description = update_data["description"] or None

    try:
        db.commit()
        db.refresh(category)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update category because its name or slug already exists",
        ) from None

    return _category_response(db, category)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    db.delete(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete this category because it is being used by other records",
        ) from None

    return {
        "message": "Category deleted successfully",
        "category_id": category_id,
    }
