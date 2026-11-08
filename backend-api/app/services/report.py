"""Excel report generation (openpyxl) for supervisor attendance exports."""

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

_HEADER_FILL = PatternFill("solid", fgColor="1E293B")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_TITLE_FONT = Font(bold=True, size=14)


def build_overview_workbook(rollups, from_date: date, to_date: date, dept_name=None) -> BytesIO:
    """Build an .xlsx of per-employee attendance rollups. Returns a BytesIO stream."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"

    scope = dept_name or "All departments"
    ws["A1"] = f"Attendance report — {scope}"
    ws["A1"].font = _TITLE_FONT
    ws["A2"] = f"Period: {from_date.isoformat()} to {to_date.isoformat()}"

    headers = ["Employee Code", "Name", "Department", "Present", "Absent", "Attendance %", "Total Hours"]
    header_row = 4
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=header_row, column=col, value=h)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.alignment = Alignment(horizontal="center")

    r = header_row + 1
    for item in rollups:
        ws.cell(row=r, column=1, value=item.external_id)
        ws.cell(row=r, column=2, value=item.display_name)
        ws.cell(row=r, column=3, value=item.department_name or "—")
        ws.cell(row=r, column=4, value=item.present)
        ws.cell(row=r, column=5, value=item.absent)
        ws.cell(row=r, column=6, value=item.attendance_pct)
        ws.cell(row=r, column=7, value=item.total_hours)
        r += 1

    # Column widths for readability.
    widths = [16, 22, 16, 10, 9, 14, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

def build_matrix_workbook(
    matrix: list[dict],
    from_date: date,
    to_date: date,
    *,
    dept_name: str | None = None,
    roles: list[str] | None = None,
    sources: list[str] | None = None,
) -> BytesIO:
    """Build a two-sheet .xlsx of the department -> employee matrix.

    Sheet 1 ("Matrix") mirrors the collapsible web view:
      - department rows carry the totals (Staff / Present / Absent / Attend% / Hours)
      - employee rows sit under their department
      - employee rows use Excel's outline level 1, so the sheet has native
        collapse / expand buttons in the left margin — same UX as the web.

    Sheet 2 ("Raw data") is one flat row per employee with the department as
    a column — the easy-to-filter version for ad-hoc pivoting.

    `matrix` is the same list the frontend builds: items with
      key, name (dept name), headcount, present, absent, attendance_pct,
      total_hours, and employees (list of per-employee rollups).

    `roles` and `sources` are the ACTIVE filter values, shown as a subtitle
    so the exported file is self-documenting.
    """
    wb = Workbook()

    # ── Sheet 1: the collapsible matrix ──
    ws = wb.active
    ws.title = "Matrix"

    scope = dept_name or "All departments"
    ws["A1"] = f"Department matrix — {scope}"
    ws["A1"].font = _TITLE_FONT
    ws["A2"] = f"Period: {from_date.isoformat()} to {to_date.isoformat()}"

    # Subtitle lists the active filters so the file is self-documenting.
    filter_bits = []
    if sources:
        filter_bits.append(f"Capture: {', '.join(sources)}")
    if roles:
        filter_bits.append(f"Role: {', '.join(roles)}")
    if filter_bits:
        ws["A3"] = " · ".join(filter_bits)

    headers = ["Department / Employee", "Code", "Staff", "Present", "Absent",
               "Attendance %", "Total Hours"]
    header_row = 5
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=header_row, column=col, value=h)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.alignment = Alignment(horizontal="center")

    # Department rows carry totals; employee rows sit under them at outline
    # level 1 so Excel's native +/- buttons collapse/expand the groups.
    r = header_row + 1
    dept_font = Font(bold=True)
    for dept in matrix:
        drow = ws.cell(row=r, column=1, value=dept.get("name") or "—")
        drow.font = dept_font
        ws.cell(row=r, column=2, value="")  # no code column for a dept row
        ws.cell(row=r, column=3, value=dept.get("headcount"))
        ws.cell(row=r, column=4, value=dept.get("present"))
        ws.cell(row=r, column=5, value=dept.get("absent"))
        ws.cell(row=r, column=6, value=dept.get("attendance_pct"))
        ws.cell(row=r, column=7, value=dept.get("total_hours"))
        r += 1
        for emp in dept.get("employees") or []:
            # Indent the name visually AND set outline level so the collapse
            # control knows this row belongs to the department above.
            ws.cell(row=r, column=1, value=f"    {emp.display_name}")
            ws.cell(row=r, column=2, value=emp.external_id)
            ws.cell(row=r, column=3, value="")   # no per-employee staff count
            ws.cell(row=r, column=4, value=emp.present)
            ws.cell(row=r, column=5, value=emp.absent)
            ws.cell(row=r, column=6, value=emp.attendance_pct)
            ws.cell(row=r, column=7, value=emp.total_hours)
            ws.row_dimensions[r].outline_level = 1
            r += 1

    # Collapsed by default so the file opens tidy; users expand what they want.
    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.sheet_format.outlineLevelRow = 1

    widths = [34, 14, 8, 10, 9, 14, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    # ── Sheet 2: raw data (flat, easy to filter) ──
    ws2 = wb.create_sheet(title="Raw data")
    ws2["A1"] = "Per-employee rollup (flat)"
    ws2["A1"].font = _TITLE_FONT
    ws2["A2"] = f"Period: {from_date.isoformat()} to {to_date.isoformat()}"

    flat_headers = ["Department", "Employee Code", "Name",
                    "Present", "Absent", "Attendance %", "Total Hours"]
    for col, h in enumerate(flat_headers, start=1):
        c = ws2.cell(row=4, column=col, value=h)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.alignment = Alignment(horizontal="center")

    r = 5
    for dept in matrix:
        for emp in dept.get("employees") or []:
            ws2.cell(row=r, column=1, value=dept.get("name") or "—")
            ws2.cell(row=r, column=2, value=emp.external_id)
            ws2.cell(row=r, column=3, value=emp.display_name)
            ws2.cell(row=r, column=4, value=emp.present)
            ws2.cell(row=r, column=5, value=emp.absent)
            ws2.cell(row=r, column=6, value=emp.attendance_pct)
            ws2.cell(row=r, column=7, value=emp.total_hours)
            r += 1

    # Excel's built-in filter dropdowns on the raw sheet, so the user can
    # sort/filter without any extra setup.
    if r > 5:
        ws2.auto_filter.ref = f"A4:G{r - 1}"

    widths2 = [18, 14, 22, 10, 9, 14, 12]
    for i, w in enumerate(widths2, start=1):
        ws2.column_dimensions[ws2.cell(row=1, column=i).column_letter].width = w

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream