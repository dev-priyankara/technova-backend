from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.supplier import Supplier
from app.schemas.supplier import (
    SupplierCreate,
    SupplierDashboardResponse,
    SupplierResponse,
    SupplierUpdate,
)


router = APIRouter(
    prefix="/api/suppliers",
    tags=["Suppliers"]
)


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED
)
def create_supplier(
    supplier_data: SupplierCreate,
    db: Session = Depends(get_db)
):
    existing_supplier = db.scalar(
        select(Supplier).where(Supplier.name == supplier_data.name)
    )

    if existing_supplier:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier name already exists"
        )

    supplier = Supplier(**supplier_data.model_dump())
    db.add(supplier)

    try:
        db.commit()
        db.refresh(supplier)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier name already exists"
        )

    return supplier


@router.get(
    "",
    response_model=list[SupplierResponse]
)
def get_suppliers(
    search: str | None = Query(default=None, min_length=1, max_length=150),
    db: Session = Depends(get_db)
):
    statement = select(Supplier).order_by(Supplier.id)

    if search:
        search_term = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Supplier.name.ilike(search_term),
                Supplier.contact_person.ilike(search_term),
                Supplier.email.ilike(search_term),
            )
        )

    return db.scalars(statement).all()


@router.get(
    "/dashboard",
    response_model=SupplierDashboardResponse
)
def get_supplier_dashboard(
    recent_limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    total_suppliers = db.scalar(select(func.count()).select_from(Supplier))
    recent_suppliers = db.scalars(
        select(Supplier)
        .order_by(Supplier.id.desc())
        .limit(recent_limit)
    ).all()

    return {
        "total_suppliers": total_suppliers,
        "recent_suppliers": recent_suppliers,
    }


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse
)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    supplier = db.get(Supplier, supplier_id)

    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found"
        )

    return supplier


@router.put(
    "/{supplier_id}",
    response_model=SupplierResponse
)
def update_supplier(
    supplier_id: int,
    supplier_data: SupplierUpdate,
    db: Session = Depends(get_db)
):
    supplier = db.get(Supplier, supplier_id)

    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found"
        )

    update_data = supplier_data.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one field to update"
        )

    if "name" in update_data:
        new_name = update_data["name"]

        if new_name is None or not new_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Supplier name cannot be empty"
            )

        existing_supplier = db.scalar(
            select(Supplier).where(
                Supplier.name == new_name,
                Supplier.id != supplier_id
            )
        )

        if existing_supplier:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier name already exists"
            )

    for field, value in update_data.items():
        setattr(supplier, field, value)

    try:
        db.commit()
        db.refresh(supplier)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update supplier due to duplicate data"
        )

    return supplier


@router.delete("/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    supplier = db.get(Supplier, supplier_id)

    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found"
        )

    db.delete(supplier)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete this supplier because it is being used by other records"
        )

    return {
        "message": "Supplier deleted successfully",
        "supplier_id": supplier_id,
    }
