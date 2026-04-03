from __future__ import annotations

import ast
import json
import logging
import os
import re
import time
import unicodedata
from typing import Any

import requests
from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
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
    def normalize_confidence(cls, value: Any) -> Any:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return value
        if 1 < numeric <= 100:
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
    def normalize_quantity(cls, value: Any) -> Any:
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
    def normalize_model_specified(cls, value: Any) -> Any:
        return OpenAIAnalyzer._to_optional_bool(value)


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
    def normalize_implementation_days(cls, value: Any) -> Any:
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
    has_or_equivalent: bool = False
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
    def normalize_bool_fields(cls, value: Any) -> Any:
        return OpenAIAnalyzer._to_optional_bool(value)

    @field_validator("total_device_count", mode="before")
    @classmethod
    def normalize_total_device_count(cls, value: Any) -> Any:
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

            client_kwargs: dict[str, Any] = {
                "api_key": settings.openai_api_key,
                "base_url": settings.openai_base_url,
                "timeout": timeout or settings.openai_timeout_seconds,
            }

            if "openrouter.ai" in settings.openai_base_url:
                client_kwargs["default_headers"] = {
                    "HTTP-Referer": "http://localhost:3000",
                    "X-OpenRouter-Title": "Tender AI",
                }

            self.client = OpenAI(**client_kwargs)
            self.model = model or settings.openai_model
            self.fallback_models = self._load_fallback_models(self.model)
            self.request_retries = 2
            self.retry_backoff_seconds = 1.5
        elif self.provider == "ollama":
            self.client = None
            self.model = model or settings.ollama_model
            self.timeout = timeout or settings.ollama_timeout_seconds
            self.base_url = settings.ollama_base_url.rstrip("/")
            self.fallback_models = []
            self.request_retries = 1
            self.retry_backoff_seconds = 1.0
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

        try:
            if self.provider == "openai":
                raw_json = self._analyze_with_openai(prompt, schema)
            elif self.provider == "ollama":
                raw_json = self._analyze_with_ollama(prompt, schema)
            else:
                raise AIAnalyzerConfigurationError(
                    f"Unsupported AI provider: {self.provider}"
                )

            validated = self._validate_json(raw_json, source_payload=prepared_payload)
            return validated.model_dump()
        except AIAnalyzerConfigurationError:
            raise
        except AIAnalyzerError as exc:
            logger.exception("AI analysis failed, returning fallback result")
            fallback_payload = self._build_fallback_result(
                source_payload=prepared_payload,
                raw_output="",
                errors=[self._format_exception(exc)],
            )
            return TenderAnalysisResult.model_validate(fallback_payload).model_dump()
        except Exception as exc:
            logger.exception("Unexpected analyzer failure, returning fallback result")
            fallback_payload = self._build_fallback_result(
                source_payload=prepared_payload,
                raw_output="",
                errors=[self._format_exception(exc)],
            )
            return TenderAnalysisResult.model_validate(fallback_payload).model_dump()


    def _analyze_with_openai(self, prompt: str, schema: dict[str, Any]) -> str:
        del schema

        errors: list[str] = []
        for candidate_model in self._iter_candidate_models():
            for attempt in range(1, self.request_retries + 1):
                try:
                    response = self.client.chat.completions.create(
                        model=candidate_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0,
                        response_format={"type": "json_object"},
                    )
                    return self._extract_openai_response_text(response)
                except (RateLimitError, APITimeoutError, APIConnectionError, BadRequestError) as exc:
                    if self._is_rate_limit_error(exc):
                        message = (
                            f"{candidate_model} rate-limited on attempt {attempt}: "
                            f"{self._format_exception(exc)}"
                        )
                    else:
                        message = (
                            f"{candidate_model} request failed on attempt {attempt}: "
                            f"{self._format_exception(exc)}"
                        )
                    logger.warning(message)
                    errors.append(message)
                    if attempt < self.request_retries:
                        time.sleep(self.retry_backoff_seconds * attempt)
                        continue
                    break
                except Exception as exc:
                    if self._is_rate_limit_error(exc):
                        message = (
                            f"{candidate_model} rate-limited on attempt {attempt}: "
                            f"{self._format_exception(exc)}"
                        )
                        logger.warning(message)
                        errors.append(message)
                        if attempt < self.request_retries:
                            time.sleep(self.retry_backoff_seconds * attempt)
                            continue
                        break

                    logger.exception(
                        "OpenAI SDK parsing/request failed for model %s, trying HTTP fallback",
                        candidate_model,
                    )
                    try:
                        return self._analyze_with_openai_http_fallback(
                            prompt,
                            model_name=candidate_model,
                            original_error=exc,
                        )
                    except AIAnalyzerError as fallback_exc:
                        errors.append(self._format_exception(fallback_exc))
                        break

        raise AIAnalyzerError(
            "OpenAI-compatible API error: all model attempts failed. " + " | ".join(errors[:8])
        )


    def _analyze_with_ollama(self, prompt: str, schema: dict[str, Any]) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "num_ctx": 4096},
            "keep_alive": "10m",
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
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

    def _analyze_with_openai_http_fallback(
        self,
        prompt: str,
        model_name: str,
        original_error: Exception,
    ) -> str:
        base_url = (self.settings.openai_base_url or "").rstrip("/")
        if not base_url:
            raise AIAnalyzerError(f"Unexpected OpenAI-compatible API error: {original_error}") from original_error

        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in base_url:
            headers["HTTP-Referer"] = "http://localhost:3000"
            headers["X-OpenRouter-Title"] = "Tender AI"

        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        last_error: Exception | None = None
        for use_response_format in (True, False):
            request_payload = dict(payload)
            if not use_response_format:
                request_payload.pop("response_format", None)
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=request_payload,
                    timeout=self.settings.openai_timeout_seconds,
                )

                if response.status_code == 429:
                    raw_body = response.text[:500]
                    raise AIAnalyzerError(
                        f"Rate limit from provider for model {model_name}: {raw_body}"
                    )

                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
                raise AIAnalyzerResponseError("Empty HTTP fallback model response")
            except AIAnalyzerError as exc:
                last_error = exc
                logger.warning(
                    "HTTP fallback request rate-limited/failed for model %s (response_format=%s): %s",
                    model_name,
                    use_response_format,
                    exc,
                )
            except Exception as exc:
                last_error = exc
                logger.exception(
                    "HTTP fallback request to OpenAI-compatible API failed for model %s (response_format=%s)",
                    model_name,
                    use_response_format,
                )

        raise AIAnalyzerError(
            f"Unexpected OpenAI-compatible API error for model {model_name}: {original_error}. HTTP fallback failed: {last_error}"
        ) from original_error

    def _load_fallback_models(self, primary_model: str) -> list[str]:
        raw = os.getenv("OPENAI_FALLBACK_MODELS", "")
        models: list[str] = []
        for item in raw.split(","):
            name = item.strip()
            if name and name != primary_model and name not in models:
                models.append(name)
        return models

    def _iter_candidate_models(self) -> list[str]:
        result = [self.model]
        for name in self.fallback_models:
            if name not in result:
                result.append(name)
        return result

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        try:
            message = str(exc).strip()
        except Exception:
            message = exc.__class__.__name__
        return message or exc.__class__.__name__

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        if isinstance(exc, RateLimitError):
            return True

        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True

        response = getattr(exc, "response", None)
        if response is not None:
            response_status = getattr(response, "status_code", None)
            if response_status == 429:
                return True

        message = OpenAIAnalyzer._format_exception(exc).lower()
        rate_limit_markers = (
            "error code: 429",
            "code: 429",
            "status code 429",
            "rate-limit",
            "rate limit",
            "rate limited",
            "temporarily rate-limited",
            "too many requests",
        )
        return any(marker in message for marker in rate_limit_markers)

    def _build_prompt(self, prepared_payload: dict[str, Any]) -> str:
        return f"""
Extract data from tender documentation and return ONE valid JSON object only.

Return JSON with exactly these fields:
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

Strict output rules:
- has_or_equivalent must always be true or false, never null
- or_equivalent_evidence must always be an array, never null
- timelines must always be an object:
  {{
    "raw_text": null,
    "implementation_days": null,
    "delivery_deadline": null,
    "notes": []
  }}
- integrations must always be an array of objects:
  [{{"name": "string", "details": null}}]
- certificates must always be an array of objects:
  [{{"name": "string", "required_for": null}}]
- extracted_languages must always be an array
- assumptions must always be an array
- warnings must always be an array
- Do not wrap JSON in markdown
- Do not add explanations before or after JSON
- Use null only where a nullable scalar is expected
- Return JSON only

Source:
{json.dumps(prepared_payload, ensure_ascii=False, allow_nan=False)}
        """.strip()

    @staticmethod
    def _sanitize_text(value: Any, *, max_len: int | None = None) -> str:
        if value is None:
            text = ""
        elif isinstance(value, str):
            text = value
        else:
            text = str(value)

        text = unicodedata.normalize("NFKC", text)
        text = text.replace("\x00", " ").replace("\ufeff", "").replace("\u200b", "")
        text = "".join(
            ch if (ch in "\n\r\t" or unicodedata.category(ch)[0] != "C") else " "
            for ch in text
        )
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        if max_len is not None and len(text) > max_len:
            text = text[:max_len]
        return text

    @classmethod
    def _sanitize_json_compatible(cls, value: Any, *, max_string_len: int = 500) -> Any:
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            if value != value:
                return None
            if value == float("inf") or value == float("-inf"):
                return None
            return value
        if isinstance(value, str):
            return cls._sanitize_text(value, max_len=max_string_len)
        if isinstance(value, list):
            return [cls._sanitize_json_compatible(item, max_string_len=max_string_len) for item in value[:50]]
        if isinstance(value, tuple):
            return [cls._sanitize_json_compatible(item, max_string_len=max_string_len) for item in value[:50]]
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, item in list(value.items())[:50]:
                cleaned[str(key)] = cls._sanitize_json_compatible(item, max_string_len=max_string_len)
            return cleaned
        return cls._sanitize_text(value, max_len=max_string_len)

    def _build_input_payload(
        self,
        *,
        document_text: str,
        sections: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        trimmed_text = self._sanitize_text(document_text, max_len=self.max_input_chars)

        compact_sections: list[dict[str, Any]] = []
        for section in sections[:8]:
            compact_sections.append(
                {
                    "index": section.get("index"),
                    "title": self._sanitize_text(section.get("title"), max_len=120) or None,
                    "content": self._sanitize_text(section.get("content"), max_len=700),
                }
            )

        compact_tables: list[dict[str, Any]] = []
        for table in tables[:3]:
            rows = table.get("rows") or []
            compact_tables.append(
                {
                    "index": table.get("index"),
                    "title": self._sanitize_text(table.get("title"), max_len=120) or None,
                    "page": table.get("page"),
                    "sheet": self._sanitize_text(table.get("sheet"), max_len=120) or None,
                    "rows": self._sanitize_json_compatible(rows[:8], max_string_len=250),
                }
            )

        return {
            "metadata": self._sanitize_json_compatible(metadata, max_string_len=250),
            "document_text": trimmed_text[:3000],
            "sections": compact_sections,
            "tables": compact_tables,
        }


    def _extract_openai_response_text(self, response: Any) -> str:
        try:
            choice = response.choices[0]
            message = choice.message
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
                if parts:
                    return "\n".join(parts)
        except Exception:
            logger.exception("Failed to parse OpenAI-compatible response")
        raise AIAnalyzerResponseError("Empty or unreadable OpenAI-compatible response")

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        optional = OpenAIAnalyzer._to_optional_bool(value)
        return default if optional is None else optional

    @staticmethod
    def _to_optional_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "да"}:
                return True
            if normalized in {"false", "0", "no", "n", "нет", ""}:
                return False
        return None

    @staticmethod
    def _to_string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    result.append(text)
            return result
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return []

    @staticmethod
    def _to_timeline_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                "raw_text": value.get("raw_text") or value.get("text") or value.get("raw"),
                "implementation_days": value.get("implementation_days") or value.get("days"),
                "delivery_deadline": value.get("delivery_deadline") or value.get("deadline"),
                "notes": OpenAIAnalyzer._to_string_list(value.get("notes")),
            }
        if isinstance(value, str):
            text = value.strip()
            return {
                "raw_text": text or None,
                "implementation_days": None,
                "delivery_deadline": None,
                "notes": [],
            }
        return {
            "raw_text": None,
            "implementation_days": None,
            "delivery_deadline": None,
            "notes": [],
        }

    @staticmethod
    def _to_integrations_list(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        result: list[dict[str, Any]] = []
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("system")
                if name:
                    result.append(
                        {
                            "name": str(name).strip(),
                            "details": (
                                str(item.get("details")).strip()
                                if item.get("details") is not None
                                else None
                            ),
                        }
                    )
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    result.append({"name": text, "details": None})
        return result

    @staticmethod
    def _to_certificates_list(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        result: list[dict[str, Any]] = []
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title")
                if name:
                    result.append(
                        {
                            "name": str(name).strip(),
                            "required_for": (
                                str(item.get("required_for")).strip()
                                if item.get("required_for") is not None
                                else None
                            ),
                        }
                    )
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    result.append({"name": text, "required_for": None})
        return result

    @staticmethod
    def _to_equipment_list(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        result: list[dict[str, Any]] = []
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("device")
                if not name:
                    continue
                result.append(
                    {
                        "name": str(name).strip(),
                        "quantity": item.get("quantity"),
                        "unit": item.get("unit"),
                        "vendor": item.get("vendor"),
                        "characteristics": OpenAIAnalyzer._to_string_list(
                            item.get("characteristics")
                        ),
                        "model": item.get("model"),
                        "exact_model": item.get("exact_model"),
                        "vendor_model": item.get("vendor_model"),
                        "model_specified": item.get("model_specified"),
                    }
                )
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    result.append(
                        {
                            "name": text,
                            "quantity": None,
                            "unit": None,
                            "vendor": None,
                            "characteristics": [],
                            "model": None,
                            "exact_model": None,
                            "vendor_model": None,
                            "model_specified": None,
                        }
                    )
        return result

    @staticmethod
    def _to_vendors_list(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        result: list[dict[str, Any]] = []
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("vendor") or item.get("title")
                if name:
                    result.append(
                        {
                            "name": str(name).strip(),
                            "confidence": item.get("confidence"),
                        }
                    )
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    result.append({"name": text, "confidence": None})
        return result

    @staticmethod
    def _normalize_result_payload(data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(data)
        normalized.setdefault("project_type", None)
        normalized["equipment"] = OpenAIAnalyzer._to_equipment_list(normalized.get("equipment"))
        normalized["total_device_count"] = normalized.get("total_device_count")
        normalized["vendors"] = OpenAIAnalyzer._to_vendors_list(normalized.get("vendors"))
        normalized["has_or_equivalent"] = OpenAIAnalyzer._to_bool(
            normalized.get("has_or_equivalent"),
            default=False,
        )
        normalized["or_equivalent_evidence"] = OpenAIAnalyzer._to_string_list(
            normalized.get("or_equivalent_evidence")
        )
        normalized["timelines"] = OpenAIAnalyzer._to_timeline_dict(normalized.get("timelines"))
        normalized["integrations"] = OpenAIAnalyzer._to_integrations_list(
            normalized.get("integrations")
        )
        normalized["certificates"] = OpenAIAnalyzer._to_certificates_list(
            normalized.get("certificates")
        )
        normalized["extracted_languages"] = OpenAIAnalyzer._to_string_list(
            normalized.get("extracted_languages")
        )
        normalized["assumptions"] = OpenAIAnalyzer._to_string_list(normalized.get("assumptions"))
        normalized["warnings"] = OpenAIAnalyzer._to_string_list(normalized.get("warnings"))
        normalized["manufacturer_authorization_required"] = OpenAIAnalyzer._to_optional_bool(
            normalized.get("manufacturer_authorization_required")
        )
        normalized["has_object_scheme"] = OpenAIAnalyzer._to_optional_bool(
            normalized.get("has_object_scheme")
        )
        normalized["has_installation_points"] = OpenAIAnalyzer._to_optional_bool(
            normalized.get("has_installation_points")
        )
        normalized["specific_model_detected"] = OpenAIAnalyzer._to_optional_bool(
            normalized.get("specific_model_detected")
        )
        return normalized

    def _validate_json(
        self,
        raw_json: str,
        source_payload: dict[str, Any] | None = None,
    ) -> TenderAnalysisResult:
        errors: list[str] = []
        parsed_object = self._parse_model_output(raw_json, errors)

        if isinstance(parsed_object, dict):
            normalized = self._normalize_result_payload(parsed_object)
            try:
                return TenderAnalysisResult.model_validate(normalized)
            except ValidationError as exc:
                errors.append(f"schema validation failed: {exc}")
                logger.exception("Model JSON failed schema validation")

        logger.warning(
            "Falling back to heuristic analysis result because model output was invalid. Errors: %s",
            errors,
        )
        fallback_payload = self._build_fallback_result(source_payload=source_payload, raw_output=raw_json, errors=errors)
        try:
            return TenderAnalysisResult.model_validate(fallback_payload)
        except ValidationError as exc:
            logger.exception("Fallback result validation failed")
            raise AIAnalyzerResponseError(
                f"Fallback result validation failed: {exc}"
            ) from exc

    def _parse_model_output(self, raw_json: str, errors: list[str]) -> dict[str, Any] | None:
        candidates = self._candidate_json_texts(raw_json)
        seen: set[str] = set()
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)

            parsed = self._try_json_loads(candidate, errors)
            if isinstance(parsed, dict):
                return parsed

            repaired = self._repair_json_text(candidate)
            if repaired != candidate:
                parsed = self._try_json_loads(repaired, errors)
                if isinstance(parsed, dict):
                    return parsed

            parsed = self._try_literal_eval(candidate, errors)
            if isinstance(parsed, dict):
                return parsed

            if repaired != candidate:
                parsed = self._try_literal_eval(repaired, errors)
                if isinstance(parsed, dict):
                    return parsed

        return None

    def _candidate_json_texts(self, raw_json: str) -> list[str]:
        normalized = self._normalize_json_text(raw_json)
        candidates: list[str] = []
        if normalized:
            candidates.append(normalized)

        stripped = self._strip_code_fences(normalized)
        if stripped and stripped not in candidates:
            candidates.append(stripped)

        extracted = self._extract_first_json_object(stripped)
        if extracted and extracted not in candidates:
            candidates.append(extracted)

        if stripped:
            first_brace = stripped.find("{")
            last_brace = stripped.rfind("}")
            if 0 <= first_brace < last_brace:
                sliced = stripped[first_brace : last_brace + 1]
                if sliced and sliced not in candidates:
                    candidates.append(sliced)

        return candidates

    @staticmethod
    def _normalize_json_text(text: str) -> str:
        if not isinstance(text, str):
            return ""
        normalized = OpenAIAnalyzer._sanitize_text(text)
        replacements = {
            "“": '"',
            "”": '"',
            "„": '"',
            "’": "'",
            "‘": "'",
            "—": "-",
            "–": "-",
            "\xa0": " ",
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        return normalized


    @staticmethod
    def _strip_code_fences(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        return stripped.strip()

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        start = text.find("{")
        if start == -1:
            return ""
        depth = 0
        in_string = False
        escape = False
        quote_char = '"'

        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote_char:
                    in_string = False
                continue

            if char in {'"', "'"}:
                in_string = True
                quote_char = char
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return ""

    def _repair_json_text(self, text: str) -> str:
        repaired = text.strip()
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        repaired = re.sub(r'(?<!")([A-Za-z_][A-Za-z0-9_\-]*)\s*:', r'"\1":', repaired)
        repaired = re.sub(r'"([^"\\]+)"\s+"([^"\\]+)"', r'"\1", "\2"', repaired)
        repaired = re.sub(r'([}\]0-9"a-zA-Z])\s+("[A-Za-z_][^"\\]*"\s*:)', r'\1, \2', repaired)
        repaired = re.sub(r':\s*"([^"\\]+)"\s+"([A-Za-z_][^"\\]*)"\s*:', r': "\1", "\2":', repaired)
        repaired = re.sub(r':\s*([^,\]}\s][^,\]}]*)\s+"([A-Za-z_][^"\\]*)"\s*:', r': \1, "\2":', repaired)
        return repaired

    @staticmethod
    def _try_json_loads(text: str, errors: list[str]) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"json.loads failed: {exc}")
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _try_literal_eval(text: str, errors: list[str]) -> dict[str, Any] | None:
        python_like = re.sub(r"\btrue\b", "True", text, flags=re.IGNORECASE)
        python_like = re.sub(r"\bfalse\b", "False", python_like, flags=re.IGNORECASE)
        python_like = re.sub(r"\bnull\b", "None", python_like, flags=re.IGNORECASE)
        try:
            parsed = ast.literal_eval(python_like)
        except (ValueError, SyntaxError) as exc:
            errors.append(f"literal_eval failed: {exc}")
            return None
        return parsed if isinstance(parsed, dict) else None

    def _build_fallback_result(
        self,
        *,
        source_payload: dict[str, Any] | None,
        raw_output: str,
        errors: list[str],
    ) -> dict[str, Any]:
        text_parts: list[str] = []
        if source_payload:
            document_text = source_payload.get("document_text")
            if isinstance(document_text, str) and document_text.strip():
                text_parts.append(document_text)
            sections = source_payload.get("sections") or []
            for section in sections:
                if isinstance(section, dict):
                    content = section.get("content")
                    if isinstance(content, str) and content.strip():
                        text_parts.append(content)
        if raw_output.strip():
            text_parts.append(raw_output[:1500])

        combined_text = "\n".join(text_parts)
        combined_lower = combined_text.lower()

        languages: list[str] = []
        if re.search(r"[а-яё]", combined_text, flags=re.IGNORECASE):
            languages.append("ru")
        if re.search(r"[a-z]", combined_text, flags=re.IGNORECASE):
            languages.append("en")

        implementation_days = self._extract_implementation_days(combined_text)
        has_or_equivalent = bool(re.search(r"\bor equivalent\b|\bили эквивалент\b", combined_lower))
        manufacturer_auth = bool(
            re.search(
                r"manufacturer authorization|authorization letter|авторизационн|письмо производителя",
                combined_lower,
            )
        )
        has_object_scheme = bool(
            re.search(r"scheme|diagram|layout|схем[аы]|план объект", combined_lower)
        )
        has_installation_points = bool(
            re.search(r"installation point|mounting point|точк[аи] установки|места установки", combined_lower)
        )
        specific_model_detected = bool(
            re.search(r"\b[A-Z]{2,}[\-_/]?[A-Z0-9]{2,}\b", combined_text)
        )

        warnings = [
            "Model output was invalid. Returned heuristic fallback result to keep the pipeline running."
        ]
        warnings.extend(errors[:5])

        return {
            "project_type": None,
            "equipment": [],
            "total_device_count": None,
            "vendors": [],
            "has_or_equivalent": has_or_equivalent,
            "or_equivalent_evidence": self._collect_or_equivalent_evidence(combined_text),
            "timelines": {
                "raw_text": self._extract_timeline_text(combined_text),
                "implementation_days": implementation_days,
                "delivery_deadline": None,
                "notes": [],
            },
            "integrations": [],
            "certificates": [],
            "extracted_languages": languages,
            "assumptions": [
                "Fallback result generated because the model response could not be parsed safely."
            ],
            "warnings": warnings,
            "manufacturer_authorization_required": manufacturer_auth,
            "has_object_scheme": has_object_scheme,
            "has_installation_points": has_installation_points,
            "specific_model_detected": specific_model_detected,
        }

    @staticmethod
    def _extract_implementation_days(text: str) -> int | None:
        patterns = [
            r"within\s+(\d{1,4})\s+calendar\s+days",
            r"within\s+(\d{1,4})\s+days",
            r"implementation\s*[:\-]?\s*(\d{1,4})\s+days",
            r"срок\s*[:\-]?\s*(\d{1,4})\s+дн",
            r"в\s*течение\s*(\d{1,4})\s+дн",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _extract_timeline_text(text: str) -> str | None:
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned and re.search(r"deadline|срок|calendar days|дней|дн", cleaned, flags=re.IGNORECASE):
                return cleaned[:500]
        return None

    @staticmethod
    def _collect_or_equivalent_evidence(text: str) -> list[str]:
        evidence: list[str] = []
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned and re.search(r"\bor equivalent\b|\bили эквивалент\b", cleaned, flags=re.IGNORECASE):
                evidence.append(cleaned[:300])
                if len(evidence) >= 3:
                    break
        return evidence

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
                            "confidence": {
                                "type": ["number", "null"],
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["name", "confidence"],
                    },
                },
                "has_or_equivalent": {"type": "boolean"},
                "or_equivalent_evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "timelines": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "raw_text": {"type": ["string", "null"]},
                        "implementation_days": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "delivery_deadline": {"type": ["string", "null"]},
                        "notes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "raw_text",
                        "implementation_days",
                        "delivery_deadline",
                        "notes",
                    ],
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
                "extracted_languages": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "assumptions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "warnings": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "manufacturer_authorization_required": {
                    "type": ["boolean", "null"]
                },
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
