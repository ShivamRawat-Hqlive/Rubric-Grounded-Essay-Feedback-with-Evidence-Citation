import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authApi } from "../api/services";
import { setAccessToken } from "../api/client";
import type { User } from "../api/types";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  register: (fullName: string, email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const handleExpired = () => {
      setAccessToken(null);
      setUser(null);
      setIsLoading(false);
    };
    window.addEventListener("auth:expired", handleExpired);

    void authApi
      .refresh()
      .then(({ access_token }) => {
        setAccessToken(access_token);
        return authApi.currentUser();
      })
      .then((currentUser) => {
        if (active) {
          setUser(currentUser);
        }
      })
      .catch(() => {
        setAccessToken(null);
        if (active) {
          setUser(null);
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
      window.removeEventListener("auth:expired", handleExpired);
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    setAccessToken(null);
    const { access_token } = await authApi.login({ email, password });
    setAccessToken(access_token);
    try {
      const currentUser = await authApi.currentUser();
      setUser(currentUser);
      return currentUser;
    } catch (error) {
      setAccessToken(null);
      setUser(null);
      throw error;
    }
  }, []);

  const register = useCallback(
    (fullName: string, email: string, password: string) =>
      authApi.register({ full_name: fullName, email, password }),
    [],
  );

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, signIn, register, signOut }),
    [user, isLoading, signIn, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return context;
}
