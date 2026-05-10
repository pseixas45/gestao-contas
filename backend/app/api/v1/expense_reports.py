"""
Endpoints para relatórios de reembolso de despesas de trabalho.
"""

from typing import List
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.auth import get_current_active_user
from app.models.user import User
from app.schemas.expense_report import (
    ExpenseReportCreate,
    ExpenseReportUpdate,
    ExpenseReportDetail,
    ExpenseReportSummary,
    UnreportedTransaction,
    ExpectedItemsResponse,
)
from app.services.expense_report_service import ExpenseReportService

router = APIRouter()


@router.get("/expected-items", response_model=ExpectedItemsResponse)
def get_expected_items(
    lookback: int = 6,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    return service.get_expected_items(lookback)


@router.get("/unreported-transactions", response_model=List[UnreportedTransaction])
def get_unreported_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    return service.get_unreported_transactions()


@router.get("", response_model=List[ExpenseReportSummary])
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    return service.list_reports()


@router.post("", response_model=ExpenseReportDetail)
def create_report(
    data: ExpenseReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    return service.create_report(data)


@router.get("/{report_id}", response_model=ExpenseReportDetail)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    return service.get_report(report_id)


@router.put("/{report_id}", response_model=ExpenseReportDetail)
def update_report(
    report_id: int,
    data: ExpenseReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    return service.update_report(report_id, data)


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    service.delete_report(report_id)
    return {"ok": True}


@router.get("/{report_id}/export")
def export_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExpenseReportService(db)
    buffer, filename = service.export_to_excel(report_id)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
