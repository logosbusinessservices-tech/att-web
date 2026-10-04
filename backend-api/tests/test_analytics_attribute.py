"""Attendance analytics grouped by designation / employment type (+ Other bucket)."""

from app.db.models import Designation, EmploymentType, Person


def test_by_attribute_groups_by_designation(client, chief_headers, db_session, seed_params):
    eng = Designation(name="Engineer", is_other=False)
    db_session.add(eng)
    db_session.commit()
    emp = db_session.query(Person).filter_by(external_id="EMP001").one()
    emp.designation_id = eng.id
    db_session.commit()

    r = client.get("/supervisor/analytics/by-attribute", headers=chief_headers,
                   params={"attribute": "designation", **seed_params})
    assert r.status_code == 200, r.text
    keys = {row["key"] for row in r.json()}
    assert "Engineer" in keys


def test_other_rolls_into_single_bucket(client, chief_headers, db_session, seed_params):
    other = EmploymentType(name="Other", is_other=True)
    db_session.add(other)
    db_session.commit()
    for ext in ("EMP001", "EMP002"):
        p = db_session.query(Person).filter_by(external_id=ext).one()
        p.employment_type_id = other.id
        p.employment_type_custom = f"Custom-{ext}"
    db_session.commit()

    r = client.get("/supervisor/analytics/by-attribute", headers=chief_headers,
                   params={"attribute": "employment_type", **seed_params})
    assert r.status_code == 200, r.text
    rows = {row["key"]: row for row in r.json()}
    # Both custom employees collapse under the single "Other" bucket.
    assert "Other" in rows
    assert rows["Other"]["headcount"] >= 2


def test_by_attribute_invalid(client, chief_headers):
    r = client.get("/supervisor/analytics/by-attribute", headers=chief_headers,
                   params={"attribute": "bogus"})
    assert r.status_code == 400


def test_by_attribute_requires_supervisor(client, emp_headers):
    r = client.get("/supervisor/analytics/by-attribute", headers=emp_headers,
                   params={"attribute": "designation"})
    assert r.status_code == 403
