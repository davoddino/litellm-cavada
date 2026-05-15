from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Type, TypeVar
from xml.sax.saxutils import escape as xml_escape

from fastapi import HTTPException, status
from pydantic import BaseModel

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    CavadaLabsDispatcherService,
    _actor_key_hash,
    _actor_user_id,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsBillingReportFormat,
    CavadaLabsBillingReportGenerateRequest,
    CavadaLabsBillingReportListResponse,
    CavadaLabsBillingReportResponse,
    CavadaLabsBillingReportStatus,
    CavadaLabsCompanyResponse,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_JSON_FIELDS = {
    "inputs_snapshot",
    "totals",
    "breakdowns",
    "artifacts",
    "metadata",
}
_PAGE_SIZE = 1000


def _row_to_dict(row: Any, response_model: Type[ModelT]) -> Dict[str, Any]:
    if isinstance(row, dict):
        data = dict(row)
    else:
        model_dump = getattr(row, "model_dump", None)
        data = {}
        if callable(model_dump):
            try:
                dumped = model_dump()
                if isinstance(dumped, dict):
                    data = dumped
            except Exception:
                data = {}
        if not data:
            for field_name in response_model.model_fields.keys():
                if field_name in getattr(row, "__dict__", {}):
                    data[field_name] = getattr(row, field_name)

    for key in _JSON_FIELDS:
        value = data.get(key)
        if isinstance(value, str):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                data[key] = {}
    return data


def _parse_response(row: Any, response_model: Type[ModelT]) -> ModelT:
    return response_model.model_validate(_row_to_dict(row, response_model))


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        period_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return period_start, period_end


def _as_dict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    model_dump = getattr(row, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return dict(getattr(row, "__dict__", {}))


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _stable_json(data: Dict[str, Any]) -> str:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), default=_json_default
    )


def _sha256(data: Dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(data).encode("utf-8")).hexdigest()


def _row_date(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        result = datetime.now(timezone.utc)
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _day_key(value: Any) -> str:
    return _row_date(value).date().isoformat()


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _float_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _entity_key(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    return "unassigned"


class _BreakdownAccumulator:
    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}

    def add(self, key: str, row: Dict[str, Any]) -> None:
        target = self.rows.setdefault(
            key,
            {
                "id": key,
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "spend": 0.0,
            },
        )
        target["requests"] += 1
        target["prompt_tokens"] += _int_value(row.get("prompt_tokens"))
        target["completion_tokens"] += _int_value(row.get("completion_tokens"))
        target["total_tokens"] += _int_value(row.get("total_tokens"))
        target["spend"] += _float_value(row.get("spend"))

    def values(self) -> List[Dict[str, Any]]:
        return sorted(
            self.rows.values(),
            key=lambda item: (-float(item["spend"]), str(item["id"])),
        )


class CavadaLabsBillingService:
    def __init__(self, prisma_client: Any):
        self.prisma_client = prisma_client

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    async def generate_monthly_report(
        self,
        data: CavadaLabsBillingReportGenerateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsBillingReportResponse:
        company = await CavadaLabsDispatcherService(self.prisma_client).get_company(
            data.company_id
        )
        period_start, period_end = _month_range(data.year, data.month)
        company_rows = await self._fetch_many(
            self.db.cavadalabs_requestledgertable,
            where={
                "company_id": data.company_id,
                "created_at": {"gte": period_start, "lt": period_end},
            },
            order={"created_at": "asc"},
        )
        node_ids = sorted(
            {
                row["node_id"]
                for row in company_rows
                if isinstance(row.get("node_id"), str) and row["node_id"]
            }
        )
        all_node_rows = (
            await self._fetch_many(
                self.db.cavadalabs_requestledgertable,
                where={
                    "node_id": {"in": node_ids},
                    "created_at": {"gte": period_start, "lt": period_end},
                },
                order={"created_at": "asc"},
            )
            if node_ids
            else []
        )
        node_daily_reports = (
            await self._fetch_many(
                self.db.cavadalabs_nodedailyreporttable,
                where={
                    "node_id": {"in": node_ids},
                    "report_date": {"gte": period_start, "lt": period_end},
                },
                order={"report_date": "asc"},
            )
            if node_ids
            else []
        )

        calculation = self._calculate_report(
            company=company,
            company_rows=company_rows,
            all_node_rows=all_node_rows,
            node_daily_reports=node_daily_reports,
            period_start=period_start,
            period_end=period_end,
            currency=data.currency,
            tax_rate=data.tax_rate,
            metadata=data.metadata,
        )
        report_version = await self._next_report_version(
            company_id=data.company_id,
            period_start=period_start,
            period_end=period_end,
        )
        calculation["inputs_snapshot"]["report_version"] = report_version
        checksum = _sha256(
            {
                "inputs_snapshot": calculation["inputs_snapshot"],
                "totals": calculation["totals"],
                "breakdowns": calculation["breakdowns"],
            }
        )
        existing = await self.db.cavadalabs_billingreporttable.find_unique(
            where={"checksum": checksum}
        )
        if existing is not None:
            return _parse_response(existing, CavadaLabsBillingReportResponse)

        formats = [
            item.value if isinstance(item, CavadaLabsBillingReportFormat) else item
            for item in data.formats
        ]
        artifacts = self._build_artifacts(
            formats=formats,
            company=company,
            calculation=calculation,
            checksum=checksum,
        )
        create_data = serialize_prisma_json_fields(
            {
            "company_id": data.company_id,
            "report_version": report_version,
            "period_start": period_start,
            "period_end": period_end,
            "currency": data.currency,
            "status": CavadaLabsBillingReportStatus.GENERATED.value,
            "formats": formats,
            "total_requests": calculation["totals"]["requests"],
            "total_tokens": calculation["totals"]["total_tokens"],
            "total_spend": calculation["totals"]["total_spend"],
            "provider_cost": calculation["totals"]["provider_cost"],
            "cavadalabs_node_cost": calculation["totals"]["cavadalabs_node_cost"],
            "tax_rate": data.tax_rate,
            "tax_amount": calculation["totals"]["tax_amount"],
            "grand_total": calculation["totals"]["grand_total"],
            "checksum": checksum,
            "inputs_snapshot": calculation["inputs_snapshot"],
            "totals": calculation["totals"],
            "breakdowns": calculation["breakdowns"],
            "artifacts": artifacts,
            "metadata": data.metadata,
            "generated_by": _actor_user_id(user_api_key_dict),
            }
        )
        row = await self.db.cavadalabs_billingreporttable.create(data=create_data)
        response = _parse_response(row, CavadaLabsBillingReportResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="generated",
            resource_type="billing_report",
            resource_id=response.report_id,
            company_id=response.company_id,
            before_value=None,
            after_value={
                "report_id": response.report_id,
                "checksum": response.checksum,
                "period_start": response.period_start.isoformat(),
                "period_end": response.period_end.isoformat(),
                "grand_total": response.grand_total,
            },
        )
        return response

    async def list_billing_reports(
        self,
        company_id: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None,
        take: int = 100,
        skip: int = 0,
    ) -> CavadaLabsBillingReportListResponse:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        if year is not None and month is not None:
            period_start, period_end = _month_range(year, month)
            where["period_start"] = period_start
            where["period_end"] = period_end
        rows = await self.db.cavadalabs_billingreporttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"generated_at": "desc"},
        )
        reports = [
            _parse_response(row, CavadaLabsBillingReportResponse) for row in rows
        ]
        return CavadaLabsBillingReportListResponse(
            billing_reports=reports,
            count=len(reports),
        )

    async def get_billing_report(
        self, report_id: str
    ) -> CavadaLabsBillingReportResponse:
        row = await self.db.cavadalabs_billingreporttable.find_unique(
            where={"report_id": report_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Billing report '{report_id}' not found"},
            )
        return _parse_response(row, CavadaLabsBillingReportResponse)

    async def _fetch_many(
        self,
        table: Any,
        where: Dict[str, Any],
        order: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        skip = 0
        while True:
            page = await table.find_many(
                where=where,
                take=_PAGE_SIZE,
                skip=skip,
                order=order,
            )
            page_rows = [_as_dict(row) for row in page]
            rows.extend(page_rows)
            if len(page_rows) < _PAGE_SIZE:
                return rows
            skip += _PAGE_SIZE

    async def _next_report_version(
        self,
        company_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> int:
        rows = await self.db.cavadalabs_billingreporttable.find_many(
            where={
                "company_id": company_id,
                "period_start": period_start,
                "period_end": period_end,
            },
            take=1,
            order={"report_version": "desc"},
        )
        if not rows:
            return 1
        first = _as_dict(rows[0])
        return _int_value(first.get("report_version")) + 1

    def _calculate_report(
        self,
        *,
        company: CavadaLabsCompanyResponse,
        company_rows: List[Dict[str, Any]],
        all_node_rows: List[Dict[str, Any]],
        node_daily_reports: List[Dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
        currency: str,
        tax_rate: Optional[float],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        breakdowns = {
            "projects": _BreakdownAccumulator(),
            "chatbots": _BreakdownAccumulator(),
            "providers": _BreakdownAccumulator(),
            "models": _BreakdownAccumulator(),
            "nodes": _BreakdownAccumulator(),
            "gpus": _BreakdownAccumulator(),
            "web_tokens": _BreakdownAccumulator(),
        }
        totals = {
            "requests": len(company_rows),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "total_spend": 0.0,
            "provider_cost": 0.0,
            "cavadalabs_node_cost": 0.0,
            "tax_amount": None,
            "grand_total": 0.0,
            "currency": currency,
        }
        for row in company_rows:
            totals["prompt_tokens"] += _int_value(row.get("prompt_tokens"))
            totals["completion_tokens"] += _int_value(row.get("completion_tokens"))
            totals["total_tokens"] += _int_value(row.get("total_tokens"))
            totals["total_spend"] += _float_value(row.get("spend"))
            for name, field in (
                ("projects", "project_id"),
                ("chatbots", "chatbot_id"),
                ("providers", "provider"),
                ("models", "model"),
                ("nodes", "node_id"),
                ("gpus", "gpu_id"),
                ("web_tokens", "web_token_id"),
            ):
                breakdowns[name].add(_entity_key(row.get(field)), row)

        node_cost_allocations = self._allocate_node_costs(
            company_rows=company_rows,
            all_node_rows=all_node_rows,
            node_daily_reports=node_daily_reports,
        )
        totals["cavadalabs_node_cost"] = sum(
            allocation["allocated_cost"] for allocation in node_cost_allocations
        )
        totals["provider_cost"] = totals["total_spend"]
        subtotal = totals["provider_cost"] + totals["cavadalabs_node_cost"]
        if tax_rate is not None:
            totals["tax_amount"] = subtotal * tax_rate
        totals["grand_total"] = subtotal + (totals["tax_amount"] or 0.0)

        source_request_ids = [
            row.get("request_id")
            for row in company_rows
            if isinstance(row.get("request_id"), str)
        ]
        source_ledger_ids = [
            row.get("ledger_id")
            for row in company_rows
            if isinstance(row.get("ledger_id"), str)
        ]
        source_daily_report_ids = [
            row.get("report_id")
            for row in node_daily_reports
            if isinstance(row.get("report_id"), str)
        ]
        breakdown_values = {
            name: accumulator.values() for name, accumulator in breakdowns.items()
        }
        breakdown_values["node_cost_allocations"] = node_cost_allocations
        return {
            "inputs_snapshot": {
                "company": {
                    "company_id": company.company_id,
                    "legal_name": company.legal_name,
                    "billing_name": company.billing_name,
                    "vat_tax_id": company.vat_tax_id,
                    "billing_address": company.billing_address,
                    "default_billing_settings": company.default_billing_settings,
                },
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "source_request_ids": source_request_ids,
                "source_ledger_ids": source_ledger_ids,
                "source_node_daily_report_ids": source_daily_report_ids,
                "methodology": {
                    "provider_cost": "sum of CavadaLabs request ledger spend for the company and period",
                    "node_cost": "daily node cost allocated by company token share per node/day",
                    "raw_prompt_response_storage": "not included in billing reports",
                },
                "metadata": metadata,
            },
            "totals": totals,
            "breakdowns": breakdown_values,
        }

    def _allocate_node_costs(
        self,
        *,
        company_rows: List[Dict[str, Any]],
        all_node_rows: List[Dict[str, Any]],
        node_daily_reports: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        company_tokens_by_node_day: Dict[tuple[str, str], int] = defaultdict(int)
        all_tokens_by_node_day: Dict[tuple[str, str], int] = defaultdict(int)
        for row in company_rows:
            node_id = row.get("node_id")
            if not isinstance(node_id, str) or not node_id:
                continue
            token_weight = _int_value(row.get("total_tokens")) or 1
            company_tokens_by_node_day[
                (node_id, _day_key(row.get("created_at")))
            ] += token_weight
        for row in all_node_rows:
            node_id = row.get("node_id")
            if not isinstance(node_id, str) or not node_id:
                continue
            token_weight = _int_value(row.get("total_tokens")) or 1
            all_tokens_by_node_day[
                (node_id, _day_key(row.get("created_at")))
            ] += token_weight

        allocations = []
        for report in node_daily_reports:
            node_id = report.get("node_id")
            if not isinstance(node_id, str) or not node_id:
                continue
            key = (node_id, _day_key(report.get("report_date")))
            company_tokens = company_tokens_by_node_day.get(key, 0)
            all_tokens = all_tokens_by_node_day.get(key, 0)
            if company_tokens <= 0 or all_tokens <= 0:
                continue
            share = min(company_tokens / all_tokens, 1.0)
            node_cost = _float_value(report.get("node_cost_estimate"))
            allocations.append(
                {
                    "node_id": node_id,
                    "report_id": report.get("report_id"),
                    "report_date": _day_key(report.get("report_date")),
                    "company_token_weight": company_tokens,
                    "all_token_weight": all_tokens,
                    "share": share,
                    "node_cost_estimate": node_cost,
                    "allocated_cost": node_cost * share,
                }
            )
        return allocations

    def _build_artifacts(
        self,
        *,
        formats: List[str],
        company: CavadaLabsCompanyResponse,
        calculation: Dict[str, Any],
        checksum: str,
    ) -> Dict[str, Any]:
        artifacts: Dict[str, Any] = {
            "checksum": checksum,
            "formats": formats,
        }
        if CavadaLabsBillingReportFormat.JSON.value in formats:
            artifacts["json"] = calculation
        if CavadaLabsBillingReportFormat.CSV.value in formats:
            artifacts["csv"] = self._build_csv_artifact(calculation)
        if CavadaLabsBillingReportFormat.XLSX.value in formats:
            xlsx_bytes = self._build_xlsx_artifact(calculation)
            artifacts["xlsx_base64"] = base64.b64encode(xlsx_bytes).decode("ascii")
        if CavadaLabsBillingReportFormat.PDF.value in formats:
            pdf_bytes = self._build_pdf_artifact(
                company=company,
                calculation=calculation,
                checksum=checksum,
            )
            artifacts["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
        artifacts["sizes"] = {
            "csv_bytes": len(artifacts.get("csv", "").encode("utf-8")),
            "xlsx_bytes": (
                len(base64.b64decode(artifacts["xlsx_base64"]))
                if "xlsx_base64" in artifacts
                else 0
            ),
            "pdf_bytes": (
                len(base64.b64decode(artifacts["pdf_base64"]))
                if "pdf_base64" in artifacts
                else 0
            ),
        }
        return artifacts

    def _build_csv_artifact(self, calculation: Dict[str, Any]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "id", "requests", "tokens", "spend", "extra"])
        totals = calculation["totals"]
        writer.writerow(
            [
                "totals",
                "company",
                totals["requests"],
                totals["total_tokens"],
                totals["total_spend"],
                f"grand_total={totals['grand_total']}",
            ]
        )
        for section, rows in calculation["breakdowns"].items():
            if section == "node_cost_allocations":
                for row in rows:
                    writer.writerow(
                        [
                            section,
                            row["node_id"],
                            "",
                            row["company_token_weight"],
                            row["allocated_cost"],
                            f"share={row['share']};report_id={row['report_id']}",
                        ]
                    )
                continue
            for row in rows:
                writer.writerow(
                    [
                        section,
                        row["id"],
                        row["requests"],
                        row["total_tokens"],
                        row["spend"],
                        "",
                    ]
                )
        return output.getvalue()

    def _build_xlsx_artifact(self, calculation: Dict[str, Any]) -> bytes:
        rows: List[List[Any]] = [
            ["section", "id", "requests", "tokens", "spend", "extra"],
        ]
        totals = calculation["totals"]
        rows.append(
            [
                "totals",
                "company",
                totals["requests"],
                totals["total_tokens"],
                totals["total_spend"],
                f"grand_total={totals['grand_total']}",
            ]
        )
        for section, values in calculation["breakdowns"].items():
            if section == "node_cost_allocations":
                for row in values:
                    rows.append(
                        [
                            section,
                            row["node_id"],
                            "",
                            row["company_token_weight"],
                            row["allocated_cost"],
                            f"share={row['share']};report_id={row['report_id']}",
                        ]
                    )
                continue
            for row in values:
                rows.append(
                    [
                        section,
                        row["id"],
                        row["requests"],
                        row["total_tokens"],
                        row["spend"],
                        "",
                    ]
                )
        sheet_xml = self._xlsx_sheet_xml(rows)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
            )
            archive.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
            )
            archive.writestr(
                "xl/workbook.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Billing Report" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
            )
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        return buffer.getvalue()

    @staticmethod
    def _xlsx_sheet_xml(rows: List[List[Any]]) -> str:
        row_xml = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row, start=1):
                column_letter = chr(ord("A") + column_index - 1)
                cell_ref = f"{column_letter}{row_index}"
                if isinstance(value, (int, float)) and value != "":
                    cells.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
                else:
                    escaped = xml_escape(str(value))
                    cells.append(
                        f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'
                    )
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
        )

    def _build_pdf_artifact(
        self,
        *,
        company: CavadaLabsCompanyResponse,
        calculation: Dict[str, Any],
        checksum: str,
    ) -> bytes:
        totals = calculation["totals"]
        lines = [
            "CavadaLabs Billing Report",
            f"Company: {company.legal_name}",
            f"Period: {calculation['inputs_snapshot']['period_start']} - {calculation['inputs_snapshot']['period_end']}",
            f"Requests: {totals['requests']}",
            f"Tokens: {totals['total_tokens']}",
            f"Provider cost: {totals['provider_cost']:.6f} {totals['currency']}",
            f"Node cost: {totals['cavadalabs_node_cost']:.6f} {totals['currency']}",
            f"Grand total: {totals['grand_total']:.6f} {totals['currency']}",
            f"Checksum: {checksum}",
            "Methodology: provider spend from CavadaLabs ledger; node cost allocated by token share.",
        ]
        return self._minimal_pdf(lines)

    @staticmethod
    def _minimal_pdf(lines: Iterable[str]) -> bytes:
        escaped_lines = [
            str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in lines
        ]
        text_ops = ["BT", "/F1 10 Tf", "12 TL", "50 780 Td"]
        for line in escaped_lines:
            text_ops.append(f"({line}) Tj")
            text_ops.append("T*")
        text_ops.append("ET")
        stream = "\n".join(text_ops).encode("utf-8")
        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
            b"5 0 obj << /Length "
            + str(len(stream)).encode("ascii")
            + b" >> stream\n"
            + stream
            + b"\nendstream endobj\n",
        ]
        output = io.BytesIO()
        output.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(output.tell())
            output.write(obj)
        xref_offset = output.tell()
        output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        output.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.write(
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
                "ascii"
            )
        )
        return output.getvalue()

    async def _audit(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        action: str,
        resource_type: str,
        resource_id: str,
        before_value: Optional[Dict[str, Any]],
        after_value: Optional[Dict[str, Any]],
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        try:
            await self.db.cavadalabs_auditlogtable.create(
                data=serialize_prisma_json_fields(
                    {
                    "actor_user_id": _actor_user_id(user_api_key_dict),
                    "actor_api_key_hash": _actor_key_hash(user_api_key_dict),
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "company_id": company_id,
                    "project_id": project_id,
                    "before_value": before_value,
                    "after_value": after_value,
                    }
                )
            )
        except Exception as exc:
            verbose_proxy_logger.warning(
                "Failed to write CavadaLabs audit log for %s/%s: %s",
                resource_type,
                resource_id,
                exc,
            )
