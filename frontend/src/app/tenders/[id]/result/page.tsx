"use client";

import { DownloadReportButton } from "@/components/DownloadReportButton";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AnalysisStatus } from "@/components/AnalysisStatus";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { RawJsonView } from "@/components/RawJsonView";
import { ReportView } from "@/components/ReportView";
import { StateMessage } from "@/components/StateMessage";
import { useTenderPolling } from "@/hooks/useTenderPolling";
import { getStatusLabel, isAnalyzingTenderStatus } from "@/lib/utils";

export default function TenderResultPage() {
  const params = useParams<{ id: string }>();
  const tenderId = useMemo(() => {
    const rawValue = params?.id;
    return typeof rawValue === "string" ? rawValue : null;
  }, [params]);

  const { tender, loading, error, isPolling } = useTenderPolling(tenderId, true);
  const [activeTab, setActiveTab] = useState<"report" | "raw">("report");

  return (
    <ProtectedRoute>
      <div className="stack-lg">
        <div className="page-header">
          <div>
            <h1>Analysis Result</h1>
            <p className="muted">Polling GET /api/v1/tenders/{'{id}'} every 3 seconds until analysis is finished.</p>
          </div>
          {tender ? (
            <div className="button-row">
              <Link href={`/tenders/${tender.id}`} className="button button-secondary">
                Back to Tender
              </Link>
              <DownloadReportButton tender={tender} />
            </div>
          ) : null}
        </div>

        {loading ? <StateMessage title="Loading result" description="Fetching tender state and report payload." /> : null}
        {error ? <StateMessage title="Failed to load result" description={error} tone="danger" /> : null}

        {!loading && !error && !tender ? (
          <StateMessage title="Tender not found" description="No tender data returned for this ID." tone="warning" />
        ) : null}

        {tender ? (
          <>
            <AnalysisStatus tender={tender} />

            {isAnalyzingTenderStatus(tender.status) ? (
              <StateMessage
                title={isPolling ? "Analyzing tender" : `Status: ${getStatusLabel(tender.status)}`}
                description="Analysis is still in progress. This page refreshes automatically every 3 seconds."
                tone="warning"
              />
            ) : null}

            {String(tender.status).toLowerCase() === "failed" ? (
              <StateMessage
                title="Analysis failed"
                description={tender.analysis_summary || "Backend marked this tender as failed. Check raw JSON and backend logs."}
                tone="danger"
              />
            ) : null}

            {String(tender.status).toLowerCase() === "analyzed" ? (
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