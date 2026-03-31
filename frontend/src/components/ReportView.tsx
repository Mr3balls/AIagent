import { SectionCard } from "@/components/SectionCard";
import { Tender, TenderDocument } from "@/lib/types";
import {
  ensureArray,
  formatDate,
  getDocumentLabel,
  getStatusLabel,
  getStatusTone,
  isObject,
  normalizeDocuments,
  prettifyKey,
} from "@/lib/utils";

interface ReportViewProps {
  tender: Tender;
}

function StructuredValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return <p className="muted">No data</p>;
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <p>{String(value)}</p>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <p className="muted">No items</p>;
    }

    return (
      <ul className="structured-list">
        {value.map((item, index) => (
          <li key={index}>
            <StructuredValue value={item} />
          </li>
        ))}
      </ul>
    );
  }

  if (isObject(value)) {
    const entries = Object.entries(value);

    if (entries.length === 0) {
      return <p className="muted">No fields</p>;
    }

    return (
      <div className="structured-object">
        {entries.map(([key, nestedValue]) => (
          <div key={key} className="structured-object-item">
            <span className="label">{prettifyKey(key)}</span>
            <StructuredValue value={nestedValue} />
          </div>
        ))}
      </div>
    );
  }

  return <p>{String(value)}</p>;
}

function DocumentsSection({ documents }: { documents: TenderDocument[] }) {
  if (documents.length === 0) {
    return <p className="muted">No uploaded documents found.</p>;
  }

  return (
    <div className="document-list">
      {documents.map((document, index) => (
        <div key={`${getDocumentLabel(document, index)}-${index}`} className="document-item">
          <strong>{getDocumentLabel(document, index)}</strong>
          <div className="document-meta">
            <span>{document.content_type || document.mime_type || "Unknown type"}</span>
            <span>{document.file_size || document.size ? `${Math.round(Number(document.file_size || document.size) / 1024)} KB` : "—"}</span>
            <span>{formatDate(document.uploaded_at || document.created_at)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ReportView({ tender }: ReportViewProps) {
  const reportPayload = tender.report_payload || {};
  const report = isObject(reportPayload.report) ? reportPayload.report : {};
  const risk = isObject(reportPayload.risk) ? reportPayload.risk : {};
  const documents = normalizeDocuments(tender);

  const sections = [
    { key: "general_information", title: "General Information" },
    { key: "technical_specification_summary", title: "Technical Specification Summary" },
    { key: "key_requirements", title: "Key Requirements" },
    { key: "documentation_completeness", title: "Documentation Completeness" },
    { key: "tailoring_signs", title: "Tailoring Signs" },
    { key: "timeline_analysis", title: "Timeline Analysis" },
    { key: "risks", title: "Risks" },
    { key: "questions_to_customer", title: "Questions to Customer" },
    { key: "conclusion", title: "Conclusion" },
  ];

  return (
    <div className="stack-lg">
      <section className="card">
        <div className="status-header">
          <h2>Analysis Report</h2>
          <span className={`badge badge-${getStatusTone(tender.status)}`}>{getStatusLabel(tender.status)}</span>
        </div>

        <div className="summary-grid">
          <div className="summary-item">
            <span className="label">Tender Risk Score</span>
            <strong>{tender.tender_risk_score ?? "—"}</strong>
          </div>
          <div className="summary-item">
            <span className="label">Title</span>
            <strong>{tender.title}</strong>
          </div>
          <div className="summary-item">
            <span className="label">Customer</span>
            <strong>{tender.customer_name}</strong>
          </div>
        </div>

        {tender.analysis_summary ? (
          <div className="top-border">
            <span className="label">Analysis Summary</span>
            <p>{tender.analysis_summary}</p>
          </div>
        ) : null}
      </section>

      <SectionCard title="Extracted Requirements">
        <StructuredValue value={tender.extracted_requirements} />
      </SectionCard>

      {sections.map(({ key, title }) => (
        <SectionCard key={key} title={title}>
          <StructuredValue value={report[key]} />
        </SectionCard>
      ))}

      <SectionCard title="Risk Details">
        <StructuredValue value={risk} />
      </SectionCard>

      <SectionCard title="Documents">
        <DocumentsSection documents={ensureArray(documents)} />
      </SectionCard>
    </div>
  );
}