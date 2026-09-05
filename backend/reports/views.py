"""Report and export endpoints (§25, §26, §28).

Admin-only. Both reports read across every employee by design, so there is no
own-data variant here — an employee's own numbers are `/api/me/summary/`, which takes
no employee parameter at all.

Exports are audited. A read normally is not, but an export takes the whole workforce's
attendance and PC activity out of the system and into a file that leaves with whoever
downloaded it; that is worth a row saying who, when, and over what range.
"""

from __future__ import annotations

from django.http import HttpResponse, StreamingHttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import AppSettings
from core.audit import record
from core.models import AuditLog
from core.permissions import IsAdmin

from .exporters import (
    ACTIVITY_COLUMNS,
    ATTENDANCE_COLUMNS,
    activity_cells,
    attendance_cells,
    csv_stream,
    filename,
    office_tz,
    xlsx_bytes,
)
from .filters import FilterError, ReportFilters
from .queries import activity_rows, attendance_rows, page

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _ReportView(APIView):
    """Shared plumbing: parse the filters, refuse bad ones, hand back a page of rows."""

    permission_classes = [IsAdmin]
    report_name = ""

    def rows(self, filters):  # pragma: no cover - overridden
        raise NotImplementedError

    def get(self, request):
        settings_obj = AppSettings.load()
        try:
            filters = ReportFilters(request.query_params, settings_obj)
        except FilterError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows, has_more = page(self.rows(filters), filters.limit, filters.offset)
        return Response(
            {
                "report": self.report_name,
                "timezone": settings_obj.timezone,
                "filters": filters.describe(),
                "limit": filters.limit,
                "offset": filters.offset,
                "has_more": has_more,
                "rows": rows,
            }
        )


class AttendanceReportView(_ReportView):
    """§25's attendance report."""

    report_name = "attendance"

    def rows(self, filters):
        return attendance_rows(filters)


class ActivityReportView(_ReportView):
    """§25's PC activity report."""

    report_name = "activity"

    def rows(self, filters):
        return activity_rows(filters)


class ReportExportView(APIView):
    """`/api/reports/{type}/export/?format=csv|xlsx` (§26).

    CSV is streamed: the response starts before the last row has been read, so a large
    range does not sit in memory waiting to be complete. Excel cannot be streamed — the
    file is a zip whose central directory is written last — so it is built in
    write-only mode and sent whole.
    """

    permission_classes = [IsAdmin]

    def get(self, request, report):
        if report not in ("attendance", "activity"):
            return Response({"detail": f"Unknown report: {report}"}, status=404)

        export_format = (request.query_params.get("format") or "csv").lower()
        if export_format in ("excel", "xls"):
            export_format = "xlsx"
        if export_format not in ("csv", "xlsx"):
            return Response({"detail": "format must be csv or xlsx."}, status=400)

        settings_obj = AppSettings.load()
        try:
            filters = ReportFilters(request.query_params, settings_obj)
        except FilterError as exc:
            return Response({"detail": str(exc)}, status=400)

        tz = office_tz(settings_obj)
        detail = request.query_params.get("detail") == "punches"

        if report == "attendance":
            columns = ATTENDANCE_COLUMNS
            cells = attendance_cells(attendance_rows(filters), tz, detail=detail)
            sheet_title = "Attendance"
        else:
            columns = ACTIVITY_COLUMNS
            cells = activity_cells(activity_rows(filters), tz)
            sheet_title = "PC activity"

        headers = [header for header, _ in columns]

        # Counting rows as they are written costs nothing and makes the audit entry
        # answer the question anyone would actually ask of it: how much left the system.
        counter = _Counter()
        cells = counter.wrap(cells)

        name = filename(report, filters, export_format)
        if export_format == "csv":
            response = StreamingHttpResponse(
                csv_stream(headers, cells), content_type="text/csv; charset=utf-8"
            )
            # The audit entry is written when the stream is exhausted, not before it
            # starts — otherwise a cancelled download would be logged as a completed one.
            response.streaming_content = _audited(
                response.streaming_content, request, report, filters, export_format, counter
            )
        else:
            payload = xlsx_bytes(headers, cells, sheet_title=sheet_title)
            response = HttpResponse(payload, content_type=XLSX_CONTENT_TYPE)
            _write_audit(request, report, filters, export_format, counter.count)

        response["Content-Disposition"] = f'attachment; filename="{name}"'
        # The browser fetch that triggers the download reads this to name the file.
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response


class _Counter:
    def __init__(self):
        self.count = 0

    def wrap(self, iterable):
        for item in iterable:
            self.count += 1
            yield item


def _write_audit(request, report, filters, export_format, rows):
    record(
        request.user,
        AuditLog.Action.REPORT_EXPORTED,
        payload={
            "report": report,
            "format": export_format,
            "rows": rows,
            "filters": filters.describe(),
        },
        target_type="Report",
        target_id=report,
    )


def _audited(stream, request, report, filters, export_format, counter):
    yield from stream
    _write_audit(request, report, filters, export_format, counter.count)
