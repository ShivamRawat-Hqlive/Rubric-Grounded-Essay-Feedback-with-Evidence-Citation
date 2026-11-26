import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { appApi } from "../../api/services";
import { getApiErrorMessage } from "../../api/client";
import type {
  Course,
  Essay,
  EssayText,
  Evaluation,
  Rubric,
  RubricVersion,
} from "../../api/types";
import { EvaluationResults } from "../../components/evaluations/EvaluationResults";
import {
  EmptyState,
  ErrorAlert,
  LoadingState,
  StatusBadge,
} from "../../components/ui/Feedback";

export function EssayDetailPage() {
  const { essayId = "" } = useParams();
  const [essay, setEssay] = useState<Essay | null>(null);
  const [essayText, setEssayText] = useState<EssayText | null>(null);
  const [course, setCourse] = useState<Course | null>(null);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [rubricVersions, setRubricVersions] = useState<
    { rubric: Rubric; version: RubricVersion }[]
  >([]);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadEssay = useCallback(async () => {
    setError("");
    try {
      const [essayResult, textResult, courseList, evaluationList, rubricList] =
        await Promise.all([
          appApi.essay(essayId),
          appApi.essayText(essayId),
          appApi.courses(),
          appApi.evaluations({ essayId, limit: 100 }),
          appApi.rubrics(),
        ]);
      const matchedCourse =
        courseList.find((item) => item.id === essayResult.course_id) ?? null;
      const courseRubrics = rubricList.filter(
        (rubric) =>
          rubric.course_id === essayResult.course_id &&
          rubric.status === "published",
      );
      const versionGroups = await Promise.all(
        courseRubrics.map(async (rubric) => ({
          rubric,
          versions: await appApi.rubricVersions(rubric.id),
        })),
      );
      const availableVersions = versionGroups.flatMap(({ rubric, versions }) =>
        versions
          .filter((version) => version.is_published)
          .map((version) => ({ rubric, version })),
      );
      setEssay(essayResult);
      setEssayText(textResult);
      setCourse(matchedCourse);
      setEvaluations(evaluationList);
      setRubricVersions(availableVersions);
      setSelectedVersion((current) =>
        availableVersions.some(({ version }) => version.id === current)
          ? current
          : availableVersions[0]?.version.id ?? "",
      );
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load this essay."));
    } finally {
      setLoading(false);
    }
  }, [essayId]);

  useEffect(() => {
    void loadEssay();
  }, [loadEssay]);

  async function handleEvaluate() {
    if (!selectedVersion) {
      setError("Choose a published rubric version first.");
      return;
    }
    setError("");
    setSuccess("");
    setStarting(true);
    try {
      await appApi.startEvaluation(essayId, selectedVersion);
      setSuccess("Evaluation completed and is pending faculty review.");
      await loadEssay();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Evaluation could not be started."));
    } finally {
      setStarting(false);
    }
  }

  const criterionMaps = useMemo(() => {
    const map = new Map<string, RubricVersion["criteria"]>();
    for (const { version } of rubricVersions) {
      map.set(version.id, version.criteria);
    }
    return map;
  }, [rubricVersions]);

  if (loading) {
    return <LoadingState label="Loading essay details and available rubrics…" />;
  }
  if (error && !essay) {
    return (
      <div className="space-y-4">
        <ErrorAlert message={error} />
        <Link className="font-semibold text-indigo-700 hover:underline" to="/student">
          Return to dashboard
        </Link>
      </div>
    );
  }
  if (!essay) {
    return <EmptyState title="Essay not found" />;
  }

  return (
    <div className="space-y-6">
      <Link className="text-sm font-semibold text-indigo-700 hover:underline" to="/student">
        ← Back to submissions
      </Link>
      <header className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
              Essay submission
            </p>
            <h2 className="mt-1 break-words text-2xl font-bold text-navy-900">
              {essay.original_filename}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              {course?.code ?? "No course"}{course ? ` — ${course.name}` : ""} ·{" "}
              {new Date(essay.created_at).toLocaleString()}
            </p>
          </div>
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">
            {essay.parse_status}
          </span>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-slate-500">File type</dt>
            <dd className="font-medium text-slate-800">{essay.content_type}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Size</dt>
            <dd className="font-medium text-slate-800">
              {(essay.size_bytes / 1024).toFixed(1)} KB
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Text extraction</dt>
            <dd className="font-medium text-slate-800">{essay.extractor_name}</dd>
          </div>
        </dl>
        {essay.page_map.length > 0 && (
          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div className="rounded-lg bg-slate-50 p-3">
              <p className="text-slate-500">Pages processed</p>
              <p className="mt-1 font-medium text-slate-800">
                {essay.page_map.filter((page) => page.page_number !== null).length ||
                  "Document-wide"}
              </p>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <p className="text-slate-500">Extraction method</p>
              <p className="mt-1 font-medium text-slate-800">
                {essay.page_map.some((page) => page.extraction_method === "ocr")
                  ? "OCR (mixed with any native text)"
                  : "Native text"}
              </p>
            </div>
          </div>
        )}
      </header>

      {error && <ErrorAlert message={error} />}
      {success && (
        <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800" role="status">
          {success}
        </p>
      )}

      {essay.course_id ? (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold text-navy-900">Evaluate with a rubric</h3>
              <p className="mt-1 text-sm text-slate-500">
                The rubric must be published for this course. Evaluation runs synchronously.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadEssay()}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Refresh status
            </button>
          </div>
          {rubricVersions.length === 0 ? (
            <div className="mt-4">
              <EmptyState title="No published rubrics available">
                Ask your faculty member to publish a rubric for this course.
              </EmptyState>
            </div>
          ) : (
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <label className="flex-1 text-sm font-medium text-slate-700">
                Published rubric version
                <select
                  value={selectedVersion}
                  onChange={(event) => setSelectedVersion(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                >
                  {rubricVersions.map(({ rubric, version }) => (
                    <option key={version.id} value={version.id}>
                      {rubric.title} · v{version.version_number}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() => void handleEvaluate()}
                disabled={!selectedVersion || starting}
                className="self-end rounded-lg bg-navy-800 px-5 py-3 text-sm font-semibold text-white hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {starting ? "Evaluating…" : "Start evaluation"}
              </button>
            </div>
          )}
        </section>
      ) : (
        <p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
          This essay has no course. Course enrollment is required to select a rubric
          and request evaluation.
        </p>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-navy-900">Extracted text preview</h3>
          {essay.page_map.some((page) => page.extraction_method === "ocr") && (
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-900">
              OCR text — verify page references
            </span>
          )}
        </div>
        {essayText ? (
          <>
            <p className="mt-3 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700">
              {essayText.extracted_text.slice(0, 1500)}
              {essayText.extracted_text.length > 1500 ? "…" : ""}
            </p>
            {essay.page_map.some((page) => page.page_number !== null) && (
              <div className="mt-3 flex flex-wrap gap-2">
                {essay.page_map.map((page) => (
                  <span
                    key={`${page.page_number}-${page.extracted_char_start}`}
                    className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600"
                  >
                    Page {page.page_number}: {page.extraction_method === "ocr" ? "OCR" : "native"}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="mt-3 text-sm text-amber-900">
            The document was uploaded, but extracted text is unavailable.
            Upload a clearer scan or a typed document.
          </p>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-navy-900">Evaluations</h3>
        </div>
        {evaluations.length === 0 ? (
          <EmptyState title="No evaluations yet">
            Select a published rubric above to start the first evaluation.
          </EmptyState>
        ) : (
          <div className="space-y-5">
            {evaluations.map((evaluation) => {
              const rubric = rubricVersions.find(
                ({ version }) => version.id === evaluation.rubric_version_id,
              );
              return (
                <article key={evaluation.id} className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={evaluation.status} />
                      <span className="text-xs text-slate-500">
                        {rubric
                          ? `${rubric.rubric.title} · v${rubric.version.version_number}`
                          : "Published rubric version"}
                      </span>
                      {evaluation.evaluation_mode === "mock" && (
                        <span className="rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-bold text-fuchsia-900">
                          MOCK — NOT AI-GENERATED
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-500">
                      {new Date(evaluation.started_at).toLocaleString()}
                    </span>
                  </div>
                  <EvaluationResults
                    evaluation={evaluation}
                    criteria={criterionMaps.get(evaluation.rubric_version_id) ?? []}
                    sourceText={essayText?.extracted_text}
                    audience="student"
                  />
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
