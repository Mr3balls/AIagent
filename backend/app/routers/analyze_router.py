from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tender, User
from app.security import get_current_user
from app.tasks.tender_analysis import analyze_tender

router = APIRouter(prefix="/tenders", tags=["tender-analysis"])


@router.post(
    "/{tender_id}/analyze",
    status_code=status.HTTP_202_ACCEPTED,
)
def run_tender_analysis(
    tender_id: UUID,
    db: Session = Depends(get_db),
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> dict:
    tender = db.execute(
        select(Tender).where(Tender.id == tender_id, Tender.owner_id == current_user.id)
    ).scalar_one_or_none()

    if tender is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )

    result = analyze_tender.delay(str(tender_id))

    return {
        "message": "Tender analysis started",
        "tender_id": str(tender_id),
        "task_id": result.id,
        "status": "accepted",
    }