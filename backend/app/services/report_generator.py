from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)

    return result


def _extract_general_info(
    tender_data: dict[str, Any],
    analysis_data: dict[str, Any],
) -> dict[str, Any]:
    timelines = _safe_dict(analysis_data.get("timelines"))

    return {
        "tender_id": tender_data.get("id"),
        "title": _safe_str(tender_data.get("title")),
        "customer_name": _safe_str(tender_data.get("customer_name")),
        "description": _safe_str(tender_data.get("description")),
        "status": _safe_str(tender_data.get("status")),
        "project_type": _safe_str(analysis_data.get("project_type")),
        "delivery_deadline": _safe_str(timelines.get("delivery_deadline")),
        "implementation_days": timelines.get("implementation_days"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_vendor_names(vendors: list[Any]) -> list[str]:
    names: list[str] = []
    for vendor in vendors:
        if isinstance(vendor, dict):
            name = _safe_str(vendor.get("name"))
            if name:
                names.append(name)
        else:
            name = _safe_str(vendor)
            if name:
                names.append(name)
    return _unique_preserve_order(names)


def _generate_summary(
    tender_data: dict[str, Any],
    analysis_data: dict[str, Any],
) -> str:
    title = _safe_str(tender_data.get("title")) or "Тендер"
    project_type = _safe_str(analysis_data.get("project_type")) or "тип проекта не определен"

    equipment = _safe_list(analysis_data.get("equipment"))
    total_device_count = analysis_data.get("total_device_count")
    vendors = _safe_list(analysis_data.get("vendors"))
    timelines = _safe_dict(analysis_data.get("timelines"))

    summary_parts = [
        f"{title}.",
        f"Предварительно документ относится к типу проекта: {project_type}.",
    ]

    if equipment:
        summary_parts.append(f"Выявлено позиций оборудования: {len(equipment)}.")
    if total_device_count is not None:
        summary_parts.append(f"Суммарное количество устройств: {total_device_count}.")
    if vendors:
        summary_parts.append(f"Упоминаемые вендоры: {', '.join(_extract_vendor_names(vendors))}.")
    if timelines.get("implementation_days") is not None:
        summary_parts.append(
            f"Срок реализации: {timelines.get('implementation_days')} дней."
        )

    has_or_equivalent = analysis_data.get("has_or_equivalent")
    if has_or_equivalent is True:
        summary_parts.append('Формулировка "или эквивалент" обнаружена.')
    elif has_or_equivalent is False:
        summary_parts.append('Формулировка "или эквивалент" не обнаружена.')

    return " ".join(summary_parts)


def _build_key_requirements(analysis_data: dict[str, Any]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []

    project_type = _safe_str(analysis_data.get("project_type"))
    if project_type:
        requirements.append(
            {
                "category": "project_type",
                "title": "Тип проекта",
                "value": project_type,
            }
        )

    equipment = _safe_list(analysis_data.get("equipment"))
    for item in equipment:
        if not isinstance(item, dict):
            continue

        requirement = {
            "category": "equipment",
            "title": _safe_str(item.get("name")) or "Оборудование",
            "quantity": item.get("quantity"),
            "unit": _safe_str(item.get("unit")),
            "vendor": _safe_str(item.get("vendor")),
            "characteristics": _safe_list(item.get("characteristics")),
            "model": _safe_str(item.get("model")),
        }
        requirements.append(requirement)

    integrations = _safe_list(analysis_data.get("integrations"))
    for item in integrations:
        if not isinstance(item, dict):
            continue
        requirements.append(
            {
                "category": "integration",
                "title": _safe_str(item.get("name")) or "Интеграция",
                "details": _safe_str(item.get("details")),
            }
        )

    certificates = _safe_list(analysis_data.get("certificates"))
    for item in certificates:
        if not isinstance(item, dict):
            continue
        requirements.append(
            {
                "category": "certificate",
                "title": _safe_str(item.get("name")) or "Сертификат",
                "details": _safe_str(item.get("required_for")),
            }
        )

    timelines = _safe_dict(analysis_data.get("timelines"))
    if timelines:
        requirements.append(
            {
                "category": "timeline",
                "title": "Сроки реализации",
                "value": {
                    "raw_text": _safe_str(timelines.get("raw_text")),
                    "implementation_days": timelines.get("implementation_days"),
                    "delivery_deadline": _safe_str(timelines.get("delivery_deadline")),
                    "notes": _safe_list(timelines.get("notes")),
                },
            }
        )

    return requirements


def _evaluate_document_completeness(
    analysis_data: dict[str, Any],
    tender_data: dict[str, Any],
) -> dict[str, Any]:
    documents = _safe_list(tender_data.get("documents"))

    checks = [
        {
            "code": "has_description",
            "label": "Есть описание тендера",
            "present": bool(_safe_str(tender_data.get("description"))),
        },
        {
            "code": "has_documents",
            "label": "Загружены документы",
            "present": len(documents) > 0,
        },
        {
            "code": "has_equipment",
            "label": "Выявлены позиции оборудования",
            "present": len(_safe_list(analysis_data.get("equipment"))) > 0,
        },
        {
            "code": "has_timeline",
            "label": "Выявлены сроки реализации",
            "present": _safe_dict(analysis_data.get("timelines")).get("implementation_days") is not None
            or bool(_safe_str(_safe_dict(analysis_data.get("timelines")).get("delivery_deadline"))),
        },
        {
            "code": "has_integrations_or_certificates",
            "label": "Есть данные по интеграциям или сертификатам",
            "present": len(_safe_list(analysis_data.get("integrations"))) > 0
            or len(_safe_list(analysis_data.get("certificates"))) > 0,
        },
        {
            "code": "has_object_scheme_info",
            "label": "Есть схема объекта",
            "present": bool(analysis_data.get("has_object_scheme")) if analysis_data.get("has_object_scheme") is not None else False,
        },
        {
            "code": "has_installation_points_info",
            "label": "Есть точки установки",
            "present": bool(analysis_data.get("has_installation_points")) if analysis_data.get("has_installation_points") is not None else False,
        },
    ]

    present_count = sum(1 for item in checks if item["present"])
    total_count = len(checks)
    completeness_percent = round((present_count / total_count) * 100, 2) if total_count else 0.0

    missing_items = [item["label"] for item in checks if not item["present"]]

    return {
        "score_percent": completeness_percent,
        "present_checks": present_count,
        "total_checks": total_count,
        "checks": checks,
        "missing_items": missing_items,
    }


def _build_tailoring_signs(
    analysis_data: dict[str, Any],
    risk_data: dict[str, Any],
) -> dict[str, Any]:
    signs: list[dict[str, Any]] = []

    equipment = _safe_list(analysis_data.get("equipment"))
    specific_model_detected = False
    for item in equipment:
        if not isinstance(item, dict):
            continue
        if item.get("model") or item.get("exact_model") or item.get("vendor_model") or item.get("model_specified"):
            specific_model_detected = True
            break
        name = _safe_str(item.get("name")) or ""
        if any(char.isdigit() for char in name) and len(name) >= 5:
            specific_model_detected = True
            break

    if specific_model_detected:
        signs.append(
            {
                "code": "specific_model_equipment",
                "title": "Указана конкретная модель оборудования",
                "risk_level": "high",
            }
        )

    if analysis_data.get("has_or_equivalent") is False:
        signs.append(
            {
                "code": "no_or_equivalent",
                "title": 'Отсутствует формулировка "или эквивалент"',
                "risk_level": "high",
            }
        )

    if analysis_data.get("manufacturer_authorization_required") is True:
        signs.append(
            {
                "code": "manufacturer_authorization_required",
                "title": "Требуется авторизация производителя",
                "risk_level": "medium",
            }
        )

    for reason in _safe_list(risk_data.get("reasons")):
        if not isinstance(reason, dict):
            continue
        code = _safe_str(reason.get("code"))
        if code and not any(sign["code"] == code for sign in signs):
            signs.append(
                {
                    "code": code,
                    "title": _safe_str(reason.get("description")) or code,
                    "risk_level": "medium",
                }
            )

    return {
        "detected": len(signs) > 0,
        "items": signs,
        "evidence": _safe_list(analysis_data.get("or_equivalent_evidence")),
    }


def _build_timeline_analysis(analysis_data: dict[str, Any]) -> dict[str, Any]:
    timelines = _safe_dict(analysis_data.get("timelines"))
    implementation_days = timelines.get("implementation_days")

    if implementation_days is None:
        status = "unknown"
        assessment = "Срок реализации не удалось определить."
    elif implementation_days < 30:
        status = "aggressive"
        assessment = f"Срок реализации {implementation_days} дней, что может ограничивать круг поставщиков."
    elif implementation_days <= 60:
        status = "moderate"
        assessment = f"Срок реализации {implementation_days} дней выглядит напряженным, но потенциально реализуемым."
    else:
        status = "normal"
        assessment = f"Срок реализации {implementation_days} дней выглядит относительно реалистичным."

    return {
        "raw_text": _safe_str(timelines.get("raw_text")),
        "implementation_days": implementation_days,
        "delivery_deadline": _safe_str(timelines.get("delivery_deadline")),
        "notes": _safe_list(timelines.get("notes")),
        "status": status,
        "assessment": assessment,
    }


def _build_risk_section(
    risk_data: dict[str, Any],
    tailoring_signs: dict[str, Any],
    completeness: dict[str, Any],
) -> dict[str, Any]:
    score = risk_data.get("score", 0)
    decision = _safe_str(risk_data.get("decision")) or "unknown"

    summary_parts: list[str] = [
        f"Итоговый риск-скор: {score}.",
        f"Категория риска: {decision}.",
    ]

    if tailoring_signs.get("detected"):
        summary_parts.append("Обнаружены признаки заточки.")
    if completeness.get("score_percent", 0) < 70:
        summary_parts.append("Документация выглядит неполной.")

    return {
        "score": score,
        "max_score": risk_data.get("max_score"),
        "decision": decision,
        "summary": " ".join(summary_parts),
        "reasons": _safe_list(risk_data.get("reasons")),
        "triggered_rules": _safe_list(risk_data.get("triggered_rules")),
    }


def _build_questions_to_customer(
    analysis_data: dict[str, Any],
    completeness: dict[str, Any],
    risk_data: dict[str, Any],
) -> list[str]:
    questions: list[str] = []

    if analysis_data.get("has_object_scheme") is False or analysis_data.get("missing_object_scheme") is True:
        questions.append("Просим предоставить схему объекта или план размещения оборудования.")

    if analysis_data.get("has_installation_points") is False or analysis_data.get("missing_installation_points") is True:
        questions.append("Просим предоставить перечень и точное расположение точек установки оборудования.")

    if analysis_data.get("has_or_equivalent") is False:
        questions.append('Допускается ли поставка аналогичного оборудования по принципу "или эквивалент"?')

    if analysis_data.get("manufacturer_authorization_required") is True:
        questions.append("Является ли авторизация производителя обязательной для участия, и какие формы подтверждения допускаются?")

    timelines = _safe_dict(analysis_data.get("timelines"))
    if timelines.get("implementation_days") is not None and timelines.get("implementation_days") < 30:
        questions.append("Возможно ли увеличение срока реализации проекта или поэтапное внедрение?")

    if len(_safe_list(analysis_data.get("integrations"))) == 0:
        questions.append("Есть ли требования по интеграции с существующими системами, которые не отражены в документации?")

    if len(_safe_list(analysis_data.get("certificates"))) == 0:
        questions.append("Требуются ли обязательные сертификаты, лицензии или иные подтверждающие документы?")

    if completeness.get("score_percent", 0) < 70:
        questions.append("Просим уточнить недостающие материалы и приложения для полноценной оценки проекта.")

    if (risk_data.get("score") or 0) >= 80:
        questions.append("Какие положения документации могут быть скорректированы для расширения конкуренции среди поставщиков?")

    return _unique_preserve_order(questions)


def _build_recommended_action(decision: str, completeness_percent: float) -> str:
    if decision == "risky":
        return "Перед участием или согласованием рекомендуется направить официальный запрос на разъяснение и провести ручную юридико-техническую экспертизу."
    if completeness_percent < 70:
        return "Рекомендуется сначала запросить недостающие документы и уточнения у заказчика."
    if decision == "medium":
        return "Рекомендуется провести дополнительную техническую валидацию спорных требований."
    return "Можно переходить к детальной технической и коммерческой оценке."


def _build_conclusion(
    tender_data: dict[str, Any],
    analysis_data: dict[str, Any],
    risk_data: dict[str, Any],
    completeness: dict[str, Any],
) -> dict[str, Any]:
    project_type = _safe_str(analysis_data.get("project_type")) or "проект не классифицирован"
    risk_score = risk_data.get("score", 0)
    decision = _safe_str(risk_data.get("decision")) or "unknown"
    completeness_percent = completeness.get("score_percent", 0)

    if decision == "risky":
        verdict = "Документация содержит существенные признаки ограничивающих условий и требует дополнительной проверки."
    elif decision == "medium":
        verdict = "Документация содержит отдельные спорные условия и требует уточнений перед принятием решения."
    else:
        verdict = "Существенных критических ограничений по текущим данным не выявлено."

    return {
        "verdict": verdict,
        "project_type": project_type,
        "risk_score": risk_score,
        "risk_decision": decision,
        "documentation_completeness_percent": completeness_percent,
        "recommended_action": _build_recommended_action(decision, completeness_percent),
        "final_note": f'Тендер "{_safe_str(tender_data.get("title")) or "Без названия"}" требует экспертной верификации перед финальным выводом.',
    }


def generate_report(
    tender_data: dict[str, Any] | None = None,
    analysis_data: dict[str, Any] | None = None,
    risk_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tender_data = tender_data if isinstance(tender_data, dict) else {}
    analysis_data = analysis_data if isinstance(analysis_data, dict) else {}
    risk_data = risk_data if isinstance(risk_data, dict) else {}

    general_info = _extract_general_info(tender_data, analysis_data)
    summary = _generate_summary(tender_data, analysis_data)
    key_requirements = _build_key_requirements(analysis_data)
    completeness = _evaluate_document_completeness(analysis_data, tender_data)
    tailoring_signs = _build_tailoring_signs(analysis_data, risk_data)
    timeline_analysis = _build_timeline_analysis(analysis_data)
    risk_section = _build_risk_section(risk_data, tailoring_signs, completeness)
    questions_to_customer = _build_questions_to_customer(analysis_data, completeness, risk_data)
    conclusion = _build_conclusion(tender_data, analysis_data, risk_data, completeness)

    return {
        "general_information": general_info,
        "technical_specification_summary": summary,
        "key_requirements": key_requirements,
        "documentation_completeness": completeness,
        "tailoring_signs": tailoring_signs,
        "timeline_analysis": timeline_analysis,
        "risks": risk_section,
        "questions_to_customer": questions_to_customer,
        "conclusion": conclusion,
    }