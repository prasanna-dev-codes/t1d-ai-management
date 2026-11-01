import { afterEach, expect, it, vi } from "vitest";
import { apiBaseUrl, getReadiness } from "./api";

afterEach(() => vi.unstubAllGlobals());

it.each(["https://user:pass@localhost:8001", "https://public.example", "http://localhost:8001/path", "ftp://localhost:8001", "http://localhost:8001?secret=a"])("rejects unsafe configured API origin %s", (url) => {
  expect(() => apiBaseUrl(url)).toThrow();
});
it("accepts configured loopback ports", () => {
  expect(apiBaseUrl("http://localhost:8002")).toBe("http://localhost:8002");
});
it.each([{ status: "ready", unexpected: "data" }, null, { status: "alive" }])("rejects incompatible health payload %j", async (body) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
  await expect(getReadiness()).rejects.toThrow("Unexpected health response");
});
