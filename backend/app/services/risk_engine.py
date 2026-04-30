from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_RISK_SCORE = 230


@dataclass(frozen=True)
class RiskRule:
    code: str
    points: int
    description: str
    block: str


RISK_RULES = {
    # Блок 1 — Признаки заточки (макс 80)
    "specific_model_equipment": RiskRule(
        code="specific_model_equipment",
        points=20,
        description="Указана конкретная модель оборудования",
        block="tailoring",
    ),
    "no_or_equivalent": RiskRule(
        code="no_or_equivalent",
        points=20,
        description='Отсутствует формулировка "или эквивалент"',
        block="tailoring",
    ),
    "manufacturer_authorization_required": RiskRule(
        code="manufacturer_authorization_required",
        points=15,
        description="Требуется авторизация производителя",
        block="tailoring",
    ),
    "partner_status_required": RiskRule(
        code="partner_status_required",
        points=15,
        description="Требуется партнерский статус",
        block="tailoring",
    ),
    "unique_characteristics_detected": RiskRule(
        code="unique_characteristics_detected",
        points=10,
        description="Выявлены уникальные технические характеристики",
        block="tailoring",
    ),
    # Блок 2 — Сроки (макс 55)
    "implementation_lt_30_days": RiskRule(
        code="implementation_lt_30_days",
        points=20,
        description="Срок реализации меньше 30 дней",
        block="timeline",
    ),
    "timeline_not_matching_scope": RiskRule(
        code="timeline_not_matching_scope",
        points=15,
        description="Сроки не соответствуют объему работ",
        block="timeline",
    ),
    "delivery_gt_project_timeline": RiskRule(
        code="delivery_gt_project_timeline",
        points=20,
        description="Срок поставки превышает срок проекта",
        block="timeline",
    ),
    # Блок 3 — Неполная документация (макс 40)
    "no_architecture_or_scheme": RiskRule(
        code="no_architecture_or_scheme",
        points=10,
        description="Отсутствует схема или архитектура решения",
        block="documentation",
    ),
    "no_object_plan": RiskRule(
        code="no_object_plan",
        points=10,
        description="Отсутствует план объекта",
        block="documentation",
    ),
    "no_installation_points": RiskRule(
        code="no_installation_points",
        points=10,
        description="Отсутствуют точки установки",
        block="documentation",
    ),
    "no_cable_routes": RiskRule(
        code="no_cable_routes",
        points=10,
        description="Отсутствуют кабельные трассы",
        block="documentation",
    ),
    # Блок 4 — Требования к опыту (макс 30)
    "unique_experience_required": RiskRule(
        code="unique_experience_required",
        points=10,
        description="Требуется уникальный опыт",
        block="experience",
    ),
    "specific_project_experience_required": RiskRule(
        code="specific_project_experience_required",
        points=10,
        description="Требуется опыт конкретного проекта",
        block="experience",
    ),
    "specific_vendor_experience_required": RiskRule(
        code="specific_vendor_experience_required",
        points=10,
        description="Требуется опыт с конкретным вендором",
        block="experience",
    ),
    # Блок 5 — Сложность проекта (макс 25)
    "external_system_integrations": RiskRule(
        code="external_system_integrations",
        points=10,
        description="Есть сложные внешние интеграции",
        block="complexity",
    ),
    "nonstandard_architecture": RiskRule(
        code="nonstandard_architecture",
        points=10,
        description="Требуется нестандартная архитектура",
        block="complexity",
    ),
    "site_survey_required": RiskRule(
        code="site_survey_required",
        points=5,
        description="Необходимо обследование объекта",
        block="complexity",
    ),
}


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"true", "1", "yes", "y", "да"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def _normalize_equipment(equipment: Any) -> list[dict[str, Any]]:
    if not isinstance(equipment, list):
        return []
    return [item for item in equipment if isinstance(item, dict)]


def _detect_specific_model(equipment: list[dict[str, Any]], analysis_data: dict[str, Any]) -> bool:
    for item in equipment:
        if _safe_bool(item.get("model_specified")):
            return True
        if item.get("model") or item.get("exact_model"):
            return True
        name = str(item.get("name", "")).strip()
        vendor_model = str(item.get("vendor_model", "")).strip()
        if any(char.isdigit() for char in name) and len(name) >= 5:
            return True
        if vendor_model:
            return True

    explicit = analysis_data.get("specific_model_detected")
    if explicit is not None:
        return _safe_bool(explicit)
    return False


def _detect_no_or_equivalent(analysis_data: dict[str, Any]) -> bool:
    has_or_equivalent = analysis_data.get("has_or_equivalent")
    if has_or_equivalent is None:
        return False
    return not _safe_bool(has_or_equivalent)


def _detect_manufacturer_authorization_required(analysis_data: dict[str, Any]) -> bool:
    explicit = analysis_data.get("manufacturer_authorization_required")
    if explicit is not None:
        return _safe_bool(explicit)

    certificates = analysis_data.get("certificates", [])
    if isinstance(certificates, list):
        for item in certificates:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).lower()
            required_for = str(item.get("required_for", "")).lower()
            if "авториза" in name or "authorization" in name:
                return True
            if "производител" in name or "manufacturer" in name:
                return True
            if "авториза" in required_for or "manufacturer" in required_for:
                return True

    warnings = analysis_data.get("warnings", [])
    if isinstance(warnings, list):
        for warning in warnings:
            text = str(warning).lower()
            if "авторизац" in text or "authorization" in text:
                return True

    return False


def _extract_implementation_days(analysis_data: dict[str, Any]) -> int | None:
    timelines = analysis_data.get("timelines")
    if isinstance(timelines, dict):
        days = _safe_int(timelines.get("implementation_days"))
        if days is not None:
            return days
    return _safe_int(analysis_data.get("implementation_days"))


def _detect_implementation_lt_30_days(analysis_data: dict[str, Any]) -> bool:
    days = _extract_implementation_days(analysis_data)
    if days is None:
        return False
    return days < 30


def _detect_no_architecture_or_scheme(analysis_data: dict[str, Any]) -> bool:
    # Check both old key (has_object_scheme) and new key (no_architecture_or_scheme)
    explicit = analysis_data.get("has_object_scheme")
    if explicit is not None:
        return not _safe_bool(explicit)
    explicit_missing = analysis_data.get("missing_object_scheme")
    if explicit_missing is not None:
        return _safe_bool(explicit_missing)
    return False


def _detect_no_installation_points(analysis_data: dict[str, Any]) -> bool:
    explicit = analysis_data.get("has_installation_points")
    if explicit is not None:
        return not _safe_bool(explicit)
    explicit_missing = analysis_data.get("missing_installation_points")
    if explicit_missing is not None:
        return _safe_bool(explicit_missing)
    return False


def _make_reason(rule: RiskRule, triggered: bool, details: str | None = None) -> dict[str, Any]:
    return {
        "code": rule.code,
        "description": rule.description,
        "points": rule.points if triggered else 0,
        "triggered": triggered,
        "details": details,
        "block": rule.block,
    }


def _build_decision(score: int) -> str:
    if score > 120:
        return "do_not_participate"
    if score > 70:
        return "risky"
    if score > 30:
        return "go_with_conditions"
    return "go"


def calculate_risk_score(analysis_data: dict[str, Any] | None) -> dict[str, Any]:
    if analysis_data is None:
        analysis_data = {}

    if not isinstance(analysis_data, dict):
        raise ValueError("analysis_data must be a dictionary")

    # New mode: scoring_inputs already prepared by AI analyzer
    if "specific_model_equipment" in analysis_data or "no_or_equivalent" in analysis_data:
        scoring_inputs = analysis_data
        score = 0
        reasons: list[dict[str, Any]] = []

        for key, enabled in scoring_inputs.items():
            if enabled is not True:
                continue
            rule = RISK_RULES.get(key)
            if rule is None:
                continue
            score += rule.points
            reasons.append(_make_reason(rule, True))

        score = min(score, MAX_RISK_SCORE)
        decision = _build_decision(score)

        return {
            "score": score,
            "max_score": MAX_RISK_SCORE,
            "decision": decision,
            "reasons": reasons,
            "triggered_rules": [reason["code"] for reason in reasons],
        }

    # Legacy mode: flat analysis_data from old format
    score = 0
    reasons: list[dict[str, Any]] = []

    equipment = _normalize_equipment(analysis_data.get("equipment"))

    if _detect_specific_model(equipment, analysis_data):
        rule = RISK_RULES["specific_model_equipment"]
        score += rule.points
        reasons.append(_make_reason(rule, True, "В документе обнаружено указание конкретной модели оборудования."))

    if _detect_no_or_equivalent(analysis_data):
        rule = RISK_RULES["no_or_equivalent"]
        score += rule.points
        reasons.append(_make_reason(rule, True, 'Формулировка "или эквивалент" не обнаружена.'))

    if _detect_manufacturer_authorization_required(analysis_data):
        rule = RISK_RULES["manufacturer_authorization_required"]
        score += rule.points
        reasons.append(_make_reason(rule, True, "В требованиях обнаружена авторизация производителя или аналогичное условие."))

    if _detect_implementation_lt_30_days(analysis_data):
        days = _extract_implementation_days(analysis_data)
        rule = RISK_RULES["implementation_lt_30_days"]
        score += rule.points
        reasons.append(_make_reason(rule, True, f"Указан срок реализации {days} дней, что меньше 30 дней."))

    if _detect_no_architecture_or_scheme(analysis_data):
        rule = RISK_RULES["no_architecture_or_scheme"]
        score += rule.points
        reasons.append(_make_reason(rule, True, "Схема объекта отсутствует или не была предоставлена."))

    if _detect_no_installation_points(analysis_data):
        rule = RISK_RULES["no_installation_points"]
        score += rule.points
        reasons.append(_make_reason(rule, True, "Точки установки отсутствуют или не были указаны."))

    score = min(score, MAX_RISK_SCORE)
    decision = _build_decision(score)

    return {
        "score": score,
        "max_score": MAX_RISK_SCORE,
        "decision": decision,
        "reasons": reasons,
        "triggered_rules": [reason["code"] for reason in reasons],
    }
