from typing import Annotated
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tender, TenderDocument, User
from app.schemas import TenderDocumentResponse, TenderUploadResponse
from app.security import get_current_user
from app.services.file_service import FileService

STORAGE_ROOT = Path("storage")

router = APIRouter(prefix="/tenders", tags=["tender-documents"])


@router.post(
    "/{tender_id}/upload",
    response_model=TenderUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_tender_documents(
    tender_id: UUID,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> TenderUploadResponse:
    tender = db.execute(
        select(Tender).where(Tender.id == tender_id, Tender.owner_id == current_user.id)
    ).scalar_one_or_none()

    if tender is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender not found",
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    service = FileService(storage_root="storage")
    created_documents: list[TenderDocument] = []

    try:
        for upload in files:
            saved = service.save_upload(str(tender.id), upload)

            document = TenderDocument(
                tender_id=tender.id,
                original_filename=saved.original_filename,
                stored_filename=saved.stored_filename,
                file_path=saved.relative_path,
                file_type=saved.file_extension,
                mime_type=saved.mime_type,
                file_size=saved.file_size,
                checksum_sha256=saved.checksum_sha256,
            )
            db.add(document)
            created_documents.append(document)

        db.commit()

        for document in created_documents:
            db.refresh(document)

        return TenderUploadResponse(
            tender_id=tender.id,
            uploaded_count=len(created_documents),
            documents=[
                TenderDocumentResponse.model_validate(doc) for doc in created_documents
            ],
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload documents",
        ) from exc


@router.get("/{tender_id}/documents/{document_id}/download")
def download_tender_document(
    tender_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> FileResponse:
    tender = db.execute(
        select(Tender).where(Tender.id == tender_id, Tender.owner_id == current_user.id)
    ).scalar_one_or_none()

    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

    document = db.execute(
        select(TenderDocument).where(
            TenderDocument.id == document_id,
            TenderDocument.tender_id == tender_id,
        )
    ).scalar_one_or_none()

    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # file_path может быть абсолютным или относительным
    path = Path(document.file_path)
    if not path.is_absolute():
        path = STORAGE_ROOT / path

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    return FileResponse(
        path=str(path),
        filename=document.original_filename,
        media_type=document.mime_type or "application/octet-stream",
    )