import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fpdf import FPDF
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database.connection import get_db
from app.models.supplier import Supplier
from app.models.admin import SupplierProfileExtension
from app.models.supplier_portal import (
    DeliveryDispatch,
    Notification,
    RestockRequest,
    RestockRequestItem,
    ReturnedProduct,
    ShopBranch,
    SupplierProduct,
    SupplierProductSubmission,
)
from app.schemas.supplier_portal import (
    DeliveryCreate,
    DeliveryResponse,
    DeliveryStatus,
    DeliveryStatusUpdate,
    NotificationResponse,
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
    SupplierSubmissionResponse,
)
from app.security import require_admin, require_supplier_access


router = APIRouter(
    prefix="/api/suppliers/{supplier_id}",
    tags=["Supplier Dashboard"],
    dependencies=[Depends(require_supplier_access)],
)

branch_router = APIRouter(
    prefix="/api/shop-branches",
    tags=["Shop Branches"],
    dependencies=[Depends(require_admin)],
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


ReportPeriod = Literal["weekly", "monthly"]


def _pdf_text(value: object) -> str:
    """Core PDF fonts only cover Latin-1; replace anything they cannot render."""
    return str(value if value is not None else "").encode("latin-1", "replace").decode("latin-1")


def _fit_pdf_cell(value: object, width: int) -> str:
    rendered = _pdf_text(value)
    return rendered if len(rendered) <= width else f"{rendered[: width - 1]}."


def _build_delivered_report_pdf(
    supplier_name: str,
    period_label: str,
    start_date: date,
    end_date: date,
    rows: list[dict],
) -> bytes:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _pdf_text("TECHNOVA - Delivered Details Report"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _pdf_text(f"Supplier: {supplier_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _pdf_text(f"Period: {period_label}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0,
        6,
        _pdf_text(f"From {start_date.isoformat()} to {end_date.isoformat()}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        _pdf_text(f"Generated: {datetime.now():%Y-%m-%d %H:%M}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    widths = (40, 34, 40, 34, 40, 30, 16, 33)
    headings = (
        "Dispatch No",
        "Reference",
        "Destination",
        "Delivered At",
        "Carrier",
        "Waybill",
        "Units",
        "Value (Rs.)",
    )
    pdf.set_fill_color(15, 23, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    for width, heading in zip(widths, headings):
        pdf.cell(width, 8, _pdf_text(heading), border=1, fill=True)
    pdf.ln(8)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    total_units = 0
    total_value = Decimal("0.00")
    for row in rows:
        delivered_at = row.get("delivered_at")
        delivered_text = (
            delivered_at.strftime("%Y-%m-%d %H:%M")
            if hasattr(delivered_at, "strftime")
            else _pdf_text(delivered_at)
        )
        cells = (
            row.get("dispatch_number"),
            row.get("reference_no"),
            row.get("branch_name"),
            delivered_text,
            row.get("carrier"),
            row.get("tracking_number"),
            row.get("total_units"),
            f"{Decimal(str(row.get('total_value') or 0)):,.2f}",
        )
        for width, value in zip(widths, cells):
            pdf.cell(width, 7, _fit_pdf_cell(value, width), border=1)
        pdf.ln(7)
        total_units += int(row.get("total_units") or 0)
        total_value += Decimal(str(row.get("total_value") or 0))

    if not rows:
        pdf.cell(0, 10, _pdf_text("No delivered dispatches in this period."), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 8, _pdf_text(f"Total deliveries: {len(rows)}    Total units: {total_units}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, _pdf_text(f"Total value: Rs. {total_value:,.2f}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


@router.get(
    "/deliveries/report.pdf",
)
def get_delivered_details_report(
    supplier_id: int,
    period: ReportPeriod = Query(default="weekly"),
    db: Session = Depends(get_db),
):
    supplier = _require_supplier(db, supplier_id)
    today = date.today()
    if period == "weekly":
        start_date = today - timedelta(days=7)
        period_label = "Weekly (last 7 days)"
    else:
        start_date = today.replace(day=1)
        period_label = "Monthly (current calendar month)"

    rows = db.execute(
        text(
            """
            SELECT d.dispatch_number,
                   COALESCE(po.po_number, rr.request_number) AS reference_no,
                   b.name AS branch_name,
                   d.delivered_at,
                   d.carrier,
                   d.tracking_number,
                   d.total_units,
                   d.total_value
            FROM deliveries d
            LEFT JOIN branches b ON b.id = d.branch_id
            LEFT JOIN purchase_orders po ON po.id = d.purchase_order_id
            LEFT JOIN restock_requests rr ON rr.id = d.request_id
            WHERE d.status = 'Delivered & Verified'
              AND d.delivered_at >= :start_date
              AND d.delivered_at < :end_date
              AND (po.supplier_id = :supplier_id OR rr.supplier_id = :supplier_id)
            ORDER BY d.delivered_at DESC
            """
        ),
        {
            "start_date": start_date,
            "end_date": today + timedelta(days=1),
            "supplier_id": supplier_id,
        },
    ).mappings().all()

    pdf_bytes = _build_delivered_report_pdf(
        supplier.company_name,
        period_label,
        start_date,
        today,
        [dict(row) for row in rows],
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="delivered-details-{period}-{today.isoformat()}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


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
    extension = db.get(SupplierProfileExtension, supplier_id)
    return {
        "id": supplier.id,
        "vendor_code": supplier.vendor_code,
        "company_name": supplier.name,
        "contact_person": supplier.contact_person,
        "email": supplier.email,
        "phone": supplier.phone,
        "street": supplier.address,
        "city": extension.city if extension else None,
        "postal_code": extension.postal_code if extension else None,
        "tax_id": supplier.tax_id,
        "contract_status": supplier.contract_status,
        "bank_name": supplier.bank_name,
        "bank_branch": supplier.bank_branch,
        "bank_account_no": supplier.bank_account_no,
        "authorized_brands": extension.authorized_brands if extension and extension.authorized_brands else [],
        "avatar_url": extension.avatar_url if extension else None,
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
    extension_values = {
        key: update_data.pop(key)
        for key in ("city", "postal_code", "authorized_brands", "avatar_url")
        if key in update_data
    }
    for field, value in update_data.items():
        setattr(supplier, field, value)
    if extension_values:
        extension = db.get(SupplierProfileExtension, supplier_id)
        if extension is None:
            extension = SupplierProfileExtension(supplier_id=supplier_id)
            db.add(extension)
        for field, value in extension_values.items():
            setattr(extension, field, value)
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


# ---------------------------------------------------------------------------
# Supplier product submissions (admin approval workflow) & notifications
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "submissions"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _submission_response(db: Session, submission: SupplierProductSubmission) -> dict:
    supplier = db.get(Supplier, submission.supplier_id)
    return {
        "id": submission.id,
        "supplier_id": submission.supplier_id,
        "supplier_name": supplier.company_name if supplier else None,
        "name": submission.name,
        "brand": submission.brand or "",
        "category_name": submission.category_name or "",
        "sku": submission.sku or "",
        "description": submission.description,
        "image_url": submission.image_url,
        "wholesale_price": submission.wholesale_price,
        "available_stock": submission.available_stock,
        "warranty_period": submission.warranty_period,
        "submission_status": submission.submission_status,
        "rejection_reason": submission.rejection_reason,
        "admin_selling_price": submission.admin_selling_price,
        "admin_category_id": submission.admin_category_id,
        "published_product_id": submission.published_product_id,
        "submitted_at": submission.submitted_at,
        "reviewed_at": submission.reviewed_at,
    }


@router.post(
    "/submissions",
    response_model=SupplierSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_supplier_submission(
    supplier_id: int,
    name: str = Form(...),
    brand: str = Form(""),
    category_name: str = Form(""),
    sku: str = Form(""),
    description: str | None = Form(None),
    wholesale_price: str = Form("0"),
    available_stock: int = Form(0),
    warranty_period: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    image_url = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            raise HTTPException(status_code=422, detail="Image must be jpg, png, webp, or gif")
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / filename
        contents = await image.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=422, detail="Image must be 5MB or smaller")
        with open(dest, "wb") as f:
            f.write(contents)
        image_url = f"/uploads/submissions/{filename}"

    try:
        price = Decimal(str(wholesale_price or "0"))
    except Exception:
        price = Decimal("0")

    submission = SupplierProductSubmission(
        supplier_id=supplier_id,
        name=name.strip(),
        brand=(brand or "").strip(),
        category_name=(category_name or "").strip(),
        sku=(sku or "").strip(),
        description=(description or "").strip() or None,
        image_url=image_url,
        wholesale_price=price,
        available_stock=max(0, int(available_stock or 0)),
        warranty_period=(warranty_period or "").strip() or None,
        submission_status="Pending",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return _submission_response(db, submission)


@router.get("/submissions", response_model=list[SupplierSubmissionResponse])
def list_supplier_submissions(
    supplier_id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    _require_supplier(db, supplier_id)
    stmt = select(SupplierProductSubmission).where(
        SupplierProductSubmission.supplier_id == supplier_id
    )
    if status_filter:
        stmt = stmt.where(SupplierProductSubmission.submission_status == status_filter)
    submissions = db.scalars(stmt.order_by(SupplierProductSubmission.id.desc())).all()
    return [_submission_response(db, s) for s in submissions]


@router.get("/notifications", response_model=list[NotificationResponse])
def list_supplier_notifications(
    supplier_id: int,
    db: Session = Depends(get_db),
):
    supplier = _require_supplier(db, supplier_id)
    stmt = select(Notification).where(
        or_(Notification.supplier_id == supplier_id, Notification.user_id == supplier.user_id)
    ).order_by(Notification.created_at.desc(), Notification.id.desc())
    return db.scalars(stmt).all()


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    supplier_id: int,
    notification_id: int,
    db: Session = Depends(get_db),
):
    supplier = _require_supplier(db, supplier_id)
    notif = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            or_(Notification.supplier_id == supplier_id, Notification.user_id == supplier.user_id),
        )
    )
    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return notif


@router.get("/me/context")
def get_supplier_context(
    supplier_id: int,
    db: Session = Depends(get_db),
):
    supplier = _require_supplier(db, supplier_id)
    unread = db.scalar(
        select(func.count()).select_from(Notification).where(
            or_(Notification.supplier_id == supplier_id, Notification.user_id == supplier.user_id),
            Notification.is_read.is_(False),
        )
    )
    return {
        "supplier_id": supplier.id,
        "company_name": supplier.company_name,
        "contact_person": supplier.contact_person,
        "email": supplier.email,
        "unread_notifications": int(unread or 0),
    }


@router.get("/me/dashboard-summary")
def get_supplier_dashboard_summary(
    supplier_id: int,
    db: Session = Depends(get_db),
):
    supplier = _require_supplier(db, supplier_id)
    extension = db.get(SupplierProfileExtension, supplier_id)
    unread = db.scalar(
        select(func.count()).select_from(Notification).where(
            or_(Notification.supplier_id == supplier_id, Notification.user_id == supplier.user_id),
            Notification.is_read.is_(False),
        )
    )
    metrics = db.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM supplier_products
                 WHERE supplier_id = :supplier_id) AS products_catalogued,
                (SELECT COUNT(*) FROM deliveries d
                 WHERE d.status = 'Delivered & Verified'
                   AND (
                     EXISTS (SELECT 1 FROM purchase_orders po
                             WHERE po.id = d.purchase_order_id
                               AND po.supplier_id = :supplier_id)
                     OR EXISTS (SELECT 1 FROM restock_requests rr
                                WHERE rr.id = d.request_id
                                  AND rr.supplier_id = :supplier_id)
                   )) AS deliveries_to_date,
                (SELECT COALESCE(SUM(d.total_units), 0) FROM deliveries d
                 WHERE d.status = 'Delivered & Verified'
                   AND (
                     EXISTS (SELECT 1 FROM purchase_orders po
                             WHERE po.id = d.purchase_order_id
                               AND po.supplier_id = :supplier_id)
                     OR EXISTS (SELECT 1 FROM restock_requests rr
                                WHERE rr.id = d.request_id
                                  AND rr.supplier_id = :supplier_id)
                   )) AS units_supplied_to_date,
                (SELECT COALESCE(SUM(d.total_value), 0) FROM deliveries d
                 WHERE d.status = 'Delivered & Verified'
                   AND (
                     EXISTS (SELECT 1 FROM purchase_orders po
                             WHERE po.id = d.purchase_order_id
                               AND po.supplier_id = :supplier_id)
                     OR EXISTS (SELECT 1 FROM restock_requests rr
                                WHERE rr.id = d.request_id
                                  AND rr.supplier_id = :supplier_id)
                   )) AS value_supplied_to_date,
                (SELECT COUNT(*) FROM product_returns
                 WHERE supplier_id = :supplier_id) AS returns_to_date,
                (SELECT COUNT(*) FROM restock_requests
                 WHERE supplier_id = :supplier_id
                   AND status = 'Pending Supplier Approval') AS pending_requests
            """
        ),
        {"supplier_id": supplier_id},
    ).mappings().one()

    return {
        "supplier_id": supplier.id,
        "company_name": supplier.company_name,
        "contact_person": supplier.contact_person,
        "email": supplier.email,
        "phone": supplier.phone,
        "address": supplier.address,
        "vendor_code": supplier.vendor_code,
        "rating": float(supplier.rating) if supplier.rating is not None else None,
        "contract_status": supplier.contract_status,
        "city": extension.city if extension else None,
        "unread_notifications": int(unread or 0),
        "products_catalogued": int(metrics["products_catalogued"]),
        "deliveries_to_date": int(metrics["deliveries_to_date"]),
        "units_supplied_to_date": int(metrics["units_supplied_to_date"]),
        "value_supplied_to_date": float(metrics["value_supplied_to_date"]),
        "returns_to_date": int(metrics["returns_to_date"]),
        "pending_requests": int(metrics["pending_requests"]),
    }
