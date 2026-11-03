from getpass import getpass
from pathlib import Path
import re
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import SessionLocal
from app.models.admin import Role, User
from app.security import hash_password


def main() -> None:
    name = input("Administrator name: ").strip()
    email = input("Administrator email: ").strip().lower()
    if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise SystemExit("A name and valid email address are required.")

    password = getpass("Password (8-128 characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 8 or len(password) > 128:
        raise SystemExit("Password must be between 8 and 128 characters.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    with SessionLocal() as db:
        admin_role = db.scalar(select(Role).where(Role.name == "Admin"))
        if admin_role is None:
            raise SystemExit("The Admin role is missing from the database.")
        admin_exists = db.scalar(
            select(User.id).where(User.role_id == admin_role.id).limit(1)
        )
        if admin_exists is not None:
            raise SystemExit("An administrator already exists; refusing to bootstrap another.")
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("That email address is already in use.")

        db.add(
            User(
                role_id=admin_role.id,
                name=name,
                email=email,
                password_hash=hash_password(password),
            )
        )
        db.commit()
    print(f"Administrator account created for {email}.")


if __name__ == "__main__":
    main()
