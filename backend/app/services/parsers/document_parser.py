from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class DocumentParser:
    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}

    def parse(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {extension}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        if extension == ".pdf":
            from app.services.parsers.pdf_parser import PdfParser

            result = PdfParser().parse(path)
        elif extension == ".docx":
            from app.services.parsers.docx_parser import DocxParser

            result = DocxParser().parse(path)
        elif extension == ".xlsx":
            from app.services.parsers.xlsx_parser import XlsxParser

            result = XlsxParser().parse(path)
        else:
            raise ValueError(f"Unsupported file type: {extension}")

        result["text"] = self.normalize_text(result.get("text", ""))
        result["sections"] = self.normalize_sections(result.get("sections", []))
        result["tables"] = self.normalize_tables(result.get("tables", []))
        return result

    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""

        text = text.replace("\xa0", " ")
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ ]+\n", "\n", text)
        return text.strip()

    @staticmethod
    def split_text_into_blocks(text: str, min_block_length: int = 30) -> list[dict[str, Any]]:
        if not text:
            return []

        raw_blocks = re.split(r"\n\s*\n", text)
        sections: list[dict[str, Any]] = []

        for index, block in enumerate(raw_blocks, start=1):
            normalized_block = block.strip()
            if not normalized_block:
                continue

            title = DocumentParser.extract_section_title(normalized_block)
            if len(normalized_block) < min_block_length and not title:
                continue

            sections.append(
                {
                    "index": index,
                    "title": title,
                    "content": normalized_block,
                }
            )

        return sections

    @staticmethod
    def extract_section_title(block: str) -> str | None:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            return None

        first_line = lines[0]

        if len(first_line) <= 120:
            if re.match(r"^\d+(\.\d+)*[\.\)]?\s+.+", first_line):
                return first_line
            if first_line.isupper():
                return first_line
            if re.match(r"^(раздел|section|глава|chapter)\b", first_line, flags=re.IGNORECASE):
                return first_line

        return None

    @staticmethod
    def normalize_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_sections: list[dict[str, Any]] = []

        for index, section in enumerate(sections, start=1):
            content = section.get("content", "")
            title = section.get("title")
            content = DocumentParser.normalize_text(content)

            if not content:
                continue

            normalized_sections.append(
                {
                    "index": section.get("index", index),
                    "title": title.strip() if isinstance(title, str) and title.strip() else None,
                    "content": content,
                }
            )

        return normalized_sections

    @staticmethod
    def normalize_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_tables: list[dict[str, Any]] = []

        for index, table in enumerate(tables, start=1):
            rows = table.get("rows", [])
            cleaned_rows: list[list[str]] = []

            for row in rows:
                cleaned_row = []
                for cell in row:
                    if cell is None:
                        cleaned_row.append("")
                    else:
                        cleaned_row.append(DocumentParser.normalize_text(str(cell)))
                if any(cell for cell in cleaned_row):
                    cleaned_rows.append(cleaned_row)

            if not cleaned_rows:
                continue

            normalized_tables.append(
                {
                    "index": table.get("index", index),
                    "title": table.get("title"),
                    "page": table.get("page"),
                    "sheet": table.get("sheet"),
                    "rows": cleaned_rows,
                }
            )

        return normalized_tables