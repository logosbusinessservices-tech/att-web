"""Seed the managed reference lists: departments, employment types, designations.

Idempotent — safe to re-run. Each list gets an `Other` sentinel row; picking it
in onboarding stores the typed value in the person's matching `*_custom` column.

Values come verbatim from the RVNL rollout lists. A few source lines held two
spelling variants separated by " / "; those were split into separate entries so
nothing is lost. Exact duplicates are de-duplicated. The EA super-admin can
tidy this list later.

Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.seed_reference
"""

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import Department, Designation, EmploymentType

DEPARTMENTS = [
    "CIVIL",
    "ELEC / Electrical",
    "S&T",
    "FINANCE",
    "MECH",
    "PP&D/ADMIN",
]

EMPLOYMENT_TYPES = [
    "CONTRACT",
    "DEPUTATION",
    "REGULAR",
    "REGULAR (On prob.)",
    "Re-employed",
    "NEXT 5 YEARS",
]

DESIGNATIONS = [
    "Dy. Manager(Contract)-Civil",
    "Dy.Manager(Contract)/Civil",
    "Asst. Manager/Civil",
    "Deputy Mgr(Contract)/Civil",
    "Manager(Contract)/Civil",
    "Dy. Manager(Contract)/Civil",
    "Dy. Mgr(Contract)/Civil",
    "Sr. Site Engineer/Civil",
    "Sr. Site Engineer/Contract",
    "Sr. Site Engineer/Civil/Contract",
    "Dy. Mgr(Contract)/Civil/Contract",
    "Asst. Manager/C/Civil",
    "Manager(Contract)/Electri",
    "Manager(Contract)/Elect",
    "Dy. Manager(Contract)/Electri",
    "Dy. Manager(Contract)/Elect",
    "Dy. Mgr(Contract)/Elect",
    "Mgr(Contract)/Electri",
    "Dy. Manager(Contract)/S&T",
    "Dy. Mgr(Contract)/S&T",
    "Dy. Mgr/S&T/Contract",
    "EXECUTIVE/FINANCE",
    "Sr. DGM/Civil",
    "AGM/ELECT",
    "Civil Expert/PMC",
    "Accountant/PMC",
    "Dy. Manager",
    "Computer Operations/PMC",
    "Supervisor/PMC",
    "Estimator/PMC",
    "Estimator",
    "Dy.Manager",
    "Account/PMC",
    "Store cum Record Keeper/HSRC",
    "Clerk",
    "SITE",
    "SITE/EPC WORKS",
    "PMC/Draftsman",
    "PMC/S&T",
    "PMC/S&T (SCR)",
    "Progressive (S&T)",
    "CPM",
    "GM/CIVIL",
    "JGM/Civil",
    "Sr. DGM/Civil - BZA",
    "DGM/Civil",
    "DM/Civil",
    "AM/CIVIL",
    "SR. DGM/Expert",
    "GM/Electrical",
    "AGM/ELECT - BZA",
    "DGM/Electrical",
    "Sr. Manager/Elec",
    "GGM/S&T",
    "Sr. DGM/S&T-EXPERT",
    "DGM/S&T",
    "DGM/S&TEXPERT",
    "GGM/MECH",
    "Manager/Mech",
    "JGM/FIN-EXPERT",
    "AM/FIN",
    "MGR/FIN",
    "DGM/PP&D",
    "Sr. Manager/Admin & Secy to CPM",
    "DGM/Finance",
]

OTHER = "Other"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.strip()
        if key and key.lower() not in seen:
            seen.add(key.lower())
            out.append(key)
    return out


def _upsert(db, model, names: list[str]) -> int:
    """Insert any missing names; ensure exactly one `is_other` sentinel row."""
    added = 0
    for name in names:
        row = db.execute(select(model).where(model.name == name)).scalar_one_or_none()
        if row is None:
            db.add(model(name=name, is_other=False))
            added += 1
    other = db.execute(select(model).where(model.name == OTHER)).scalar_one_or_none()
    if other is None:
        db.add(model(name=OTHER, is_other=True))
        added += 1
    elif not other.is_other:
        other.is_other = True
    return added


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        n = 0
        n += _upsert(db, Department, _dedupe(DEPARTMENTS))
        n += _upsert(db, EmploymentType, _dedupe(EMPLOYMENT_TYPES))
        n += _upsert(db, Designation, _dedupe(DESIGNATIONS))
        db.commit()
        print(f"Reference data seeded ({n} new row(s)).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
