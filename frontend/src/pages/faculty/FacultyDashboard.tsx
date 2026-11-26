import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { appApi } from "../../api/services";
import { getApiErrorMessage } from "../../api/client";
import type { Course, ReviewQueueItem } from "../../api/types";
import { EmptyState, ErrorAlert, LoadingState, StatusBadge } from "../../components/ui/Feedback";
import { FacultyRubricManagement } from "./FacultyRubricManagement";

export function FacultyDashboard() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadQueue = useCallback(async () => {
    setError("");
    try {
      const [queueItems, courseList] = await Promise.all([
        appApi.reviewQueue(),
        appApi.courses(),
      ]);
      setQueue(queueItems);
      setCourses(courseList);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to load the review queue."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  if (loading) {
    return <LoadingState label="Loading your course review queue…" />;
  }

  const courseById = new Map(courses.map((course) => [course.id, course]));
  const courseCounts = new Map<string, number>();
  for (const item of queue) {
    courseCounts.set(item.course_id, (courseCounts.get(item.course_id) ?? 0) + 1);
  }

  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
            Faculty workspace
          </p>
          <h2 className="mt-1 text-3xl font-bold text-navy-900">Review queue</h2>
          <p className="mt-2 text-sm text-slate-600">
            Review evaluations for your courses. Your corrections remain separate
            from the original AI-generated results.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-5 py-3">
          <p className="text-xs text-slate-500">Awaiting action</p>
          <p className="text-2xl font-bold text-navy-900">{queue.length}</p>
        </div>
      </header>

      {error && (
        <div className="space-y-3">
          <ErrorAlert message={error} />
          <button
            type="button"
            onClick={() => void loadQueue()}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-white"
          >
            Try again
          </button>
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {courses.map((course) => (
          <article
            key={course.id}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <p className="text-xs font-bold tracking-wide text-indigo-700">
              {course.code}
            </p>
            <h3 className="mt-1 font-semibold text-navy-900">{course.name}</h3>
            <p className="mt-2 text-sm text-slate-500">
              {courseCounts.get(course.id) ?? 0} pending review
            </p>
          </article>
        ))}
      </section>

      <FacultyRubricManagement courses={courses} />

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-navy-900">Evaluations to review</h3>
            <p className="mt-1 text-sm text-slate-500">
              Pending review and changes-requested evaluations for courses assigned to you.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadQueue()}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Refresh queue
          </button>
        </div>
        {queue.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="Your queue is clear">
              New evaluations for your courses will appear here.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-4 divide-y divide-slate-100">
            {queue.map((item) => {
              const course = courseById.get(item.course_id);
              return (
                <article
                  key={item.evaluation_id}
                  className="flex flex-wrap items-center justify-between gap-4 py-4 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={item.status} />
                      {item.evaluation_mode === "mock" && (
                        <span className="rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-bold text-fuchsia-900">
                          MOCK — NOT AI-GENERATED
                        </span>
                      )}
                    </div>
                    <p className="font-medium text-slate-900">
                      {course ? `${course.code} — ${course.name}` : "Assigned course"}
                    </p>
                    <p className="text-xs text-slate-500">
                      Started {new Date(item.started_at).toLocaleString()} · Student
                      record {item.student_id.slice(0, 8)}
                    </p>
                  </div>
                  <Link
                    to={`/faculty/reviews/${item.evaluation_id}`}
                    className="rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-navy-900"
                  >
                    Open review
                  </Link>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
