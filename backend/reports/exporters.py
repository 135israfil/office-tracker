"""CSV and Excel rendering of the §25 report rows (§26).

The column definitions live here once and both formats read from them, so a column
added to the CSV cannot go missing from the Excel file.

The two formats differ in one deliberate way: **durations**. CSV has no notion of a cell
type, so it gets `H:MM` text. Excel gets a real duration — the value is a fraction of a
day with an `[h]:mm` number format — because the first thing anyone does with an
exported timesheet is select a column and read the sum, and text does not add up.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from zoneinfo import ZoneInfo

# Excel's own duration format. `[h]` is the elapsed-hours form, which keeps counting
# past 24 instead of wrapping — a fortnight's PC time is not "3:30".
EXCEL_DURATION_FORMAT = "[h]:mm"
SECONDS_PER_DAY = 86_400


class Duration(int):
    """Seconds, tagged so the writers know to render it as a duration rather than a number."""


def hhmm(seconds) -> str:
    """`H:MM`, counting elapsed hours rather than clock hours."""
    if seconds is None:
        return ""
    total = max(0, int(seconds))
    return f"{total // 3600}:{(total % 3600) // 60:02d}"


def local_clock(value, tz) -> str:
    """A timestamp in office-local terms.

    Reports are read against a timesheet, and the timesheet is written in office time.
    Rendering in the exporter's timezone would put a 09:02 check-in at 03:02 for anyone
    running the export from elsewhere, which is the bug Phase 7 found on the timeline.
    """
    if not value:
        return ""
    return value.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _location(row_value) -> str:
    return {"INSIDE": "Inside office", "OUTSIDE": "Outside office"}.get(row_value, "")


def _metres(value) -> str:
    return "" if value is None else f"{value:.0f}"


# --- Column definitions -----------------------------------------------------
#
# Each column is (header, extractor). The extractor returns a plain value, or a
# `Duration` for anything measured in seconds.

ATTENDANCE_COLUMNS = [
    ("Employee ID", lambda row, tz: row["employee_code"]),
    ("Employee", lambda row, tz: row["employee_name"]),
    ("Department", lambda row, tz: row["department"]),
    ("Date", lambda row, tz: row["date"]),
    ("Check-in", lambda row, tz: local_clock(row["first_check_in_at"], tz)),
    ("Check-out", lambda row, tz: local_clock(row["last_check_out_at"], tz)),
    ("Worked", lambda row, tz: Duration(row["worked_seconds"])),
    ("Late minutes", lambda row, tz: row["late_minutes"]),
    ("Status", lambda row, tz: row["status"].title()),
    ("Check-in location", lambda row, tz: _location(row["check_in_location"])),
    ("Distance (m)", lambda row, tz: _metres(row["check_in_distance_m"])),
    ("GPS accuracy (m)", lambda row, tz: _metres(row["check_in_accuracy_m"])),
    ("Punches", lambda row, tz: row["punch_count"]),
    ("Needs review", lambda row, tz: "yes" if row["needs_review"] else ""),
    ("Adjusted", lambda row, tz: "yes" if row["is_manually_adjusted"] else ""),
]

# The per-punch detail rows (D7). One row per check-in/check-out pair, emitted under
# their day when `detail=punches` is asked for. A single-shift office never sees these
# because the day row already says everything.
PUNCH_COLUMNS = [
    ("Employee ID", lambda row, punch, tz: row["employee_code"]),
    ("Employee", lambda row, punch, tz: row["employee_name"]),
    ("Department", lambda row, punch, tz: row["department"]),
    ("Date", lambda row, punch, tz: row["date"]),
    ("Check-in", lambda row, punch, tz: local_clock(punch["check_in_at"], tz)),
    ("Check-out", lambda row, punch, tz: local_clock(punch["check_out_at"], tz)),
    ("Worked", lambda row, punch, tz: Duration(punch["duration_seconds"])),
    ("Late minutes", lambda row, punch, tz: punch["late_minutes"]),
    ("Status", lambda row, punch, tz: f"Punch {punch['sequence']}"),
    ("Check-in location", lambda row, punch, tz: _location(punch["check_in_location"])),
    ("Distance (m)", lambda row, punch, tz: _metres(punch["check_in_distance_m"])),
    ("GPS accuracy (m)", lambda row, punch, tz: ""),
    ("Punches", lambda row, punch, tz: ""),
    ("Needs review", lambda row, punch, tz: ""),
    ("Adjusted", lambda row, punch, tz: ""),
]

ACTIVITY_COLUMNS = [
    ("Employee ID", lambda row, tz: row["employee_code"]),
    ("Employee", lambda row, tz: row["employee_name"]),
    ("Department", lambda row, tz: row["department"]),
    # Empty when grouped by employee: the row covers a range, not a date.
    ("Date", lambda row, tz: row["date"] or ""),
    ("PC on time", lambda row, tz: Duration(row["pc_on_seconds"])),
    ("Active time", lambda row, tz: Duration(row["active_seconds"])),
    ("Idle time", lambda row, tz: Duration(row["idle_seconds"])),
    ("Top application", lambda row, tz: row["top_application"]["name"]),
    ("Top application time", lambda row, tz: Duration(row["top_application"]["seconds"])),
    ("Top website", lambda row, tz: row["top_website"]["name"]),
    ("Top website time", lambda row, tz: Duration(row["top_website"]["seconds"])),
    ("Applications", lambda row, tz: row["application_count"]),
    ("Websites", lambda row, tz: row["website_count"]),
]


def attendance_cells(rows, tz, *, detail=False):
    """Report rows as sequences of cells, ready for either writer."""
    for row in rows:
        yield [extract(row, tz) for _, extract in ATTENDANCE_COLUMNS]
        if detail and row["punch_count"] > 1:
            # Only split a day that actually has something to split. Repeating a
            # single punch under its own summary row is noise, not detail.
            for punch in row["punches"]:
                yield [extract(row, punch, tz) for _, extract in PUNCH_COLUMNS]


def activity_cells(rows, tz):
    for row in rows:
        yield [extract(row, tz) for _, extract in ACTIVITY_COLUMNS]


# --- CSV --------------------------------------------------------------------


class _Echo:
    """A file-like object that returns what it is asked to write.

    `csv.writer` insists on a file; a streaming response needs strings. This is the
    standard adapter between the two, and it is what makes the export a stream rather
    than a buffer that has to be complete before the first byte is sent.
    """

    def write(self, value):
        return value


def csv_stream(headers, cell_rows):
    """The CSV, one row at a time.

    Starts with a byte-order mark. Excel on Windows otherwise reads a UTF-8 CSV as the
    system code page, which turns every non-ASCII name into mojibake — and names are
    the first column.
    """
    writer = csv.writer(_Echo(), lineterminator="\r\n")
    yield "﻿"
    yield writer.writerow(headers)
    for cells in cell_rows:
        yield writer.writerow(
            [hhmm(cell) if isinstance(cell, Duration) else cell for cell in cells]
        )


# --- Excel ------------------------------------------------------------------


def xlsx_bytes(headers, cell_rows, sheet_title="Report"):
    """The workbook, as bytes.

    Written in openpyxl's write-only mode, which flushes rows to a temporary sheet file
    instead of holding a cell object per cell. The zip is still assembled in memory at
    the end, which is why CSV is the format the UI recommends for very large ranges.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.dimensions import ColumnDimension, DimensionHolder

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title=sheet_title[:31])

    # Widths must be set before the first row in write-only mode; the sheet is streamed
    # out as it is written and cannot be revisited afterwards.
    holder = DimensionHolder(worksheet=sheet)
    for index, header in enumerate(headers, start=1):
        letter = get_column_letter(index)
        holder[letter] = ColumnDimension(sheet, index=letter, width=max(11, len(header) + 3))
    sheet.column_dimensions = holder
    sheet.freeze_panes = "A2"

    from openpyxl.cell import WriteOnlyCell

    header_cells = []
    for header in headers:
        cell = WriteOnlyCell(sheet, value=header)
        cell.font = Font(bold=True)
        header_cells.append(cell)
    sheet.append(header_cells)

    for cells in cell_rows:
        row = []
        for value in cells:
            if isinstance(value, Duration):
                cell = WriteOnlyCell(sheet, value=int(value) / SECONDS_PER_DAY)
                cell.number_format = EXCEL_DURATION_FORMAT
                row.append(cell)
            elif isinstance(value, dt.date):
                cell = WriteOnlyCell(sheet, value=value)
                cell.number_format = "yyyy-mm-dd"
                row.append(cell)
            else:
                row.append(value)
        sheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --- Shared helpers ---------------------------------------------------------


def office_tz(settings_obj):
    return ZoneInfo(settings_obj.timezone)


def filename(report, filters, extension) -> str:
    """`attendance-2026-08-01_2026-08-19.csv`, or a single date when the range is one day."""
    if filters.date_from == filters.date_to:
        span = filters.date_from.isoformat()
    else:
        span = f"{filters.date_from.isoformat()}_{filters.date_to.isoformat()}"
    return f"{report}-{span}.{extension}"
