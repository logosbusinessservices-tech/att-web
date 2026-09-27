"""Set (or reset) a person's login password, and optionally their role.

The pipeline enrolled faces but never stored passwords, so run this to make an
existing person able to log in to the website.

Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.seed_password EMP001 "secret" --role employee
    backend-api/.venv/Scripts/python.exe -m scripts.seed_password SUP001 "secret" --role supervisor
"""

import argparse

from sqlalchemy import select

from app.auth.security import hash_password
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import Person


def main():
    parser = argparse.ArgumentParser(description="Set a person's password/role.")
    parser.add_argument("external_id", help="employee code (persons.external_id)")
    parser.add_argument("password", help="plaintext password to set")
    parser.add_argument("--role", choices=["employee", "supervisor"], default=None)
    parser.add_argument("--name", default=None, help="create with this display name if missing")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        person = db.execute(
            select(Person).where(Person.external_id == args.external_id)
        ).scalar_one_or_none()

        if person is None:
            if not args.name:
                raise SystemExit(
                    f"No person '{args.external_id}'. Pass --name to create one."
                )
            person = Person(
                external_id=args.external_id,
                display_name=args.name,
                role=args.role or "employee",
            )
            db.add(person)

        person.password_hash = hash_password(args.password)
        if args.role:
            person.role = args.role

        db.commit()
        print(f"Password set for {person.external_id} (role={person.role}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
