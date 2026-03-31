"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { analyzeTender } from "@/lib/api";
import { extractErrorMessage } from "@/lib/utils";

interface AnalyzeButtonProps {
  tenderId: string;
  disabled?: boolean;
}

export function AnalyzeButton({ tenderId, disabled = false }: AnalyzeButtonProps) {
  const router = useRouter();
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    if (!token) {
      setError("User is not authenticated");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await analyzeTender(tenderId, token);
      router.push(`/tenders/${tenderId}/result`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack-sm">
      {error ? <div className="alert alert-error">{error}</div> : null}
      <button type="button" className="button" onClick={handleAnalyze} disabled={loading || disabled}>
        {loading ? "Starting analysis..." : "Start Analysis"}
      </button>
    </div>
  );
}