from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Tender, User
from app.schemas import TenderCreate, TenderCreateResponse, TenderDetail, TenderListItem
from app.security import get_current_user

router = APIRouter(prefix="/tenders", tags=["tenders"])


@router.post(
    "",
    response_model=TenderCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tender(
    payload: TenderCreate,
    db: Session = Depends(get_db),
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> Tender:
    tender = Tender(
        owner_id=current_user.id,
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
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> list[Tender]:
    stmt = (
        select(Tender)
        .where(Tender.owner_id == current_user.id)
        .order_by(Tender.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    tenders = db.execute(stmt).scalars().all()
    return list(tenders)


@router.get("/{tender_id}", response_model=TenderDetail)
def get_tender(
    tender_id: UUID,
    db: Session = Depends(get_db),
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> Tender:
    stmt = (
        select(Tender)
        .options(selectinload(Tender.documents))
        .where(Tender.id == tender_id, Tender.owner_id == current_user.id)
    )
    tender = db.execute(stmt).scalar_one_or_none()

    if tender is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )

    return tender