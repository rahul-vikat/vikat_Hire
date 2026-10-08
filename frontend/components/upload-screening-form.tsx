"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

type SourceField = "linkedin" | "github" | "portfolio";

function responseMessage(body: unknown): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : "Please check the submitted information.";
  }
  return "The screening request could not be completed.";
}

export function UploadScreeningForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const jd = form.get("jd_file");
    const resume = form.get("resume_file");
    if (!(jd instanceof File) || jd.size === 0 || !(resume instanceof File) || resume.size === 0) {
      setError("Choose both a job description and a resume.");
      return;
    }

    setBusy(true);
    const screeningId = crypto.randomUUID();
    form.set("screening_id", screeningId);
    try {
      const response = await fetch("/api/screenings", { method: "POST", body: form });
      const result: unknown = await response.json();
      if (!response.ok) {
        setError(responseMessage(result));
        return;
      }
      router.push(`/screenings/${encodeURIComponent(screeningId)}`);
    } catch {
      setError("Could not reach the screening service. Your selected files remain in this page.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel form-panel" onSubmit={submit}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Start a screening</p>
          <h2>Role and candidate documents</h2>
        </div>
        <span className="step-mark">01</span>
      </div>
      <div className="file-grid">
        <label className="file-field">
          <span>Job description <b aria-hidden="true">*</b></span>
          <input name="jd_file" type="file" accept=".pdf,.docx,.txt,.md,.markdown" required />
          <small>PDF, DOCX, TXT, or Markdown</small>
        </label>
        <label className="file-field">
          <span>Resume <b aria-hidden="true">*</b></span>
          <input name="resume_file" type="file" accept=".pdf,.docx,.txt,.md,.markdown" required />
          <small>Scanned PDF resumes may take longer to extract</small>
        </label>
      </div>

      <details className="optional-sources">
        <summary>Optional public professional profiles</summary>
        <p className="muted">Only provide a source and authorize retrieval when permitted.</p>
        {(["linkedin", "github", "portfolio"] as SourceField[]).map((source) => (
          <div className="source-row" key={source}>
            <label className="field-label" htmlFor={`${source}-url`}>
              {source[0].toUpperCase() + source.slice(1)} URL
              <input id={`${source}-url`} name={`${source}_url`} type="url" placeholder="https://" />
            </label>
            <label className="check-label">
              <input name={`${source}_authorized`} type="checkbox" value="true" />
              Authorized to retrieve
            </label>
          </div>
        ))}
      </details>

      {error && <p className="alert" role="alert">{error}</p>}
      <div className="form-actions">
        <p className="muted">Files are sent to the screening backend; this page does not store them.</p>
        <button className="button primary" type="submit" disabled={busy}>
          {busy ? "Submitting…" : "Start screening"}
        </button>
      </div>
    </form>
  );
}
