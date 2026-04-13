from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _join_items(values: list[Any], fallback: str = "не указано") -> str:
    cleaned = [_clean_text(v) for v in values if _clean_text(v)]
    return ", ".join(cleaned) if cleaned else fallback


def _extract_risk_reasons(risk: dict[str, Any]) -> list[str]:
    reasons = _as_list(risk.get("reasons"))
    return [_clean_text(x) for x in reasons if _clean_text(x)]


def build_professional_report_context(
    *,
    tender_data: dict[str, Any],
    report: dict[str, Any],
    risk: dict[str, Any],
) -> dict[str, Any]:
    general = _as_dict(report.get("general_information"))
    ts_summary = _clean_text(report.get("technical_specification_summary"))
    key_requirements = _as_list(report.get("key_requirements"))
    completeness = _as_dict(report.get("documentation_completeness"))
    tailoring_signs = _as_list(report.get("tailoring_signs"))
    timeline_analysis = _clean_text(report.get("timeline_analysis"))
    risks_section = _clean_text(report.get("risks"))
    questions = _as_list(report.get("questions_to_customer"))
    conclusion = _clean_text(report.get("conclusion"))

    title = _clean_text(tender_data.get("title")) or "Тендер"
    customer = _clean_text(tender_data.get("customer_name")) or "не указан"
    score = risk.get("score")
    decision = _clean_text(risk.get("decision")) or "не определено"
    risk_reasons = _extract_risk_reasons(risk)

    project_type = _clean_text(general.get("project_type")) or "не определен"
    location = _clean_text(general.get("implementation_location")) or "не указана"
    implementation_days = general.get("implementation_days")
    budget = _clean_text(general.get("budget"))

    executive_summary_parts: list[str] = []
    executive_summary_parts.append(
        f'По результатам автоматизированного анализа тендерной документации по проекту "{title}" '
        f'для заказчика "{customer}" подготовлено предварительное экспертное заключение.'
    )
    executive_summary_parts.append(
        f"Проект классифицирован как {project_type.lower()}, место реализации: {location}."
    )

    if implementation_days:
        executive_summary_parts.append(
            f"Выявленный срок реализации составляет {implementation_days} календарных дней."
        )

    if budget:
        executive_summary_parts.append(f"Указанный бюджет: {budget}.")

    executive_summary_parts.append(
        f"Итоговый риск-скор составляет {score}, категория решения: {decision}."
    )

    if risk_reasons:
        executive_summary_parts.append(
            "Ключевыми факторами риска являются: "
            + "; ".join(risk_reasons[:5])
            + "."
        )

    executive_summary = " ".join(executive_summary_parts)

    completeness_text = _clean_text(completeness.get("summary"))
    if not completeness_text:
        missing_items = _as_list(completeness.get("missing_items"))
        if missing_items:
            completeness_text = (
                "В документации отсутствуют или недостаточно раскрыты следующие данные: "
                + _join_items(missing_items)
                + "."
            )
        else:
            completeness_text = (
                "Критичных пробелов в составе документации автоматически не выявлено, "
                "однако итоговая полнота требует дополнительной экспертной проверки."
            )

    tailoring_text = (
        "Признаки возможной заточки не выявлены."
        if not tailoring_signs
        else "Выявлены следующие признаки возможной заточки: "
        + _join_items(tailoring_signs)
        + "."
    )

    questions_text = (
        "Дополнительные уточняющие вопросы к заказчику не сформированы."
        if not questions
        else "Для уточнения параметров проекта рекомендуется направить заказчику следующие вопросы: "
        + "; ".join([_clean_text(q) for q in questions if _clean_text(q)])
        + "."
    )

    return {
        "title": title,
        "customer_name": customer,
        "executive_summary": executive_summary,
        "general_information": general,
        "technical_specification_summary": ts_summary,
        "key_requirements": [_clean_text(x) for x in key_requirements if _clean_text(x)],
        "documentation_completeness_text": completeness_text,
        "tailoring_text": tailoring_text,
        "timeline_analysis": timeline_analysis or "Анализ сроков не сформирован.",
        "risks_text": risks_section or "Анализ рисков не сформирован.",
        "questions_text": questions_text,
        "conclusion": conclusion or "Финальное заключение не сформировано.",
        "risk_score": score,
        "decision": decision,
        "risk_reasons": risk_reasons,
    }