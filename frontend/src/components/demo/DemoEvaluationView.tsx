import type { DemoEvaluation } from "../../api/types";

interface DemoEvaluationViewProps {
  evaluation: DemoEvaluation;
  showResults: boolean;
}

export function DemoEvaluationView({
  evaluation,
  showResults,
}: DemoEvaluationViewProps) {
  const pdfPages = evaluation.page_map.filter((page) => page.page_number !== null);
  const ocrPages = pdfPages.filter((page) => page.extraction_method === "ocr").length;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-navy-900">{evaluation.filename}</h2>
          <p className="mt-1 text-sm text-slate-600">
            Extracted with {evaluation.extractor_name}
            {pdfPages.length > 0
              ? ` · ${pdfPages.length} PDF page${pdfPages.length === 1 ? "" : "s"} processed (${ocrPages} OCR)`
              : " · pagination unavailable"}
          </p>
        </div>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold tracking-wide text-amber-900">
          {evaluation.demo_label}
        </span>
      </div>

      {showResults ? (
        <>
          <p className="rounded-lg bg-indigo-50 p-4 text-sm text-indigo-950">
            <strong>Demo score: {evaluation.total_score} / {evaluation.max_total_score}</strong>
            <span className="mt-1 block">
              A deterministic demonstration based on the visible heuristic for each criterion,
              not a genuine AI evaluation.
            </span>
          </p>
          <div className="space-y-4">
            {evaluation.criteria.map((criterion) => (
              <article
                key={criterion.name}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="font-semibold text-navy-900">{criterion.name}</h3>
                  <p className="text-sm font-semibold text-indigo-800">
                    {criterion.score} / {criterion.max_score} · {criterion.weight_percent}%
                  </p>
                </div>
                <p className="mt-1 text-sm text-slate-600">{criterion.description}</p>
                <p className="mt-3 text-sm text-slate-700">
                  <strong>How this demo score is generated:</strong> {criterion.basis}
                </p>
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {criterion.strengths.map((item) => <li key={item}>{item}</li>)}
                  {criterion.areas_to_improve.map((item) => <li key={item}>{item}</li>)}
                  {criterion.suggestions.map((item) => <li key={item}>{item}</li>)}
                </ul>
                {criterion.evidence_quotes.length > 0 && (
                  <div className="mt-4 border-l-2 border-indigo-300 pl-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Evidence from extracted essay
                    </p>
                    {criterion.evidence_quotes.map((citation, index) => {
                      const verified =
                        citation.existence_verified &&
                        evaluation.extracted_text.slice(
                          citation.extracted_char_start,
                          citation.extracted_char_end,
                        ) === citation.quoted_text;
                      return (
                        <blockquote
                          key={`${citation.extracted_char_start}-${index}`}
                          className="mt-2 text-sm italic leading-6 text-slate-800"
                        >
                          “{verified ? citation.quoted_text : "Citation could not be verified"}”
                          {verified && (
                            <span className="mt-1 block text-xs not-italic text-slate-500">
                              Characters {citation.extracted_char_start}–{citation.extracted_char_end}
                              {citation.page_number !== null && ` · Page ${citation.page_number}`}
                            </span>
                          )}
                        </blockquote>
                      );
                    })}
                  </div>
                )}
              </article>
            ))}
          </div>
        </>
      ) : (
        <p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
          Faculty review is {evaluation.status === "changes_requested" ? "requesting changes" : "pending"}.
          Criterion scores and feedback will appear here after faculty approval.
          {evaluation.faculty_note && (
            <span className="mt-2 block"><strong>Faculty note:</strong> {evaluation.faculty_note}</span>
          )}
        </p>
      )}

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-navy-900">
          Extracted text preview
        </summary>
        <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">
          {evaluation.extracted_text.slice(0, 4000)}
          {evaluation.extracted_text.length > 4000 && "\n\n[Preview truncated]"}
        </pre>
        <p className="mt-2 text-xs text-slate-500">
          Character offsets and citations refer to the unchanged extracted text.
        </p>
      </details>
    </div>
  );
}
