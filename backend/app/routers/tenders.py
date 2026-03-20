from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Tender
from app.schemas import TenderCreate, TenderCreateResponse, TenderDetail, TenderListItem

router = APIRouter(prefix="/tenders", tags=["tenders"])


@router.post(
    "",
    response_model=TenderCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tender(payload: TenderCreate, db: Session = Depends(get_db)) -> Tender:
    tender = Tender(
        title=payload.title,
        customer_name=payload.customer_name,
        description=payload.description,
    )

    db.add(tender)
    db.commit()
    db.refresh(tender)

    return tender


@router.get("", response_model=list[TenderListItem])
def list_tenders(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Tender]:
    stmt = (
        select(Tender)
        .order_by(Tender.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    tenders = db.execute(stmt).scalars().all()
    return list(tenders)


@router.get("/{tender_id}", response_model=TenderDetail)
def get_tender(tender_id: UUID, db: Session = Depends(get_db)) -> Tender:
    stmt = (
        select(Tender)
        .options(selectinload(Tender.documents))
        .where(Tender.id == tender_id)
    )
    tender = db.execute(stmt).scalar_one_or_none()

    if tender is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )

    return tender