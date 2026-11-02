from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class Supplier(Base):

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False
    )

    contact_person: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True
    )

    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    vendor_code: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True
    )

    tax_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    postal_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    contract_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Under Review"
    )

    bank_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    bank_branch: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    bank_account_no: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    authorized_brands: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        default=list
    )

    avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
