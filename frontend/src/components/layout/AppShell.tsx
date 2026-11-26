import { NavLink, Outlet } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "rounded-lg px-3 py-2 text-sm font-medium transition",
    isActive
      ? "bg-white/15 text-white"
      : "text-slate-200 hover:bg-white/10 hover:text-white",
  ].join(" ");

export function AppShell() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-navy-900 text-white shadow">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-300">
              Local academic demonstration
            </p>
            <NavLink to="/" className="text-lg font-semibold sm:text-xl">
              Rubric-Grounded Essay Feedback
            </NavLink>
          </div>
          <nav className="flex flex-wrap gap-1" aria-label="Main">
            <NavLink to="/" className={linkClass} end>Overview</NavLink>
            <NavLink to="/student" className={linkClass}>Student demo</NavLink>
            <NavLink to="/faculty" className={linkClass}>Faculty demo</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-500">
        Local portfolio demo only. Evaluation scores are deterministic heuristics,
        not AI-generated or a substitute for academic assessment.
      </footer>
    </div>
  );
}
