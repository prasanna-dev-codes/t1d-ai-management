import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzeVision, validateFile, visionStatus, previewDimensions } from "./vision";
const scope = { study: "11111111-1111-4111-8111-111111111111", patient: "22222222-2222-4222-8222-222222222222" };
afterEach(() => vi.unstubAllGlobals());
describe("vision transport", () => {
  it("uses scoped no-store requests and honest unavailable metadata", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ experimental: true, available: false, model: null, supported_tasks: [], reason_code: "MODEL_UNAVAILABLE" })));
    vi.stubGlobal("fetch", fetcher);
    expect((await visionStatus(scope, new AbortController().signal)).available).toBe(false);
    expect(fetcher.mock.calls[0][0]).toContain(`/patients/${scope.patient}/vision/model`);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ credentials: "omit", cache: "no-store", headers: { "X-Study-ID": scope.study } });
  });
  it.each([401, 404, 503, 422])("redacts server error payload for %s", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private-path-and-image-content", { status })));
    await expect(visionStatus(scope, new AbortController().signal)).rejects.not.toThrow("private-path-and-image-content");
  });
  it("fails closed on fabricated availability and invalid food output", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ experimental: true, available: true, model: null, supported_tasks: [], reason_code: "MODEL_READY" }))));
    await expect(visionStatus(scope, new AbortController().signal)).rejects.toThrow("Unexpected vision response");
    await expect(analyzeVision(scope, new File(["synthetic"], "fixture.png", { type: "image/png" }), new AbortController().signal)).rejects.toThrow();
  });
  it("rejects files and invalid scope before fetching", async () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    expect(() => validateFile(new File(["text"], "bad.txt", { type: "text/plain" }))).toThrow();
    expect(() => validateFile(new File([], "empty.png", { type: "image/png" }))).toThrow();
    await expect(visionStatus({ study: "invalid", patient: scope.patient }, new AbortController().signal)).rejects.toThrow("valid study");
    expect(fetcher).not.toHaveBeenCalled();
  });
});

function pngHeader(width: number, height: number): File {
  const bytes = new Uint8Array(32); bytes.set([137, 80, 78, 71, 13, 10, 26, 10]); bytes.set([73, 72, 68, 82], 12);
  const view = new DataView(bytes.buffer); view.setUint32(16, width); view.setUint32(20, height);
  return new File([bytes], "fixture.png", { type: "image/png" });
}
describe("preview before decoding", () => {
  it("reads PNG dimensions without creating a preview or uploading", async () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    await expect(previewDimensions(pngHeader(64, 32))).resolves.toEqual({ width: 64, height: 32 });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([[31, 32], [5000, 5000], [9000, 64], [0, 32]])("rejects unsupported dimensions %s × %s", async (width, height) => {
    await expect(previewDimensions(pngHeader(width, height))).rejects.toThrow("Image dimensions");
  });
  it("rejects malformed or MIME-mismatched headers", async () => {
    await expect(previewDimensions(new File(["invalid"], "fixture.png", { type: "image/png" }))).rejects.toThrow("Invalid image header");
    await expect(previewDimensions(new File(["invalid"], "fixture.jpg", { type: "image/jpeg" }))).rejects.toThrow("Invalid image header");
  });
  it("reads a bounded JPEG frame header", async () => {
    const bytes = new Uint8Array([255, 216, 255, 192, 0, 11, 8, 0, 32, 0, 64, 1, 1, 17, 0]);
    await expect(previewDimensions(new File([bytes], "fixture.jpg", { type: "image/jpeg" }))).resolves.toEqual({ width: 64, height: 32 });
  });
});
