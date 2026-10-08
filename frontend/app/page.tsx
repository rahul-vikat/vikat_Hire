import Link from "next/link";
import { UploadScreeningForm } from "@/components/upload-screening-form";

export default function HomePage() {
  return (
    <main className="shell">
      <header className="topbar">
        <Link className="brand" href="/">VikatHire</Link>
        <span className="eyebrow">Evidence-led screening</span>
      </header>
      <section className="hero">
        <p className="eyebrow">Candidate assessment</p>
        <h1>Make a decision you can trace.</h1>
        <p className="lede">
          Submit a role and resume. VikatHire evaluates evidence deterministically and keeps the
          supporting references alongside the result.
        </p>
      </section>
      <UploadScreeningForm />
      <footer className="footnote">
        Scores and policy outcomes come from the screening service. This interface displays them;
        it does not recalculate them.
      </footer>
    </main>
  );
}
