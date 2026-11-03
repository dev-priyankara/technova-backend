from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.admin import (
    AIEngineSettings,
    AIRecommendationLog,
    AdminProfileExtension,
    AdminSavedReport,
    CustomerAddress,
    InventoryTransaction,
    Order,
    OrderItem,
    Payment,
    PurchaseOrder,
    PurchaseOrderItem,
    Role,
    SupplierCategory,
    User,
)
from app.models.category import Category
from app.models.product import Product
from app.models.supplier import Supplier
from app.schemas.admin import (
    AIEngineSettingsUpdate,
    AIRecommendationCreate,
    AIRecommendationUpdate,
    AdminOrderCreate,
    AdminOrderUpdate,
    AdminOrderStatusUpdate,
    AdminCustomerCreate,
    AdminProfileUpdate,
    AdminPasswordUpdate,
    AdminSupplierCreate,
    AdminSupplierUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    POSSaleCreate,
    POSSaleUpdate,
    PurchaseOrderCreate,
    SavedReportCreate,
    SavedReportUpdate,
)
from app.security import (
    SESSION_COOKIE,
    hash_password,
    require_admin,
    require_order_access,
    revoke_other_sessions,
    verify_password,
)


router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin)])
orders_router = APIRouter(tags=["Orders"])

ROLE_IDS = {"Admin": 1, "Supplier": 2, "Cashier": 3, "Customer": 4}
ROLE_NAMES = {role_id: name for name, role_id in ROLE_IDS.items()}


def _role_name(db: Session, role_id: int) -> str:
    role = db.get(Role, role_id)
    return role.name if role else ROLE_NAMES.get(role_id, "Customer")


def _customer_metrics(db: Session, user_id: int) -> tuple[int, Decimal]:
    count, total = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0),
        ).where(
            Order.customer_id == user_id,
            Order.status != "Cancelled",
        )
    ).one()
    return int(count or 0), Decimal(total or 0)


def _user_json(db: Session, user: User) -> dict:
    role_name = _role_name(db, user.role_id)
    address = db.scalar(
        select(CustomerAddress)
        .where(CustomerAddress.user_id == user.id)
        .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id.desc())
        .limit(1)
    )
    orders_count, total_spent = _customer_metrics(db, user.id)
    return {
        "id": user.id,
        "role_id": user.role_id,
        "role": role_name,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "status": user.status,
        "created_at": user.created_at,
        "city": address.city if address else None,
        "orders_count": orders_count,
        "total_spent": total_spent,
    }


def _resolve_role_id(db: Session, role: str | None, role_id: int | None) -> int:
    requested_id = role_id if role_id is not None else ROLE_IDS.get(role or "")
    if requested_id is None:
        raise HTTPException(status_code=422, detail="A valid user role is required")
    role_record = db.get(Role, requested_id)
    if role_record is None:
        raise HTTPException(status_code=422, detail="The selected role does not exist")
    if role and role_record.name != role:
        raise HTTPException(status_code=422, detail="Role name and role_id do not match")
    return requested_id


def _find_order(db: Session, order_key: str) -> Order:
    order = db.scalar(
        select(Order).where(
            or_(Order.order_number == order_key, Order.id == _numeric_id(order_key))
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def _numeric_id(value: str) -> int:
    return int(value) if value.isdigit() else -1


def _order_json(db: Session, order: Order) -> dict:
    items = db.scalars(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
    ).all()
    return {
        "id": order.order_number,
        "order_id": order.id,
        "date": order.created_at,
        "created_at": order.created_at,
        "total": order.total,
        "subtotal": order.subtotal,
        "discount": order.discount,
        "status": order.status,
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "source": order.source,
        "recipient_name": order.recipient_name,
        "phone": order.phone,
        "shipping_address": {
            "recipient_name": order.recipient_name,
            "phone": order.phone,
            "street": order.street,
            "city": order.city,
            "district": order.district,
            "postal_code": order.postal_code,
        },
        "items": [
            {
                "product_id": item.product_id,
                "name": item.product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
            }
            for item in items
        ],
    }


def _create_payment(db: Session, order: Order) -> None:
    payment_status = "Paid" if order.payment_status == "Paid" else "Pending"
    db.add(
        Payment(
            order_id=order.id,
            method=order.payment_method or "Cash",
            amount=order.total,
            status=payment_status,
            paid_at=datetime.now() if payment_status == "Paid" else None,
        )
    )


def _supplier_json(db: Session, supplier: Supplier) -> dict:
    categories = db.scalars(
        select(Category.name)
        .join(SupplierCategory, SupplierCategory.category_id == Category.id)
        .where(SupplierCategory.supplier_id == supplier.id)
        .order_by(Category.name)
    ).all()
    pending = db.scalar(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.supplier_id == supplier.id,
            PurchaseOrder.status.in_(("Draft", "Sent", "Acknowledged")),
        )
    )
    return {
        "id": supplier.id,
        "company_name": supplier.company_name,
        "contact_person": supplier.contact_person,
        "email": supplier.email,
        "phone": supplier.phone or "",
        "address": supplier.address,
        "supplied_categories": categories,
        "pending_requests": int(pending or 0),
        "status": supplier.status,
        "created_at": supplier.created_at,
    }


def _set_supplier_categories(db: Session, supplier_id: int, names: list[str]) -> None:
    categories = []
    for name in dict.fromkeys(item.strip() for item in names if item.strip()):
        category = db.scalar(select(Category).where(Category.name == name))
        if category is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown product category: {name}",
            )
        categories.append(category)
    db.query(SupplierCategory).filter(
        SupplierCategory.supplier_id == supplier_id
    ).delete(synchronize_session=False)
    for category in categories:
        db.add(SupplierCategory(supplier_id=supplier_id, category_id=category.id))


def _report_summary(
    db: Session,
    period: str = "Month-to-Date (MTD)",
    channel: str = "Blended (POS & Online)",
) -> dict:
    today = date.today()
    if period == "Today (Last 24h)":
        period_start = datetime.combine(today, time.min)
    elif period == "Last 7 Days":
        period_start = datetime.combine(today - timedelta(days=6), time.min)
    elif period == "Quarter 3 2026":
        period_start = datetime(2026, 7, 1)
    elif period == "Full Financial Year":
        fiscal_start_year = today.year if today.month >= 4 else today.year - 1
        period_start = datetime(fiscal_start_year, 4, 1)
    else:
        period_start = datetime.combine(today.replace(day=1), time.min)
    period_end = datetime(2026, 10, 1) if period == "Quarter 3 2026" else None
    channel_source = (
        "POS" if channel == "In-Store POS Counter"
        else "Online" if channel == "Online Web Checkout"
        else None
    )
    order_filters = [
        Order.created_at >= period_start,
        Order.status != "Cancelled",
    ]
    if period_end:
        order_filters.append(Order.created_at < period_end)
    if channel_source:
        order_filters.append(Order.source == channel_source)
    revenue = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            *order_filters
        )
    )
    discounts = db.scalar(
        select(func.coalesce(func.sum(Order.discount), 0)).where(
            *order_filters
        )
    )
    order_count = db.scalar(
        select(func.count(Order.id)).where(
            *order_filters
        )
    )
    margin = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    OrderItem.line_total
                    - (OrderItem.quantity * func.coalesce(Product.cost_price, 0))
                ),
                0,
            )
        )
        .join(Order, Order.id == OrderItem.order_id)
        .outerjoin(Product, Product.id == OrderItem.product_id)
        .where(
            *order_filters
        )
    )
    channels = db.execute(
        select(Order.source, func.coalesce(func.sum(Order.total), 0))
        .where(*order_filters)
        .group_by(Order.source)
    ).all()
    categories = db.execute(
        select(
            Category.name,
            func.coalesce(func.sum(OrderItem.line_total), 0),
        )
        .join(Product, Product.category_id == Category.id)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(*order_filters)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(OrderItem.line_total).desc())
        .limit(5)
    ).all()
    total = Decimal(revenue or 0)
    return {
        "gross_sales_mtd": total,
        "gross_margin_mtd": Decimal(margin or 0),
        "discounts_mtd": Decimal(discounts or 0),
        "order_count_mtd": int(order_count or 0),
        "average_ticket": total / int(order_count) if order_count else Decimal("0"),
        "channel_breakdown": [
            {
                "channel": "In-Store POS Counter" if source == "POS" else "Online Web Checkout",
                "amount": amount,
                "percentage": round(float(amount / total * 100), 1) if total else 0,
            }
            for source, amount in channels
        ],
        "category_performance": [
            {
                "name": name,
                "sales": amount,
                "share": f"{float(amount / total * 100):.1f}%" if total else "0%",
            }
            for name, amount in categories
        ],
    }


@router.get("/api/admin/dashboard")
def get_admin_dashboard(db: Session = Depends(get_db)):
    today_start = datetime.combine(date.today(), time.min)
    month_start = datetime.combine(date.today().replace(day=1), time.min)
    today_sales = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.created_at >= today_start,
            Order.source == "POS",
            Order.status != "Cancelled",
        )
    )
    month_sales = db.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.created_at >= month_start,
            Order.status != "Cancelled",
        )
    )
    pending_orders = db.scalar(
        select(func.count(Order.id)).where(Order.status.in_(("Pending", "Processing")))
    )
    low_stock = db.scalars(
        select(Product)
        .where(
            (Product.stock_count == 0)
            | (Product.stock_count <= Product.min_stock_level)
        )
        .order_by(Product.stock_count, Product.id)
        .limit(8)
    ).all()
    recent_orders = db.scalars(
        select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(8)
    ).all()
    low_stock_total = db.scalar(
        select(func.count(Product.id)).where(
            Product.stock_count > 0,
            Product.stock_count <= Product.min_stock_level,
        )
    )
    out_of_stock = db.scalar(
        select(func.count(Product.id)).where(Product.stock_count == 0)
    )
    return {
        "today_sales": today_sales,
        "month_sales": month_sales,
        "pending_orders": pending_orders,
        "low_stock_count": low_stock_total,
        "out_of_stock_count": out_of_stock,
        "total_products": db.scalar(select(func.count(Product.id))),
        "total_customers": db.scalar(
            select(func.count(User.id)).where(User.role_id == ROLE_IDS["Customer"])
        ),
        "recent_orders": [_order_json(db, order) for order in recent_orders],
        "recent_pos_sales": get_pos_sales(db)[:8],
        "low_stock_products": [
            {
                "id": item.id,
                "name": item.name,
                "sku": item.sku,
                "stock_count": item.stock_count,
                "min_stock_level": item.min_stock_level,
            }
            for item in low_stock
        ],
        **_report_summary(db),
    }


@router.get("/api/users")
def get_users(
    search: str | None = Query(default=None, min_length=1, max_length=150),
    db: Session = Depends(get_db),
):
    statement = select(User).order_by(User.id.desc())
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(User.name.ilike(pattern), User.email.ilike(pattern), User.phone.ilike(pattern))
        )
    return [_user_json(db, user) for user in db.scalars(statement).all()]


@router.post("/api/users", status_code=status.HTTP_201_CREATED)
def create_user(user_data: AdminUserCreate, db: Session = Depends(get_db)):
    role_id = _resolve_role_id(db, user_data.role, user_data.role_id)
    if db.scalar(select(User.id).where(User.email == user_data.email)):
        raise HTTPException(status_code=409, detail="Email address is already registered")
    user = User(
        role_id=role_id,
        name=user_data.name,
        email=user_data.email,
        phone=user_data.phone,
        password_hash=hash_password(user_data.tempPassword),
    )
    db.add(user)
    try:
        db.flush()
        if role_id == ROLE_IDS["Supplier"]:
            supplier = db.scalar(select(Supplier).where(Supplier.email == user.email))
            if supplier is not None and supplier.user_id is None:
                supplier.user_id = user.id
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create the user") from None
    return _user_json(db, user)


@router.patch("/api/users/{user_id}")
def update_user(
    user_id: int,
    update: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    values = update.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    if user.id == current_admin.id and (
        values.get("status") == "Inactive"
        or values.get("role_id") not in (None, ROLE_IDS["Admin"])
        or values.get("role") not in (None, "Admin")
    ):
        raise HTTPException(status_code=400, detail="You cannot remove your own administrator access")
    previous_role_id = user.role_id
    if "role" in values or "role_id" in values:
        user.role_id = _resolve_role_id(db, values.pop("role", None), values.pop("role_id", None))
    city = values.pop("city", None)
    for field in ("name", "email", "phone", "status"):
        if field in values:
            setattr(user, field, values[field])
    linked_supplier = db.scalar(select(Supplier).where(Supplier.user_id == user.id))
    if previous_role_id == ROLE_IDS["Supplier"] and user.role_id != ROLE_IDS["Supplier"]:
        if linked_supplier is not None:
            linked_supplier.user_id = None
    elif user.role_id == ROLE_IDS["Supplier"]:
        matching_supplier = db.scalar(select(Supplier).where(Supplier.email == user.email))
        if matching_supplier is not None:
            if matching_supplier.user_id not in (None, user.id):
                raise HTTPException(status_code=409, detail="Supplier is linked to another user account")
            matching_supplier.user_id = user.id
    if city is not None:
        address = db.scalar(
            select(CustomerAddress)
            .where(CustomerAddress.user_id == user.id)
            .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id.desc())
            .limit(1)
        )
        if address is None:
            address = CustomerAddress(
                user_id=user.id,
                recipient_name=user.name,
                phone=user.phone,
                street="",
                city=city,
                is_default=1,
            )
            db.add(address)
        else:
            address.city = city
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email address is already in use") from None
    return _user_json(db, user)


@router.patch("/api/users/{user_id}/toggle-status")
def toggle_user_status(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "Inactive" if user.status == "Active" else "Active"
    db.commit()
    db.refresh(user)
    return _user_json(db, user)


@router.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if user.role_id == ROLE_IDS["Admin"]:
        admin_count = db.scalar(
            select(func.count(User.id)).where(User.role_id == ROLE_IDS["Admin"])
        )
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="The last administrator cannot be deleted")
    db.delete(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This user has related business records and cannot be deleted",
        ) from None
    return {"message": "User deleted", "user_id": user_id}


@router.get("/api/customers")
def get_customers(db: Session = Depends(get_db)):
    customers = db.scalars(
        select(User)
        .where(User.role_id == ROLE_IDS["Customer"])
        .order_by(User.created_at.desc(), User.id.desc())
    ).all()
    return [_user_json(db, user) for user in customers]


@router.post("/api/customers", status_code=status.HTTP_201_CREATED)
def create_customer(data: AdminCustomerCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise HTTPException(status_code=409, detail="Email address is already registered")
    customer = User(
        role_id=ROLE_IDS["Customer"],
        name=data.name,
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.tempPassword),
    )
    db.add(customer)
    db.flush()
    db.add(
        CustomerAddress(
            user_id=customer.id,
            recipient_name=customer.name,
            phone=customer.phone,
            street="",
            city=data.city,
            is_default=1,
        )
    )
    try:
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create customer") from None
    return _user_json(db, customer)


@router.get("/api/admin/orders")
def get_admin_orders(
    search: str | None = Query(default=None, min_length=1, max_length=150),
    db: Session = Depends(get_db),
):
    statement = select(Order).order_by(Order.created_at.desc(), Order.id.desc())
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Order.order_number.ilike(pattern),
                Order.recipient_name.ilike(pattern),
                Order.phone.ilike(pattern),
            )
        )
    return [_order_json(db, order) for order in db.scalars(statement).all()]


@orders_router.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: AdminOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_order_access),
):
    is_admin = current_user.role_id == ROLE_IDS["Admin"]
    is_customer = current_user.role_id == ROLE_IDS["Customer"]
    is_cashier = current_user.role_id == ROLE_IDS["Cashier"]
    customer = None
    if is_customer:
        customer = current_user
    elif is_admin and order_data.customer_email:
        customer = db.scalar(select(User).where(User.email == order_data.customer_email))
    address = order_data.shipping_address
    order_items = list(order_data.items)
    if is_admin and not order_items and order_data.total_amount is not None:
        order_items = [
            {
                "product_id": None,
                "product_name": order_data.items_summary or "Manual Hardware Order",
                "quantity": 1,
                "unit_price": order_data.total_amount,
            }
        ]
    if not is_admin and not order_items:
        raise HTTPException(status_code=422, detail="Orders must contain catalog products")
    prepared_items = []
    subtotal = Decimal("0.00")
    for item in order_items:
        product_id = item.product_id if hasattr(item, "product_id") else item["product_id"]
        product = (
            db.scalar(select(Product).where(Product.id == product_id).with_for_update())
            if product_id
            else None
        )
        quantity = item.quantity if hasattr(item, "quantity") else item["quantity"]
        supplied_price = item.unit_price if hasattr(item, "unit_price") else item.get("unit_price")
        product_name = (
            item.product_name if hasattr(item, "product_name") else item.get("product_name")
        )
        if product_id is not None and product is None:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        if not is_admin:
            if product is None:
                raise HTTPException(status_code=422, detail="Orders must contain catalog products")
            if product.status != "Active":
                raise HTTPException(status_code=409, detail=f"Product {product.name} is inactive")
            if product.stock_count < quantity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Insufficient stock for product {product.name}",
                )
            unit_price = Decimal(product.price)
            stock_before = product.stock_count
            product.stock_count -= quantity
            db.add(
                InventoryTransaction(
                    product_id=product.id,
                    user_id=current_user.id,
                    change_qty=-quantity,
                    stock_before=stock_before,
                    stock_after=product.stock_count,
                    reason="Order sale",
                    reference_type="order",
                    notes="Stock reserved for authenticated order",
                )
            )
        else:
            unit_price = supplied_price or (Decimal(product.price) if product else None)
            if unit_price is None:
                raise HTTPException(status_code=422, detail="Each manual item requires a unit price")
        subtotal += unit_price * quantity
        prepared_items.append((product, product_name, quantity, unit_price))

    discount = (
        (subtotal * Decimal("0.02")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if is_cashier and subtotal > Decimal("400000")
        else Decimal("0.00")
    )
    shipping_fee = (
        Decimal("1500.00")
        if is_customer and Decimal("0.00") < subtotal <= Decimal("50000")
        else Decimal("0.00")
    )
    order = Order(
        order_number=f"ORD-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer.id if customer else None,
        cashier_id=current_user.id if is_cashier else None,
        source="POS" if is_cashier else "Online",
        status="Delivered" if is_cashier else "Pending" if not is_admin else order_data.status,
        payment_status="Paid" if is_cashier else "Pending" if not is_admin else order_data.payment_status,
        payment_method=order_data.payment_method,
        subtotal=subtotal,
        discount=discount,
        shipping_fee=shipping_fee,
        total=(
            order_data.total_amount
            if is_admin and order_data.total_amount is not None
            else subtotal - discount + shipping_fee
        ),
        recipient_name=(current_user.name if is_customer else address.get("recipient_name")) or "Guest Customer",
        phone=current_user.phone if is_customer else address.get("phone"),
        street=address.get("street"),
        city=address.get("city"),
        district=address.get("district"),
        postal_code=address.get("postal_code"),
    )
    db.add(order)
    db.flush()
    for product, product_name, quantity, unit_price in prepared_items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id if product else None,
                product_name=product.name if product else (product_name or order_data.items_summary or "Manual Item"),
                sku=product.sku if product else None,
                quantity=quantity,
                unit_price=unit_price,
                line_total=unit_price * quantity,
                warranty=product.warranty if product else None,
            )
        )
    for transaction in db.new:
        if isinstance(transaction, InventoryTransaction) and transaction.reference_type == "order":
            transaction.reference_id = order.id
    db.flush()
    _create_payment(db, order)
    try:
        db.commit()
        db.refresh(order)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create order") from None
    return _order_json(db, order)


@router.patch("/api/orders/{order_key}/status")
def update_order_status(
    order_key: str,
    update: AdminOrderStatusUpdate,
    db: Session = Depends(get_db),
):
    order = _find_order(db, order_key)
    order.status = update.status
    if update.payment_status is not None:
        order.payment_status = update.payment_status
        payments = db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
        for payment in payments:
            payment.status = "Paid" if update.payment_status == "Paid" else (
                "Refunded" if update.payment_status == "Refunded" else "Pending"
            )
    db.commit()
    db.refresh(order)
    return _order_json(db, order)


@router.patch("/api/orders/{order_key}")
def update_order(
    order_key: str,
    update: AdminOrderUpdate,
    db: Session = Depends(get_db),
):
    order = _find_order(db, order_key)
    values = update.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    item_changes = "items_summary" in values or "total_amount" in values
    items: list[OrderItem] = []
    if item_changes:
        items = db.scalars(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
        ).all()
        if len(items) != 1:
            raise HTTPException(
                status_code=409,
                detail="Item details can only be edited for single-line manual orders",
            )
    if "customer_name" in values:
        order.recipient_name = values["customer_name"]
    if "phone" in values:
        order.phone = values["phone"]
    if "status" in values:
        order.status = values["status"]
    if "payment_status" in values:
        order.payment_status = values["payment_status"]
        for payment in db.scalars(select(Payment).where(Payment.order_id == order.id)).all():
            payment.status = (
                "Paid" if values["payment_status"] == "Paid"
                else "Refunded" if values["payment_status"] == "Refunded"
                else "Pending"
            )
    if item_changes:
        item = items[0]
        if "items_summary" in values:
            item.product_name = values["items_summary"]
        if "total_amount" in values:
            order.total = values["total_amount"]
            order.subtotal = values["total_amount"] + order.discount
            item.line_total = order.subtotal
            item.unit_price = order.subtotal / item.quantity
            for payment in db.scalars(select(Payment).where(Payment.order_id == order.id)).all():
                payment.amount = order.total
    db.commit()
    db.refresh(order)
    return _order_json(db, order)


@router.delete("/api/orders/{order_key}")
def cancel_order(order_key: str, db: Session = Depends(get_db)):
    order = _find_order(db, order_key)
    order.status = "Cancelled"
    db.commit()
    return {"message": "Order cancelled", "id": order.order_number}


@router.get("/api/admin/pos/sales")
def get_pos_sales(db: Session = Depends(get_db)):
    orders = db.scalars(
        select(Order)
        .where(Order.source == "POS", Order.status != "Cancelled")
        .order_by(Order.created_at.desc(), Order.id.desc())
    ).all()
    results = []
    for order in orders:
        items_count = db.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0)).where(
                OrderItem.order_id == order.id
            )
        )
        cashier = db.get(User, order.cashier_id) if order.cashier_id else None
        results.append(
            {
                "id": order.id,
                "receipt_no": order.order_number,
                "date": order.created_at,
                "cashier_name": cashier.name if cashier else order.recipient_name,
                "subtotal": order.subtotal,
                "discount": order.discount,
                "final_amount": order.total,
                "payment_method": order.payment_method,
                "items_count": int(items_count or 0),
                "status": order.status,
            }
        )
    return results


@router.post("/api/admin/pos/sales", status_code=status.HTTP_201_CREATED)
def create_pos_sale(sale: POSSaleCreate, db: Session = Depends(get_db)):
    discount = (
        (sale.subtotal * Decimal("0.02")).quantize(Decimal("0.01"))
        if sale.subtotal > Decimal("400000")
        else Decimal("0.00")
    )
    total = sale.subtotal - discount
    cashier = db.scalar(
        select(User).where(
            User.name == sale.cashier_name,
            User.role_id == ROLE_IDS["Cashier"],
        )
    )
    order = Order(
        order_number=f"POS-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        cashier_id=cashier.id if cashier else None,
        source="POS",
        status="Delivered",
        payment_status="Paid",
        payment_method=sale.payment_method,
        subtotal=sale.subtotal,
        discount=discount,
        shipping_fee=Decimal("0.00"),
        total=total,
        recipient_name=sale.cashier_name,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            product_name="Manual POS Sale",
            quantity=sale.items_count,
            unit_price=sale.subtotal / sale.items_count if sale.items_count else sale.subtotal,
            line_total=sale.subtotal,
        )
    )
    _create_payment(db, order)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "receipt_no": order.order_number,
        "date": order.created_at,
        "cashier_name": sale.cashier_name,
        "subtotal": order.subtotal,
        "discount": order.discount,
        "final_amount": order.total,
        "payment_method": order.payment_method,
        "items_count": sale.items_count,
        "status": order.status,
    }


@router.patch("/api/admin/pos/sales/{sale_id}")
def update_pos_sale(sale_id: int, update: POSSaleUpdate, db: Session = Depends(get_db)):
    order = db.get(Order, sale_id)
    if order is None or order.source != "POS":
        raise HTTPException(status_code=404, detail="POS transaction not found")
    if order.status == "Cancelled":
        raise HTTPException(status_code=409, detail="Voided transactions cannot be edited")
    if update.cashier_name is not None:
        cashier = db.scalar(
            select(User).where(
                User.name == update.cashier_name,
                User.role_id == ROLE_IDS["Cashier"],
            )
        )
        order.cashier_id = cashier.id if cashier else None
        order.recipient_name = update.cashier_name
    if update.items_count is not None:
        item = db.scalar(select(OrderItem).where(OrderItem.order_id == order.id))
        if item is not None:
            item.quantity = update.items_count
            item.unit_price = order.subtotal / update.items_count
    if update.payment_method is not None:
        order.payment_method = update.payment_method
        for payment in db.scalars(select(Payment).where(Payment.order_id == order.id)).all():
            payment.method = update.payment_method
    db.commit()
    db.refresh(order)
    return {"id": order.id, "receipt_no": order.order_number}


@router.post("/api/admin/pos/sales/{sale_id}/void")
def void_pos_sale(sale_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, sale_id)
    if order is None or order.source != "POS":
        raise HTTPException(status_code=404, detail="POS transaction not found")
    if order.status == "Cancelled":
        raise HTTPException(status_code=409, detail="Transaction is already voided")
    order.status = "Cancelled"
    order.payment_status = "Refunded"
    for payment in db.scalars(select(Payment).where(Payment.order_id == order.id)).all():
        payment.status = "Refunded"
    db.commit()
    return {"message": "POS transaction voided", "id": sale_id}


@router.get("/api/admin/inventory/transactions")
def get_inventory_transactions(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    transactions = db.scalars(
        select(InventoryTransaction)
        .order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())
        .limit(limit)
    ).all()
    result = []
    for transaction in transactions:
        product = db.get(Product, transaction.product_id)
        result.append(
            {
                "id": transaction.id,
                "product_id": transaction.product_id,
                "product_name": product.name if product else "Deleted product",
                "sku": product.sku if product else "",
                "change": transaction.change_qty,
                "resulting_stock": transaction.stock_after,
                "reason": transaction.reason,
                "notes": transaction.notes,
                "created_at": transaction.created_at,
            }
        )
    return result


@router.get("/api/admin/ai/settings")
def get_ai_settings(db: Session = Depends(get_db)):
    settings = db.get(AIEngineSettings, 1)
    return {
        "id": 1,
        "budget_tolerance_pct": settings.budget_tolerance_pct if settings else Decimal("10.00"),
        "creativity_mode": settings.creativity_mode if settings else "Strict Catalogue Matches",
        "stock_constraint": settings.stock_constraint if settings else "Strict In-Stock Only",
        "min_confidence_score": settings.min_confidence_score if settings else Decimal("85.00"),
        "is_active": bool(settings.is_active) if settings else True,
    }


@router.put("/api/admin/ai/settings")
def update_ai_settings(
    update: AIEngineSettingsUpdate,
    db: Session = Depends(get_db),
):
    settings = db.get(AIEngineSettings, 1)
    if settings is None:
        settings = AIEngineSettings(id=1)
        db.add(settings)
    for key, value in update.model_dump().items():
        setattr(settings, key, int(value) if key == "is_active" else value)
    db.commit()
    db.refresh(settings)
    return get_ai_settings(db)


@router.get("/api/admin/ai/logs")
def get_ai_logs(db: Session = Depends(get_db)):
    logs = db.scalars(
        select(AIRecommendationLog)
        .order_by(AIRecommendationLog.created_at.desc(), AIRecommendationLog.id.desc())
    ).all()
    return [
        {
            "id": log.id,
            "timestamp": log.created_at,
            "budget": log.budget,
            "intent": log.intent or "",
            "recommended": log.recommended or "",
            "outcome": log.outcome or "",
            "status": log.status,
            "reasoning": log.reasoning,
        }
        for log in logs
    ]


@router.post("/api/admin/ai/logs", status_code=status.HTTP_201_CREATED)
def create_ai_log(log_data: AIRecommendationCreate, db: Session = Depends(get_db)):
    log = AIRecommendationLog(**log_data.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id, "timestamp": log.created_at}


@router.patch("/api/admin/ai/logs/{log_id}")
def update_ai_log(
    log_id: int,
    update: AIRecommendationUpdate,
    db: Session = Depends(get_db),
):
    log = db.get(AIRecommendationLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="AI telemetry log not found")
    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(log, key, value)
    db.commit()
    db.refresh(log)
    return {"id": log.id, "timestamp": log.created_at}


@router.delete("/api/admin/ai/logs/{log_id}")
def delete_ai_log(log_id: int, db: Session = Depends(get_db)):
    log = db.get(AIRecommendationLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="AI telemetry log not found")
    db.delete(log)
    db.commit()
    return {"message": "AI telemetry log deleted"}


@router.delete("/api/admin/ai/logs")
def clear_ai_logs(db: Session = Depends(get_db)):
    db.query(AIRecommendationLog).delete(synchronize_session=False)
    db.commit()
    return {"message": "AI telemetry logs cleared"}


@router.get("/api/admin/profile")
def get_admin_profile(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    extension = db.get(AdminProfileExtension, admin.id)
    return {
        "id": admin.id,
        "name": admin.name,
        "email": admin.email,
        "phone": admin.phone or "",
        "role": "Super Admin (POS & Ops)",
        "street": extension.street if extension else "",
        "city": extension.city if extension else "",
        "postal_code": extension.postal_code if extension else "",
        "avatar_url": extension.avatar_url if extension else "",
    }


@router.put("/api/admin/profile")
def update_admin_profile(
    update: AdminProfileUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    admin.name = update.name
    admin.email = update.email
    admin.phone = update.phone
    extension = db.get(AdminProfileExtension, admin.id)
    if extension is None:
        extension = AdminProfileExtension(user_id=admin.id)
        db.add(extension)
    extension.street = update.street
    extension.city = update.city
    extension.postal_code = update.postal_code
    extension.avatar_url = update.avatar_url
    try:
        db.commit()
        db.refresh(admin)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Profile email is already in use") from None
    extension = db.get(AdminProfileExtension, admin.id)
    return {
        "id": admin.id,
        "name": admin.name,
        "email": admin.email,
        "phone": admin.phone or "",
        "role": "Super Admin (POS & Ops)",
        "street": extension.street if extension else "",
        "city": extension.city if extension else "",
        "postal_code": extension.postal_code if extension else "",
        "avatar_url": extension.avatar_url if extension else "",
    }


@router.put("/api/admin/password")
def update_admin_password(
    update: AdminPasswordUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not verify_password(update.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    admin.password_hash = hash_password(update.new_password)
    revoke_other_sessions(db, admin.id, request.cookies.get(SESSION_COOKIE))
    db.commit()
    return {"message": "Administrator password updated"}


@router.get("/api/admin/suppliers")
def get_admin_suppliers(db: Session = Depends(get_db)):
    suppliers = db.scalars(select(Supplier).order_by(Supplier.id.desc())).all()
    return [_supplier_json(db, supplier) for supplier in suppliers]


@router.post("/api/admin/suppliers", status_code=status.HTTP_201_CREATED)
def create_admin_supplier(
    supplier_data: AdminSupplierCreate,
    db: Session = Depends(get_db),
):
    supplier = Supplier(
        company_name=supplier_data.company_name,
        contact_person=supplier_data.contact_person,
        email=supplier_data.email,
        phone=supplier_data.phone,
        address=supplier_data.address,
        status=supplier_data.status,
        user_id=db.scalar(
            select(User.id).where(
                User.email == supplier_data.email,
                User.role_id == ROLE_IDS["Supplier"],
            )
        ),
    )
    db.add(supplier)
    try:
        db.flush()
        _set_supplier_categories(db, supplier.id, supplier_data.supplied_categories)
        db.commit()
        db.refresh(supplier)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Supplier email already exists") from None
    return _supplier_json(db, supplier)


@router.patch("/api/admin/suppliers/{supplier_id}")
def update_admin_supplier(
    supplier_id: int,
    update: AdminSupplierUpdate,
    db: Session = Depends(get_db),
):
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    values = update.model_dump(exclude_unset=True)
    category_names = values.pop("supplied_categories", None)
    for key, value in values.items():
        setattr(supplier, key, value)
    if category_names is not None:
        _set_supplier_categories(db, supplier.id, category_names)
    try:
        db.commit()
        db.refresh(supplier)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Supplier email already exists") from None
    return _supplier_json(db, supplier)


@router.delete("/api/admin/suppliers/{supplier_id}")
def delete_admin_supplier(supplier_id: int, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    db.delete(supplier)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Supplier has related purchase records and cannot be deleted",
        ) from None
    return {"message": "Supplier deleted"}


@router.get("/api/admin/purchase-orders")
def get_purchase_orders(db: Session = Depends(get_db)):
    orders = db.scalars(
        select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    ).all()
    result = []
    for purchase_order in orders:
        supplier = db.get(Supplier, purchase_order.supplier_id)
        items = db.scalars(
            select(PurchaseOrderItem).where(
                PurchaseOrderItem.purchase_order_id == purchase_order.id
            )
        ).all()
        result.append(
            {
                "id": purchase_order.id,
                "po_number": purchase_order.po_number,
                "supplier_id": purchase_order.supplier_id,
                "supplier_name": supplier.company_name if supplier else "Deleted supplier",
                "status": purchase_order.status,
                "urgency": purchase_order.urgency,
                "total": purchase_order.total,
                "created_at": purchase_order.created_at,
                "items": [
                    {
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "received_qty": item.received_qty,
                        "unit_cost": item.unit_cost,
                        "line_total": item.line_total,
                    }
                    for item in items
                ],
            }
        )
    return result


@router.post("/api/admin/purchase-orders", status_code=status.HTTP_201_CREATED)
def create_purchase_order(data: PurchaseOrderCreate, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, data.supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    total = data.unit_cost * data.quantity
    purchase_order = PurchaseOrder(
        po_number=f"PO-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        supplier_id=supplier.id,
        status="Sent",
        urgency=data.urgency,
        notes=data.notes,
        total=total,
    )
    db.add(purchase_order)
    db.flush()
    db.add(
        PurchaseOrderItem(
            purchase_order_id=purchase_order.id,
            product_name=data.product_name,
            quantity=data.quantity,
            received_qty=0,
            unit_cost=data.unit_cost,
            line_total=total,
        )
    )
    db.commit()
    db.refresh(purchase_order)
    return {
        "id": purchase_order.id,
        "po_number": purchase_order.po_number,
        "supplier_id": supplier.id,
        "supplier_name": supplier.company_name,
        "status": purchase_order.status,
        "urgency": purchase_order.urgency,
        "total": purchase_order.total,
        "created_at": purchase_order.created_at,
    }


@router.get("/api/admin/reports/summary")
def get_report_summary(
    period: str = Query(default="Month-to-Date (MTD)", max_length=100),
    channel: str = Query(default="Blended (POS & Online)", max_length=100),
    db: Session = Depends(get_db),
):
    return _report_summary(db, period, channel)


@router.get("/api/admin/reports")
def get_saved_reports(db: Session = Depends(get_db)):
    reports = db.scalars(
        select(AdminSavedReport).order_by(AdminSavedReport.created_at.desc())
    ).all()
    return [
        {
            "id": report.id,
            "title": report.title,
            "type": report.report_type,
            "period": report.period,
            "channel": report.channel,
            "created_at": report.created_at,
            "gross_amount": report.gross_amount,
            "status": report.status,
            "notes": report.notes or "",
        }
        for report in reports
    ]


@router.post("/api/admin/reports", status_code=status.HTTP_201_CREATED)
def create_saved_report(data: SavedReportCreate, db: Session = Depends(get_db)):
    report = AdminSavedReport(
        title=data.title,
        report_type=data.report_type,
        period=data.period,
        channel=data.channel,
        status=data.status,
        notes=data.notes,
        gross_amount=_report_summary(db, data.period, data.channel)["gross_sales_mtd"],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "created_at": report.created_at}


@router.patch("/api/admin/reports/{report_id}")
def update_saved_report(
    report_id: int,
    update: SavedReportUpdate,
    db: Session = Depends(get_db),
):
    report = db.get(AdminSavedReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Saved report not found")
    values = update.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    for key, value in values.items():
        setattr(report, "report_type" if key == "report_type" else key, value)
    db.commit()
    return {"id": report.id}


@router.delete("/api/admin/reports/{report_id}")
def delete_saved_report(report_id: int, db: Session = Depends(get_db)):
    report = db.get(AdminSavedReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Saved report not found")
    db.delete(report)
    db.commit()
    return {"message": "Saved report deleted"}
