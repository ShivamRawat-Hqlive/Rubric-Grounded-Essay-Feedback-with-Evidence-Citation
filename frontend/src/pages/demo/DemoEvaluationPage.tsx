import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getApiErrorMessage } from "../../api/client";
import { demoApi } from "../../api/services";
import type { DemoEvaluation } from "../../api/types";
import { DemoEvaluationView } from "../../components/demo/DemoEvaluationView";

export function DemoEvaluationPage() {
  const { essayId } = useParams<{ essayId: string }>();
  const [evaluation, setEvaluation] = useState<DemoEvaluation | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    if (!essayId) return;
    demoApi.evaluation(essayId)
      .then((result) => {
        if (active) setEvaluation(result);
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(getApiErrorMessage(
            requestError,
            "The demo evaluation could not be loaded. It may have been cleared by a backend restart.",
          ));
        }
      });
    return () => { active = false; };
  }, [essayId]);

  return (
    <section className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
            Student results
          </p>
          <h1 className="mt-2 text-3xl font-bold text-navy-900">Essay evaluation</h1>
        </div>
        <Link to="/student" className="text-sm font-semibold text-indigo-700 hover:underline">
          Submit another essay
        </Link>
      </div>
      {error && <p role="alert" className="rounded-lg bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
      {!evaluation && !error && <p role="status">Loading evaluation…</p>}
      {evaluation && (
        <DemoEvaluationView
          evaluation={evaluation}
          showResults={evaluation.status === "approved"}
        />
      )}
    </section>
  );
}
