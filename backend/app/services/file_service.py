from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}


@dataclass
class SavedFileMeta:
    original_filename: str
    stored_filename: str
    relative_path: str
    absolute_path: str
    file_extension: str
    mime_type: str | None
    file_size: int
    checksum_sha256: str


class FileService:
    def __init__(self, storage_root: str = "storage") -> None:
        self.storage_root = Path(storage_root)

    def ensure_storage_root(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def get_tender_directory(self, tender_id: str) -> Path:
        self.ensure_storage_root()
        tender_dir = self.storage_root / tender_id
        tender_dir.mkdir(parents=True, exist_ok=True)
        return tender_dir

    def save_upload(self, tender_id: str, upload_file: UploadFile) -> SavedFileMeta:
        self._validate_upload(upload_file)

        tender_dir = self.get_tender_directory(tender_id)
        original_filename = upload_file.filename or "unnamed_file"
        extension = Path(original_filename).suffix.lower()

        safe_original_name = self._sanitize_filename(Path(original_filename).stem)
        stored_filename = f"{uuid.uuid4().hex}_{safe_original_name}{extension}"

        destination = tender_dir / stored_filename

        file_size = 0
        sha256 = hashlib.sha256()

        try:
            with destination.open("wb") as buffer:
                while True:
                    chunk = upload_file.file.read(1024 * 1024)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    sha256.update(chunk)
                    buffer.write(chunk)
        except Exception as exc:
            if destination.exists():
                destination.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {original_filename}",
            ) from exc
        finally:
            upload_file.file.close()

        relative_path = str(destination.as_posix())

        return SavedFileMeta(
            original_filename=original_filename,
            stored_filename=stored_filename,
            relative_path=relative_path,
            absolute_path=str(destination.resolve()),
            file_extension=extension,
            mime_type=upload_file.content_type,
            file_size=file_size,
            checksum_sha256=sha256.hexdigest(),
        )

    def _validate_upload(self, upload_file: UploadFile) -> None:
        if not upload_file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file must have a filename",
            )

        extension = Path(upload_file.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported file type: {extension}. "
                    f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                ),
            )

        if upload_file.content_type and upload_file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported content type: {upload_file.content_type}. "
                    "Allowed: PDF, DOCX, XLSX"
                ),
            )

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename).strip("._")
        return sanitized or "file"