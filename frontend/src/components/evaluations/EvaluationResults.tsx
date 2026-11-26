import type {
  CriterionScore,
  Evaluation,
  RubricCriterion,
} from "../../api/types";
import { StatusBadge } from "../ui/Feedback";

function FeedbackList({
  label,
  items,
}: {
  label: string;
  items: string[] | null;
}) {
  if (items === null) {
    return null;
  }
  return (
    <div>
      <h5 className="text-sm font-semibold text-slate-800">{label}</h5>
      {items.length > 0 ? (
        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
          {items.map((item, index) => (
            <li key={`${label}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-slate-500">No items provided.</p>
      )}
    </div>
  );
}

function EvidenceExcerpt({
  quote,
  sourceText,
}: {
  quote: CriterionScore["claims"][number]["evidence_quotes"][number];
  sourceText?: string;
}) {
  const { extracted_char_start: start, extracted_char_end: end } = quote;
  const sourceMatch =
    sourceText !== undefined &&
    start >= 0 &&
    end > start &&
    end <= sourceText.length &&
    sourceText.slice(start, end) === quote.quoted_text;
  const before = sourceMatch
    ? sourceText.slice(Math.max(0, start - 72), start)
    : "";
  const after = sourceMatch
    ? sourceText.slice(end, Math.min(sourceText.length, end + 72))
    : "";

  const location = [
    quote.page_start === null
      ? null
      : quote.page_start === quote.page_end
        ? `page ${quote.page_start}`
        : `pages ${quote.page_start}–${quote.page_end}`,
    quote.paragraph_start === null
      ? null
      : quote.paragraph_start === quote.paragraph_end
        ? `paragraph ${quote.paragraph_start}`
        : `paragraphs ${quote.paragraph_start}–${quote.paragraph_end}`,
    `extracted characters [${start}, ${end})`,
  ].filter(Boolean);

  return (
    <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-800">
          Excerpt {quote.existence_status}
        </span>
        <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">
          Relevance {quote.relevance_status}
        </span>
      </div>
      <blockquote className="mt-3 border-l-4 border-navy-700 pl-3 text-sm leading-6 text-slate-800">
        {sourceMatch ? (
          <>
            <span>{before}</span>
            <mark className="rounded bg-yellow-200 px-0.5">
              {sourceText.slice(start, end)}
            </mark>
            <span>{after}</span>
          </>
        ) : (
          <span>{quote.quoted_text}</span>
        )}
      </blockquote>
      {!sourceMatch && sourceText !== undefined && (
        <p className="mt-2 text-xs font-medium text-rose-700">
          The returned offset did not match the essay text loaded by the browser.
        </p>
      )}
      <p className="mt-2 text-xs text-slate-500">
        {location.join(" · ")}
        {sourceText === undefined && " · Full essay text was not loaded"}
      </p>
      <p className="mt-2 text-sm text-slate-600">
        <span className="font-medium">Model relevance explanation (not verified):</span>{" "}
        {quote.model_relevance_rationale}
      </p>
    </article>
  );
}

function CriterionCard({
  score,
  criterion,
  sourceText,
  audience,
}: {
  score: CriterionScore;
  criterion?: RubricCriterion;
  sourceText?: string;
  audience: "student" | "faculty";
}) {
  const facultyHasFeedback =
    score.faculty_score !== null ||
    score.faculty_rationale !== null ||
    score.faculty_strengths !== null ||
    score.faculty_weaknesses !== null ||
    score.faculty_suggestions !== null;

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-navy-900">
            {criterion?.name ?? "Rubric criterion"}
          </h3>
          {criterion && (
            <p className="mt-1 max-w-3xl text-sm text-slate-600">
              {criterion.description}
            </p>
          )}
        </div>
        <div className="rounded-lg bg-navy-50 px-3 py-2 text-right">
          <p className="text-xs text-slate-500">
            {audience === "student" ? "Approved score" : "AI score"}
          </p>
          <p className="text-lg font-semibold text-navy-900">
            {audience === "student"
              ? (score.faculty_score ?? score.ai_score)
              : score.ai_score}
          </p>
          {audience === "student" &&
            score.faculty_score !== null &&
            score.faculty_score !== score.ai_score && (
              <p className="text-xs text-slate-500">
                Original AI score: {score.ai_score}
              </p>
            )}
          {criterion && (
            <p className="text-xs text-slate-500">
              Range {criterion.min_score}–{criterion.max_score} · Weight{" "}
              {Number(criterion.weight) * 100}%
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <div>
            <h4 className="text-sm font-semibold text-slate-800">AI rationale</h4>
            <p className="mt-1 text-sm leading-6 text-slate-700">
              {score.ai_rationale}
            </p>
          </div>
          <FeedbackList label="AI strengths" items={score.strengths} />
          <FeedbackList label="AI areas to improve" items={score.weaknesses} />
          <FeedbackList label="AI suggestions" items={score.suggestions} />
        </div>

        {facultyHasFeedback && (
          <div className="space-y-3 rounded-lg border border-indigo-100 bg-indigo-50/60 p-4">
            <h4 className="font-semibold text-indigo-950">Faculty review</h4>
            {score.faculty_score !== null && (
              <p className="text-sm text-indigo-950">
                Faculty score: <strong>{score.faculty_score}</strong>
              </p>
            )}
            {score.faculty_rationale && (
              <p className="text-sm leading-6 text-indigo-950">
                {score.faculty_rationale}
              </p>
            )}
            <FeedbackList label="Faculty strengths" items={score.faculty_strengths} />
            <FeedbackList
              label="Faculty areas to improve"
              items={score.faculty_weaknesses}
            />
            <FeedbackList
              label="Faculty suggestions"
              items={score.faculty_suggestions}
            />
          </div>
        )}
      </div>

      <div className="mt-5 border-t border-slate-100 pt-4">
        <h4 className="font-semibold text-slate-900">Criterion claims and evidence</h4>
        {score.claims.length === 0 ? (
          <p className="mt-2 text-sm text-amber-800">
            No evidence claims were returned for this criterion.
          </p>
        ) : (
          <div className="mt-3 space-y-4">
            {score.claims.map((claim, claimIndex) => (
              <div key={`${score.id}-claim-${claimIndex}`} className="space-y-2">
                <p className="text-sm text-slate-800">{claim.text}</p>
                {claim.evidence_quotes.length > 0 ? (
                  claim.evidence_quotes.map((quote, quoteIndex) => (
                    <EvidenceExcerpt
                      key={`${score.id}-quote-${claimIndex}-${quoteIndex}`}
                      quote={quote}
                      sourceText={sourceText}
                    />
                  ))
                ) : (
                  <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">
                    This claim has no cited excerpt; its support is not established.
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

export function EvaluationResults({
  evaluation,
  criteria,
  sourceText,
  audience,
}: {
  evaluation: Evaluation;
  criteria: RubricCriterion[];
  sourceText?: string;
  audience: "student" | "faculty";
}) {
  if (audience === "student" && evaluation.status !== "approved") {
    const statusMessage =
      evaluation.status === "failed"
        ? {
            title: "Evaluation did not complete",
            detail: "No scores or feedback are available. Ask your faculty member for help.",
          }
        : evaluation.status === "rejected"
          ? {
              title: "Evaluation was not approved",
              detail: "Scores, comments, and evidence remain hidden from students.",
            }
          : evaluation.status === "queued" || evaluation.status === "running"
            ? {
                title: "Evaluation is in progress",
                detail: "Results will be available after evaluation and faculty review.",
              }
            : {
                title: "Faculty review is required",
                detail: "Scores, comments, and evidence are hidden until this evaluation is approved.",
              };
    return (
      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="font-semibold text-amber-950">
          {statusMessage.title}
        </h2>
        <p className="mt-1 text-sm text-amber-900">
          {statusMessage.detail}
        </p>
      </section>
    );
  }

  const total = evaluation.faculty_total_score ?? evaluation.ai_total_score;
  const criterionById = new Map(criteria.map((criterion) => [criterion.id, criterion]));

  return (
    <section className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
              Evaluation result
            </p>
            <h2 className="mt-1 text-xl font-semibold text-navy-900">
              Weighted total: {total ?? "—"}
            </h2>
            {evaluation.faculty_total_score !== null && (
              <p className="mt-1 text-xs text-slate-500">
                Uses faculty score overrides where set and AI scores otherwise.
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={evaluation.status} />
            {evaluation.evaluation_mode === "mock" && (
              <span className="rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-bold text-fuchsia-900">
                MOCK — NOT AI-GENERATED
              </span>
            )}
          </div>
        </div>
        {evaluation.has_unsupported_flags && (
          <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-900">
            One or more claims have no verified excerpt. Exact quotation matching
            does not independently establish relevance.
          </p>
        )}
      </header>
      {evaluation.criterion_scores.map((score) => (
        <CriterionCard
          key={score.id}
          score={score}
          criterion={criterionById.get(score.criterion_id)}
          sourceText={sourceText}
          audience={audience}
        />
      ))}
    </section>
  );
}
