
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


# ==========================================
# 1. CREATE CATEGORY
# ==========================================

@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED
)
def create_category(
    category_data: CategoryCreate,
    db: Session = Depends(get_db)
):

    # Check whether category name already exists
    existing_category = db.scalar(
        select(Category).where(
            Category.name == category_data.name
        )
    )

    if existing_category:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category name already exists"
        )

    # Create new category
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
            status_code=status.HTTP_409_CONFLICT,
            detail="Category name already exists"
        )

    return new_category


# ==========================================
# 2. GET ALL CATEGORIES
# ==========================================

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


# ==========================================
# 3. GET CATEGORY BY ID
# ==========================================

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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    return category


# ==========================================
# 4. UPDATE CATEGORY
# ==========================================

@router.put(
    "/{category_id}",
    response_model=CategoryResponse
)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    db: Session = Depends(get_db)
):

    # Find category by ID
    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # Get only fields provided in the request
    update_data = category_data.model_dump(
        exclude_unset=True
    )

    # Check whether request body is empty
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one field to update"
        )

    # Update category name if provided
    if "name" in update_data:

        new_name = update_data["name"]

        # Category name cannot be empty or null
        if new_name is None or not new_name.strip():

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Category name cannot be empty"
            )

        # Check duplicate category name
        existing_category = db.scalar(
            select(Category).where(
                Category.name == new_name,
                Category.id != category_id
            )
        )

        if existing_category:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category name already exists"
            )

        category.name = new_name

    # Update description if provided
    if "description" in update_data:

        category.description = update_data["description"]

    # Save changes to MySQL
    try:

        db.commit()
        db.refresh(category)

    except IntegrityError:

        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update category due to duplicate data"
        )

    return category


# ==========================================
# 5. DELETE CATEGORY
# ==========================================

@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db)
):

    # Find category by ID
    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )

    # Delete category
    db.delete(category)

    try:

        db.commit()

    except IntegrityError:

        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete this category because it is being used by other records"
        )

    return {
        "message": "Category deleted successfully",
        "category_id": category_id
    }
