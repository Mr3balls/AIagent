from __future__ import annotations

import json
import logging
from typing import Any

import requests
from openai import APIConnectionError, APITimeoutError, BadRequestError, OpenAI, RateLimitError
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import get_settings

logger = logging.getLogger(__name__)


class AIAnalyzerError(Exception):
    pass


class AIAnalyzerConfigurationError(AIAnalyzerError):
    pass


class AIAnalyzerResponseError(AIAnalyzerError):
    pass


class VendorItem(BaseModel):
    name: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value):
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return value
        if numeric > 1 and numeric <= 100:
            return numeric / 100
        return numeric


class EquipmentItem(BaseModel):
    name: str
    quantity: int | None = Field(default=None, ge=0)
    unit: str | None = None
    vendor: str | None = None
    characteristics: list[str] = Field(default_factory=list)
    model: str | None = None
    exact_model: str | None = None
    vendor_model: str | None = None
    model_specified: bool | None = None

    @field_validator("quantity", mode="before")
    @classmethod
    def normalize_quantity(cls, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            if not cleaned:
                return None
            try:
                return int(float(cleaned))
            except ValueError:
                return value
        return value

    @field_validator("model_specified", mode="before")
    @classmethod
    def normalize_model_specified(cls, value):
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "да"}:
                return True
            if normalized in {"false", "0", "no", "n", "нет"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return value


class IntegrationItem(BaseModel):
    name: str
    details: str | None = None


class CertificateItem(BaseModel):
    name: str
    required_for: str | None = None


class TimelineInfo(BaseModel):
    raw_text: str | None = None
    implementation_days: int | None = Field(default=None, ge=0)
    delivery_deadline: str | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("implementation_days", mode="before")
    @classmethod
    def normalize_implementation_days(cls, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            if not cleaned:
                return None
            try:
                return int(float(cleaned))
            except ValueError:
                return value
        return value


class TenderAnalysisResult(BaseModel):
    project_type: str | None = None
    equipment: list[EquipmentItem] = Field(default_factory=list)
    total_device_count: int | None = Field(default=None, ge=0)
    vendors: list[VendorItem] = Field(default_factory=list)
    has_or_equivalent: bool
    or_equivalent_evidence: list[str] = Field(default_factory=list)
    timelines: TimelineInfo = Field(default_factory=TimelineInfo)
    integrations: list[IntegrationItem] = Field(default_factory=list)
    certificates: list[CertificateItem] = Field(default_factory=list)
    extracted_languages: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manufacturer_authorization_required: bool | None = None
    has_object_scheme: bool | None = None
    has_installation_points: bool | None = None
    specific_model_detected: bool | None = None

    @field_validator(
        "has_or_equivalent",
        "manufacturer_authorization_required",
        "has_object_scheme",
        "has_installation_points",
        "specific_model_detected",
        mode="before",
    )
    @classmethod
    def normalize_bool_fields(cls, value):
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "да"}:
                return True
            if normalized in {"false", "0", "no", "n", "нет"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return value

    @field_validator("total_device_count", mode="before")
    @classmethod
    def normalize_total_device_count(cls, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            if not cleaned:
                return None
            try:
                return int(float(cleaned))
            except ValueError:
                return value
        return value


class OpenAIAnalyzer:
    def __init__(
        self,
        *,
        model: str | None = None,
        timeout: float | None = None,
        max_input_chars: int = 6000,
    ) -> None:
        settings = get_settings()

        self.settings = settings
        self.provider = settings.ai_provider.strip().lower()
        self.max_input_chars = max_input_chars

        if self.provider == "openai":
            if not settings.openai_api_key:
                raise AIAnalyzerConfigurationError("OPENAI_API_KEY is not configured")
            self.client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=timeout or 90.0,
            )
            self.model = model or "gpt-4.1"
        elif self.provider == "ollama":
            self.client = None
            self.model = model or settings.ollama_model
            self.timeout = timeout or settings.ollama_timeout_seconds
            self.base_url = settings.ollama_base_url.rstrip("/")
        else:
            raise AIAnalyzerConfigurationError(
                f"Unsupported AI_PROVIDER: {settings.ai_provider}"
            )

    def analyze_document(
        self,
        *,
        document_text: str,
        sections: list[dict[str, Any]] | None = None,
        tables: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sections = sections or []
        tables = tables or []
        metadata = metadata or {}

        prepared_payload = self._build_input_payload(
            document_text=document_text,
            sections=sections,
            tables=tables,
            metadata=metadata,
        )

        prompt = self._build_prompt(prepared_payload)
        schema = self._json_schema()

        if self.provider == "openai":
            raw_json = self._analyze_with_openai(prompt, schema)
        elif self.provider == "ollama":
            raw_json = self._analyze_with_ollama(prompt, schema)
        else:
            raise AIAnalyzerConfigurationError(
                f"Unsupported AI provider: {self.provider}"
            )

        validated = self._validate_json(raw_json)
        return validated.model_dump()

    def _analyze_with_openai(self, prompt: str, schema: dict[str, Any]) -> str:
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
                temperature=0,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "tender_analysis",
                        "schema": schema,
                        "strict": True,
                    }
                },
            )
        except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
            logger.exception("OpenAI API error during tender analysis")
            raise AIAnalyzerError(f"OpenAI API error: {exc}") from exc
        except BadRequestError as exc:
            logger.exception("Bad request sent to OpenAI API")
            raise AIAnalyzerError(f"OpenAI API bad request: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected OpenAI API error")
            raise AIAnalyzerError(f"Unexpected OpenAI API error: {exc}") from exc

        return self._extract_openai_response_text(response)

    def _analyze_with_ollama(self, prompt: str, schema: dict[str, Any]) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            "options": {
                "temperature": 0,
                "num_ctx": 4096,
            },
            "keep_alive": "10m",
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            logger.exception("Ollama request timeout")
            raise AIAnalyzerError(f"Ollama timeout: {exc}") from exc
        except requests.RequestException as exc:
            logger.exception("Ollama request failed")
            raise AIAnalyzerError(f"Ollama request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            logger.exception("Ollama returned non-JSON response envelope")
            raise AIAnalyzerResponseError("Invalid Ollama response envelope") from exc

        content = data.get("message", {}).get("content") if isinstance(data, dict) else None

        if not isinstance(content, str) or not content.strip():
            raise AIAnalyzerResponseError("Empty Ollama model response")

        return content.strip()

    def _build_prompt(self, prepared_payload: dict[str, Any]) -> str:
        return f"""
Extract data from tender documentation and return JSON only.

Fields to extract:
- project_type
- equipment
- total_device_count
- vendors
- has_or_equivalent
- or_equivalent_evidence
- timelines
- integrations
- certificates
- extracted_languages
- assumptions
- warnings
- manufacturer_authorization_required
- has_object_scheme
- has_installation_points
- specific_model_detected

Rules:
- Use only explicit information where possible.
- If missing, return null or empty arrays.
- confidence must be between 0 and 1.
- Keep output concise.
- Return JSON only.

Source:
{json.dumps(prepared_payload, ensure_ascii=False)}
        """.strip()

    def _build_input_payload(
        self,
        *,
        document_text: str,
        sections: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        trimmed_text = (document_text or "").strip()
        if len(trimmed_text) > self.max_input_chars:
            trimmed_text = trimmed_text[: self.max_input_chars]

        compact_sections = []
        for section in sections[:8]:
            compact_sections.append(
                {
                    "index": section.get("index"),
                    "title": section.get("title"),
                    "content": (section.get("content") or "")[:700],
                }
            )

        compact_tables = []
        for table in tables[:3]:
            rows = table.get("rows") or []
            compact_tables.append(
                {
                    "index": table.get("index"),
                    "title": table.get("title"),
                    "page": table.get("page"),
                    "sheet": table.get("sheet"),
                    "rows": rows[:8],
                }
            )

        return {
            "metadata": metadata,
            "document_text": trimmed_text[:3000],
            "sections": compact_sections,
            "tables": compact_tables,
        }

    def _extract_openai_response_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text and isinstance(output_text, str):
            return output_text.strip()

        try:
            output = getattr(response, "output", []) or []
            collected: list[str] = []

            for item in output:
                content = getattr(item, "content", []) or []
                for part in content:
                    part_text = getattr(part, "text", None)
                    if isinstance(part_text, str):
                        collected.append(part_text)

            merged = "\n".join(collected).strip()
            if merged:
                return merged
        except Exception:
            logger.exception("Failed to parse OpenAI response fallback")

        raise AIAnalyzerResponseError("Empty or unreadable OpenAI response")

    def _validate_json(self, raw_json: str) -> TenderAnalysisResult:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.exception("Model returned invalid JSON")
            raise AIAnalyzerResponseError(f"Invalid JSON from model: {exc}") from exc

        try:
            return TenderAnalysisResult.model_validate(data)
        except ValidationError as exc:
            logger.exception("Model JSON failed schema validation")
            raise AIAnalyzerResponseError(
                f"Model JSON schema validation failed: {exc}"
            ) from exc

    @staticmethod
    def _json_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "project_type": {"type": ["string", "null"]},
                "equipment": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": ["integer", "null"], "minimum": 0},
                            "unit": {"type": ["string", "null"]},
                            "vendor": {"type": ["string", "null"]},
                            "characteristics": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "model": {"type": ["string", "null"]},
                            "exact_model": {"type": ["string", "null"]},
                            "vendor_model": {"type": ["string", "null"]},
                            "model_specified": {"type": ["boolean", "null"]},
                        },
                        "required": [
                            "name",
                            "quantity",
                            "unit",
                            "vendor",
                            "characteristics",
                            "model",
                            "exact_model",
                            "vendor_model",
                            "model_specified",
                        ],
                    },
                },
                "total_device_count": {"type": ["integer", "null"], "minimum": 0},
                "vendors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                        },
                        "required": ["name", "confidence"],
                    },
                },
                "has_or_equivalent": {"type": "boolean"},
                "or_equivalent_evidence": {"type": "array", "items": {"type": "string"}},
                "timelines": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "raw_text": {"type": ["string", "null"]},
                        "implementation_days": {"type": ["integer", "null"], "minimum": 0},
                        "delivery_deadline": {"type": ["string", "null"]},
                        "notes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["raw_text", "implementation_days", "delivery_deadline", "notes"],
                },
                "integrations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "details": {"type": ["string", "null"]},
                        },
                        "required": ["name", "details"],
                    },
                },
                "certificates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "required_for": {"type": ["string", "null"]},
                        },
                        "required": ["name", "required_for"],
                    },
                },
                "extracted_languages": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "manufacturer_authorization_required": {"type": ["boolean", "null"]},
                "has_object_scheme": {"type": ["boolean", "null"]},
                "has_installation_points": {"type": ["boolean", "null"]},
                "specific_model_detected": {"type": ["boolean", "null"]},
            },
            "required": [
                "project_type",
                "equipment",
                "total_device_count",
                "vendors",
                "has_or_equivalent",
                "or_equivalent_evidence",
                "timelines",
                "integrations",
                "certificates",
                "extracted_languages",
                "assumptions",
                "warnings",
                "manufacturer_authorization_required",
                "has_object_scheme",
                "has_installation_points",
                "specific_model_detected",
            ],
        }