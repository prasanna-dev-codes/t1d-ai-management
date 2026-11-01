import type { ReadinessResponse } from "@t1d/shared-contracts";

export function apiBaseUrl(raw = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001"): string {
  const url = new URL(raw);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
      url.pathname !== "/" || url.search || url.hash ||
      !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) {
    throw new Error("A local API origin without credentials is required");
  }
  return url.origin;
}

export async function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const timeout = AbortSignal.timeout(5000);
  const response = await fetch(`${apiBaseUrl()}/api/v1/health/ready`, {
    cache: "no-store", credentials: "omit",
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  if (!response.ok) throw new Error("Backend unavailable");
  const body: unknown = await response.json();
  if (typeof body !== "object" || body === null || !("status" in body) ||
      body.status !== "ready" || Object.keys(body).length !== 1) {
    throw new Error("Unexpected health response");
  }
  return { status: body.status };
}
