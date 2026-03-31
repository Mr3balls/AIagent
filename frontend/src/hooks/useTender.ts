"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getTenderById } from "@/lib/api";
import { Tender } from "@/lib/types";
import { extractErrorMessage } from "@/lib/utils";

export function useTender(tenderId: string | null | undefined) {
  const { token, loading: authLoading } = useAuth();
  const [tender, setTender] = useState<Tender | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!token || !tenderId) {
      return null;
    }

    setError(null);
    setLoading(true);

    try {
      const data = await getTenderById(tenderId, token);
      setTender(data);
      return data;
    } catch (err) {
      const message = extractErrorMessage(err);
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [token, tenderId]);

  useEffect(() => {
    if (authLoading) {
      return;
    }

    if (!token || !tenderId) {
      setLoading(false);
      return;
    }

    refetch();
  }, [authLoading, token, tenderId, refetch]);

  return {
    tender,
    setTender,
    loading,
    error,
    refetch,
  };
}