import Link from "next/link";
import { Tender } from "@/lib/types";
import { formatDate, getStatusLabel, getStatusTone } from "@/lib/utils";

interface TenderCardProps {
  tender: Tender;
}

export function TenderCard({ tender }: TenderCardProps) {
  return (
    <article className="card tender-card">
      <div className="tender-card-top">
        <div>
          <h3>{tender.title}</h3>
          <p className="muted">{tender.customer_name}</p>
        </div>
        <span className={`badge badge-${getStatusTone(tender.status)}`}>{getStatusLabel(tender.status)}</span>
      </div>

      <div className="data-grid compact-grid">
        <div>
          <span className="label">Risk score</span>
          <strong>{tender.tender_risk_score ?? "—"}</strong>
        </div>
        <div>
          <span className="label">Created</span>
          <strong>{formatDate(tender.created_at)}</strong>
        </div>
      </div>

      <div className="card-actions">
        <Link href={`/tenders/${tender.id}`} className="button button-secondary">
          Open Details
        </Link>
      </div>
    </article>
  );
}