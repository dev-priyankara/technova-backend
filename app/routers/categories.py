from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.category import Category
from app.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse
)


router = APIRouter(
    prefix="/api/categories",
    tags=["Categories"]
)


# --------------------------------
# CREATE CATEGORY
# --------------------------------

@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED
)
def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db)
):

    new_category = Category(
        name=category_data.name,
        description=category_data.description
    )

    db.add(new_category)

    try:
        db.commit()
        db.refresh(new_category)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Category name already exists"
        )

    return new_category


# --------------------------------
# GET ALL CATEGORIES
# --------------------------------

@router.get(
    "",
    response_model=list[CategoryResponse]
)
def get_categories(
    db: Session = Depends(get_db)
):

    statement = select(Category).order_by(Category.id)

    categories = db.scalars(statement).all()

    return categories


# --------------------------------
# GET CATEGORY BY ID
# --------------------------------

@router.get(
    "/{category_id}",
    response_model=CategoryResponse
)
def get_category(
    category_id: int,
    db: Session = Depends(get_db)
):

    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Category not found"
        )

    return category


# --------------------------------
# UPDATE CATEGORY
# --------------------------------

@router.put(
    "/{category_id}",
    response_model=CategoryResponse
)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db)
):

    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Category not found"
        )

    category.name = category_data.name

    category.description = category_data.description

    try:
        db.commit()
        db.refresh(category)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Category name already exists"
        )

    return category


# --------------------------------
# DELETE CATEGORY
# --------------------------------

@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db)
):

    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Category not found"
        )

    db.delete(category)
    db.commit()

    return {
        "message": "Category deleted successfully"
    }