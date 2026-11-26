import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { getApiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { ErrorAlert } from "../../components/ui/Feedback";

interface LoginLocationState {
  from?: { pathname?: string };
  message?: string;
}

function homeForRole(role: string): string {
  if (role === "faculty") {
    return "/faculty";
  }
  if (role === "student") {
    return "/student";
  }
  return "/";
}

export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as LoginLocationState | null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const user = await signIn(email, password);
      navigate(state?.from?.pathname ?? homeForRole(user.role), {
        replace: true,
      });
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Sign in failed."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="mx-auto max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
        Welcome back
      </p>
      <h2 className="mt-2 text-2xl font-bold text-navy-900">Sign in</h2>
      <p className="mt-2 text-sm text-slate-600">
        Use your student or faculty account to continue.
      </p>
      {state?.message && (
        <p className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800" role="status">
          {state.message}
        </p>
      )}
      {error && (
        <div className="mt-4">
          <ErrorAlert message={error} />
        </div>
      )}
      <form className="mt-6 space-y-4" onSubmit={(event) => void handleSubmit(event)}>
        <label className="block text-sm font-medium text-slate-700">
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none ring-indigo-500 focus:ring-2"
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none ring-indigo-500 focus:ring-2"
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-navy-800 px-4 py-3 text-sm font-semibold text-white hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-5 text-sm text-slate-600">
        New student?{" "}
        <Link className="font-semibold text-indigo-700 hover:underline" to="/register">
          Create an account
        </Link>
      </p>
    </section>
  );
}
