import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage } from "../../api/client";
import { demoApi } from "../../api/services";
import type { DemoEvaluation } from "../../api/types";
import { DemoEvaluationView } from "../../components/demo/DemoEvaluationView";

export function DemoFacultyPage() {
  const [evaluations, setEvaluations] = useState<DemoEvaluation[]>([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  async function refresh() {
    try {
      setEvaluations(await demoApi.evaluations());
      setError("");
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The faculty review queue could not be loaded."));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleReview(
    evaluationId: string,
    action: "approved" | "changes_requested",
  ) {
    setBusyId(evaluationId);
    setError("");
    try {
      const updated = await demoApi.review(evaluationId, action);
      setEvaluations((current) =>
        current.map((item) => item.id === evaluationId ? updated : item),
      );
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The review action could not be saved."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
            Faculty demonstration
          </p>
          <h1 className="mt-2 text-3xl font-bold text-navy-900">Review submissions</h1>
          <p className="mt-2 text-slate-600">
            Inspect the complete demo feedback, then approve it or request changes.
          </p>
        </div>
        <Link to="/student" className="text-sm font-semibold text-indigo-700 hover:underline">
          Switch to student demo
        </Link>
      </div>
      {error && <p role="alert" className="rounded-lg bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
      {evaluations.length === 0 && !error ? (
        <p className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          No submissions yet. Upload an essay from the{" "}
          <Link to="/student" className="font-semibold text-indigo-700 hover:underline">
            student demo
          </Link>{" "}
          to add one to this review queue.
        </p>
      ) : (
        <div className="space-y-5">
          {evaluations.map((evaluation) => (
            <article key={evaluation.id} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
                <div>
                  <p className="text-sm font-semibold text-navy-900">{evaluation.filename}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Review status: {evaluation.status.replace("_", " ")}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyId === evaluation.id || evaluation.status === "approved"}
                    onClick={() => void handleReview(evaluation.id, "changes_requested")}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    Request changes
                  </button>
                  <button
                    type="button"
                    disabled={busyId === evaluation.id || evaluation.status === "approved"}
                    onClick={() => void handleReview(evaluation.id, "approved")}
                    className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
                  >
                    {busyId === evaluation.id ? "Saving…" : "Approve"}
                  </button>
                </div>
              </div>
              <DemoEvaluationView evaluation={evaluation} showResults />
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
