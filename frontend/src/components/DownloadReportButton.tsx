"use client";

import { useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { downloadTenderReportDocx } from "@/lib/api";
import { Tender } from "@/lib/types";

interface DownloadReportButtonProps {
  tender: Tender;
}

export function DownloadReportButton({ tender }: DownloadReportButtonProps) {
  const { token } = useAuth();
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAnalyzed = useMemo(
    () => String(tender.status).toLowerCase() === "analyzed",
    [tender.status]
  );

  const isReady = useMemo(
    () => Boolean(tender.report_docx_filename),
    [tender.report_docx_filename]
  );

  const isDisabled = !token || !isAnalyzed || !isReady || isDownloading;

  async function handleDownload() {
    if (!token || !isReady) {
      return;
    }

    setError(null);
    setIsDownloading(true);

    try {
      await downloadTenderReportDocx(tender.id, token);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Не удалось скачать Word-отчет";
      setError(message);
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <div className="stack-sm">
      <button
        type="button"
        className="button button-secondary"
        onClick={handleDownload}
        disabled={isDisabled}
        title={
          !isAnalyzed
            ? "Сначала нужно завершить анализ"
            : !isReady
              ? "Word-отчет еще не подготовлен"
              : "Скачать анализ в формате DOCX"
        }
      >
        {isDownloading
          ? "Скачивание..."
          : isReady
            ? "Скачать анализ в Word"
            : "Word-отчет не готов"}
      </button>

      {tender.report_docx_generated_at ? (
        <p className="muted">
          DOCX создан: {new Date(tender.report_docx_generated_at).toLocaleString()}
        </p>
      ) : null}

      {error ? <div className="alert alert-error">{error}</div> : null}
    </div>
  );
}