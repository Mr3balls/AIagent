from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Tender, TenderStatus
from app.services.ai_analyzer import AIAnalyzerError, OpenAIAnalyzer
from app.services.parsers.document_parser import DocumentParser
from app.services.report_generator import generate_report
from app.services.risk_engine import calculate_risk_score
from app.services.docx_report_generator import generate_tender_report_docx
from app.services.professional_report_writer import build_professional_report_context

def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _merge_unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)

    return result


def _merge_vendors(doc_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for result in doc_results:
        for vendor in _safe_list(result.get("vendors")):
            if not isinstance(vendor, dict):
                continue

            name = _safe_str(vendor.get("name"))
            if not name:
                continue

            key = name.lower()
            existing = merged.get(key)

            if existing is None:
                merged[key] = {
                    "name": name,
                    "confidence": vendor.get("confidence"),
                }
            else:
                old_conf = existing.get("confidence")
                new_conf = vendor.get("confidence")

                if isinstance(new_conf, (int, float)):
                    if old_conf is None or (isinstance(old_conf, (int, float)) and new_conf > old_conf):
                        existing["confidence"] = float(new_conf)

    return list(merged.values())


def _merge_equipment(doc_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for result in doc_results:
        for item in _safe_list(result.get("equipment")):
            if not isinstance(item, dict):
                continue

            name = _safe_str(item.get("name"))
            vendor = _safe_str(item.get("vendor"))
            model = _safe_str(item.get("model")) or _safe_str(item.get("exact_model")) or _safe_str(item.get("vendor_model"))

            key_parts = [
                (name or "").lower(),
                (vendor or "").lower(),
                (model or "").lower(),
            ]
            key = "|".join(key_parts)

            if key not in merged:
                merged[key] = {
                    "name": name,
                    "quantity": item.get("quantity"),
                    "unit": _safe_str(item.get("unit")),
                    "vendor": vendor,
                    "model": model,
                    "exact_model": _safe_str(item.get("exact_model")),
                    "vendor_model": _safe_str(item.get("vendor_model")),
                    "model_specified": item.get("model_specified"),
                    "characteristics": _merge_unique_strings(
                        [str(x) for x in _safe_list(item.get("characteristics"))]
                    ),
                }
            else:
                existing = merged[key]

                existing_qty = existing.get("quantity")
                new_qty = item.get("quantity")
                if existing_qty is None and new_qty is not None:
                    existing["quantity"] = new_qty

                if not existing.get("unit") and item.get("unit"):
                    existing["unit"] = _safe_str(item.get("unit"))

                if not existing.get("vendor") and vendor:
                    existing["vendor"] = vendor

                if not existing.get("model") and model:
                    existing["model"] = model

                if not existing.get("exact_model") and item.get("exact_model"):
                    existing["exact_model"] = _safe_str(item.get("exact_model"))

                if not existing.get("vendor_model") and item.get("vendor_model"):
                    existing["vendor_model"] = _safe_str(item.get("vendor_model"))

                if existing.get("model_specified") is None and item.get("model_specified") is not None:
                    existing["model_specified"] = item.get("model_specified")

                existing["characteristics"] = _merge_unique_strings(
                    existing.get("characteristics", [])
                    + [str(x) for x in _safe_list(item.get("characteristics"))]
                )

    return list(merged.values())


def _merge_integrations(doc_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for result in doc_results:
        for item in _safe_list(result.get("integrations")):
            if not isinstance(item, dict):
                continue

            name = _safe_str(item.get("name"))
            details = _safe_str(item.get("details"))

            if not name:
                continue

            key = name.lower()
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "details": details,
                }
            else:
                if not merged[key].get("details") and details:
                    merged[key]["details"] = details

    return list(merged.values())


def _merge_certificates(doc_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for result in doc_results:
        for item in _safe_list(result.get("certificates")):
            if not isinstance(item, dict):
                continue

            name = _safe_str(item.get("name"))
            required_for = _safe_str(item.get("required_for"))

            if not name:
                continue

            key = name.lower()
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "required_for": required_for,
                }
            else:
                if not merged[key].get("required_for") and required_for:
                    merged[key]["required_for"] = required_for

    return list(merged.values())


def _merge_timelines(doc_results: list[dict[str, Any]]) -> dict[str, Any]:
    raw_texts: list[str] = []
    deadlines: list[str] = []
    notes: list[str] = []
    min_days: int | None = None

    for result in doc_results:
        timelines = _safe_dict(result.get("timelines"))
        raw_text = _safe_str(timelines.get("raw_text"))
        deadline = _safe_str(timelines.get("delivery_deadline"))
        impl_days = timelines.get("implementation_days")

        if raw_text:
            raw_texts.append(raw_text)
        if deadline:
            deadlines.append(deadline)

        for note in _safe_list(timelines.get("notes")):
            note_text = _safe_str(note)
            if note_text:
                notes.append(note_text)

        if isinstance(impl_days, int):
            if min_days is None or impl_days < min_days:
                min_days = impl_days

    return {
        "raw_text": "\n".join(_merge_unique_strings(raw_texts)) or None,
        "implementation_days": min_days,
        "delivery_deadline": "; ".join(_merge_unique_strings(deadlines)) or None,
        "notes": _merge_unique_strings(notes),
    }


def _detect_project_type(doc_results: list[dict[str, Any]]) -> str | None:
    counter: dict[str, int] = {}

    for result in doc_results:
        value = _safe_str(result.get("project_type"))
        if not value:
            continue
        key = value.lower()
        counter[key] = counter.get(key, 0) + 1

    if not counter:
        return None

    best_key = max(counter, key=counter.get)
    for result in doc_results:
        value = _safe_str(result.get("project_type"))
        if value and value.lower() == best_key:
            return value

    return None


def _sum_total_device_count(equipment: list[dict[str, Any]]) -> int | None:
    total = 0
    found = False

    for item in equipment:
        quantity = item.get("quantity")
        if isinstance(quantity, int):
            total += quantity
            found = True

    return total if found else None


def _collect_languages(doc_results: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for result in doc_results:
        for lang in _safe_list(result.get("extracted_languages")):
            lang_text = _safe_str(lang)
            if lang_text:
                values.append(lang_text)
    return _merge_unique_strings(values)


def _collect_assumptions(doc_results: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for result in doc_results:
        for item in _safe_list(result.get("assumptions")):
            text = _safe_str(item)
            if text:
                values.append(text)
    return _merge_unique_strings(values)


def _collect_warnings(doc_results: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for result in doc_results:
        for item in _safe_list(result.get("warnings")):
            text = _safe_str(item)
            if text:
                values.append(text)
    return _merge_unique_strings(values)


def _collect_or_equivalent_evidence(doc_results: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for result in doc_results:
        for item in _safe_list(result.get("or_equivalent_evidence")):
            text = _safe_str(item)
            if text:
                values.append(text)
    return _merge_unique_strings(values)


def _merge_boolean_flags(doc_results: list[dict[str, Any]], field_name: str) -> bool | None:
    values: list[bool] = []
    for result in doc_results:
        value = result.get(field_name)
        if isinstance(value, bool):
            values.append(value)

    if not values:
        return None

    return any(values)

def _merge_dicts_prefer_meaningful(doc_results: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in doc_results:
        value = item.get(field_name)
        if not isinstance(value, dict):
            continue
        for key, incoming in value.items():
            if key not in result or result[key] in (None, "", [], {}, "unknown"):
                result[key] = incoming
                continue

            current = result[key]

            if isinstance(current, list) and isinstance(incoming, list):
                merged = current[:]
                for x in incoming:
                    if x not in merged:
                        merged.append(x)
                result[key] = merged
            elif current in (None, "", "unknown") and incoming not in (None, "", "unknown"):
                result[key] = incoming
    return result

def _build_analysis_summary(aggregated_analysis: dict[str, Any], risk_result: dict[str, Any]) -> str:
    parts: list[str] = []

    project_type = _safe_str(aggregated_analysis.get("project_type"))
    if project_type:
        parts.append(f"Тип проекта: {project_type}")

    total_device_count = aggregated_analysis.get("total_device_count")
    if total_device_count is not None:
        parts.append(f"Общее количество устройств: {total_device_count}")

    has_or_equivalent = aggregated_analysis.get("has_or_equivalent")
    if has_or_equivalent is False:
        parts.append('Формулировка "или эквивалент" не обнаружена')
    elif has_or_equivalent is True:
        parts.append('Формулировка "или эквивалент" обнаружена')

    timeline_assessment = _safe_dict(aggregated_analysis.get("timeline_assessment"))
    timelines = _safe_dict(aggregated_analysis.get("timelines"))

    implementation_days = timeline_assessment.get("implementation_days")
    if implementation_days is None:
        implementation_days = timelines.get("implementation_days")

    if implementation_days is not None:
        parts.append(f"Срок реализации: {implementation_days} дней")

    tailoring = _safe_dict(aggregated_analysis.get("tailoring_analysis"))
    tailoring_signs = _safe_list(tailoring.get("tailoring_signs"))
    if tailoring_signs:
        parts.append("Признаки заточки: " + "; ".join(map(str, tailoring_signs[:3])))

    completeness = _safe_dict(aggregated_analysis.get("documentation_completeness"))
    missing_info = _safe_list(completeness.get("missing_information"))
    if missing_info:
        parts.append("Недостающие данные: " + ", ".join(map(str, missing_info[:4])))

    score = risk_result.get("score")
    decision = _safe_str(risk_result.get("decision"))
    if score is not None and decision:
        parts.append(f"Risk score: {score}, категория: {decision}")

    decision_block = _safe_dict(aggregated_analysis.get("decision"))
    recommendation = _safe_str(decision_block.get("recommendation"))
    if recommendation:
        parts.append(f"Рекомендация: {recommendation}")

    return ". ".join(parts).strip() + "."


def _aggregate_document_analyses(doc_analyses: list[dict[str, Any]]) -> dict[str, Any]:
    equipment = _merge_equipment(doc_analyses)

    aggregated = {
        "project_type": _detect_project_type(doc_analyses),
        "equipment": equipment,
        "total_device_count": _sum_total_device_count(equipment),
        "vendors": _merge_vendors(doc_analyses),
        "has_or_equivalent": _merge_boolean_flags(doc_analyses, "has_or_equivalent"),
        "or_equivalent_evidence": _collect_or_equivalent_evidence(doc_analyses),
        "timelines": _merge_timelines(doc_analyses),
        "integrations": _merge_integrations(doc_analyses),
        "certificates": _merge_certificates(doc_analyses),
        "extracted_languages": _collect_languages(doc_analyses),
        "assumptions": _collect_assumptions(doc_analyses),
        "warnings": _collect_warnings(doc_analyses),
        "manufacturer_authorization_required": _merge_boolean_flags(
            doc_analyses,
            "manufacturer_authorization_required",
        ),
        "has_object_scheme": _merge_boolean_flags(doc_analyses, "has_object_scheme"),
        "has_installation_points": _merge_boolean_flags(doc_analyses, "has_installation_points"),
        "specific_model_detected": _merge_boolean_flags(doc_analyses, "specific_model_detected"),

        # new blocks
        "documentation_completeness": _merge_dicts_prefer_meaningful(doc_analyses, "documentation_completeness"),
        "tailoring_analysis": _merge_dicts_prefer_meaningful(doc_analyses, "tailoring_analysis"),
        "timeline_assessment": _merge_dicts_prefer_meaningful(doc_analyses, "timeline_assessment"),
        "technical_feasibility": _merge_dicts_prefer_meaningful(doc_analyses, "technical_feasibility"),
    }

    clarifying_questions: list[str] = []
    for item in doc_analyses:
        for question in _safe_list(item.get("clarifying_questions")):
            text = _safe_str(question)
            if text and text not in clarifying_questions:
                clarifying_questions.append(text)
    aggregated["clarifying_questions"] = clarifying_questions

    scoring_inputs: dict[str, bool] = {}
    for item in doc_analyses:
        value = item.get("scoring_inputs")
        if not isinstance(value, dict):
            continue
        for key, flag in value.items():
            if flag is True:
                scoring_inputs[key] = True
            elif key not in scoring_inputs:
                scoring_inputs[key] = bool(flag)
    aggregated["scoring_inputs"] = scoring_inputs

    decision_block = _merge_dicts_prefer_meaningful(doc_analyses, "decision")
    aggregated["decision"] = decision_block

    return aggregated


def _build_tender_payload(tender: Tender) -> dict[str, Any]:
    return {
        "id": str(tender.id),
        "title": tender.title,
        "customer_name": tender.customer_name,
        "description": tender.description,
        "status": tender.status.value if hasattr(tender.status, "value") else str(tender.status),
        "documents": [
            {
                "id": str(doc.id),
                "original_filename": doc.original_filename,
                "stored_filename": doc.stored_filename,
                "file_path": doc.file_path,
                "file_type": doc.file_type,
                "mime_type": doc.mime_type,
                "file_size": doc.file_size,
            }
            for doc in tender.documents
        ],
    }


@celery_app.task(name="tasks.analyze_tender")
def analyze_tender(tender_id: str) -> dict[str, Any]:
    db = SessionLocal()

    try:
        tender_uuid = uuid.UUID(tender_id)

        tender = db.execute(
            select(Tender)
            .options(selectinload(Tender.documents))
            .where(Tender.id == tender_uuid)
        ).scalar_one_or_none()

        if tender is None:
            return {"status": "error", "message": "Tender not found", "tender_id": tender_id}

        if not tender.documents:
            tender.status = TenderStatus.FAILED
            tender.analysis_summary = "No documents uploaded for analysis."
            tender.report_payload = {
                "error": "No documents uploaded for analysis."
            }
            db.add(tender)
            db.commit()

            return {
                "status": "error",
                "message": "No documents uploaded for analysis",
                "tender_id": tender_id,
            }

        tender.status = TenderStatus.IN_REVIEW
        db.add(tender)
        db.commit()

        parser = DocumentParser()
        analyzer = OpenAIAnalyzer()

        per_document_results: list[dict[str, Any]] = []

        for document in tender.documents:
            parsed = parser.parse(document.file_path)

            ai_result = analyzer.analyze_document(
                document_text=parsed["text"],
                sections=parsed["sections"],
                tables=parsed["tables"],
                metadata={
                    "tender_id": str(tender.id),
                    "document_id": str(document.id),
                    "filename": document.original_filename,
                    "file_type": document.file_type,
                },
            )

            per_document_results.append(
                {
                    "document": {
                        "id": str(document.id),
                        "original_filename": document.original_filename,
                        "stored_filename": document.stored_filename,
                        "file_path": document.file_path,
                        "file_type": document.file_type,
                    },
                    "parsed": parsed,
                    "analysis": ai_result,
                }
            )

        aggregated_analysis = _aggregate_document_analyses(
            [item["analysis"] for item in per_document_results]
        )

        risk_result = calculate_risk_score(
            aggregated_analysis.get("scoring_inputs") or aggregated_analysis
        )

        tender_payload = _build_tender_payload(tender)

        
        
        report = generate_report(
            tender_data=tender_payload,
            analysis_data=aggregated_analysis,
            risk_data=risk_result,
        )

        docx_meta: dict[str, Any] | None = None

        try:
            professional_context = build_professional_report_context(
                tender_data=tender_payload,
                report=report,
                risk=risk_result,
            )
            docx_meta = generate_tender_report_docx(
                tender_id=str(tender.id),
                context=professional_context,
            )
        except Exception as docx_exc:
            docx_meta = {
                "error": str(docx_exc),
            }

        docx_meta_for_payload: dict[str, Any] | None = None
        if docx_meta is not None:
            docx_meta_for_payload = dict(docx_meta)

            generated_at_value = docx_meta_for_payload.get("generated_at")
            if isinstance(generated_at_value, datetime):
                docx_meta_for_payload["generated_at"] = generated_at_value.isoformat()

        tender.status = TenderStatus.ANALYZED
        tender.tender_risk_score = float(risk_result["score"])
        tender.analysis_summary = _build_analysis_summary(aggregated_analysis, risk_result)
        tender.extracted_requirements = aggregated_analysis
        tender.report_payload = {
            "report": report,
            "risk": risk_result,
            "documents": per_document_results,
            "docx": docx_meta_for_payload,
        }

        if docx_meta and "path" in docx_meta:
            tender.report_docx_path = docx_meta["path"]
            tender.report_docx_filename = docx_meta["filename"]
            tender.report_docx_generated_at = docx_meta["generated_at"]
        else:
            tender.report_docx_path = None
            tender.report_docx_filename = None
            tender.report_docx_generated_at = None

        db.add(tender)
        db.commit()

        return {
            "status": "ok",
            "tender_id": str(tender.id),
            "documents_processed": len(per_document_results),
            "risk_score": risk_result["score"],
            "decision": risk_result["decision"],
            "report_docx_ready": bool(docx_meta and "path" in docx_meta),
        }

    except (ValueError, FileNotFoundError, AIAnalyzerError) as exc:
        try:
            tender_uuid = uuid.UUID(tender_id)
            tender = db.execute(
                select(Tender).where(Tender.id == tender_uuid)
            ).scalar_one_or_none()
            if tender is not None:
                tender.status = TenderStatus.FAILED
                tender.analysis_summary = f"Analysis failed: {str(exc)}"
                tender.report_payload = {"error": str(exc)}
                db.add(tender)
                db.commit()
        except Exception:
            db.rollback()

        return {
            "status": "error",
            "message": str(exc),
            "tender_id": tender_id,
        }

    except Exception as exc:
        db.rollback()

        try:
            tender_uuid = uuid.UUID(tender_id)
            tender = db.execute(
                select(Tender).where(Tender.id == tender_uuid)
            ).scalar_one_or_none()
            if tender is not None:
                tender.status = TenderStatus.FAILED
                tender.analysis_summary = f"Unexpected analysis error: {str(exc)}"
                tender.report_payload = {"error": str(exc)}
                db.add(tender)
                db.commit()
        except Exception:
            db.rollback()

        return {
            "status": "error",
            "message": f"Unexpected analysis error: {str(exc)}",
            "tender_id": tender_id,
        }

    finally:
        db.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m app.tasks.tender_analysis <tender_id>")
        raise SystemExit(1)

    task_result = analyze_tender(sys.argv[1])
    print(json.dumps(task_result, ensure_ascii=False, indent=2))