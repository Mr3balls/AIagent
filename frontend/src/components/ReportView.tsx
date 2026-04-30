"use client";

import { useState } from "react";
import { Tender, TenderDocument } from "@/lib/types";
import { ensureArray, formatDate, getDocumentLabel, isObject, normalizeDocuments } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { downloadTenderDocument } from "@/lib/api";

interface ReportViewProps {
  tender: Tender;
}

// ── helpers ────────────────────────────────────────────────────────────────

function safeStr(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

function safeArr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function safeObj(v: unknown): Record<string, unknown> {
  return isObject(v) ? v : {};
}

// ── theme tokens (matches globals.css) ────────────────────────────────────

const T = {
  surface:   "var(--surface)",
  surface2:  "var(--surface-2)",
  border:    "var(--border)",
  text:      "var(--text)",
  muted:     "var(--muted)",
  success:   "#8ef0c0",
  warning:   "#ffd676",
  danger:    "#ff93a7",
  successBg: "rgba(31,157,98,0.15)",
  warningBg: "rgba(183,129,3,0.15)",
  dangerBg:  "rgba(207,63,91,0.15)",
  successBd: "rgba(31,157,98,0.45)",
  warningBd: "rgba(183,129,3,0.45)",
  dangerBd:  "rgba(207,63,91,0.45)",
};

// ── decision config ────────────────────────────────────────────────────────

type DecisionKey = "go" | "go_with_conditions" | "risky" | "do_not_participate";

const DECISION: Record<DecisionKey, { label: string; bg: string; bd: string; fg: string; icon: string }> = {
  go: {
    label: "Участвовать",
    bg: T.successBg, bd: T.successBd, fg: T.success, icon: "✓",
  },
  go_with_conditions: {
    label: "Участвовать с условиями",
    bg: T.warningBg, bd: T.warningBd, fg: T.warning, icon: "⚠",
  },
  risky: {
    label: "Высокий риск",
    bg: T.dangerBg, bd: T.dangerBd, fg: T.danger, icon: "⚠",
  },
  do_not_participate: {
    label: "Не участвовать",
    bg: T.dangerBg, bd: T.dangerBd, fg: T.danger, icon: "✕",
  },
};

const BLOCK_LABELS: Record<string, string> = {
  tailoring:     "Признаки заточки",
  timeline:      "Сроки",
  documentation: "Документация",
  experience:    "Требования к опыту",
  complexity:    "Сложность проекта",
};

// ── layout primitives ──────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      borderRadius: 16,
      padding: "18px 20px",
    }}>
      <div style={{
        fontSize: 13,
        fontWeight: 700,
        color: T.muted,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        marginBottom: 14,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Divider() {
  return <div style={{ borderTop: `1px solid ${T.border}`, margin: "8px 0" }} />;
}

function GroupLabel({ label }: { label: string }) {
  return (
    <div style={{
      fontSize: 11,
      fontWeight: 600,
      color: T.muted,
      textTransform: "uppercase",
      letterSpacing: "0.05em",
      marginBottom: 6,
      marginTop: 4,
    }}>
      {label}
    </div>
  );
}

// ── decision banner ────────────────────────────────────────────────────────

function DecisionBanner({ risk, tender }: { risk: Record<string, unknown>; tender: Tender }) {
  const key = safeStr(risk.decision) as DecisionKey;
  const cfg = DECISION[key] ?? { label: key || "Нет данных", bg: "transparent", bd: T.border, fg: T.muted, icon: "?" };
  const score    = typeof risk.score === "number" ? risk.score : null;
  const maxScore = typeof risk.max_score === "number" ? risk.max_score : 230;
  const pct      = score !== null ? Math.min(100, Math.round((score / maxScore) * 100)) : 0;

  return (
    <div style={{
      background: cfg.bg,
      border: `1px solid ${cfg.bd}`,
      borderRadius: 16,
      padding: "18px 20px",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20, color: cfg.fg, fontWeight: 700 }}>{cfg.icon}</span>
          <span style={{ fontSize: 19, fontWeight: 700, color: cfg.fg }}>{cfg.label}</span>
        </div>
        {score !== null && (
          <span style={{ fontSize: 14, color: cfg.fg, fontWeight: 600 }}>
            {score} / {maxScore} баллов
          </span>
        )}
      </div>

      {score !== null && (
        <div style={{ marginTop: 10, height: 4, borderRadius: 2, background: T.border }}>
          <div style={{ height: "100%", width: `${pct}%`, background: cfg.fg, borderRadius: 2 }} />
        </div>
      )}

      <div style={{ marginTop: 10, fontSize: 13, color: T.muted }}>
        <span>{tender.title}</span>
        {tender.customer_name && <span> &nbsp;·&nbsp; {tender.customer_name}</span>}
      </div>
    </div>
  );
}

// ── risk rules list ────────────────────────────────────────────────────────

interface RiskReason {
  code:        string;
  description: string;
  points:      number;
  triggered:   boolean;
  details:     string | null;
  block:       string;
}

function RiskRow({ reason, last }: { reason: RiskReason; last: boolean }) {
  const fg = reason.triggered ? T.danger : T.success;
  const icon = reason.triggered ? "✕" : "✓";

  return (
    <div style={{
      display: "flex",
      alignItems: "flex-start",
      gap: 10,
      padding: "9px 0",
      borderBottom: last ? "none" : `1px solid ${T.border}`,
    }}>
      <span style={{ color: fg, fontWeight: 700, fontSize: 13, minWidth: 14, marginTop: 1 }}>{icon}</span>
      <div style={{ flex: 1 }}>
        <span style={{ fontSize: 14, color: T.text }}>{reason.description}</span>
        {reason.details && (
          <div style={{ fontSize: 12, color: T.muted, marginTop: 3 }}>{reason.details}</div>
        )}
      </div>
      {reason.triggered && (
        <span style={{ color: T.danger, fontWeight: 700, fontSize: 13, whiteSpace: "nowrap" }}>
          +{reason.points} б
        </span>
      )}
    </div>
  );
}

function RiskSection({ risk }: { risk: Record<string, unknown> }) {
  const reasons  = safeArr(risk.reasons) as RiskReason[];
  const triggered = reasons.filter(r => r.triggered);

  if (triggered.length === 0) {
    return (
      <Section title="Выявленные риски">
        <span style={{ fontSize: 14, color: T.success }}>✓ &nbsp;Рисков не обнаружено</span>
      </Section>
    );
  }

  const byBlock: Record<string, RiskReason[]> = {};
  for (const r of triggered) {
    const b = r.block ?? "other";
    if (!byBlock[b]) byBlock[b] = [];
    byBlock[b].push(r);
  }
  const blocks = Object.entries(byBlock);

  return (
    <Section title="Выявленные риски">
      {blocks.map(([block, items], bi) => (
        <div key={block}>
          {bi > 0 && <Divider />}
          <GroupLabel label={BLOCK_LABELS[block] ?? block} />
          {items.map((r, i) => (
            <RiskRow key={r.code} reason={r} last={i === items.length - 1} />
          ))}
        </div>
      ))}
    </Section>
  );
}

// ── documentation ──────────────────────────────────────────────────────────

const DOC_FIELDS: Array<{ key: string; label: string }> = [
  { key: "has_architecture_scheme",          label: "Схема архитектуры" },
  { key: "has_object_plan",                  label: "План объекта" },
  { key: "has_installation_points",          label: "Точки установки" },
  { key: "has_cable_routes",                 label: "Кабельные трассы" },
  { key: "has_power_supply_info",            label: "Данные об электропитании" },
  { key: "has_existing_infrastructure_info", label: "Существующая инфраструктура" },
  { key: "enough_data_for_estimation",       label: "Достаточно данных для оценки" },
];

function PresenceRow({ label, status, last }: { label: string; status: string; last: boolean }) {
  const icon  = status === "yes" ? "✓" : status === "no" ? "✕" : "?";
  const color = status === "yes" ? T.success : status === "no" ? T.danger : T.muted;

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "8px 0",
      borderBottom: last ? "none" : `1px solid ${T.border}`,
    }}>
      <span style={{ color, fontWeight: 700, fontSize: 13, minWidth: 14 }}>{icon}</span>
      <span style={{ fontSize: 14, color: status === "no" ? T.danger : T.text }}>{label}</span>
    </div>
  );
}

function DocumentationSection({ completeness }: { completeness: Record<string, unknown> }) {
  const missing = safeArr(completeness.missing_information).map(x => safeStr(x)).filter(Boolean);
  const comment = safeStr(completeness.completeness_comment);
  const hasAny  = DOC_FIELDS.some(f => completeness[f.key]);

  if (!hasAny && missing.length === 0) return null;

  return (
    <Section title="Полнота документации">
      {DOC_FIELDS.map(({ key, label }, i) => {
        const val = safeStr(completeness[key] as string) || "unknown";
        if (val === "unknown") return null;
        const isLast = i === DOC_FIELDS.length - 1 || DOC_FIELDS.slice(i + 1).every(f => (safeStr(completeness[f.key] as string) || "unknown") === "unknown");
        return <PresenceRow key={key} label={label} status={val} last={isLast && missing.length === 0} />;
      })}
      {missing.length > 0 && (
        <div style={{ marginTop: 10, padding: "10px 14px", background: T.surface2, borderRadius: 10, border: `1px solid ${T.border}` }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.muted, textTransform: "uppercase", marginBottom: 6 }}>
            Отсутствует в документации
          </div>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13, color: T.danger, display: "flex", flexDirection: "column", gap: 3 }}>
            {missing.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      )}
      {comment && <p style={{ marginTop: 10, fontSize: 12, color: T.muted }}>{comment}</p>}
    </Section>
  );
}

// ── timeline ───────────────────────────────────────────────────────────────

function TimelineSection({ timeline, assessment }: {
  timeline:   Record<string, unknown>;
  assessment: Record<string, unknown>;
}) {
  const days         = assessment.implementation_days ?? timeline.implementation_days;
  const deliveryDays = assessment.delivery_days_estimate;
  const deadline     = safeStr(timeline.delivery_deadline);
  const riskLevel    = safeStr(assessment.timeline_risk_level as string);
  const comment      = safeStr(assessment.timeline_comment as string);
  const rawText      = safeStr(timeline.raw_text);
  const matchScope   = safeStr(assessment.timeline_matches_scope as string);
  const exceedsProj  = safeStr(assessment.delivery_exceeds_project_timeline as string);
  const siteSurvey   = safeStr(assessment.requires_site_survey as string);

  const hasAny = typeof days === "number" || typeof deliveryDays === "number" || deadline || rawText;
  if (!hasAny) return null;

  const riskColor = riskLevel === "high" ? T.danger : riskLevel === "medium" ? T.warning : T.success;
  const daysColor = typeof days === "number" && days < 30 ? T.danger : T.text;

  const flags: string[] = [];
  if (matchScope === "no")    flags.push("Сроки не соответствуют объёму работ");
  if (exceedsProj === "yes")  flags.push("Срок поставки превышает срок проекта");
  if (siteSurvey === "yes")   flags.push("Требуется обследование объекта");

  return (
    <Section title="Сроки">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: flags.length ? 10 : 0 }}>
        {typeof days === "number" && (
          <div style={{ fontSize: 14 }}>
            <span style={{ color: T.muted, fontSize: 12 }}>Срок реализации&nbsp;</span>
            <span style={{ fontWeight: 700, color: daysColor }}>{days} дней</span>
          </div>
        )}
        {typeof deliveryDays === "number" && (
          <div style={{ fontSize: 14 }}>
            <span style={{ color: T.muted, fontSize: 12 }}>Срок поставки&nbsp;</span>
            <span style={{ fontWeight: 700, color: T.text }}>{deliveryDays} дней</span>
          </div>
        )}
        {deadline && (
          <div style={{ fontSize: 14 }}>
            <span style={{ color: T.muted, fontSize: 12 }}>Дедлайн&nbsp;</span>
            <span style={{ fontWeight: 700, color: T.text }}>{deadline}</span>
          </div>
        )}
        {riskLevel && (
          <div style={{ fontSize: 14 }}>
            <span style={{ color: T.muted, fontSize: 12 }}>Уровень риска&nbsp;</span>
            <span style={{ fontWeight: 700, color: riskColor }}>
              {riskLevel === "low" ? "низкий" : riskLevel === "medium" ? "средний" : "высокий"}
            </span>
          </div>
        )}
      </div>
      {flags.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {flags.map((f, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: T.danger }}>
              <span style={{ fontWeight: 700 }}>⚠</span> {f}
            </div>
          ))}
        </div>
      )}
      {rawText && <p style={{ marginTop: 8, fontSize: 12, color: T.muted }}>{rawText}</p>}
      {comment  && <p style={{ marginTop: 4,  fontSize: 12, color: T.muted }}>{comment}</p>}
    </Section>
  );
}

// ── tailoring ──────────────────────────────────────────────────────────────

function TailoringSection({ tailoring }: { tailoring: Record<string, unknown> }) {
  const signs   = safeArr(tailoring.tailoring_signs).map(x => safeStr(x)).filter(Boolean);
  const models  = safeArr(tailoring.specific_models_detected).map(x => safeStr(x)).filter(Boolean);
  const prob    = safeStr(tailoring.tailoring_probability as string);
  const comment = safeStr(tailoring.tailoring_comment as string);

  if (signs.length === 0 && models.length === 0 && !prob) return null;

  const probColor = prob === "high" ? T.danger : prob === "medium" ? T.warning : T.success;
  const probLabel = prob === "low" ? "низкая" : prob === "medium" ? "средняя" : prob === "high" ? "высокая" : prob;

  return (
    <Section title="Признаки заточки под поставщика">
      {prob && (
        <div style={{ marginBottom: 12, fontSize: 14 }}>
          <span style={{ color: T.muted, fontSize: 12 }}>Вероятность заточки&nbsp;</span>
          <span style={{ fontWeight: 700, color: probColor }}>{probLabel}</span>
        </div>
      )}
      {models.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <GroupLabel label="Обнаруженные модели" />
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13, color: T.text, display: "flex", flexDirection: "column", gap: 3 }}>
            {models.map((m, i) => <li key={i}>{m}</li>)}
          </ul>
        </div>
      )}
      {signs.length > 0 && (
        <div>
          <GroupLabel label="Выявленные признаки" />
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13, color: T.text, display: "flex", flexDirection: "column", gap: 3 }}>
            {signs.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {comment && <p style={{ marginTop: 10, fontSize: 12, color: T.muted }}>{comment}</p>}
    </Section>
  );
}

// ── questions ──────────────────────────────────────────────────────────────

function QuestionsSection({ questions }: { questions: string[] }) {
  if (questions.length === 0) return null;
  return (
    <Section title="Вопросы заказчику">
      <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 8 }}>
        {questions.map((q, i) => (
          <li key={i} style={{ fontSize: 14, color: T.text, lineHeight: 1.5 }}>{q}</li>
        ))}
      </ol>
    </Section>
  );
}

// ── documents ──────────────────────────────────────────────────────────────

function DocDownloadButton({
  tenderId,
  doc,
  token,
}: {
  tenderId: string;
  doc: TenderDocument;
  token: string | null;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const docId = doc.id as string | undefined;
  if (!docId) return null;

  const filename = getDocumentLabel(doc, 0);

  async function handleClick() {
    setError(null);
    setLoading(true);
    try {
      await downloadTenderDocument(tenderId, docId!, filename, token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка скачивания");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {error && <span style={{ fontSize: 11, color: T.danger }}>{error}</span>}
      <button
        onClick={handleClick}
        disabled={loading}
        style={{
          background: "transparent",
          border: `1px solid ${T.border}`,
          borderRadius: 8,
          color: loading ? T.muted : T.text,
          fontSize: 12,
          padding: "4px 10px",
          cursor: loading ? "not-allowed" : "pointer",
          whiteSpace: "nowrap",
        }}
      >
        {loading ? "…" : "↓ Скачать"}
      </button>
    </div>
  );
}

function DocumentsSection({ documents, tenderId, token }: {
  documents: TenderDocument[];
  tenderId: string;
  token: string | null;
}) {
  if (documents.length === 0) return null;
  return (
    <Section title="Документы">
      <div style={{ display: "flex", flexDirection: "column" }}>
        {documents.map((doc, i) => (
          <div key={i} style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: 13,
            padding: "9px 0",
            borderBottom: i < documents.length - 1 ? `1px solid ${T.border}` : "none",
            gap: 12,
          }}>
            <div>
              <span style={{ color: T.text }}>{getDocumentLabel(doc, i)}</span>
              <span style={{ color: T.muted, marginLeft: 10 }}>
                {doc.file_size ? `${Math.round(Number(doc.file_size) / 1024)} KB` : ""}
                {doc.created_at ? ` · ${formatDate(doc.created_at)}` : ""}
              </span>
            </div>
            <DocDownloadButton tenderId={tenderId} doc={doc} token={token} />
          </div>
        ))}
      </div>
    </Section>
  );
}

// ── main export ────────────────────────────────────────────────────────────

export function ReportView({ tender }: ReportViewProps) {
  const { token }     = useAuth();
  const reportPayload = safeObj(tender.report_payload);
  const risk          = safeObj(reportPayload.risk);
  const analysis      = safeObj(tender.extracted_requirements);
  const documents     = ensureArray(normalizeDocuments(tender));

  const completeness = safeObj(analysis.documentation_completeness);
  const tailoring    = safeObj(analysis.tailoring_analysis);
  const timeline     = safeObj(analysis.timelines);
  const assessment   = safeObj(analysis.timeline_assessment);
  const questions    = safeArr(analysis.clarifying_questions).map(x => safeStr(x)).filter(Boolean);

  return (
    <div className="stack-sm">
      <DecisionBanner risk={risk} tender={tender} />
      <RiskSection risk={risk} />
      <DocumentationSection completeness={completeness} />
      <TimelineSection timeline={timeline} assessment={assessment} />
      <TailoringSection tailoring={tailoring} />
      <QuestionsSection questions={questions} />
      <DocumentsSection documents={documents} tenderId={tender.id} token={token} />
    </div>
  );
}
