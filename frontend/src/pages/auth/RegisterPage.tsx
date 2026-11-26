import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getApiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { ErrorAlert } from "../../components/ui/Feedback";

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register(fullName, email, password);
      navigate("/login", {
        replace: true,
        state: { message: "Student account created. You can now sign in." },
      });
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Account registration failed."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="mx-auto max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
        Student account
      </p>
      <h2 className="mt-2 text-2xl font-bold text-navy-900">
        Create your account
      </h2>
      <p className="mt-2 text-sm text-slate-600">
        Student registration is open. Faculty accounts are provisioned by an administrator.
      </p>
      {error && (
        <div className="mt-4">
          <ErrorAlert message={error} />
        </div>
      )}
      <form className="mt-6 space-y-4" onSubmit={(event) => void handleSubmit(event)}>
        <label className="block text-sm font-medium text-slate-700">
          Full name
          <input
            autoComplete="name"
            required
            maxLength={120}
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none ring-indigo-500 focus:ring-2"
          />
        </label>
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
            autoComplete="new-password"
            minLength={12}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none ring-indigo-500 focus:ring-2"
          />
          <span className="mt-1 block text-xs text-slate-500">
            Use at least 12 characters.
          </span>
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-navy-800 px-4 py-3 text-sm font-semibold text-white hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Creating account…" : "Create student account"}
        </button>
      </form>
      <p className="mt-5 text-sm text-slate-600">
        Already registered?{" "}
        <Link className="font-semibold text-indigo-700 hover:underline" to="/login">
          Sign in
        </Link>
      </p>
    </section>
  );
}
