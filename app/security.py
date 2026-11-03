from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.connection import get_db
from app.models.admin import AuthSession, Role, User
from app.models.supplier import Supplier


SESSION_COOKIE = "technova_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
CSRF_HEADER = "x-requested-with"
CSRF_HEADER_VALUE = "TECHNOVA"
ROLE_IDS = {"Admin": 1, "Supplier": 2, "Cashier": 3, "Customer": 4}


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except ValueError:
        return False
    if not 100_000 <= iterations <= 1_000_000:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_session(db: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=utc_now_naive().replace(microsecond=0)
            + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
        )
    )
    db.flush()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def revoke_other_sessions(
    db: Session,
    user_id: int,
    current_token: str | None,
) -> None:
    current_token_hash = (
        hashlib.sha256(current_token.encode()).hexdigest() if current_token else ""
    )
    db.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
        AuthSession.token_hash != current_token_hash,
    ).update({"revoked_at": utc_now_naive()}, synchronize_session=False)


def require_authenticated_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utc_now_naive(),
        )
    )
    user = db.get(User, session.user_id) if session else None
    if user is None or user.status != "Active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> User:
    role = db.get(Role, user.role_id)
    if user.role_id != ROLE_IDS["Admin"] or role is None or role.name != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return user


def require_order_access(
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> User:
    role = db.get(Role, user.role_id)
    if (
        role is None
        or role.name not in {"Admin", "Cashier", "Customer"}
        or user.role_id != ROLE_IDS.get(role.name)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to place orders",
        )
    return user


def require_supplier_access(
    request: Request,
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> User:
    role = db.get(Role, user.role_id)
    if user.role_id == ROLE_IDS["Admin"] and role is not None and role.name == "Admin":
        return user
    raw_supplier_id = request.path_params.get("supplier_id")
    supplier_id = (
        int(raw_supplier_id)
        if isinstance(raw_supplier_id, str) and raw_supplier_id.isdigit()
        else None
    )
    supplier = db.get(Supplier, supplier_id) if supplier_id is not None else None
    if (
        user.role_id != ROLE_IDS["Supplier"]
        or role is None
        or role.name != "Supplier"
        or supplier is None
        or supplier.user_id != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this supplier account",
        )
    return user
