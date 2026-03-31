"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getTenderById } from "@/lib/api";
import { Tender } from "@/lib/types";
import { extractErrorMessage, isTerminalTenderStatus } from "@/lib/utils";

export function useTenderPolling(tenderId: string | null | undefined, enabled: boolean) {
  const { token, loading: authLoading } = useAuth();
  const [tender, setTender] = useState<Tender | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  const fetchTender = useCallback(async () => {
    if (!token || !tenderId) {
      return null;
    }

    try {
      const data = await getTenderById(tenderId, token);
      setTender(data);
      setError(null);
      return data;
    } catch (err) {
      const message = extractErrorMessage(err);
      setError(message);
      return null;
    }
  }, [token, tenderId]);

  useEffect(() => {
    if (authLoading) {
      return;
    }

    if (!token || !tenderId) {
      setLoading(false);
      setIsPolling(false);
      return;
    }

    let isMounted = true;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    async function start() {
      setLoading(true);
      const firstData = await fetchTender();

      if (!isMounted) {
        return;
      }

      setLoading(false);

      const shouldPoll = enabled && firstData && !isTerminalTenderStatus(firstData.status);
      setIsPolling(Boolean(shouldPoll));

      if (!shouldPoll) {
        return;
      }

      intervalId = setInterval(async () => {
        const nextData = await fetchTender();

        if (!isMounted) {
          return;
        }

        if (nextData && isTerminalTenderStatus(nextData.status)) {
          setIsPolling(false);

          if (intervalId) {
            clearInterval(intervalId);
          }
        }
      }, 3000);
    }

    start();

    return () => {
      isMounted = false;
      setIsPolling(false);

      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [authLoading, token, tenderId, enabled, fetchTender]);

  const isTerminal = useMemo(() => isTerminalTenderStatus(tender?.status), [tender?.status]);

  return {
    tender,
    loading,
    error,
    isPolling,
    isTerminal,
    refetch: fetchTender,
  };
}