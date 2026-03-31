"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { StateMessage } from "@/components/StateMessage";
import { TenderList } from "@/components/TenderList";
import { useAuth } from "@/hooks/useAuth";
import { getTenders } from "@/lib/api";
import { Tender } from "@/lib/types";
import { extractErrorMessage } from "@/lib/utils";

export default function TendersPage() {
  const { token } = useAuth();
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      return;
    }

    let mounted = true;

    async function loadTenders() {
      setLoading(true);
      setError(null);

      try {
        const data = await getTenders(token);

        if (!mounted) {
          return;
        }

        setTenders(data);
      } catch (err) {
        if (!mounted) {
          return;
        }

        setError(extractErrorMessage(err));
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadTenders();

    return () => {
      mounted = false;
    };
  }, [token]);

  return (
    <ProtectedRoute>
      <div className="stack-lg">
        <div className="page-header">
          <div>
            <h1>Tenders</h1>
            <p className="muted">List of your tenders returned by GET /api/v1/tenders.</p>
          </div>
          <Link href="/tenders/new" className="button">
            Create Tender
          </Link>
        </div>

        {loading ? <StateMessage title="Loading tenders" description="Fetching your tender list." /> : null}
        {error ? <StateMessage title="Failed to load tenders" description={error} tone="danger" /> : null}
        {!loading && !error ? <TenderList tenders={tenders} /> : null}
      </div>
    </ProtectedRoute>
  );
}