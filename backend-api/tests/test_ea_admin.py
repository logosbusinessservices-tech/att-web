"""EA super-admin: global account administration (all departments) + role moves."""

from app.db.models import Designation, EmploymentType, Person


def test_ea_lists_accounts_across_departments(client, ea_headers):
    rows = client.get("/assistant/accounts", headers=ea_headers).json()
    ids = {r["external_id"] for r in rows}
    # EMP001 is in Operations, EMP003 is in Signals — EA sees both.
    assert "EMP001" in ids
    assert "EMP003" in ids


def test_ea_edits_account_in_another_department(client, ea_headers, sup_headers):
    # SUP001 (Operations) cannot touch EMP003 (Signals)...
    blocked = client.patch("/supervisor/employees/EMP003/settings",
                           headers=sup_headers, json={"phone": "+91 90000 00003"})
    assert blocked.status_code == 403
    # ...but the EA super-admin can, across departments.
    r = client.patch("/assistant/accounts/EMP003", headers=ea_headers,
                      json={"phone": "+91 90000 00003"})
    assert r.status_code == 200, r.text
    assert r.json()["phone"] == "+91 90000 00003"


def test_ea_promotes_employee_to_supervisor(client, ea_headers):
    r = client.patch("/assistant/accounts/EMP001", headers=ea_headers,
                      json={"role": "supervisor"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "supervisor"
    # Persisted.
    again = client.get("/assistant/accounts/EMP001", headers=ea_headers).json()
    assert again["role"] == "supervisor"


def test_ea_rejects_invalid_role(client, ea_headers):
    r = client.patch("/assistant/accounts/EMP001", headers=ea_headers,
                     json={"role": "chief"})
    assert r.status_code == 400


def test_ea_sets_designation_and_employment(client, ea_headers, db_session):
    eng = Designation(name="Engineer", is_other=False)
    reg = EmploymentType(name="REGULAR", is_other=False)
    db_session.add_all([eng, reg])
    db_session.commit()
    r = client.patch("/assistant/accounts/EMP001", headers=ea_headers,
                     json={"designation_id": eng.id, "employment_type_id": reg.id})
    assert r.status_code == 200, r.text
    assert r.json()["designation_name"] == "Engineer"
    assert r.json()["employment_type_name"] == "REGULAR"
    assert r.json()["designation_custom"] is None


def test_ea_other_designation_requires_custom(client, ea_headers, db_session):
    other = Designation(name="Other", is_other=True)
    db_session.add(other)
    db_session.commit()
    # Missing custom text -> 400.
    bad = client.patch("/assistant/accounts/EMP001", headers=ea_headers,
                       json={"designation_id": other.id})
    assert bad.status_code == 400
    # With custom text -> stored verbatim, grouped under the Other row.
    ok = client.patch("/assistant/accounts/EMP001", headers=ea_headers,
                      json={"designation_id": other.id, "designation_custom": "Signal Tech"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["designation_custom"] == "Signal Tech"


def test_ref_options_lists_reference_data(client, ea_headers, db_session):
    db_session.add(Designation(name="Clerk", is_other=False))
    db_session.commit()
    o = client.get("/assistant/ref-options", headers=ea_headers).json()
    assert any(d["name"] == "Operations" for d in o["departments"])
    assert "designations" in o and "employment_types" in o


def test_accounts_require_assistant(client, emp_headers, sup_headers):
    assert client.get("/assistant/accounts", headers=emp_headers).status_code == 403
    assert client.get("/assistant/accounts", headers=sup_headers).status_code == 403
