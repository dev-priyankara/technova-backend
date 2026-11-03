from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.admin import InventoryTransaction
from app.models.category import Category
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.security import require_admin


router = APIRouter(prefix="/api/products", tags=["Products"])


def _category_id(
    db: Session,
    category_name: str | None,
    category_id: int | None,
) -> int | None:
    if category_id is not None:
        category = db.get(Category, category_id)
    elif category_name is not None:
        category = db.scalar(select(Category).where(Category.name == category_name))
    else:
        return None

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return category.id


def _product_response(db: Session, product: Product) -> ProductResponse:
    category = db.get(Category, product.category_id) if product.category_id else None
    category_name = category.name if category else ""
    return ProductResponse(
        id=product.id,
        category_id=product.category_id,
        category=category_name,
        category_name=category_name,
        name=product.name,
        sku=product.sku,
        description=product.description,
        specs=product.specs,
        cost_price=product.cost_price,
        price=product.price,
        stock_count=product.stock_count,
        min_stock_level=product.min_stock_level,
        warranty=product.warranty,
        status=product.status,
        in_stock=product.stock_count > 0,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("", response_model=list[ProductResponse])
def get_products(
    search: str | None = Query(default=None, min_length=1, max_length=200),
    category_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    statement = select(Product).order_by(Product.id)
    if search:
        statement = statement.where(
            Product.name.ilike(f"%{search.strip()}%")
            | Product.sku.ilike(f"%{search.strip()}%")
        )
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    products = db.scalars(statement).all()
    return [_product_response(db, product) for product in products]


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
):
    product = Product(
        name=product_data.name,
        sku=product_data.sku,
        category_id=_category_id(
            db, product_data.category, product_data.category_id
        ),
        description=product_data.description,
        specs=product_data.specs,
        cost_price=product_data.cost_price,
        price=product_data.price,
        stock_count=product_data.stock_count,
        min_stock_level=product_data.min_stock_level,
        warranty=product_data.warranty,
    )
    db.add(product)
    try:
        db.flush()
        if product.stock_count:
            db.add(
                InventoryTransaction(
                    product_id=product.id,
                    change_qty=product.stock_count,
                    stock_before=0,
                    stock_after=product.stock_count,
                    reason="Initial stock",
                    reference_type="product",
                    reference_id=product.id,
                )
            )
        db.commit()
        db.refresh(product)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product SKU already exists",
        ) from None
    return _product_response(db, product)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return _product_response(db, product)


@router.patch("/{product_id}", response_model=ProductResponse)
@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    update_data = product_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one field to update",
        )

    if "category" in update_data or "category_id" in update_data:
        product.category_id = _category_id(
            db,
            update_data.get("category"),
            update_data.get("category_id"),
        )
        update_data.pop("category", None)
        update_data.pop("category_id", None)

    previous_stock = product.stock_count
    for field, value in update_data.items():
        setattr(product, field, value)

    try:
        if product.stock_count != previous_stock:
            db.add(
                InventoryTransaction(
                    product_id=product.id,
                    change_qty=product.stock_count - previous_stock,
                    stock_before=previous_stock,
                    stock_after=product.stock_count,
                    reason="Product stock update",
                    reference_type="product",
                    reference_id=product.id,
                )
            )
        db.commit()
        db.refresh(product)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product SKU already exists",
        ) from None
    return _product_response(db, product)


@router.patch("/{product_id}/stock", response_model=ProductResponse)
def update_product_stock(
    product_id: int,
    stock_delta: int = Query(...),
    min_stock_level: int | None = Query(default=None, ge=0),
    reason: str = Query(default="Stock adjustment", max_length=100),
    notes: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    new_stock = product.stock_count + stock_delta
    if new_stock < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Stock cannot be reduced below zero",
        )
    previous_stock = product.stock_count
    product.stock_count = new_stock
    if min_stock_level is not None:
        product.min_stock_level = min_stock_level
    if stock_delta:
        db.add(
            InventoryTransaction(
                product_id=product.id,
                change_qty=stock_delta,
                stock_before=previous_stock,
                stock_after=new_stock,
                reason=reason,
                reference_type="product",
                reference_id=product.id,
                notes=notes,
            )
        )
    db.commit()
    db.refresh(product)
    return _product_response(db, product)


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    db.delete(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete this product because it is being used by other records",
        ) from None
    return {"message": "Product deleted successfully", "product_id": product_id}
