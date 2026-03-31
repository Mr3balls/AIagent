import { Tender } from "@/lib/types";
import { getStatusLabel, getStatusTone, isAnalyzingTenderStatus } from "@/lib/utils";

interface AnalysisStatusProps {
  tender: Tender;
}

export function AnalysisStatus({ tender }: AnalysisStatusProps) {
  const tone = getStatusTone(tender.status);
  const isAnalyzing = isAnalyzingTenderStatus(tender.status);

  return (
    <div className="card">
      <div className="status-header">
        <h2>Analysis Status</h2>
        <span className={`badge badge-${tone}`}>{getStatusLabel(tender.status)}</span>
      </div>

      <div className="data-grid compact-grid">
        <div>
          <span className="label">Tender Risk Score</span>
          <strong>{tender.tender_risk_score ?? "—"}</strong>
        </div>
        <div>
          <span className="label">Current state</span>
          <strong>{isAnalyzing ? "Analysis in progress" : getStatusLabel(tender.status)}</strong>
        </div>
      </div>

      {tender.analysis_summary ? (
        <div className="top-border">
          <span className="label">Analysis summary</span>
          <p>{tender.analysis_summary}</p>
        </div>
      ) : null}
    </div>
  );
}