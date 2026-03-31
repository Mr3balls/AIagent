"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { StateMessage } from "@/components/StateMessage";
import { TenderList } from "@/components/TenderList";
import { useAuth } from "@/hooks/useAuth";
import { getHealth, getTenders } from "@/lib/api";
import { HealthResponse, Tender } from "@/lib/types";
import { extractErrorMessage, safeJsonStringify } from "@/lib/utils";

export default function DashboardPage() {
  const { user, token, logout } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      return;
    }

    let mounted = true;

    async function loadData() {
      setLoading(true);
      setError(null);

      try {
        const [healthData, tendersData] = await Promise.all([getHealth(), getTenders(token)]);

        if (!mounted) {
          return;
        }

        setHealth(healthData);
        setTenders(tendersData.slice(0, 5));
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

    loadData();

    return () => {
      mounted = false;
    };
  }, [token]);

  return (
    <ProtectedRoute>
      <div className="stack-lg">
        <div className="page-header">
          <div>
            <h1>Dashboard</h1>
            <p className="muted">Overview of backend health, current user and latest tenders.</p>
          </div>
          <div className="button-row">
            <Link href="/tenders/new" className="button">
              Create Tender
            </Link>
            <Link href="/tenders" className="button button-secondary">
              View Tenders
            </Link>
            <button type="button" className="button button-secondary" onClick={logout}>
              Logout
            </button>
          </div>
        </div>

        {loading ? <StateMessage title="Loading dashboard" description="Fetching backend health and your recent tenders." /> : null}
        {error ? <StateMessage title="Dashboard error" description={error} tone="danger" /> : null}

        {user ? (
          <div className="card">
            <h2>Current User</h2>
            <div className="data-grid">
              <div>
                <span className="label">Full name</span>
                <strong>{user.full_name}</strong>
              </div>
              <div>
                <span className="label">Email</span>
                <strong>{user.email}</strong>
              </div>
              <div>
                <span className="label">Created at</span>
                <strong>{user.created_at || "—"}</strong>
              </div>
            </div>
          </div>
        ) : null}

        <div className="card">
          <h2>Backend Health</h2>
          {health ? <pre className="json-block">{safeJsonStringify(health)}</pre> : <p className="muted">No health data yet.</p>}
        </div>

        <div className="stack-sm">
          <h2>Latest My Tenders</h2>
          <TenderList tenders={tenders} />
        </div>
      </div>
    </ProtectedRoute>
  );
}