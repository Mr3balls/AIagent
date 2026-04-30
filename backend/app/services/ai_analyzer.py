from __future__ import annotations

import ast
import json
import logging
import re
import time
import unicodedata
from typing import Any, Literal

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

PresenceStatus = Literal["yes", "no", "unknown"]
RiskLevel = Literal["low", "medium", "high", "unknown"]
Recommendation = Literal["go", "go_with_conditions", "risky", "do_not_participate"]


class DocumentationCompleteness(BaseModel):
    enough_data_for_estimation: PresenceStatus = "unknown"
    has_architecture_scheme: PresenceStatus = "unknown"
    has_object_plan: PresenceStatus = "unknown"
    has_installation_points: PresenceStatus = "unknown"
    has_cable_routes: PresenceStatus = "unknown"
    has_power_supply_info: PresenceStatus = "unknown"
    has_existing_infrastructure_info: PresenceStatus = "unknown"
    missing_information: list[str] = Field(default_factory=list)
    completeness_comment: str | None = None


class TailoringAnalysis(BaseModel):
    specific_vendor_detected: PresenceStatus = "unknown"
    specific_models_detected: list[str] = Field(default_factory=list)
    or_equivalent_missing: PresenceStatus = "unknown"
    manufacturer_authorization_required: PresenceStatus = "unknown"
    partner_status_required: PresenceStatus = "unknown"
    unique_characteristics_detected: PresenceStatus = "unknown"
    tailoring_signs: list[str] = Field(default_factory=list)
    tailoring_probability: RiskLevel | None = None
    tailoring_comment: str | None = None


class TimelineAssessment(BaseModel):
    implementation_days: int | None = Field(default=None, ge=0)
    delivery_days_estimate: int | None = Field(default=None, ge=0)
    timeline_matches_scope: PresenceStatus = "unknown"
    delivery_exceeds_project_timeline: PresenceStatus = "unknown"
    requires_site_survey: PresenceStatus = "unknown"
    timeline_risk_level: RiskLevel | None = None
    timeline_comment: str | None = None


class TechnicalFeasibility(BaseModel):
    is_technically_feasible: PresenceStatus = "unknown"
    requires_additional_design: PresenceStatus = "unknown"
    requires_nonstandard_architecture: PresenceStatus = "unknown"
    depends_on_external_systems: PresenceStatus = "unknown"
    critical_technical_risks: list[str] = Field(default_factory=list)
    technical_comment: str | None = None


class DecisionInfo(BaseModel):
    recommendation: Recommendation | None = None
    decision_rationale: list[str] = Field(default_factory=list)
    go_conditions: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)

class TenderAnalysisResult(BaseModel):
    project_type: str | None = None
    equipment: list[EquipmentItem] = Field(default_factory=list)
    total_device_count: int | None = None
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

    # new v2 blocks
    documentation_completeness: DocumentationCompleteness = Field(default_factory=DocumentationCompleteness)
    tailoring_analysis: TailoringAnalysis = Field(default_factory=TailoringAnalysis)
    timeline_assessment: TimelineAssessment = Field(default_factory=TimelineAssessment)
    technical_feasibility: TechnicalFeasibility = Field(default_factory=TechnicalFeasibility)
    clarifying_questions: list[str] = Field(default_factory=list)
    decision: DecisionInfo = Field(default_factory=DecisionInfo)
    scoring_inputs: dict[str, Any] = Field(default_factory=dict)

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
        max_input_chars: int | None = None,
    ) -> None:
        settings = get_settings()

        self.settings = settings
        self.max_input_chars = max_input_chars if max_input_chars is not None else settings.max_input_chars

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
        self.fallback_models = settings.fallback_models_list
        self.request_retries = 2
        self.retry_backoff_seconds = 1.5

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
            raw_json = self._analyze_with_openai(prompt, schema)
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
                        max_tokens=self.settings.max_output_tokens,
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
        document_text = prepared_payload.get("document_text") or ""
        sections = prepared_payload.get("sections") or []
        metadata = prepared_payload.get("metadata") or {}

        section_texts: list[str] = []
        for section in sections:
            if isinstance(section, dict):
                heading = str(section.get("heading") or "").strip()
                content = str(section.get("content") or "").strip()
                if heading or content:
                    section_texts.append(f"[SECTION] {heading}\n{content}".strip())

        joined_sections = "\n\n".join(section_texts[:30])

        return f"""
Извлеки данные из тендерной документации и верни ОДИН валидный JSON-объект.

Ты выступаешь в роли:
- старшего аналитика тендерной документации
- пресейл-инженера
- технического эксперта по оценке заявок

Твоя задача — не только извлечение данных, но и экспертная оценка.

Верни JSON со следующими полями:

1. Основные поля:
- project_type — тип проекта
- equipment — список оборудования (name, quantity, unit, vendor, characteristics, model, exact_model, vendor_model, model_specified)
- total_device_count — общее количество устройств
- vendors — список вендоров (name, confidence)
- has_or_equivalent — есть ли формулировка "или эквивалент"
- or_equivalent_evidence — цитаты из документа с этой формулировкой
- timelines — сроки (raw_text, implementation_days, delivery_deadline, notes)
- integrations — список интеграций (name, details)
- certificates — требуемые сертификаты/авторизации (name, required_for)
- extracted_languages — языки документа
- assumptions — допущения, сделанные при анализе
- warnings — предупреждения и замечания
- manufacturer_authorization_required — требуется ли авторизация производителя
- has_object_scheme — есть ли схема объекта
- has_installation_points — указаны ли точки установки
- specific_model_detected — указана ли конкретная модель

2. Аналитические блоки:

documentation_completeness (полнота документации):
- enough_data_for_estimation — достаточно данных для оценки (yes/no/unknown)
- has_architecture_scheme — есть схема архитектуры (yes/no/unknown)
- has_object_plan — есть план объекта (yes/no/unknown)
- has_installation_points — указаны точки установки (yes/no/unknown)
- has_cable_routes — указаны кабельные трассы (yes/no/unknown)
- has_power_supply_info — есть данные об электропитании (yes/no/unknown)
- has_existing_infrastructure_info — есть данные о существующей инфраструктуре (yes/no/unknown)
- missing_information — список отсутствующих данных
- completeness_comment — комментарий

tailoring_analysis (признаки заточки под конкретного поставщика):
- specific_vendor_detected — обнаружен конкретный вендор (yes/no/unknown)
- specific_models_detected — список конкретных моделей
- or_equivalent_missing — отсутствует "или эквивалент" (yes/no/unknown)
- manufacturer_authorization_required — требуется авторизация производителя (yes/no/unknown)
- partner_status_required — требуется партнерский статус (yes/no/unknown)
- unique_characteristics_detected — уникальные характеристики (yes/no/unknown)
- tailoring_signs — список признаков заточки
- tailoring_probability — вероятность заточки (low/medium/high)
- tailoring_comment — комментарий

timeline_assessment (оценка сроков):
- implementation_days — срок реализации в днях
- delivery_days_estimate — оценка срока поставки в днях
- timeline_matches_scope — сроки соответствуют объему работ (yes/no/unknown)
- delivery_exceeds_project_timeline — срок поставки превышает срок проекта (yes/no/unknown)
- requires_site_survey — требуется обследование объекта (yes/no/unknown)
- timeline_risk_level — уровень риска по срокам (low/medium/high)
- timeline_comment — комментарий

technical_feasibility (техническая реализуемость):
- is_technically_feasible — технически реализуемо (yes/no/unknown)
- requires_additional_design — требуется дополнительное проектирование (yes/no/unknown)
- requires_nonstandard_architecture — нестандартная архитектура (yes/no/unknown)
- depends_on_external_systems — зависит от внешних систем (yes/no/unknown)
- critical_technical_risks — список критических технических рисков
- technical_comment — комментарий

decision (решение):
- recommendation — рекомендация: go / go_with_conditions / risky / do_not_participate
- decision_rationale — обоснование решения
- go_conditions — условия для участия
- blocking_issues — блокирующие проблемы

scoring_inputs (булевы флаги для расчёта рисков, true/false):
- specific_model_equipment — указана конкретная модель оборудования
- no_or_equivalent — отсутствует "или эквивалент"
- manufacturer_authorization_required — требуется авторизация производителя
- partner_status_required — требуется партнерский статус
- unique_characteristics_detected — уникальные технические характеристики
- implementation_lt_30_days — срок реализации менее 30 дней
- timeline_not_matching_scope — сроки не соответствуют объему работ
- delivery_gt_project_timeline — срок поставки превышает срок проекта
- no_architecture_or_scheme — отсутствует схема архитектуры
- no_object_plan — отсутствует план объекта
- no_installation_points — не указаны точки установки
- no_cable_routes — не указаны кабельные трассы
- unique_experience_required — требуется уникальный опыт
- specific_project_experience_required — требуется опыт конкретного проекта
- specific_vendor_experience_required — требуется опыт с конкретным вендором
- external_system_integrations — сложные внешние интеграции
- nonstandard_architecture — нестандартная архитектура
- site_survey_required — требуется обследование объекта

Поддерживаемые языки документов: русский, английский, казахский.
Документ может быть написан на одном или нескольких из этих языков одновременно.
Анализируй текст независимо от языка — ключевые термины встречаются на всех трёх.

Правила:
- используй только факты из документа
- если что-то неясно — используй "unknown"
- не придумывай вендоров, сроки, сертификаты, интеграции, бюджеты или опыт
- сомнения помещай в assumptions
- если документ неполный — отражай это в documentation_completeness.missing_information
- clarifying_questions — практические вопросы заказчику
- в поле extracted_languages укажи все языки документа: "ru", "en", "kk"

Метаданные:
{json.dumps(metadata, ensure_ascii=False, indent=2)}

Текст документа:
{document_text[:120000]}

Разделы:
{joined_sections[:40000]}
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
        for section in sections[:self.settings.max_sections]:
            compact_sections.append(
                {
                    "index": section.get("index"),
                    "title": self._sanitize_text(section.get("title"), max_len=120) or None,
                    "content": self._sanitize_text(section.get("content"), max_len=self.settings.max_section_chars),
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
            "document_text": trimmed_text,
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
    def _to_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            cleaned = value.strip().lower().replace(",", ".")
            if cleaned in {"", "unknown", "n/a", "none", "null", "not specified"}:
                return None
            try:
                return int(float(cleaned))
            except ValueError:
                digits = "".join(ch for ch in cleaned if ch.isdigit())
                if digits:
                    try:
                        return int(digits)
                    except ValueError:
                        return None
        return None


    @staticmethod
    def _to_optional_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().lower().replace(",", ".")
            if cleaned in {"", "unknown", "n/a", "none", "null", "not specified"}:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @staticmethod
    def _to_presence_status(value: Any) -> str:
        """Converts bool/str to 'yes'/'no'/'unknown'."""
        if value is None:
            return "unknown"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"yes", "true", "1", "да"}:
                return "yes"
            if normalized in {"no", "false", "0", "нет"}:
                return "no"
        return "unknown"

    @staticmethod
    def _to_risk_level(value: Any) -> str | None:
        """Converts any value to 'low'/'medium'/'high' or None."""
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"low", "medium", "high"}:
            return text
        if text in {"unknown", ""}:
            return None
        return None

    @staticmethod
    def _to_recommendation(value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip().lower()
        if not text:
            return None

        if text in {"go", "go_with_conditions", "risky", "do_not_participate"}:
            return text

        if "cannot proceed" in text or "additional information" in text or "clarification" in text:
            return "go_with_conditions"

        if "do not participate" in text or "not participate" in text:
            return "do_not_participate"

        if "risky" in text or "high risk" in text:
            return "risky"

        if "go with conditions" in text:
            return "go_with_conditions"

        if text == "go":
            return "go"

        return "go_with_conditions"
    
    

    @staticmethod
    def _normalize_result_payload(data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(data)
        normalized.setdefault("project_type", None)
        normalized["equipment"] = OpenAIAnalyzer._to_equipment_list(normalized.get("equipment"))
        normalized["total_device_count"] = OpenAIAnalyzer._to_optional_int(
            normalized.get("total_device_count")
        )
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
        
        decision = normalized.get("decision")
        if isinstance(decision, dict):
            decision = dict(decision)
        else:
            decision = {}

        decision["recommendation"] = OpenAIAnalyzer._to_recommendation(
            decision.get("recommendation")
        )
        decision["decision_rationale"] = OpenAIAnalyzer._to_string_list(
            decision.get("decision_rationale")
        )
        decision["go_conditions"] = OpenAIAnalyzer._to_string_list(
            decision.get("go_conditions")
        )
        decision["blocking_issues"] = OpenAIAnalyzer._to_string_list(
            decision.get("blocking_issues")
        )
        normalized["decision"] = decision

        raw_scoring_inputs = normalized.get("scoring_inputs")
        if isinstance(raw_scoring_inputs, dict):
            scoring_inputs = dict(raw_scoring_inputs)
        else:
            scoring_inputs = {}

        for key, value in list(scoring_inputs.items()):
            if key in {"clarity_score", "overall_score"}:
                scoring_inputs[key] = OpenAIAnalyzer._to_optional_float(value)
            else:
                normalized_bool = OpenAIAnalyzer._to_optional_bool(value)
                scoring_inputs[key] = False if normalized_bool is None else normalized_bool

        normalized["scoring_inputs"] = scoring_inputs

        # --- normalize documentation_completeness ---
        dc = normalized.get("documentation_completeness")
        dc = dict(dc) if isinstance(dc, dict) else {}
        for key in (
            "enough_data_for_estimation", "has_architecture_scheme", "has_object_plan",
            "has_installation_points", "has_cable_routes", "has_power_supply_info",
            "has_existing_infrastructure_info",
        ):
            dc[key] = OpenAIAnalyzer._to_presence_status(dc.get(key))
        dc.setdefault("missing_information", [])
        dc["missing_information"] = OpenAIAnalyzer._to_string_list(dc["missing_information"])
        normalized["documentation_completeness"] = dc

        # --- normalize tailoring_analysis ---
        ta = normalized.get("tailoring_analysis")
        ta = dict(ta) if isinstance(ta, dict) else {}
        for key in (
            "specific_vendor_detected", "or_equivalent_missing",
            "manufacturer_authorization_required", "partner_status_required",
            "unique_characteristics_detected",
        ):
            ta[key] = OpenAIAnalyzer._to_presence_status(ta.get(key))
        ta["specific_models_detected"] = OpenAIAnalyzer._to_string_list(ta.get("specific_models_detected"))
        ta["tailoring_signs"] = OpenAIAnalyzer._to_string_list(ta.get("tailoring_signs"))
        ta["tailoring_probability"] = OpenAIAnalyzer._to_risk_level(ta.get("tailoring_probability"))
        normalized["tailoring_analysis"] = ta

        # --- normalize timeline_assessment ---
        tl = normalized.get("timeline_assessment")
        tl = dict(tl) if isinstance(tl, dict) else {}
        tl["implementation_days"] = OpenAIAnalyzer._to_optional_int(tl.get("implementation_days"))
        tl["delivery_days_estimate"] = OpenAIAnalyzer._to_optional_int(tl.get("delivery_days_estimate"))
        for key in ("timeline_matches_scope", "delivery_exceeds_project_timeline", "requires_site_survey"):
            tl[key] = OpenAIAnalyzer._to_presence_status(tl.get(key))
        tl["timeline_risk_level"] = OpenAIAnalyzer._to_risk_level(tl.get("timeline_risk_level"))
        normalized["timeline_assessment"] = tl

        # --- normalize technical_feasibility ---
        tf = normalized.get("technical_feasibility")
        tf = dict(tf) if isinstance(tf, dict) else {}
        for key in (
            "is_technically_feasible", "requires_additional_design",
            "requires_nonstandard_architecture", "depends_on_external_systems",
        ):
            tf[key] = OpenAIAnalyzer._to_presence_status(tf.get(key))
        tf["critical_technical_risks"] = OpenAIAnalyzer._to_string_list(tf.get("critical_technical_risks"))
        normalized["technical_feasibility"] = tf    

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
        # Казахские буквы, которых нет в русском алфавите
        if re.search(r"[әғқңөұүһі]", combined_text, flags=re.IGNORECASE):
            languages.append("kk")

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

        legacy_result = {
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
            "documentation_completeness": {
                "enough_data_for_estimation": "unknown",
                "has_architecture_scheme": "yes" if has_object_scheme else "unknown",
                "has_object_plan": "yes" if has_object_scheme else "unknown",
                "has_installation_points": "yes" if has_installation_points else "unknown",
                "has_cable_routes": "unknown",
                "has_power_supply_info": "unknown",
                "has_existing_infrastructure_info": "unknown",
                "missing_information": [],
                "completeness_comment": "Fallback heuristic result.",
            },
            "tailoring_analysis": {
                "specific_vendor_detected": "unknown",
                "specific_models_detected": [],
                "or_equivalent_missing": "yes" if not has_or_equivalent else "no",
                "manufacturer_authorization_required": "yes" if manufacturer_auth else "unknown",
                "partner_status_required": "unknown",
                "unique_characteristics_detected": "unknown",
                "tailoring_signs": [],
                "tailoring_probability": None,
                "tailoring_comment": None,
            },
            "timeline_assessment": {
                "implementation_days": implementation_days,
                "delivery_days_estimate": None,
                "timeline_matches_scope": "unknown",
                "delivery_exceeds_project_timeline": "unknown",
                "requires_site_survey": "unknown",
                "timeline_risk_level": None,
                "timeline_comment": None,
            },
            "technical_feasibility": {
                "is_technically_feasible": "unknown",
                "requires_additional_design": "unknown",
                "requires_nonstandard_architecture": "unknown",
                "depends_on_external_systems": "unknown",
                "critical_technical_risks": [],
                "technical_comment": None,
            },
            "clarifying_questions": [],
            "decision": {
                "recommendation": None,
                "decision_rationale": [],
                "go_conditions": [],
                "blocking_issues": [],
            },
            "scoring_inputs": {},
        }
        return legacy_result

    @staticmethod
    def _extract_implementation_days(text: str) -> int | None:
        patterns = [
            r"within\s+(\d{1,4})\s+calendar\s+days",
            r"within\s+(\d{1,4})\s+days",
            r"implementation\s*[:\-]?\s*(\d{1,4})\s+days",
            r"срок\s*[:\-]?\s*(\d{1,4})\s+дн",
            r"в\s*течение\s*(\d{1,4})\s+дн",
            # Казахский: "X күн ішінде" / "мерзімі X күн"
            r"(\d{1,4})\s+күн\s+ішінде",
            r"мерзім[іи]\s*[:\-]?\s*(\d{1,4})\s+күн",
            r"орындау\s+мерзім[іи]\s*[:\-]?\s*(\d{1,4})",
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
            if cleaned and re.search(
                r"deadline|срок|calendar days|дней|дн|күн|мерзім",
                cleaned, flags=re.IGNORECASE,
            ):
                return cleaned[:500]
        return None

    @staticmethod
    def _collect_or_equivalent_evidence(text: str) -> list[str]:
        evidence: list[str] = []
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned and re.search(
                r"\bor equivalent\b|\bили эквивалент\b|\bнемесе балама\b|\bнемесе оған балама\b",
                cleaned, flags=re.IGNORECASE,
            ):
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
