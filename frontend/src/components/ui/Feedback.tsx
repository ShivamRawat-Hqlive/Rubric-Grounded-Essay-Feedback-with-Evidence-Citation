import type { EvaluationStatus } from "../../api/types";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="rounded-xl border border-slate-200 bg-white p-5 text-slate-600" role="status">
      {label}
    </p>
  );
}

export function ErrorAlert({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
      role="alert"
    >
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center">
      <h3 className="font-semibold text-slate-800">{title}</h3>
      {children && <div className="mt-2 text-sm text-slate-600">{children}</div>}
    </div>
  );
}

const statusLabels: Record<EvaluationStatus, string> = {
  queued: "Queued",
  running: "Evaluating",
  needs_review: "Pending faculty review",
  approved: "Approved",
  rejected: "Rejected",
  changes_requested: "Changes requested",
  failed: "Evaluation failed",
};

const statusStyles: Record<EvaluationStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  running: "bg-blue-100 text-blue-800",
  needs_review: "bg-amber-100 text-amber-900",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-rose-100 text-rose-800",
  changes_requested: "bg-orange-100 text-orange-800",
  failed: "bg-rose-100 text-rose-800",
};

export function StatusBadge({ status }: { status: EvaluationStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[status]}`}
    >
      {statusLabels[status]}
    </span>
  );
}
