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

# ──────────────────────────────────────────────────────────────────────────
# Phase 9: EA001 re-upload employee photos
# ──────────────────────────────────────────────────────────────────────────

def _one_png_bytes():
    """Minimal 1x1 PNG so the UploadFile parsing succeeds. The actual face
    detection will reject it (no face), which lets us test the 422 path
    without needing a real face image in the tests."""
    import base64
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )


def test_re_enroll_requires_super_admin(client, ea2_headers):
    """Phase 9: A regular EA (not EA001) cannot re-enroll — gets 403."""
    files = {"photos": ("x.png", _one_png_bytes(), "image/png")}
    r = client.post("/assistant/accounts/EMP001/re-enroll",
                    headers=ea2_headers, files=files)
    assert r.status_code == 403
    assert "super admin" in r.json()["detail"].lower()


def test_re_enroll_rejects_bad_photos(client, ea_headers):
    """Phase 9: A 1x1 PNG has no detectable face; enrollment returns 422."""
    files = {"photos": ("tiny.png", _one_png_bytes(), "image/png")}
    r = client.post("/assistant/accounts/EMP001/re-enroll",
                    headers=ea_headers, files=files)
    assert r.status_code == 422


def test_re_enroll_rejects_empty_upload(client, ea_headers):
    """Phase 9: Upload with no photos returns 422."""
    # FastAPI's File(...) will reject a POST without the required field.
    r = client.post("/assistant/accounts/EMP001/re-enroll", headers=ea_headers)
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# Phase 10: EA001 can reset any account's password to default
# ──────────────────────────────────────────────────────────────────────────

def test_reset_password_requires_super_admin(client, ea2_headers):
    """Phase 10: A regular EA cannot reset passwords."""
    r = client.post("/assistant/accounts/EMP001/reset-password",
                    headers=ea2_headers)
    assert r.status_code == 403


def test_reset_password_sets_default_and_must_change(client, ea_headers, db_session):
    """Phase 10: After reset, password hash matches the employee code AND
    must_change_password flag is set."""
    from app.auth.security import verify_password

    r = client.post("/assistant/accounts/EMP001/reset-password", headers=ea_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["external_id"] == "EMP001"
    assert body["default_password"] == "EMP001"

    emp = db_session.query(Person).filter_by(external_id="EMP001").one()
    db_session.refresh(emp)
    assert verify_password("EMP001", emp.password_hash)
    assert emp.must_change_password is True


def test_reset_password_super_admin_can_reset_self(client, ea_headers):
    """Phase 10: EA001 can reset their own password (agreed design)."""
    r = client.post("/assistant/accounts/EA001/reset-password", headers=ea_headers)
    assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# Phase 11: EA001 can remove (soft delete) an employee
# ──────────────────────────────────────────────────────────────────────────

def test_remove_requires_super_admin(client, ea2_headers):
    """Phase 11: Only EA001 can remove."""
    r = client.post("/assistant/accounts/EMP002/remove", headers=ea2_headers)
    assert r.status_code == 403


def test_remove_soft_deletes_person(client, ea_headers, db_session):
    """Phase 11: After remove, person row stays but status=deleted,
    is_active=False, and deleted_at is set."""
    from app.db.models import FaceEmbedding

    emp = db_session.query(Person).filter_by(external_id="EMP002").one()
    # Seed a fake embedding so we can verify it gets deleted.
    db_session.add(FaceEmbedding(person_id=emp.id, embedding=b"\x00" * 2048, num_photos=1))
    db_session.commit()

    r = client.post("/assistant/accounts/EMP002/remove", headers=ea_headers)
    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is not None

    db_session.refresh(emp)
    assert emp.status == "deleted"
    assert emp.is_active is False
    assert emp.deleted_at is not None
    # Face embedding should be gone.
    assert db_session.query(FaceEmbedding).filter_by(person_id=emp.id).first() is None


def test_remove_super_admin_cannot_remove_self(client, ea_headers):
    """Phase 11: EA001 can't lock themselves out."""
    r = client.post("/assistant/accounts/EA001/remove", headers=ea_headers)
    assert r.status_code == 400
    assert "your own" in r.json()["detail"].lower()


def test_remove_double_remove_rejected(client, ea_headers):
    """Phase 11: Removing an already-removed account should 409."""
    r1 = client.post("/assistant/accounts/EMP003/remove", headers=ea_headers)
    assert r1.status_code == 200
    r2 = client.post("/assistant/accounts/EMP003/remove", headers=ea_headers)
    assert r2.status_code == 409
    assert "already removed" in r2.json()["detail"].lower()


def test_removed_employee_hidden_from_account_list(client, ea_headers):
    """Phase 11: A removed employee should NOT appear in /assistant/accounts."""
    client.post("/assistant/accounts/EMP002/remove", headers=ea_headers)
    rows = client.get("/assistant/accounts", headers=ea_headers).json()
    ids = {r["external_id"] for r in rows}
    assert "EMP002" not in ids
    # Other accounts should still be there.
    assert "EMP001" in ids


# ──────────────────────────────────────────────────────────────────────────
# Phase 12: EA001 can discard (hard delete) an account
# ──────────────────────────────────────────────────────────────────────────

def test_discard_preview_counts_everything(client, ea_headers):
    """Phase 12: Preview returns counts for every category."""
    # EMP001 has seeded attendance events, so this verifies the count works.
    r = client.get("/assistant/accounts/EMP001/discard-preview", headers=ea_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["external_id"] == "EMP001"
    assert body["attendance_events"] >= 1  # seed has 4 events for EMP001
    for key in ("corrections", "disputes", "leave_requests",
                "delegated_tasks", "notifications"):
        assert key in body


def test_discard_requires_super_admin(client, ea2_headers):
    """Phase 12: A regular EA cannot discard."""
    r = client.delete("/assistant/accounts/EMP002/discard?confirmation=DELETE",
                      headers=ea2_headers)
    assert r.status_code == 403


def test_discard_requires_delete_confirmation(client, ea_headers):
    """Phase 12: Confirmation string must be exactly 'DELETE'."""
    # Wrong case.
    r1 = client.delete("/assistant/accounts/EMP002/discard?confirmation=delete",
                       headers=ea_headers)
    assert r1.status_code == 400
    # Misspelled.
    r2 = client.delete("/assistant/accounts/EMP002/discard?confirmation=DELET",
                       headers=ea_headers)
    assert r2.status_code == 400


def test_discard_hard_deletes_everything(client, ea_headers, db_session):
    """Phase 12: Discard removes person + all related data from the DB."""
    from app.db.models import AttendanceEvent

    emp = db_session.query(Person).filter_by(external_id="EMP001").one()
    pid = emp.id
    pre_events = db_session.query(AttendanceEvent).filter_by(person_id=pid).count()
    assert pre_events >= 1  # sanity: seed has events for EMP001

    r = client.delete("/assistant/accounts/EMP001/discard?confirmation=DELETE",
                      headers=ea_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["attendance_events_deleted"] == pre_events

    # Person row gone.
    assert db_session.query(Person).filter_by(id=pid).first() is None
    # Attendance events gone.
    assert db_session.query(AttendanceEvent).filter_by(person_id=pid).count() == 0


def test_discard_super_admin_cannot_discard_self(client, ea_headers):
    """Phase 12: EA001 can't discard themselves."""
    r = client.delete("/assistant/accounts/EA001/discard?confirmation=DELETE",
                      headers=ea_headers)
    assert r.status_code == 400
    assert "your own" in r.json()["detail"].lower()