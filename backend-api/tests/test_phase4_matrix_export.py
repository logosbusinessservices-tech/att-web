"""Phase 4 matrix export: the department -> employee .xlsx download."""

from io import BytesIO

from openpyxl import load_workbook


# ── Permission & auth ─────────────────────────────────────────────────────
def test_matrix_export_requires_auth(client):
    assert client.get("/supervisor/attendance/matrix-export").status_code == 401


def test_matrix_export_blocks_employee(client, emp_headers):
    assert client.get("/supervisor/attendance/matrix-export",
                      headers=emp_headers).status_code == 403


def test_matrix_export_allowed_for_supervisor(client, sup_headers):
    r = client.get("/supervisor/attendance/matrix-export", headers=sup_headers)
    assert r.status_code == 200


def test_matrix_export_allowed_for_chief(client, chief_headers):
    r = client.get("/supervisor/attendance/matrix-export", headers=chief_headers)
    assert r.status_code == 200


# ── Response shape: real xlsx, right filename, right headers ──────────────
def test_matrix_export_returns_xlsx_mime(client, sup_headers):
    r = client.get("/supervisor/attendance/matrix-export", headers=sup_headers)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_matrix_export_filename_in_content_disposition(client, sup_headers, seed_params):
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params=seed_params,
    )
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "attendance_matrix_" in cd
    assert ".xlsx" in cd


def test_matrix_export_file_is_a_valid_xlsx(client, sup_headers, seed_params):
    """openpyxl must be able to open the bytes."""
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params=seed_params,
    )
    assert r.status_code == 200
    wb = load_workbook(BytesIO(r.content))
    assert "Matrix" in wb.sheetnames
    assert "Raw data" in wb.sheetnames


# ── Matrix sheet: structure matches the web view ──────────────────────────
def test_matrix_sheet_has_title_and_period(client, sup_headers, seed_params):
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params=seed_params,
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Matrix"]
    assert "Department matrix" in str(ws["A1"].value)
    assert "Period:" in str(ws["A2"].value)


def test_matrix_sheet_lists_department_and_employees(client, sup_headers, seed_params):
    """Operations department with EMP001, EMP002 should appear."""
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params=seed_params,
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Matrix"]
    # Walk all cells in column A + column B, collect non-empty values.
    col_a = [c.value for c in ws["A"] if c.value]
    col_b = [c.value for c in ws["B"] if c.value]
    joined = " | ".join(str(x) for x in col_a + col_b)
    assert "Operations" in joined
    assert "EMP001" in joined
    assert "EMP002" in joined


def test_matrix_sheet_employee_rows_have_outline_level(client, sup_headers, seed_params):
    """Employee rows must be at outline level 1 so Excel's collapse works.

    This is the Phase 4 upgrade — the old HTML-xls had no grouping at all.
    """
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params=seed_params,
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Matrix"]
    # Find a row with EMP001 and confirm its outline level.
    emp_row = None
    for row in ws.iter_rows(values_only=False):
        for cell in row:
            if cell.value == "EMP001":
                emp_row = cell.row
                break
        if emp_row:
            break
    assert emp_row is not None, "EMP001 should be in the Matrix sheet"
    assert ws.row_dimensions[emp_row].outline_level == 1


# ── Raw data sheet: flat, has auto-filter ─────────────────────────────────
def test_raw_sheet_has_flat_rows(client, sup_headers, seed_params):
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params=seed_params,
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Raw data"]
    # Row 4 is the header; data starts at row 5. Column A is Department,
    # Column B is Employee Code. Should see at least EMP001, EMP002.
    codes = [c.value for c in ws["B"] if c.value]
    assert "EMP001" in codes
    assert "EMP002" in codes


def test_raw_sheet_has_autofilter(client, sup_headers, seed_params):
    """The raw sheet should enable Excel's filter dropdowns automatically."""
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params=seed_params,
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Raw data"]
    assert ws.auto_filter.ref is not None
    assert ws.auto_filter.ref.startswith("A4:")


# ── Filter respect: roles / sources / department ──────────────────────────
def test_matrix_export_respects_roles_filter(client, sup_headers, seed_params):
    """roles=supervisor should include SUP001 and exclude the EMP rows."""
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params={**seed_params, "roles": "supervisor"},
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Raw data"]
    codes = [c.value for c in ws["B"] if c.value and str(c.value).startswith(("EMP", "SUP"))]
    assert "SUP001" in codes
    assert "EMP001" not in codes
    assert "EMP002" not in codes


def test_matrix_export_respects_sources_filter(client, sup_headers, seed_params):
    """sources=field hides EMP001's camera-only present days (present=0)."""
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params={**seed_params, "sources": "field"},
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Raw data"]
    # Find EMP001's present column (D).
    emp1_present = None
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row and row[1] == "EMP001":
            emp1_present = row[3]  # column D
            break
    assert emp1_present == 0, "Field-only filter should hide camera-only days"


def test_matrix_export_subtitle_lists_filters(client, sup_headers, seed_params):
    """When filters are applied, the Matrix sheet subtitle shows them."""
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params={**seed_params, "sources": "camera", "roles": "employee"},
    )
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Matrix"]
    subtitle = str(ws["A3"].value or "")
    assert "camera" in subtitle.lower() or "Capture" in subtitle


def test_matrix_export_legacy_types_param(client, sup_headers, seed_params):
    """Old URLs with ?types=supervisor still work (backward compat)."""
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params={**seed_params, "types": "supervisor"},
    )
    assert r.status_code == 200
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Raw data"]
    codes = [c.value for c in ws["B"] if c.value and str(c.value).startswith(("EMP", "SUP"))]
    assert "SUP001" in codes


def test_matrix_export_chief_department_filter(client, chief_headers, db_session):
    """Chief can filter to a specific department in the export."""
    from app.db.models import Department
    signals = db_session.query(Department).filter_by(name="Signals").one()
    r = client.get(
        f"/supervisor/attendance/matrix-export?department_id={signals.id}",
        headers=chief_headers,
    )
    assert r.status_code == 200
    wb = load_workbook(BytesIO(r.content))
    ws = wb["Raw data"]
    codes = [c.value for c in ws["B"] if c.value and str(c.value).startswith(("EMP", "SUP"))]
    assert "EMP003" in codes
    assert "EMP001" not in codes


# ── Empty case: no data in range ──────────────────────────────────────────
def test_matrix_export_handles_empty_range(client, sup_headers):
    """A range with no employees/events should still produce a valid file."""
    # Far-future range -> no data.
    r = client.get(
        "/supervisor/attendance/matrix-export",
        headers=sup_headers,
        params={"from_date": "2099-01-01", "to_date": "2099-01-02"},
    )
    assert r.status_code == 200
    wb = load_workbook(BytesIO(r.content))
    # Both sheets still exist.
    assert "Matrix" in wb.sheetnames
    assert "Raw data" in wb.sheetnames