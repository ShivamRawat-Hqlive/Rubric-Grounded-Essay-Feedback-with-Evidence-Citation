import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { appApi, type EvaluationHistoryOptions } from "../../api/services";
import { getApiErrorMessage } from "../../api/client";
import type { Course, Essay, Evaluation } from "../../api/types";
import { EmptyState, ErrorAlert, LoadingState, StatusBadge } from "../../components/ui/Feedback";

export function StudentDashboard() {
  const navigate = useNavigate();
  const [courses, setCourses] = useState<Course[]>([]);
  const [availableCourses, setAvailableCourses] = useState<Course[]>([]);
  const [essays, setEssays] = useState<Essay[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [selectedCourse, setSelectedCourse] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [enrollingCourseId, setEnrollingCourseId] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadDashboard = useCallback(async () => {
    setError("");
    try {
      const [courseList, availableCourseList, essayList, evaluationList] = await Promise.all([
        appApi.courses(),
        appApi.availableCourses(),
        appApi.essays(),
        appApi.evaluations({ limit: 100 } satisfies EvaluationHistoryOptions),
      ]);
      setCourses(courseList);
      setAvailableCourses(availableCourseList);
      setEssays(essayList);
      setEvaluations(evaluationList);
      setSelectedCourse((current) =>
        courseList.some((course) => course.id === current)
          ? current
          : courseList[0]?.id ?? "",
      );
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load your dashboard."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (!file || !selectedCourse) {
      setError("Choose an enrolled course and a PDF, DOCX, or TXT file.");
      return;
    }
    setUploading(true);
    try {
      const essay = await appApi.uploadEssay(file, selectedCourse);
      setSuccess("Essay uploaded and processed.");
      setFile(null);
      await loadDashboard();
      navigate(`/student/essays/${essay.id}`);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "The essay could not be uploaded."));
    } finally {
      setUploading(false);
    }
  }

  async function handleEnroll(course: Course) {
    setError("");
    setSuccess("");
    setEnrollingCourseId(course.id);
    try {
      await appApi.enrollInCourse(course.id);
      setSuccess(`You are now enrolled in ${course.name}.`);
      await loadDashboard();
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to enroll in this course."));
    } finally {
      setEnrollingCourseId("");
    }
  }

  if (loading) {
    return <LoadingState label="Loading your courses and submissions…" />;
  }

  const courseById = new Map(courses.map((course) => [course.id, course]));
  const evaluationsByEssay = new Map<string, Evaluation[]>();
  for (const evaluation of evaluations) {
    const essayEvaluations = evaluationsByEssay.get(evaluation.essay_id) ?? [];
    essayEvaluations.push(evaluation);
    evaluationsByEssay.set(evaluation.essay_id, essayEvaluations);
  }

  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
            Student workspace
          </p>
          <h2 className="mt-1 text-3xl font-bold text-navy-900">Your submissions</h2>
          <p className="mt-2 text-sm text-slate-600">
            Upload work to an enrolled course and follow it through faculty review.
          </p>
        </div>
        <div className="flex gap-3">
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <p className="text-xs text-slate-500">Courses</p>
            <p className="text-xl font-bold text-navy-900">{courses.length}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <p className="text-xs text-slate-500">Essays</p>
            <p className="text-xl font-bold text-navy-900">{essays.length}</p>
          </div>
        </div>
      </header>

      {error && <ErrorAlert message={error} />}
      {success && (
        <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800" role="status">
          {success}
        </p>
      )}

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(300px,0.7fr)]">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-navy-900">Essay submissions</h3>
              <p className="mt-1 text-sm text-slate-500">
                Open a submission to choose a published rubric or review available results.
              </p>
            </div>
          </div>
          {essays.length === 0 ? (
            <div className="mt-4">
              <EmptyState title="No essays submitted yet">
                Upload your first essay using the form.
              </EmptyState>
            </div>
          ) : (
            <div className="mt-4 divide-y divide-slate-100">
              {essays.map((essay) => {
                const latestEvaluation = evaluationsByEssay
                  .get(essay.id)
                  ?.sort(
                    (left, right) =>
                      new Date(right.started_at).getTime() -
                      new Date(left.started_at).getTime(),
                  )[0];
                return (
                  <article
                    key={essay.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-slate-900">
                        {essay.original_filename}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {courseById.get(essay.course_id ?? "")?.name ?? "No course"} ·{" "}
                        {new Date(essay.created_at).toLocaleDateString()} ·{" "}
                        {essay.parse_status}
                      </p>
                      {latestEvaluation && (
                        <div className="mt-2">
                          <StatusBadge status={latestEvaluation.status} />
                        </div>
                      )}
                    </div>
                    <Link
                      to={`/student/essays/${essay.id}`}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-navy-800 hover:bg-slate-50"
                    >
                      View details
                    </Link>
                  </article>
                );
              })}
            </div>
          )}
        </div>

        <aside className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-lg font-semibold text-navy-900">Upload an essay</h3>
          <p className="mt-1 text-sm text-slate-500">
            Accepted formats: PDF, DOCX, and plain-text TXT.
            {" "}Scanned PDFs use OCR when it is enabled in the local backend configuration.
          </p>
          <form className="mt-5 space-y-4" onSubmit={(event) => void handleUpload(event)}>
            <label className="block text-sm font-medium text-slate-700">
              Enrolled course
              <select
                required
                value={selectedCourse}
                onChange={(event) => setSelectedCourse(event.target.value)}
                disabled={courses.length === 0}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
              >
                <option value="">Select a course</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.code} — {course.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Essay file
              <input
                type="file"
                accept=".pdf,.docx,.txt,application/pdf,text/plain"
                required
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="mt-1 block w-full rounded-lg border border-slate-300 p-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:font-semibold file:text-indigo-800"
              />
            </label>
            <button
              type="submit"
              disabled={uploading || courses.length === 0}
              className="w-full rounded-lg bg-navy-800 px-4 py-3 text-sm font-semibold text-white hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {uploading ? "Uploading and processing…" : "Upload essay"}
            </button>
            {courses.length === 0 && (
              <p className="text-sm text-amber-800">
                You need to be enrolled in a course before submitting an essay.
              </p>
            )}
          </form>
        </aside>
      </section>

      <section>
        <h3 className="mb-3 text-lg font-semibold text-navy-900">Enrolled courses</h3>
        {courses.length === 0 ? (
          <EmptyState title="No course enrollments">
            Contact your faculty member to be enrolled in a course.
          </EmptyState>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {courses.map((course) => (
              <article
                key={course.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <p className="text-xs font-bold tracking-wide text-indigo-700">
                  {course.code}
                </p>
                <h4 className="mt-1 font-semibold text-navy-900">{course.name}</h4>
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-3 text-lg font-semibold text-navy-900">Available Courses</h3>
        {availableCourses.length === 0 ? (
          <EmptyState title="No available courses">
            Check back later for courses you can join.
          </EmptyState>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {availableCourses.map((course) => (
              <article
                key={course.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <p className="text-xs font-bold tracking-wide text-indigo-700">
                  {course.code}
                </p>
                <h4 className="mt-1 font-semibold text-navy-900">{course.name}</h4>
                {course.description && (
                  <p className="mt-2 text-sm text-slate-600">{course.description}</p>
                )}
                {course.faculty_name && (
                  <p className="mt-2 text-sm text-slate-500">
                    Faculty: {course.faculty_name}
                  </p>
                )}
                <button
                  type="button"
                  disabled={enrollingCourseId !== ""}
                  onClick={() => void handleEnroll(course)}
                  className="mt-4 rounded-lg bg-navy-800 px-4 py-2 text-sm font-semibold text-white hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {enrollingCourseId === course.id ? "Enrolling…" : "Enroll"}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
