import { Tender, TenderDocument, TenderStatus } from "@/lib/types";

export function formatDate(value?: string | null): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function prettifyKey(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^./, (char) => char.toUpperCase());
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isTerminalTenderStatus(status?: TenderStatus): boolean {
  const normalized = String(status ?? "").toLowerCase();
  return normalized === "analyzed" || normalized === "failed";
}

export function isAnalyzingTenderStatus(status?: TenderStatus): boolean {
  const normalized = String(status ?? "").toLowerCase();
  return ["created", "in_review", "queued", "processing", "analyzing"].includes(normalized);
}

export function getStatusLabel(status?: TenderStatus): string {
  if (!status) {
    return "Unknown";
  }

  return prettifyKey(String(status));
}

export function getStatusTone(status?: TenderStatus): "default" | "success" | "warning" | "danger" {
  const normalized = String(status ?? "").toLowerCase();

  if (normalized === "analyzed") {
    return "success";
  }

  if (normalized === "failed") {
    return "danger";
  }

  if (["created", "in_review", "queued", "processing", "analyzing"].includes(normalized)) {
    return "warning";
  }

  return "default";
}

export function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  if (typeof error === "string") {
    return error;
  }

  return "Something went wrong";
}

export function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function ensureArray<T>(value: T | T[] | null | undefined): T[] {
  if (Array.isArray(value)) {
    return value;
  }

  if (value === null || value === undefined) {
    return [];
  }

  return [value];
}

export function normalizeDocuments(tender: Tender | null | undefined): TenderDocument[] {
  if (!tender) {
    return [];
  }

  const reportDocuments = tender.report_payload?.documents;

  if (Array.isArray(tender.documents) && tender.documents.length > 0) {
    return tender.documents;
  }

  if (Array.isArray(reportDocuments)) {
    return reportDocuments as TenderDocument[];
  }

  return [];
}

export function getDocumentLabel(document: TenderDocument, fallbackIndex: number): string {
  return (
    document.original_filename ||
    document.filename ||
    document.name ||
    `Document ${fallbackIndex + 1}`
  );
}