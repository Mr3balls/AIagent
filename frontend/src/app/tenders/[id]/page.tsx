"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AnalysisStatus } from "@/components/AnalysisStatus";
import { AnalyzeButton } from "@/components/AnalyzeButton";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { RawJsonView } from "@/components/RawJsonView";
import { ReportView } from "@/components/ReportView";
import { StateMessage } from "@/components/StateMessage";
import { UploadForm } from "@/components/UploadForm";
import { useTender } from "@/hooks/useTender";
import { formatDate, getDocumentLabel, normalizeDocuments } from "@/lib/utils";

export default function TenderDetailsPage() {
  const params = useParams<{ id: string }>();
  const tenderId = useMemo(() => {
    const rawValue = params?.id;
    return typeof rawValue === "string" ? rawValue : null;
  }, [params]);

  const { tender, loading, error, refetch } = useTender(tenderId);
  const [activeTab, setActiveTab] = useState<"report" | "raw">("report");

  return (
    <ProtectedRoute>
      <div className="stack-lg">
        {loading ? <StateMessage title="Loading tender" description="Fetching tender details." /> : null}
        {error ? <StateMessage title="Failed to load tender" description={error} tone="danger" /> : null}

        {!loading && !error && !tender ? (
          <StateMessage title="Tender not found" description="No tender data returned for this ID." tone="warning" />
        ) : null}

        {tender ? (
          <>
            <div className="page-header">
              <div>
                <h1>{tender.title}</h1>
                <p className="muted">Tender details, document upload and analysis preview.</p>
              </div>
              <div className="button-row">
                <Link href={`/tenders/${tender.id}/result`} className="button button-secondary">
                  Open Result Page
                </Link>
              </div>
            </div>

            <div className="card">
              <div className="data-grid">
                <div>
                  <span className="label">Customer name</span>
                  <strong>{tender.customer_name}</strong>
                </div>
                <div>
                  <span className="label">Created at</span>
                  <strong>{formatDate(tender.created_at)}</strong>
                </div>
                <div>
                  <span className="label">Updated at</span>
                  <strong>{formatDate(tender.updated_at)}</strong>
                </div>
              </div>

              <div className="top-border">
                <span className="label">Description</span>
                <p>{tender.description || "—"}</p>
              </div>
            </div>

            <AnalysisStatus tender={tender} />

            <UploadForm tenderId={tender.id} onUploaded={refetch} />

            <div className="card">
              <h2>Uploaded Documents</h2>
              {normalizeDocuments(tender).length > 0 ? (
                <div className="document-list">
                  {normalizeDocuments(tender).map((document, index) => (
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
              ) : (
                <p className="muted">No documents uploaded yet.</p>
              )}
            </div>

            <div className="card">
              <h2>Run Analysis</h2>
              <p className="muted">Starts POST /api/v1/tenders/{'{id}'}/analyze and redirects to the result page with polling.</p>
              <div className="top-border">
                <AnalyzeButton tenderId={tender.id} disabled={normalizeDocuments(tender).length === 0} />
              </div>
            </div>

            {tender.report_payload || tender.extracted_requirements || tender.analysis_summary ? (
              <div className="stack-sm">
                <div className="tabs">
                  <button
                    type="button"
                    className={`tab-button ${activeTab === "report" ? "active" : ""}`}
                    onClick={() => setActiveTab("report")}
                  >
                    Report View
                  </button>
                  <button
                    type="button"
                    className={`tab-button ${activeTab === "raw" ? "active" : ""}`}
                    onClick={() => setActiveTab("raw")}
                  >
                    Raw JSON
                  </button>
                </div>

                {activeTab === "report" ? <ReportView tender={tender} /> : <RawJsonView data={tender} />}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </ProtectedRoute>
  );
}