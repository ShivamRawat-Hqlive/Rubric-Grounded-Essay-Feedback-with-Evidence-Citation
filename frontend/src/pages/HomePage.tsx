import { Link } from "react-router-dom";

export function HomePage() {
  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-navy-900 via-navy-800 to-indigo-900 px-6 py-10 text-white shadow-lg sm:px-10 sm:py-14">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-indigo-200">
          Personal portfolio · academic writing
        </p>
        <h1 className="mt-3 max-w-3xl text-3xl font-bold tracking-tight sm:text-5xl">
          Evidence-grounded essay feedback, in a simple local demo.
        </h1>
        <p className="mt-5 max-w-2xl text-sm leading-7 text-slate-200 sm:text-base">
          Upload a PDF or TXT essay, inspect exact quotations and character
          offsets, then switch to the faculty demonstration to review the result.
          No OpenAI key or account is required.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            to="/student"
            className="rounded-lg bg-white px-5 py-3 text-sm font-semibold text-navy-900 hover:bg-indigo-50"
          >
            Start student demo
          </Link>
          <Link
            to="/faculty"
            className="rounded-lg border border-white/40 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10"
          >
            Open faculty review
          </Link>
        </div>
      </section>
      <section className="grid gap-4 md:grid-cols-3">
        {[
          ["01", "Submit an essay", "Upload a text-based PDF or UTF-8 TXT document."],
          ["02", "Inspect evidence", "Every displayed quotation is verified against the exact extracted text."],
          ["03", "Review and approve", "Use the faculty demo to approve or request changes before student results are shown."],
        ].map(([number, title, description]) => (
          <article
            key={number}
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <p className="text-xs font-bold tracking-widest text-indigo-700">{number}</p>
            <h2 className="mt-2 font-semibold text-navy-900">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
          </article>
        ))}
      </section>
      <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
        <strong>Demo evaluator:</strong> Scores use transparent word-count,
        vocabulary-variety, structure, reasoning-marker and cohesion heuristics.
        They are not genuine LLM judgments.
      </p>
    </div>
  );
}
