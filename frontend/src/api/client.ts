import axios, {
  type AxiosError,
  type InternalAxiosRequestConfig,
} from "axios";
import type { AccessTokenResponse } from "./types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
  withCredentials: true,
  headers: { Accept: "application/json" },
});

type RetriableConfig = InternalAxiosRequestConfig & {
  _authRetry?: boolean;
};

let accessToken: string | null = null;
let refreshRequest: Promise<string | null> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

function isAuthEndpoint(url = ""): boolean {
  const path = url.split("?")[0];
  return [
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
    "/auth/logout",
  ].includes(path);
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshRequest) {
    refreshRequest = api
      .post<AccessTokenResponse>("/auth/refresh")
      .then(({ data }) => {
        setAccessToken(data.access_token);
        return data.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshRequest = null;
      });
  }
  return refreshRequest;
}

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  } else {
    config.headers.delete("Authorization");
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined;
    if (
      error.response?.status !== 401 ||
      !config ||
      isAuthEndpoint(config.url)
    ) {
      return Promise.reject(error);
    }

    if (config._authRetry) {
      setAccessToken(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("auth:expired"));
      }
      return Promise.reject(error);
    }

    config._authRetry = true;
    const refreshedToken = await refreshAccessToken();
    if (!refreshedToken) {
      setAccessToken(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("auth:expired"));
      }
      return Promise.reject(error);
    }

    config.headers.set("Authorization", `Bearer ${refreshedToken}`);
    return api.request(config);
  },
);

export function getApiErrorMessage(
  error: unknown,
  fallback = "The request could not be completed.",
): string {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail;
    if (
      typeof detail === "object" &&
      detail !== null &&
      "code" in detail &&
      typeof detail.code === "string"
    ) {
      const providerMessages: Record<string, string> = {
        OPENAI_AUTHENTICATION_ERROR:
          "OpenAI rejected its configured API key. An administrator should check that the key is active and belongs to the intended project.",
        OPENAI_QUOTA_EXCEEDED:
          "The OpenAI account or project has no available API quota. An administrator should check billing and usage limits.",
        OPENAI_MODEL_NOT_FOUND:
          "The configured OpenAI model is unavailable to this project. An administrator should check the model setting and access.",
        OPENAI_PERMISSION_ERROR:
          "The configured OpenAI key lacks permission for this request. An administrator should check project access.",
        OPENAI_INVALID_REQUEST:
          "OpenAI rejected the evaluation request configuration. An administrator should check model and request compatibility.",
        OPENAI_RATE_LIMIT:
          "OpenAI rate-limited the evaluation. Wait briefly, then try again.",
        OPENAI_CONNECTION_ERROR:
          "The backend could not connect to OpenAI. Check network access and try again.",
        OPENAI_SERVER_ERROR:
          "OpenAI returned a temporary server error. Try the evaluation again shortly.",
        OPENAI_MALFORMED_RESPONSE:
          "OpenAI returned a malformed response. Try again; contact an administrator if it continues.",
        OPENAI_EMPTY_RESPONSE:
          "OpenAI returned an empty response. Try the evaluation again.",
        OPENAI_REFUSAL:
          "OpenAI declined the evaluation request. Contact an administrator if this persists.",
        OPENAI_PROVIDER_ERROR:
          "OpenAI could not complete the request. An administrator can check backend diagnostics.",
        LLM_TIMEOUT:
          "The OpenAI request timed out. Try again shortly.",
        INVALID_PROVIDER_OUTPUT:
          "The model did not return valid structured evaluation data. Try again; contact an administrator if it continues.",
      };
      const message = providerMessages[detail.code];
      if (message) {
        return message;
      }
    }
    if (typeof detail === "string") {
      return detail;
    }
    if (
      typeof detail === "object" &&
      detail !== null &&
      "message" in detail &&
      typeof detail.message === "string"
    ) {
      return detail.message;
    }
    if (error.message) {
      return error.message;
    }
  }
  return fallback;
}

export default api;
