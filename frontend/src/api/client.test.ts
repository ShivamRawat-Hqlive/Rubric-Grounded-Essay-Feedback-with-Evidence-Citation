import {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import api, { getAccessToken, getApiErrorMessage, setAccessToken } from "./client";
import type { AccessTokenResponse } from "./types";

function response<T>(
  config: InternalAxiosRequestConfig,
  data: T,
  status = 200,
): AxiosResponse<T> {
  return {
    data,
    status,
    statusText: status === 200 ? "OK" : "Unauthorized",
    headers: new AxiosHeaders(),
    config,
  };
}

function unauthorized(config: InternalAxiosRequestConfig): AxiosError {
  return new AxiosError(
    "Unauthorized",
    "ERR_BAD_REQUEST",
    config,
    undefined,
    response(config, { detail: "Not authenticated" }, 401),
  );
}

const originalAdapter = api.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = originalAdapter;
  setAccessToken(null);
  vi.restoreAllMocks();
});

test("refreshes an expired access token once and retries the protected request", async () => {
  setAccessToken("expired-access-token");
  let protectedRequests = 0;
  let refreshRequests = 0;
  const adapter: AxiosAdapter = async (config) => {
    if (config.url === "/auth/refresh") {
      refreshRequests += 1;
      const token: AccessTokenResponse = {
        access_token: "refreshed-access-token",
        token_type: "bearer",
        expires_in: 900,
      };
      return response(config, token);
    }
    protectedRequests += 1;
    if (config.headers.get("Authorization") === "Bearer expired-access-token") {
      throw unauthorized(config);
    }
    return response(config, { ok: true });
  };
  api.defaults.adapter = adapter;

  const result = await api.get<{ ok: boolean }>("/private");

  expect(result.data.ok).toBe(true);
  expect(protectedRequests).toBe(2);
  expect(refreshRequests).toBe(1);
  expect(getAccessToken()).toBe("refreshed-access-token");
  expect(result.config.headers.get("Authorization")).toBe(
    "Bearer refreshed-access-token",
  );
});

test("clears the access token and announces expiration when refresh fails", async () => {
  setAccessToken("expired-access-token");
  const expired = vi.fn();
  window.addEventListener("auth:expired", expired);
  const adapter: AxiosAdapter = async (config) => {
    throw unauthorized(config);
  };
  api.defaults.adapter = adapter;

  await expect(api.get("/private")).rejects.toBeDefined();

  expect(getAccessToken()).toBeNull();
  expect(expired).toHaveBeenCalledOnce();
  window.removeEventListener("auth:expired", expired);
});

test("maps OpenAI authentication failures to a safe actionable message", () => {
  const config = {
    headers: new AxiosHeaders(),
    url: "/essays/essay-id/evaluations",
  } as InternalAxiosRequestConfig;
  const error = new AxiosError(
    "Request failed",
    "ERR_BAD_REQUEST",
    config,
    undefined,
    response(
      config,
      {
        detail: {
          code: "OPENAI_AUTHENTICATION_ERROR",
          message: "Provider detail must not be shown",
        },
      },
      502,
    ),
  );

  expect(getApiErrorMessage(error)).toContain("OpenAI rejected its configured API key");
  expect(getApiErrorMessage(error)).not.toContain("Provider detail");
});
