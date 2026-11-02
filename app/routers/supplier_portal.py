from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database.connection import get_db
from app.models.supplier import Supplier
from app.models.supplier_portal import (
    DeliveryDispatch,
    RestockRequest,
    RestockRequestItem,
    ReturnedProduct,
    ShopBranch,
    SupplierProduct,
)
from app.schemas.supplier_portal import (
    DeliveryCreate,
    DeliveryResponse,
    DeliveryStatus,
    DeliveryStatusUpdate,
    RestockRequestCreate,
    RestockRequestResponse,
    RestockRequestStatusUpdate,
    RestockStatus,
    ReturnedProductCreate,
    ReturnedProductResponse,
    ReturnedProductStatusUpdate,
    ReturnStatus,
    ShopBranchCreate,
    ShopBranchResponse,
    SupplierOverviewResponse,
    SupplierProductCreate,
    SupplierProductResponse,
    SupplierProductUpdate,
    SupplierProfileResponse,
    SupplierProfileUpdate,
)


router = APIRouter(
    prefix="/api/suppliers/{supplier_id}",
    tags=["Supplier Dashboard"],
)

branch_router = APIRouter(
    prefix="/api/shop-branches",
    tags=["Shop Branches"],
)


def _require_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )
    return supplier


def _require_branch(db: Session, branch_id: int) -> ShopBranch:
    branch = db.get(ShopBranch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop branch not found",
        )
    return branch


def _get_product(
    db: Session,
    supplier_id: int,
    product_id: int,
) -> SupplierProduct:
    product = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.id == product_id,
            SupplierProduct.supplier_id == supplier_id,
        )
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier product not found",
        )
    return product


def _stock_status(stock: int) -> str:
    if stock == 0:
        return "Out of Stock"
    if stock <= 5:
        return "Low Supply"
    return "In Stock"


@router.get(
    "/overview",
    response_model=SupplierOverviewResponse,
)
def get_supplier_overview(
    supplier_id: int,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    pending_requests = select(RestockRequest).where(
        RestockRequest.supplier_id == supplier_id,
        RestockRequest.status == "Pending Supplier Approval",
    )
    active_deliveries = ("Preparing Dispatch", "In-Transit")
    return {
        "supplier_id": supplier_id,
        "total_products": db.scalar(
            select(func.count()).select_from(SupplierProduct).where(
                SupplierProduct.supplier_id == supplier_id
            )
        ),
        "pending_requests": db.scalar(
            select(func.count()).select_from(pending_requests.subquery())
        ),
        "pending_request_value": db.scalar(
            select(func.coalesce(func.sum(RestockRequest.total_est_value), 0)).where(
                RestockRequest.supplier_id == supplier_id,
                RestockRequest.status == "Pending Supplier Approval",
            )
        ),
        "active_deliveries": db.scalar(
            select(func.count()).select_from(DeliveryDispatch).where(
                DeliveryDispatch.supplier_id == supplier_id,
                DeliveryDispatch.status.in_(active_deliveries),
            )
        ),
        "total_returns": db.scalar(
            select(func.count()).select_from(ReturnedProduct).where(
                ReturnedProduct.supplier_id == supplier_id
            )
        ),
        "pending_inspections": db.scalar(
            select(func.count()).select_from(ReturnedProduct).where(
                ReturnedProduct.supplier_id == supplier_id,
                ReturnedProduct.status == "Pending Inspection",
            )
        ),
        "recent_requests": db.scalars(
            select(RestockRequest)
            .options(selectinload(RestockRequest.items))
            .where(RestockRequest.supplier_id == supplier_id)
            .order_by(RestockRequest.id.desc())
            .limit(3)
        ).all(),
        "recent_deliveries": db.scalars(
            select(DeliveryDispatch)
            .where(DeliveryDispatch.supplier_id == supplier_id)
            .order_by(DeliveryDispatch.id.desc())
            .limit(5)
        ).all(),
    }


@router.get(
    "/profile",
    response_model=SupplierProfileResponse,
)
def get_supplier_profile(
    supplier_id: int,
    db: Session = Depends(get_db),
):
    supplier = _require_supplier(db, supplier_id)
    return {
        "id": supplier.id,
        "vendor_code": supplier.vendor_code,
        "company_name": supplier.name,
        "contact_person": supplier.contact_person,
        "email": supplier.email,
        "phone": supplier.phone,
        "street": supplier.address,
        "city": supplier.city,
        "postal_code": supplier.postal_code,
        "tax_id": supplier.tax_id,
        "contract_status": supplier.contract_status,
        "bank_name": supplier.bank_name,
        "bank_branch": supplier.bank_branch,
        "bank_account_no": supplier.bank_account_no,
        "authorized_brands": supplier.authorized_brands or [],
        "avatar_url": supplier.avatar_url,
    }


@router.put(
    "/profile",
    response_model=SupplierProfileResponse,
)
def update_supplier_profile(
    supplier_id: int,
    profile_data: SupplierProfileUpdate,
    db: Session = Depends(get_db),
):
    supplier = _require_supplier(db, supplier_id)
    update_data = profile_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one field to update",
        )
    if "company_name" in update_data:
        company_name = update_data.pop("company_name")
        if company_name is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Company name cannot be empty",
            )
        supplier.name = company_name
    if "street" in update_data:
        supplier.address = update_data.pop("street")
    for field, value in update_data.items():
        setattr(supplier, field, value)
    try:
        db.commit()
        db.refresh(supplier)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update supplier profile due to duplicate data",
        )
    return get_supplier_profile(supplier_id, db)


@router.post(
    "/products",
    response_model=SupplierProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_product(
    supplier_id: int,
    product_data: SupplierProductCreate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    product = SupplierProduct(
        supplier_id=supplier_id,
        **product_data.model_dump(),
        status=_stock_status(product_data.available_stock),
    )
    db.add(product)
    try:
        db.commit()
        db.refresh(product)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this SKU already exists for the supplier",
        )
    return product


@router.get(
    "/products",
    response_model=list[SupplierProductResponse],
)
def get_supplier_products(
    supplier_id: int,
    search: str | None = Query(default=None, min_length=1, max_length=150),
    brand: str | None = Query(default=None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    statement = select(SupplierProduct).where(
        SupplierProduct.supplier_id == supplier_id
    )
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                SupplierProduct.name.ilike(pattern),
                SupplierProduct.sku.ilike(pattern),
                SupplierProduct.category.ilike(pattern),
            )
        )
    if brand:
        statement = statement.where(SupplierProduct.brand == brand)
    return db.scalars(statement.order_by(SupplierProduct.id.desc())).all()


@router.get(
    "/products/{product_id}",
    response_model=SupplierProductResponse,
)
def get_supplier_product(
    supplier_id: int,
    product_id: int,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    return _get_product(db, supplier_id, product_id)


@router.put(
    "/products/{product_id}",
    response_model=SupplierProductResponse,
)
def update_supplier_product(
    supplier_id: int,
    product_id: int,
    product_data: SupplierProductUpdate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    product = _get_product(db, supplier_id, product_id)
    update_data = product_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one field to update",
        )
    for field, value in update_data.items():
        setattr(product, field, value)
    if "available_stock" in update_data:
        product.status = _stock_status(product.available_stock)
    try:
        db.commit()
        db.refresh(product)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this SKU already exists for the supplier",
        )
    return product


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_supplier_product(
    supplier_id: int,
    product_id: int,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    product = _get_product(db, supplier_id, product_id)
    db.delete(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a product referenced by an existing request or return",
        )


@branch_router.get("", response_model=list[ShopBranchResponse])
def get_shop_branches(
    db: Session = Depends(get_db),
):
    return db.scalars(select(ShopBranch).order_by(ShopBranch.name)).all()


@branch_router.post(
    "",
    response_model=ShopBranchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_shop_branch(
    branch_data: ShopBranchCreate,
    db: Session = Depends(get_db),
):
    branch = ShopBranch(**branch_data.model_dump())
    db.add(branch)
    try:
        db.commit()
        db.refresh(branch)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A shop branch with this name already exists",
        )
    return branch


@router.post(
    "/requests",
    response_model=RestockRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_restock_request(
    supplier_id: int,
    request_data: RestockRequestCreate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    _require_branch(db, request_data.branch_id)
    request_items = []
    total_value = Decimal("0.00")
    for item_data in request_data.items:
        product = _get_product(db, supplier_id, item_data.product_id)
        line_total = product.wholesale_price * item_data.requested_qty
        total_value += line_total
        request_items.append(
            RestockRequestItem(
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                current_shop_stock=item_data.current_shop_stock,
                min_threshold=item_data.min_threshold,
                requested_qty=item_data.requested_qty,
                wholesale_price=product.wholesale_price,
                line_total=line_total,
            )
        )
    restock_request = RestockRequest(
        supplier_id=supplier_id,
        branch_id=request_data.branch_id,
        request_no=request_data.request_no,
        shop_manager=request_data.shop_manager,
        shop_phone=request_data.shop_phone,
        urgency=request_data.urgency,
        total_est_value=total_value,
        shop_notes=request_data.shop_notes,
        items=request_items,
    )
    db.add(restock_request)
    try:
        db.commit()
        db.refresh(restock_request)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A restock request with this number already exists",
        )
    return restock_request


@router.get(
    "/requests",
    response_model=list[RestockRequestResponse],
)
def get_restock_requests(
    supplier_id: int,
    request_status: RestockStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    statement = (
        select(RestockRequest)
        .options(selectinload(RestockRequest.items))
        .where(RestockRequest.supplier_id == supplier_id)
    )
    if request_status:
        statement = statement.where(RestockRequest.status == request_status)
    return db.scalars(statement.order_by(RestockRequest.id.desc())).all()


@router.patch(
    "/requests/{request_id}/status",
    response_model=RestockRequestResponse,
)
def update_restock_request_status(
    supplier_id: int,
    request_id: int,
    status_data: RestockRequestStatusUpdate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    restock_request = db.scalar(
        select(RestockRequest)
        .options(selectinload(RestockRequest.items))
        .where(
            RestockRequest.id == request_id,
            RestockRequest.supplier_id == supplier_id,
        )
    )
    if restock_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restock request not found",
        )
    allowed_transitions = {
        "Pending Supplier Approval": {
            "Accepted & Preparing",
            "Declined",
        },
        "Accepted & Preparing": {"Dispatched"},
    }
    if status_data.status not in allowed_transitions.get(
        restock_request.status,
        set(),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change request status from {restock_request.status} to {status_data.status}",
        )
    restock_request.status = status_data.status
    db.commit()
    db.refresh(restock_request)
    return restock_request


@router.post(
    "/deliveries",
    response_model=DeliveryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_delivery(
    supplier_id: int,
    delivery_data: DeliveryCreate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    branch = _require_branch(db, delivery_data.branch_id)
    request_no = None
    if delivery_data.request_id is not None:
        restock_request = db.scalar(
            select(RestockRequest).where(
                RestockRequest.id == delivery_data.request_id,
                RestockRequest.supplier_id == supplier_id,
            )
        )
        if restock_request is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Restock request not found",
            )
        request_no = restock_request.request_no

    total_units = 0
    total_value = Decimal("0.00")
    for item in delivery_data.items:
        product = _get_product(db, supplier_id, item.product_id)
        if product.available_stock < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Only {product.available_stock} units are available for SKU {product.sku}",
            )
        product.available_stock -= item.quantity
        product.status = _stock_status(product.available_stock)
        total_units += item.quantity
        total_value += product.wholesale_price * item.quantity

    if not delivery_data.items:
        if delivery_data.total_units is None or delivery_data.total_value is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Provide delivery items or both total_units and total_value",
            )
        total_units = delivery_data.total_units
        total_value = delivery_data.total_value

    dispatch = DeliveryDispatch(
        supplier_id=supplier_id,
        branch_id=branch.id,
        request_id=delivery_data.request_id,
        request_no=request_no,
        dispatch_no=delivery_data.dispatch_no,
        carrier=delivery_data.carrier,
        tracking_number=delivery_data.tracking_number,
        dispatch_date=delivery_data.dispatch_date,
        estimated_arrival=delivery_data.estimated_arrival,
        total_units=total_units,
        total_value=total_value,
        status="Dispatched",
        driver_name=delivery_data.driver_name,
        driver_phone=delivery_data.driver_phone,
    )
    db.add(dispatch)
    try:
        db.commit()
        db.refresh(dispatch)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A delivery with this dispatch number already exists",
        )
    return dispatch


@router.get(
    "/deliveries",
    response_model=list[DeliveryResponse],
)
def get_deliveries(
    supplier_id: int,
    delivery_status: DeliveryStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    statement = select(DeliveryDispatch).where(
        DeliveryDispatch.supplier_id == supplier_id
    )
    if delivery_status:
        statement = statement.where(DeliveryDispatch.status == delivery_status)
    return db.scalars(statement.order_by(DeliveryDispatch.id.desc())).all()


@router.patch(
    "/deliveries/{delivery_id}/status",
    response_model=DeliveryResponse,
)
def update_delivery_status(
    supplier_id: int,
    delivery_id: int,
    status_data: DeliveryStatusUpdate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    delivery = db.scalar(
        select(DeliveryDispatch).where(
            DeliveryDispatch.id == delivery_id,
            DeliveryDispatch.supplier_id == supplier_id,
        )
    )
    if delivery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )
    delivery.status = status_data.status
    db.commit()
    db.refresh(delivery)
    return delivery


@router.post(
    "/returns",
    response_model=ReturnedProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_return(
    supplier_id: int,
    return_data: ReturnedProductCreate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    _require_branch(db, return_data.branch_id)
    product = _get_product(db, supplier_id, return_data.product_id)
    returned_product = ReturnedProduct(
        supplier_id=supplier_id,
        branch_id=return_data.branch_id,
        product_id=product.id,
        rma_number=return_data.rma_number,
        product_name=product.name,
        sku=product.sku,
        serial_number=return_data.serial_number,
        customer_issue=return_data.customer_issue,
        return_reason=return_data.return_reason,
        warranty_valid=return_data.warranty_valid,
        status="Pending Inspection",
        resolution_notes="Received at distributor RMA warehouse. Awaiting technical bench test.",
    )
    db.add(returned_product)
    try:
        db.commit()
        db.refresh(returned_product)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A return with this RMA number already exists",
        )
    return returned_product


@router.get(
    "/returns",
    response_model=list[ReturnedProductResponse],
)
def get_returns(
    supplier_id: int,
    return_status: ReturnStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    statement = select(ReturnedProduct).where(
        ReturnedProduct.supplier_id == supplier_id
    )
    if return_status:
        statement = statement.where(ReturnedProduct.status == return_status)
    return db.scalars(statement.order_by(ReturnedProduct.id.desc())).all()


@router.patch(
    "/returns/{return_id}/status",
    response_model=ReturnedProductResponse,
)
def update_return_status(
    supplier_id: int,
    return_id: int,
    status_data: ReturnedProductStatusUpdate,
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    returned_product = db.scalar(
        select(ReturnedProduct).where(
            ReturnedProduct.id == return_id,
            ReturnedProduct.supplier_id == supplier_id,
        )
    )
    if returned_product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Returned product not found",
        )
    if returned_product.status != "Pending Inspection":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only returns pending inspection can be resolved",
        )
    returned_product.status = status_data.status
    returned_product.resolution_notes = status_data.resolution_notes
    db.commit()
    db.refresh(returned_product)
    return returned_product
