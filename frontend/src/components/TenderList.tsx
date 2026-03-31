import { Tender } from "@/lib/types";
import { TenderCard } from "@/components/TenderCard";
import { StateMessage } from "@/components/StateMessage";

interface TenderListProps {
  tenders: Tender[];
}

export function TenderList({ tenders }: TenderListProps) {
  if (tenders.length === 0) {
    return <StateMessage title="No tenders yet" description="Create your first tender to start uploading documents and running analysis." />;
  }

  return (
    <div className="cards-grid">
      {tenders.map((tender) => (
        <TenderCard key={tender.id} tender={tender} />
      ))}
    </div>
  );
}