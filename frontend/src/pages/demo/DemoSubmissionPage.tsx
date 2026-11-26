import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { getApiErrorMessage } from "../../api/client";
import { demoApi } from "../../api/services";

export function DemoSubmissionPage() {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a PDF or TXT essay to continue.");
      return;
    }

    setError("");
    setIsSubmitting(true);
    try {
      const evaluation = await demoApi.uploadEssay(file);
      navigate(`/student/essays/${evaluation.id}`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The essay could not be processed."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
          Student demonstration
        </p>
        <h1 className="mt-2 text-3xl font-bold text-navy-900">Submit an essay</h1>
        <p className="mt-3 leading-7 text-slate-600">
          This creates a clearly labelled local demo evaluation using the built-in
          five-criterion rubric. No account, course, or paid AI API is needed.
        </p>
      </div>
      <form
        onSubmit={(event) => void handleSubmit(event)}
        className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-slate-800">
            Essay file
          </span>
          <input
            type="file"
            accept=".pdf,application/pdf,.txt,text/plain"
            aria-label="Essay file"
            onChange={(event) => {
              setError("");
              setFile(event.currentTarget.files?.[0] ?? null);
            }}
            className="block w-full rounded-lg border border-slate-300 p-3 text-sm file:mr-4 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:font-semibold file:text-indigo-800"
            aria-describedby="upload-help"
          />
          <span id="upload-help" className="mt-2 block text-xs leading-5 text-slate-500">
            PDF or UTF-8 TXT. Text-based PDFs work directly. Scanned PDFs require
            optional OCR to be enabled locally.
          </span>
        </label>
        {error && <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-lg bg-indigo-700 px-5 py-3 text-sm font-semibold text-white hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? "Extracting and evaluating…" : "Upload and evaluate"}
        </button>
      </form>
      <p className="text-xs leading-5 text-slate-500">
        Demo submissions are held in memory by the backend and disappear when it restarts.
        Use only non-sensitive sample essays.
      </p>
    </section>
  );
}
