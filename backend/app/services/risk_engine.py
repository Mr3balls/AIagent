from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_RISK_SCORE = 230


@dataclass(frozen=True)
class RiskRule:
    code: str
    points: int
    description: str


RISK_RULES = {
    "specific_model_equipment": RiskRule(
        code="specific_model_equipment",
        points=20,
        description="Указана конкретная модель оборудования",
    ),
    "no_or_equivalent": RiskRule(
        code="no_or_equivalent",
        points=20,
        description='Отсутствует формулировка "или эквивалент"',
    ),
    "manufacturer_authorization_required": RiskRule(
        code="manufacturer_authorization_required",
        points=15,
        description="Требуется авторизация производителя",
    ),
    "implementation_lt_30_days": RiskRule(
        code="implementation_lt_30_days",
        points=20,
        description="Срок реализации меньше 30 дней",
    ),
    "no_object_scheme": RiskRule(
        code="no_object_scheme",
        points=10,
        description="Отсутствует схема объекта",
    ),
    "no_installation_points": RiskRule(
        code="no_installation_points",
        points=10,
        description="Отсутствуют точки установки",
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

    normalized: list[dict[str, Any]] = []
    for item in equipment:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


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


def _detect_no_object_scheme(analysis_data: dict[str, Any]) -> bool:
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

    # New mode: scoring_inputs already prepared
    if "specific_model_equipment" in analysis_data or "no_or_equivalent" in analysis_data:
        scoring_inputs = analysis_data
        score = 0
        reasons: list[dict[str, Any]] = []

        mapping = {
            "specific_model_equipment": ("specific_model_equipment", "Указаны конкретные модели оборудования"),
            "no_or_equivalent": ("no_or_equivalent", 'Отсутствует формулировка "или эквивалент"'),
            "manufacturer_authorization_required": ("manufacturer_authorization_required", "Требуется авторизация производителя"),
            "partner_status_required": ("partner_status_required", "Требуется партнерский статус"),
            "unique_characteristics_detected": ("specific_model_equipment", "Выявлены уникальные технические характеристики"),
            "implementation_lt_30_days": ("implementation_lt_30_days", "Срок реализации менее 30 дней"),
            "timeline_not_matching_scope": ("implementation_lt_30_days", "Сроки не соответствуют объему работ"),
            "delivery_gt_project_timeline": ("implementation_lt_30_days", "Срок поставки превышает срок проекта"),
            "no_architecture_or_scheme": ("no_object_scheme", "Отсутствует схема или архитектура решения"),
            "no_object_plan": ("no_object_scheme", "Отсутствует план объекта"),
            "no_installation_points": ("no_installation_points", "Отсутствуют точки установки"),
            "no_cable_routes": ("no_installation_points", "Отсутствуют кабельные трассы"),
            "unique_experience_required": ("manufacturer_authorization_required", "Требуется уникальный опыт"),
            "specific_project_experience_required": ("manufacturer_authorization_required", "Требуется опыт конкретного проекта"),
            "specific_vendor_experience_required": ("manufacturer_authorization_required", "Требуется опыт с конкретным вендором"),
            "external_system_integrations": ("implementation_lt_30_days", "Есть сложные внешние интеграции"),
            "nonstandard_architecture": ("implementation_lt_30_days", "Требуется нестандартная архитектура"),
            "site_survey_required": ("no_object_scheme", "Необходимо обследование объекта"),
        }

        for key, enabled in scoring_inputs.items():
            if enabled is not True:
                continue

            mapped = mapping.get(key)
            if not mapped:
                continue

            base_rule_code, details = mapped
            rule = RISK_RULES.get(base_rule_code)
            if rule is None:
                continue

            score += rule.points
            reasons.append(
                _make_reason(
                    rule,
                    True,
                    details,
                )
            )

        score = min(score, MAX_RISK_SCORE)
        decision = _build_decision(score)

        return {
            "score": score,
            "max_score": MAX_RISK_SCORE,
            "decision": decision,
            "reasons": reasons,
            "triggered_rules": [reason["code"] for reason in reasons],
        }

    # Legacy mode: old aggregated flat analysis_data
    score = 0
    reasons: list[dict[str, Any]] = []

    equipment = _normalize_equipment(analysis_data.get("equipment"))

    specific_model_detected = _detect_specific_model(equipment, analysis_data)
    if specific_model_detected:
        rule = RISK_RULES["specific_model_equipment"]
        score += rule.points
        reasons.append(
            _make_reason(
                rule,
                True,
                "В документе обнаружено указание конкретной модели оборудования.",
            )
        )

    no_or_equivalent = _detect_no_or_equivalent(analysis_data)
    if no_or_equivalent:
        rule = RISK_RULES["no_or_equivalent"]
        score += rule.points
        reasons.append(
            _make_reason(
                rule,
                True,
                'Формулировка "или эквивалент" не обнаружена.',
            )
        )

    manufacturer_authorization_required = _detect_manufacturer_authorization_required(analysis_data)
    if manufacturer_authorization_required:
        rule = RISK_RULES["manufacturer_authorization_required"]
        score += rule.points
        reasons.append(
            _make_reason(
                rule,
                True,
                "В требованиях обнаружена авторизация производителя или аналогичное условие.",
            )
        )

    implementation_lt_30_days = _detect_implementation_lt_30_days(analysis_data)
    if implementation_lt_30_days:
        days = _extract_implementation_days(analysis_data)
        rule = RISK_RULES["implementation_lt_30_days"]
        score += rule.points
        reasons.append(
            _make_reason(
                rule,
                True,
                f"Указан срок реализации {days} дней, что меньше 30 дней.",
            )
        )

    no_object_scheme = _detect_no_object_scheme(analysis_data)
    if no_object_scheme:
        rule = RISK_RULES["no_object_scheme"]
        score += rule.points
        reasons.append(
            _make_reason(
                rule,
                True,
                "Схема объекта отсутствует или не была предоставлена.",
            )
        )

    no_installation_points = _detect_no_installation_points(analysis_data)
    if no_installation_points:
        rule = RISK_RULES["no_installation_points"]
        score += rule.points
        reasons.append(
            _make_reason(
                rule,
                True,
                "Точки установки отсутствуют или не были указаны.",
            )
        )

    score = min(score, MAX_RISK_SCORE)
    decision = _build_decision(score)

    return {
        "score": score,
        "max_score": MAX_RISK_SCORE,
        "decision": decision,
        "reasons": reasons,
        "triggered_rules": [reason["code"] for reason in reasons],
    }