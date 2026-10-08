"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type {
  DimensionEvaluation,
  DimensionScore,
  Evidence,
  Provenance,
  ScreeningAPIResponse,
} from "@/lib/contracts";

function asApiResponse(value: unknown): ScreeningAPIResponse | null {
  if (typeof value !== "object" || value === null || !("report" in value)) return null;
  return value as ScreeningAPIResponse;
}

function errorDetail(value: unknown): string {
  if (typeof value === "object" && value !== null && "detail" in value) {
    const detail = (value as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return "The screening service could not complete this request.";
}

function formatDecimal(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : value;
}

function readable(value: string): string {
  return value.replaceAll("_", " ");
}

function jsonText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export function ScreeningDetail({ screeningId }: { screeningId: string }) {
  const [result, setResult] = useState<ScreeningAPIResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/screenings/${encodeURIComponent(screeningId)}`, {
        cache: "no-store",
      });
      const body: unknown = await response.json();
      if (!response.ok) throw new Error(errorDetail(body));
      const parsed = asApiResponse(body);
      if (!parsed) throw new Error("The backend returned an unexpected screening report.");
      setResult(parsed);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load this screening.");
    } finally {
      setLoading(false);
    }
  }, [screeningId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function resume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!result?.interruption) return;
    const form = new FormData(event.currentTarget);
    const missing = new Set(result.interruption.required_inputs_missing);
    for (const field of ["jd_file", "resume_file"] as const) {
      const key = field === "jd_file" ? "jd.extracted_content" : "resume.extracted_content";
      const file = form.get(field);
      if (missing.has(key) && (!(file instanceof File) || file.size === 0)) {
        setError(`Upload the ${field === "jd_file" ? "job description" : "resume"} to continue.`);
        return;
      }
      if (!missing.has(key)) form.delete(field);
    }

    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/screenings/${encodeURIComponent(screeningId)}/resume`,
        { method: "POST", body: form },
      );
      const body: unknown = await response.json();
      if (!response.ok) throw new Error(errorDetail(body));
      const parsed = asApiResponse(body);
      if (!parsed) throw new Error("The backend returned an unexpected resume result.");
      setResult(parsed);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not resume this screening.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !result) {
    return <main className="shell"><p className="muted">Loading authoritative screening report…</p></main>;
  }
  if (error && !result) {
    return (
      <main className="shell">
        <Link href="/" className="back-link">← New screening</Link>
        <div className="alert" role="alert">{error}</div>
        <button className="button secondary" onClick={() => void refresh()}>Try again</button>
      </main>
    );
  }
  if (!result) return null;

  const { report, interruption } = result;
  const scores = new Map(report.score?.dimensions.map((item) => [item.dimension, item]) ?? []);
  const evidenceById = new Map(report.evidence.map((item) => [item.evidence_id, item]));
  const provenanceById = new Map(report.provenances.map((item) => [item.provenance_id, item]));

  return (
    <main className="shell">
      <header className="topbar">
        <Link className="brand" href="/">VikatHire</Link>
        <button className="button secondary compact" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh report"}
        </button>
      </header>
      <div className="report-heading">
        <div>
          <p className="eyebrow">Screening report</p>
          <h1>{readable(report.workflow_status)}</h1>
          <p className="muted id-line">Screening ID · <code>{report.screening_id}</code></p>
        </div>
        <div className="score-card">
          <span className="eyebrow">Authoritative score</span>
          <strong>{report.score?.score ?? "Not available"}</strong>
          <span className="muted">{report.score?.score == null ? "insufficient applicable score" : "out of 100"}</span>
        </div>
      </div>

      {error && <p className="alert" role="alert">{error}</p>}
      {report.classification && (
        <section className="panel classification-card" aria-label="Job classification">
          <div>
            <p className="eyebrow">Job description classification</p>
            <strong>{readable(report.classification.jd_type)}</strong>
          </div>
          <p>{report.classification.rationale}</p>
        </section>
      )}
      {interruption && (
        <section className="panel interrupt-panel">
          <p className="eyebrow">Action required · {interruption.current_node}</p>
          <h2>Upload the missing document{interruption.required_inputs_missing.length > 1 ? "s" : ""}</h2>
          <ul className="missing-list">
            {interruption.required_inputs_missing.map((item) => <li key={item}>{readable(item)}</li>)}
          </ul>
          <form onSubmit={resume} className="resume-form">
            {interruption.required_inputs_missing.includes("jd.extracted_content") && (
              <label className="file-field">
                <span>Job description</span>
                <input name="jd_file" type="file" accept=".pdf,.docx,.txt,.md,.markdown" required />
              </label>
            )}
            {interruption.required_inputs_missing.includes("resume.extracted_content") && (
              <label className="file-field">
                <span>Resume</span>
                <input name="resume_file" type="file" accept=".pdf,.docx,.txt,.md,.markdown" required />
              </label>
            )}
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? "Extracting and resuming…" : "Upload and resume"}
            </button>
          </form>
        </section>
      )}

      {report.policy && (
        <section className="summary-grid" aria-label="Policy outcome">
          <div className="panel summary-card">
            <span className="eyebrow">Eligibility</span>
            <strong>{report.policy.suitability_eligible ? "Eligible" : "Not eligible"}</strong>
          </div>
          <div className="panel summary-card">
            <span className="eyebrow">Confidence</span>
            <strong>{readable(report.policy.confidence_level)}</strong>
          </div>
          <div className="panel summary-card">
            <span className="eyebrow">Policy configuration</span>
            <strong className="small-strong">{report.policy.configuration_ref}</strong>
          </div>
        </section>
      )}

      {report.evaluation && (
        <section className="section-block">
          <div className="section-title">
            <div><p className="eyebrow">Deterministic evaluation</p><h2>Dimension breakdown</h2></div>
            <span className="muted">Weight applied by scoring service</span>
          </div>
          <div className="dimension-grid">
            {report.evaluation.dimensions.map((dimension) => (
              <DimensionCard
                dimension={dimension}
                score={scores.get(dimension.dimension)}
                evidenceById={evidenceById}
                provenanceById={provenanceById}
                key={dimension.dimension}
              />
            ))}
          </div>
        </section>
      )}

      {report.policy && (
        <section className="panel section-panel">
          <p className="eyebrow">Deterministic policy</p>
          <h2>Gates and review</h2>
          <div className="gate-list">
            {report.policy.gates.map((gate, index) => (
              <div className="gate-row" key={String(gate.gate_id ?? index)}>
                <span>{String(gate.name ?? "Policy gate")}</span>
                <strong className={gate.passed === true ? "positive" : "negative"}>
                  {gate.passed === true ? "Pass" : "Fail"}
                </strong>
                <p>{String(gate.rationale ?? "")}</p>
              </div>
            ))}
          </div>
          {report.review_requests.length > 0 && (
            <div className="review-list">
              <h3>Review requests</h3>
              {report.review_requests.map((request, index) => (
                <article className="review-item" key={String(request.review_id ?? index)}>
                  <strong>{readable(String(request.reason ?? "review required"))}</strong>
                  <p>{String(request.requested_action ?? "")}</p>
                  <small>{request.blocking === true ? "Blocking review" : "Non-blocking review"}</small>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {report.explanation && (
        <section className="panel section-panel explanation-panel">
          <p className="eyebrow">Advisory explanation · {report.explanation.generated_by}</p>
          <p>{report.explanation.summary}</p>
        </section>
      )}

      <section className="section-block">
        <div className="section-title">
          <div><p className="eyebrow">Audit trail</p><h2>Evidence and provenance</h2></div>
          <span className="muted">{report.evidence.length} evidence items · {report.provenances.length} sources</span>
        </div>
        <EvidencePanel
          evidence={report.evidence}
          provenances={report.provenances}
          provenanceById={provenanceById}
        />
      </section>

      {report.llm_semantic_proposals.length > 0 && (
        <details className="panel section-panel advisory-panel">
          <summary>Advisory semantic proposals ({report.llm_semantic_proposals.length})</summary>
          <p className="muted">These proposals are not the authoritative deterministic evaluation.</p>
          <pre>{jsonText(report.llm_semantic_proposals)}</pre>
        </details>
      )}
    </main>
  );
}

function DimensionCard({
  dimension,
  score,
  evidenceById,
  provenanceById,
}: {
  dimension: DimensionEvaluation;
  score?: DimensionScore;
  evidenceById: Map<string, Evidence>;
  provenanceById: Map<string, Provenance>;
}) {
  return (
    <article className="panel dimension-card">
      <div className="dimension-topline">
        <h3>{readable(dimension.dimension)}</h3>
        <span className={`badge ${dimension.resolution === "evaluated" ? "badge-good" : "badge-muted"}`}>
          {readable(dimension.resolution)}
        </span>
      </div>
      <div className="dimension-values">
        <div><span className="muted">Raw value</span><strong>{formatDecimal(dimension.raw_value)}</strong></div>
        <div><span className="muted">Weight</span><strong>{formatDecimal(score?.weight)}%</strong></div>
        <div><span className="muted">Contribution</span><strong>{formatDecimal(score?.weighted_contribution)}</strong></div>
      </div>
      <p>{dimension.rationale}</p>
      {dimension.exclusion_reason && <p className="muted">Excluded: {readable(dimension.exclusion_reason)}</p>}
      <small className="muted">Applicability: {readable(dimension.applicability)}</small>
      {!!dimension.requirement_refs.length && (
        <details><summary>Requirement references ({dimension.requirement_refs.length})</summary>
          <ul>{dimension.requirement_refs.map((ref) => <li key={ref}><code>{ref}</code></li>)}</ul>
        </details>
      )}
      {!!dimension.evidence_refs.length && (
        <details>
          <summary>Evidence references ({dimension.evidence_refs.length})</summary>
          <div className="dimension-references">
            {dimension.evidence_refs.map((ref) => {
              const item = evidenceById.get(ref);
              return (
                <article className="linked-evidence" key={ref}>
                  <code>{ref}</code>
                  {item ? <p>{jsonText(item.content)}</p> : <p className="muted">Evidence detail is not present in this report.</p>}
                  {item && <ReferenceList refs={item.provenance_refs} labels={provenanceById} />}
                </article>
              );
            })}
          </div>
        </details>
      )}
      {!!dimension.provenance_refs.length && (
        <details>
          <summary>Provenance references ({dimension.provenance_refs.length})</summary>
          <ReferenceList refs={dimension.provenance_refs} labels={provenanceById} />
        </details>
      )}
    </article>
  );
}

function EvidencePanel({
  evidence,
  provenances,
  provenanceById,
}: {
  evidence: Evidence[];
  provenances: Provenance[];
  provenanceById: Map<string, Provenance>;
}) {
  const referencedEvidence = useMemo(() => new Set(evidence.map((item) => item.evidence_id)), [evidence]);
  if (evidence.length === 0 && provenances.length === 0) {
    return <div className="panel empty-state">No evidence artifacts were included in this report.</div>;
  }
  return (
    <div className="audit-grid">
      <div className="panel audit-panel">
        <h3>Evidence</h3>
        {evidence.map((item) => (
          <details className="audit-item" key={item.evidence_id}>
            <summary>
              <span>{readable(item.status)}</span>
              <code>{item.evidence_id.slice(0, 8)}</code>
            </summary>
            <p>{jsonText(item.content)}</p>
            <small>Confidence: {readable(item.confidence)} · Reliability: {readable(item.source_reliability)}</small>
            {item.notes && <p className="muted">{item.notes}</p>}
            <ReferenceList refs={item.provenance_refs} labels={provenanceById} />
          </details>
        ))}
      </div>
      <div className="panel audit-panel">
        <h3>Provenance</h3>
        {provenances.map((item) => (
          <article className="audit-item" key={item.provenance_id}>
            <strong>{readable(item.source_type)}</strong>
            <p>{safeWebUrl(item.source_uri) ? <a href={safeWebUrl(item.source_uri)!} target="_blank" rel="noreferrer">{item.source_uri}</a> : item.source_uri ?? item.source_ref ?? "Source reference unavailable"}</p>
            <small>{readable(item.method)} · {readable(item.access_status)}</small>
            {item.excerpt && <blockquote>{item.excerpt}</blockquote>}
            <code>{item.provenance_id}</code>
          </article>
        ))}
        {referencedEvidence.size === 0 && <p className="muted">No linked evidence objects were supplied.</p>}
      </div>
    </div>
  );
}

function ReferenceList({ refs, labels }: { refs: string[]; labels: Map<string, Provenance> }) {
  if (refs.length === 0) return <small className="muted">No provenance references</small>;
  return (
    <ul className="refs-list">
      {refs.map((ref) => {
        const source = labels.get(ref);
        return <li key={ref}>{source ? `${readable(source.source_type)} · ${source.source_uri ?? source.source_ref ?? ref}` : ref}</li>;
      })}
    </ul>
  );
}

function safeWebUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}
