import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { appApi } from "../../api/services";
import { getApiErrorMessage } from "../../api/client";
import type {
  CriterionScore,
  Essay,
  EssayText,
  Evaluation,
  ReviewEvent,
  RubricVersion,
} from "../../api/types";
import { EvaluationResults } from "../../components/evaluations/EvaluationResults";
import {
  EmptyState,
  ErrorAlert,
  LoadingState,
  StatusBadge,
} from "../../components/ui/Feedback";

interface CriterionDraft {
  score: string;
  rationale: string;
  strengths: string;
  weaknesses: string;
  suggestions: string;
}

function draftFromScore(score: CriterionScore): CriterionDraft {
  return {
    score: score.faculty_score ?? "",
    rationale: score.faculty_rationale ?? "",
    strengths: (score.faculty_strengths ?? []).join("\n"),
    weaknesses: (score.faculty_weaknesses ?? []).join("\n"),
    suggestions: (score.faculty_suggestions ?? []).join("\n"),
  };
}

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function editableStatus(status: Evaluation["status"]): boolean {
  return status === "needs_review" || status === "changes_requested";
}

export function FacultyReviewPage() {
  const { evaluationId = "" } = useParams();
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [essay, setEssay] = useState<Essay | null>(null);
  const [essayText, setEssayText] = useState<EssayText | null>(null);
  const [rubric, setRubric] = useState<RubricVersion | null>(null);
  const [drafts, setDrafts] = useState<Record<string, CriterionDraft>>({});
  const [note, setNote] = useState("");
  const [decisionNotes, setDecisionNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingCriterion, setSavingCriterion] = useState<string | null>(null);
  const [savingNote, setSavingNote] = useState(false);
  const [decision, setDecision] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadReview = useCallback(async () => {
    setError("");
    try {
      const evaluationResult = await appApi.evaluation(evaluationId);
      const [essayResult, textResult, rubricResult] = await Promise.all([
        appApi.essay(evaluationResult.essay_id),
        appApi.essayText(evaluationResult.essay_id),
        appApi.rubricVersion(evaluationResult.rubric_version_id),
      ]);
      setEvaluation(evaluationResult);
      setEssay(essayResult);
      setEssayText(textResult);
      setRubric(rubricResult);
      setDrafts(
        Object.fromEntries(
          evaluationResult.criterion_scores.map((score) => [
            score.id,
            draftFromScore(score),
          ]),
        ),
      );
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load this evaluation."));
    } finally {
      setLoading(false);
    }
  }, [evaluationId]);

  useEffect(() => {
    void loadReview();
  }, [loadReview]);

  function updateDraft(scoreId: string, field: keyof CriterionDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [scoreId]: { ...current[scoreId], [field]: value },
    }));
  }

  async function saveCriterion(score: CriterionScore) {
    const draft = drafts[score.id];
    if (!draft || !evaluation) {
      return;
    }
    setError("");
    setSuccess("");
    setSavingCriterion(score.id);
    try {
      await appApi.updateCriterion(evaluation.id, score.id, {
        faculty_score: draft.score.trim() ? draft.score.trim() : null,
        faculty_rationale: draft.rationale.trim() || null,
        faculty_strengths: parseLines(draft.strengths),
        faculty_weaknesses: parseLines(draft.weaknesses),
        faculty_suggestions: parseLines(draft.suggestions),
      });
      const refreshedEvaluation = await appApi.evaluation(evaluation.id);
      setEvaluation(refreshedEvaluation);
      setSuccess("Faculty correction saved. The original AI result is unchanged.");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The correction could not be saved."));
    } finally {
      setSavingCriterion(null);
    }
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!evaluation || !note.trim()) {
      return;
    }
    setError("");
    setSuccess("");
    setSavingNote(true);
    try {
      const eventRecord = await appApi.addReviewNote(evaluation.id, note.trim());
      setEvaluation((current) =>
        current
          ? {
              ...current,
              review_history: [...current.review_history, eventRecord],
            }
          : current,
      );
      setNote("");
      setSuccess("Review note added.");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The review note could not be saved."));
    } finally {
      setSavingNote(false);
    }
  }

  async function submitDecision(action: "approved" | "rejected" | "changes_requested") {
    if (!evaluation) {
      return;
    }
    setError("");
    setSuccess("");
    setDecision(action);
    try {
      const updatedEvaluation = await appApi.reviewEvaluation(
        evaluation.id,
        action,
        decisionNotes.trim() || undefined,
      );
      setEvaluation(updatedEvaluation);
      setDecisionNotes("");
      setSuccess(`Evaluation ${action.replace("_", " ")}.`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The review decision could not be saved."));
    } finally {
      setDecision("");
    }
  }

  if (loading) {
    return <LoadingState label="Loading evaluation and evidence…" />;
  }
  if (error && !evaluation) {
    return (
      <div className="space-y-4">
        <ErrorAlert message={error} />
        <Link className="font-semibold text-indigo-700 hover:underline" to="/faculty">
          Return to review queue
        </Link>
      </div>
    );
  }
  if (!evaluation || !essay || !rubric) {
    return <EmptyState title="Evaluation not found" />;
  }

  const canEdit = editableStatus(evaluation.status);
  const criterionById = new Map(
    rubric.criteria.map((criterion) => [criterion.id, criterion]),
  );
  const history: ReviewEvent[] = [...evaluation.review_history].sort(
    (left, right) =>
      new Date(left.created_at).getTime() - new Date(right.created_at).getTime(),
  );

  return (
    <div className="space-y-6">
      <Link className="text-sm font-semibold text-indigo-700 hover:underline" to="/faculty">
        ← Back to review queue
      </Link>
      <header className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
              Faculty evaluation review
            </p>
            <h2 className="mt-1 break-words text-2xl font-bold text-navy-900">
              {essay.original_filename}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Student record {essay.student_id} · Rubric version {rubric.version_number}
            </p>
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
      </header>

      {error && <ErrorAlert message={error} />}
      {success && (
        <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800" role="status">
          {success}
        </p>
      )}

      <section>
        <div className="mb-3">
          <h3 className="text-lg font-semibold text-navy-900">Evaluation and cited evidence</h3>
          <p className="mt-1 text-sm text-slate-600">
            The browser verifies that highlighted offsets match this essay text.
            Excerpt existence does not establish evidence relevance.
          </p>
        </div>
        <EvaluationResults
          evaluation={evaluation}
          criteria={rubric.criteria}
          sourceText={essayText?.extracted_text}
          audience="faculty"
        />
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-navy-900">Faculty corrections</h3>
        <p className="mt-1 text-sm text-slate-600">
          Save score or feedback overrides independently. AI-generated scores and
          comments remain preserved as the original evaluation.
        </p>
        {evaluation.criterion_scores.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="No criterion scores are available">
              This evaluation may have failed before producing results.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-5 space-y-5">
            {evaluation.criterion_scores.map((score) => {
              const criterion = criterionById.get(score.criterion_id);
              const draft = drafts[score.id] ?? draftFromScore(score);
              return (
                <fieldset
                  key={score.id}
                  disabled={!canEdit || savingCriterion !== null}
                  className="rounded-lg border border-slate-200 p-4 disabled:opacity-70"
                >
                  <legend className="px-1 font-semibold text-slate-900">
                    {criterion?.name ?? "Rubric criterion"}
                  </legend>
                  {criterion && (
                    <p className="mb-4 text-sm text-slate-600">{criterion.description}</p>
                  )}
                  <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-medium text-slate-700">
                      Faculty score (AI: {score.ai_score})
                      <input
                        type="number"
                        step="any"
                        min={criterion?.min_score}
                        max={criterion?.max_score}
                        value={draft.score}
                        onChange={(event) =>
                          updateDraft(score.id, "score", event.target.value)
                        }
                        placeholder="Leave blank to use AI score"
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                      />
                      {criterion && (
                        <span className="mt-1 block text-xs text-slate-500">
                          Permitted range: {criterion.min_score}–{criterion.max_score}
                        </span>
                      )}
                    </label>
                    <label className="text-sm font-medium text-slate-700">
                      Faculty rationale
                      <textarea
                        rows={3}
                        value={draft.rationale}
                        onChange={(event) =>
                          updateDraft(score.id, "rationale", event.target.value)
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                      />
                    </label>
                    {(
                      [
                        ["strengths", "Faculty strengths"],
                        ["weaknesses", "Areas to improve"],
                        ["suggestions", "Actionable suggestions"],
                      ] as const
                    ).map(([field, label]) => (
                      <label key={field} className="text-sm font-medium text-slate-700">
                        {label} (one item per line)
                        <textarea
                          rows={3}
                          value={draft[field]}
                          onChange={(event) =>
                            updateDraft(score.id, field, event.target.value)
                          }
                          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                        />
                      </label>
                    ))}
                  </div>
                  {canEdit && (
                    <button
                      type="button"
                      onClick={() => void saveCriterion(score)}
                      disabled={savingCriterion !== null}
                      className="mt-4 rounded-lg border border-indigo-300 px-4 py-2 text-sm font-semibold text-indigo-800 hover:bg-indigo-50 disabled:opacity-60"
                    >
                      {savingCriterion === score.id ? "Saving…" : "Save correction"}
                    </button>
                  )}
                </fieldset>
              );
            })}
          </div>
        )}
      </section>

      <section className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-lg font-semibold text-navy-900">Add review note</h3>
          {canEdit ? (
            <form className="mt-3 space-y-3" onSubmit={(event) => void addNote(event)}>
              <label className="block text-sm font-medium text-slate-700">
                Note
                <textarea
                  required
                  minLength={1}
                  maxLength={4000}
                  rows={4}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="Record context for this review…"
                />
              </label>
              <button
                type="submit"
                disabled={savingNote || !note.trim()}
                className="rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-navy-900 disabled:opacity-60"
              >
                {savingNote ? "Saving note…" : "Add note"}
              </button>
            </form>
          ) : (
            <p className="mt-2 text-sm text-slate-600">
              This evaluation is closed for edits.
            </p>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-lg font-semibold text-navy-900">Review decision</h3>
          {canEdit ? (
            <div className="mt-3 space-y-3">
              <label className="block text-sm font-medium text-slate-700">
                Decision note (optional)
                <textarea
                  rows={3}
                  maxLength={4000}
                  value={decisionNotes}
                  onChange={(event) => setDecisionNotes(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={Boolean(decision)}
                  onClick={() => void submitDecision("approved")}
                  className="rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60"
                >
                  {decision === "approved" ? "Approving…" : "Approve"}
                </button>
                <button
                  type="button"
                  disabled={Boolean(decision)}
                  onClick={() => void submitDecision("changes_requested")}
                  className="rounded-lg border border-amber-400 px-4 py-2.5 text-sm font-semibold text-amber-900 hover:bg-amber-50 disabled:opacity-60"
                >
                  {decision === "changes_requested" ? "Submitting…" : "Request changes"}
                </button>
                <button
                  type="button"
                  disabled={Boolean(decision)}
                  onClick={() => void submitDecision("rejected")}
                  className="rounded-lg border border-rose-300 px-4 py-2.5 text-sm font-semibold text-rose-800 hover:bg-rose-50 disabled:opacity-60"
                >
                  {decision === "rejected" ? "Rejecting…" : "Reject"}
                </button>
              </div>
            </div>
          ) : (
            <p className="mt-2 text-sm text-slate-600">
              Current state: <strong>{evaluation.status.replaceAll("_", " ")}</strong>.
              No further review actions are available.
            </p>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-lg font-semibold text-navy-900">Review history</h3>
        {history.length === 0 ? (
          <div className="mt-3">
            <EmptyState title="No review actions recorded yet">
              Notes, corrections, and decisions will be listed here.
            </EmptyState>
          </div>
        ) : (
          <ol className="mt-4 space-y-3">
            {history.map((event) => (
              <li
                key={event.id}
                className="rounded-lg border border-slate-200 bg-slate-50 p-4"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="font-semibold text-slate-900">
                    {event.action.replaceAll("_", " ")}
                  </p>
                  <time className="text-xs text-slate-500">
                    {new Date(event.created_at).toLocaleString()}
                  </time>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  Faculty member {event.faculty_id}
                </p>
                {event.notes && (
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">
                    {event.notes}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
