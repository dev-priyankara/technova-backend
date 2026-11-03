import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.admin import AuthSession, CustomerAddress, Order, OrderItem, Role, User
from app.schemas.auth import (
    LoginRequest,
    PasswordUpdateRequest,
    ProfileUpdateRequest,
    RegisterRequest,
)
from app.security import (
    CSRF_HEADER,
    CSRF_HEADER_VALUE,
    ROLE_IDS,
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    hash_password,
    require_authenticated_user,
    revoke_other_sessions,
    utc_now_naive,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])
orders_router = APIRouter(tags=["Orders"])


def _auth_user_json(db: Session, user: User) -> dict:
    role = db.get(Role, user.role_id)
    address = db.scalar(
        select(CustomerAddress)
        .where(CustomerAddress.user_id == user.id)
        .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id.desc())
        .limit(1)
    )
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone or "",
        "role": role.name if role else "Customer",
        "street": address.street if address else "",
        "city": address.city if address else "",
        "postal_code": address.postal_code if address else "",
        "created_at": user.created_at,
    }


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
        "shipping_fee": order.shipping_fee,
        "status": order.status,
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "recipient_name": order.recipient_name,
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
                "price": item.unit_price,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
                "sku": item.sku,
                "warranty": item.warranty,
            }
            for item in items
        ],
    }


@orders_router.get("/api/orders")
def get_my_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
):
    if user.role_id == ROLE_IDS["Customer"]:
        statement = select(Order).where(Order.customer_id == user.id)
    elif user.role_id == ROLE_IDS["Cashier"]:
        statement = select(Order).where(Order.cashier_id == user.id)
    elif user.role_id == ROLE_IDS["Admin"]:
        statement = select(Order)
    else:
        raise HTTPException(status_code=403, detail="You are not authorized to view orders")
    orders = db.scalars(statement.order_by(Order.created_at.desc(), Order.id.desc())).all()
    return [_order_json(db, order) for order in orders]


@orders_router.get("/api/orders/{order_key}")
def get_my_order(
    order_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
):
    statement = select(Order).where(Order.order_number == order_key)
    if order_key.isdigit():
        statement = select(Order).where(
            (Order.order_number == order_key) | (Order.id == int(order_key))
        )
    order = db.scalar(statement)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role_id == ROLE_IDS["Customer"] and order.customer_id != user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role_id == ROLE_IDS["Cashier"] and order.cashier_id != user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if user.role_id not in {ROLE_IDS["Admin"], ROLE_IDS["Customer"], ROLE_IDS["Cashier"]}:
        raise HTTPException(status_code=403, detail="You are not authorized to view orders")
    return _order_json(db, order)


@router.get("/profile")
def get_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
):
    return _auth_user_json(db, user)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    customer_role = db.scalar(select(Role).where(Role.name == "Customer"))
    if customer_role is None:
        raise HTTPException(status_code=503, detail="Customer role is not configured")
    if db.scalar(select(User.id).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(status_code=409, detail="Email address is already registered")

    user = User(
        role_id=customer_role.id,
        name=data.name,
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            CustomerAddress(
                user_id=user.id,
                recipient_name=user.name,
                phone=user.phone,
                street="",
                city="",
                is_default=1,
            )
        )
        create_session(db, user, response)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        clear_session_cookie(response)
        raise HTTPException(status_code=409, detail="Email address is already registered") from None
    return _auth_user_json(db, user)


@router.post("/login")
def login(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(func.lower(User.email) == data.email.lower())
    )
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status != "Active":
        raise HTTPException(status_code=403, detail="This account is inactive")
    create_session(db, user, response)
    db.commit()
    return _auth_user_json(db, user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        if request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
            raise HTTPException(status_code=403, detail="CSRF validation failed")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        request_session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
            )
        )
        if request_session is not None:
            request_session.revoked_at = utc_now_naive()
            db.commit()
    clear_session_cookie(response)
    return {"message": "Logged out"}


@router.put("/profile")
def update_profile(
    data: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
):
    user.name = data.name
    user.phone = data.phone
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
            street=data.street,
            city=data.city,
            postal_code=data.postal_code,
            is_default=1,
        )
        db.add(address)
    else:
        address.recipient_name = user.name
        address.phone = user.phone
        address.street = data.street
        address.city = data.city
        address.postal_code = data.postal_code
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to update profile") from None
    return _auth_user_json(db, user)


@router.put("/password")
def update_password(
    data: PasswordUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    revoke_other_sessions(db, user.id, request.cookies.get(SESSION_COOKIE))
    db.commit()
    return {"message": "Password updated successfully"}
