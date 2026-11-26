import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import type { UserRole } from "../api/types";

function homeForRole(role: UserRole): string {
  if (role === "faculty") {
    return "/faculty";
  }
  if (role === "student") {
    return "/student";
  }
  return "/";
}

export function ProtectedRoute({ roles }: { roles: UserRole[] }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <p className="rounded-lg bg-white p-6 text-slate-600" role="status">
        Restoring your secure session…
      </p>
    );
  }
  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location }}
      />
    );
  }
  if (!roles.includes(user.role)) {
    return <Navigate to={homeForRole(user.role)} replace />;
  }
  return <Outlet />;
}

export function RoleLanding() {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <p className="rounded-lg bg-white p-6 text-slate-600" role="status">
        Restoring your secure session…
      </p>
    );
  }
  return <Navigate to={user ? homeForRole(user.role) : "/login"} replace />;
}
