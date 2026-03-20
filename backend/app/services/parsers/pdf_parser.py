from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
import pdfplumber

from app.services.parsers.document_parser import DocumentParser


class PdfParser:
    def parse(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)

        text_parts: list[str] = []
        tables: list[dict[str, Any]] = []

        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"[Page {page_number}]\n{page_text.strip()}")

                extracted_tables = page.extract_tables() or []
                for table_index, raw_table in enumerate(extracted_tables, start=1):
                    if not raw_table:
                        continue

                    rows = []
                    for row in raw_table:
                        if row is None:
                            continue
                        rows.append([cell if cell is not None else "" for cell in row])

                    if rows:
                        tables.append(
                            {
                                "index": len(tables) + 1,
                                "title": f"PDF table {table_index}",
                                "page": page_number,
                                "rows": rows,
                            }
                        )

        merged_text = "\n\n".join(text_parts).strip()

        if len(merged_text) < 100:
            fallback_text = self._extract_text_with_pymupdf(path)
            if len(fallback_text.strip()) > len(merged_text.strip()):
                merged_text = fallback_text

        normalized_text = DocumentParser.normalize_text(merged_text)
        sections = DocumentParser.split_text_into_blocks(normalized_text)

        return {
            "text": normalized_text,
            "tables": tables,
            "sections": sections,
        }

    @staticmethod
    def _extract_text_with_pymupdf(file_path: Path) -> str:
        text_parts: list[str] = []

        doc = fitz.open(file_path)
        try:
            for page_number, page in enumerate(doc, start=1):
                page_text = page.get_text("text") or ""
                if page_text.strip():
                    text_parts.append(f"[Page {page_number}]\n{page_text.strip()}")
        finally:
            doc.close()

        return "\n\n".join(text_parts).strip()