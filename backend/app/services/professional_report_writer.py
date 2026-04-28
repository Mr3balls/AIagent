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


def _status_label(value: Any) -> str:
    if value == "yes":
        return "Да"
    if value == "no":
        return "Нет"
    if value in ("unknown", None, ""):
        return "Не определено"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return "Не определено"


def _risk_level_label(value: Any) -> str:
    mapping = {"low": "низкий", "medium": "средний", "high": "высокий"}
    return mapping.get(_clean_text(value).lower(), "не определён")


def _recommendation_label(value: Any) -> str:
    mapping = {
        "go": "Участвовать",
        "go_with_conditions": "Участвовать с условиями",
        "risky": "Высокий риск",
        "do_not_participate": "Не участвовать",
    }
    return mapping.get(_clean_text(value), _clean_text(value) or "не определено")


def _build_executive_summary(
    tender_data: dict[str, Any],
    report: dict[str, Any],
    risk: dict[str, Any],
) -> str:
    title = _clean_text(tender_data.get("title")) or "Тендер"
    customer = _clean_text(tender_data.get("customer_name")) or "не указан"
    general = _as_dict(report.get("general_information"))
    project_type = _clean_text(general.get("project_type")) or "тип проекта не определён"
    location = _clean_text(general.get("implementation_location")) or "не указана"
    implementation_days = general.get("implementation_days")
    budget = _clean_text(general.get("budget"))
    score = risk.get("score", 0)
    decision = _recommendation_label(risk.get("decision"))

    parts: list[str] = [
        f'По результатам автоматизированного анализа тендерной документации по проекту "{title}" '
        f'для заказчика "{customer}" подготовлено предварительное экспертное заключение.',
        f"Проект классифицирован как {project_type}, место реализации: {location}.",
    ]

    if implementation_days:
        parts.append(f"Выявленный срок реализации составляет {implementation_days} календарных дней.")

    if budget:
        parts.append(f"Указанный бюджет: {budget}.")

    parts.append(f"Итоговый риск-скор составляет {score}, категория решения: {decision}.")

    reasons = _as_list(risk.get("reasons"))
    reason_texts: list[str] = []
    for r in reasons[:5]:
        if isinstance(r, dict):
            desc = _clean_text(r.get("description"))
            details = _clean_text(r.get("details"))
            pts = r.get("points", "")
            if desc:
                line = desc
                if details and details.lower() != desc.lower():
                    line += f" ({details})"
                if pts:
                    line += f" [+{pts} б.]"
                reason_texts.append(line)
        elif _clean_text(r):
            reason_texts.append(_clean_text(r))

    if reason_texts:
        parts.append("Ключевыми факторами риска являются: " + "; ".join(reason_texts) + ".")

    return " ".join(parts)


def _build_key_requirements_text(report: dict[str, Any]) -> list[str]:
    raw = _as_list(report.get("key_requirements"))
    result: list[str] = []

    for item in raw:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                result.append(text)
            continue

        category = _clean_text(item.get("category"))
        title = _clean_text(item.get("title")) or "Без названия"

        if category == "project_type":
            result.append(f"Тип проекта: {_clean_text(item.get('value')) or title}")

        elif category == "equipment":
            parts = [title]
            qty = item.get("quantity")
            unit = _clean_text(item.get("unit"))
            vendor = _clean_text(item.get("vendor"))
            model = _clean_text(item.get("model"))
            if qty is not None:
                parts.append(f"количество: {qty}{(' ' + unit) if unit else ''}")
            if vendor:
                parts.append(f"вендор: {vendor}")
            if model:
                parts.append(f"модель: {model}")
            chars = _as_list(item.get("characteristics"))
            if chars:
                chars_str = ", ".join(_clean_text(c) for c in chars if _clean_text(c))
                if chars_str:
                    parts.append(f"характеристики: {chars_str}")
            result.append("; ".join(parts))

        elif category == "integration":
            details = _clean_text(item.get("details"))
            line = f"Интеграция: {title}"
            if details:
                line += f" — {details}"
            result.append(line)

        elif category == "certificate":
            details = _clean_text(item.get("details"))
            line = f"Сертификат: {title}"
            if details:
                line += f" — {details}"
            result.append(line)

        elif category == "timeline":
            tl = _as_dict(item.get("value"))
            raw_text = _clean_text(tl.get("raw_text"))
            days = tl.get("implementation_days")
            deadline = _clean_text(tl.get("delivery_deadline"))
            notes = _as_list(tl.get("notes"))

            line_parts: list[str] = ["Сроки реализации:"]
            if raw_text:
                line_parts.append(raw_text)
            elif days:
                line_parts.append(f"{days} дней")
            elif deadline:
                line_parts.append(f"дедлайн {deadline}")
            else:
                line_parts.append("не указаны")
            if notes:
                notes_str = "; ".join(_clean_text(n) for n in notes if _clean_text(n))
                if notes_str:
                    line_parts.append(f"({notes_str})")
            result.append(" ".join(line_parts))

        else:
            value = _clean_text(item.get("value"))
            result.append(f"{title}{(': ' + value) if value else ''}")

    return [r for r in result if r]


def _build_completeness_text(report: dict[str, Any]) -> str:
    completeness = _as_dict(report.get("documentation_completeness"))
    missing_items = _as_list(completeness.get("missing_items"))
    score = completeness.get("score_percent", 0)
    comment = _clean_text(completeness.get("comment"))

    checks = _as_list(completeness.get("checks"))
    check_lines: list[str] = []
    for ch in checks:
        if not isinstance(ch, dict):
            continue
        label = _clean_text(ch.get("label"))
        status = _clean_text(ch.get("status")) or _status_label(ch.get("present"))
        if label:
            check_lines.append(f"{label}: {status}")

    parts: list[str] = [f"Степень полноты документации: {score}%."]

    if check_lines:
        parts.append("Результаты проверки: " + "; ".join(check_lines) + ".")

    if missing_items:
        parts.append(
            "Отсутствуют или недостаточно раскрыты: "
            + ", ".join(_clean_text(m) for m in missing_items if _clean_text(m))
            + "."
        )
    else:
        parts.append("Критичных пробелов в составе документации не выявлено.")

    if comment:
        parts.append(comment)

    return " ".join(parts)


def _build_tailoring_text(report: dict[str, Any]) -> str:
    tailoring = _as_dict(report.get("tailoring_signs"))
    detected = tailoring.get("detected", False)

    if not detected:
        return "Признаки возможной заточки под конкретного поставщика не выявлены."

    items = _as_list(tailoring.get("items"))
    item_texts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            t = _clean_text(item.get("title"))
            risk_level = _clean_text(item.get("risk_level"))
            if t:
                suffix = f" (риск: {_risk_level_label(risk_level)})" if risk_level else ""
                item_texts.append(t + suffix)
        elif _clean_text(item):
            item_texts.append(_clean_text(item))

    prob = _clean_text(tailoring.get("probability"))
    comment = _clean_text(tailoring.get("comment"))

    parts: list[str] = []
    if item_texts:
        parts.append("Выявлены следующие признаки возможной заточки: " + "; ".join(item_texts) + ".")
    else:
        parts.append("Выявлены признаки возможной заточки под конкретного поставщика.")

    if prob:
        parts.append(f"Вероятность заточки: {_risk_level_label(prob)}.")

    evidence = _as_list(tailoring.get("evidence"))
    ev_texts = [_clean_text(e) for e in evidence if _clean_text(e)]
    if ev_texts:
        parts.append("Подтверждающие фрагменты: " + "; ".join(ev_texts[:3]) + ".")

    if comment:
        parts.append(comment)

    return " ".join(parts)


def _build_timeline_text(report: dict[str, Any]) -> str:
    tl = _as_dict(report.get("timeline_analysis"))
    if not tl:
        return "Анализ сроков не сформирован."

    parts: list[str] = []

    raw_text = _clean_text(tl.get("raw_text"))
    days = tl.get("implementation_days")
    deadline = _clean_text(tl.get("delivery_deadline"))
    assessment = _clean_text(tl.get("assessment"))
    status = _clean_text(tl.get("status"))
    matches_scope = _status_label(tl.get("timeline_matches_scope"))
    exceeds = _status_label(tl.get("delivery_exceeds_project_timeline"))
    site_survey = _status_label(tl.get("requires_site_survey"))
    notes = _as_list(tl.get("notes"))

    if raw_text:
        parts.append(f"Указанный срок: {raw_text}.")
    elif days is not None:
        parts.append(f"Срок реализации: {days} дней.")
    elif deadline:
        parts.append(f"Дедлайн поставки: {deadline}.")
    else:
        parts.append("Конкретные сроки реализации в документации не указаны.")

    if assessment:
        parts.append(assessment)

    if status and status not in ("unknown", ""):
        parts.append(f"Статус сроков: {status}.")

    parts.append(f"Соответствие сроков объёму работ: {matches_scope}.")
    parts.append(f"Сроки поставки превышают проектные: {exceeds}.")
    parts.append(f"Требуется выезд на объект: {site_survey}.")

    if notes:
        notes_str = "; ".join(_clean_text(n) for n in notes if _clean_text(n))
        if notes_str:
            parts.append(f"Примечания: {notes_str}.")

    return " ".join(parts)


def _build_risks_text(report: dict[str, Any]) -> str:
    risks = _as_dict(report.get("risks"))
    if not risks:
        return "Анализ рисков не сформирован."

    score = risks.get("score", 0)
    max_score = risks.get("max_score")
    decision = _recommendation_label(risks.get("decision"))
    summary = _clean_text(risks.get("summary"))

    score_str = f"{score}" + (f" из {max_score}" if max_score else "")
    parts: list[str] = [f"Итоговый риск-скор: {score_str}. Категория риска: {decision}."]

    if summary:
        parts.append(summary)

    reasons = _as_list(risks.get("reasons"))
    reason_lines: list[str] = []
    for r in reasons:
        if not isinstance(r, dict):
            continue
        desc = _clean_text(r.get("description"))
        details = _clean_text(r.get("details"))
        pts = r.get("points", "")
        if desc:
            line = desc
            if details and details.lower() != desc.lower():
                line += f": {details}"
            if pts:
                line += f" (+{pts} баллов)"
            reason_lines.append(line)

    if reason_lines:
        parts.append("Факторы риска: " + "; ".join(reason_lines) + ".")

    return " ".join(parts)


def _build_questions_text(report: dict[str, Any]) -> str:
    questions = _as_list(report.get("questions_to_customer"))
    q_texts = [_clean_text(q) for q in questions if _clean_text(q)]

    if not q_texts:
        return "Дополнительные уточняющие вопросы к заказчику не сформированы."

    return (
        "Для уточнения параметров проекта рекомендуется направить заказчику следующие вопросы: "
        + "; ".join(q_texts)
        + "."
    )


def _build_conclusion_text(report: dict[str, Any]) -> str:
    cn = _as_dict(report.get("conclusion"))
    if not cn:
        return "Финальное заключение не сформировано."

    verdict = _clean_text(cn.get("verdict"))
    recommendation = _recommendation_label(cn.get("recommendation"))
    risk_score = cn.get("risk_score", 0)
    rationale = _as_list(cn.get("decision_rationale"))
    go_conditions = _as_list(cn.get("go_conditions"))
    blocking_issues = _as_list(cn.get("blocking_issues"))
    completeness_pct = cn.get("documentation_completeness_percent", 0)
    recommended_action = _clean_text(cn.get("recommended_action"))
    final_note = _clean_text(cn.get("final_note"))

    parts: list[str] = []

    if verdict:
        parts.append(verdict)

    parts.append(
        f"Итоговая рекомендация: {recommendation}. "
        f"Риск-скор: {risk_score}. "
        f"Полнота документации: {completeness_pct}%."
    )

    if rationale:
        rat_texts = [_clean_text(r) for r in rationale if _clean_text(r)]
        if rat_texts:
            parts.append("Обоснование: " + " ".join(rat_texts))

    if blocking_issues:
        bi_texts = [_clean_text(b) for b in blocking_issues if _clean_text(b)]
        if bi_texts:
            parts.append("Блокирующие вопросы: " + "; ".join(bi_texts) + ".")

    if go_conditions:
        gc_texts = [_clean_text(c) for c in go_conditions if _clean_text(c)]
        if gc_texts:
            parts.append("Условия участия: " + "; ".join(gc_texts) + ".")

    if recommended_action:
        parts.append(recommended_action)

    if final_note:
        parts.append(final_note)

    return " ".join(parts)


def build_professional_report_context(
    *,
    tender_data: dict[str, Any],
    report: dict[str, Any],
    risk: dict[str, Any],
) -> dict[str, Any]:
    general = _as_dict(report.get("general_information"))
    title = _clean_text(tender_data.get("title")) or "Тендер"
    customer = _clean_text(tender_data.get("customer_name")) or "не указан"

    return {
        "title": title,
        "customer_name": customer,
        "executive_summary": _build_executive_summary(tender_data, report, risk),
        "general_information": general,
        "technical_specification_summary": _clean_text(
            report.get("technical_specification_summary")
        ),
        "key_requirements": _build_key_requirements_text(report),
        "documentation_completeness_text": _build_completeness_text(report),
        "tailoring_text": _build_tailoring_text(report),
        "timeline_analysis": _build_timeline_text(report),
        "risks_text": _build_risks_text(report),
        "questions_text": _build_questions_text(report),
        "conclusion": _build_conclusion_text(report),
        "risk_score": risk.get("score"),
        "decision": _recommendation_label(risk.get("decision")),
    }