import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VisionTester } from "./vision-tester";
const model = { model_id: "33333333-3333-4333-8333-333333333333", version: "test-only", taxonomy_version: "test", dataset_version: "synthetic", preprocessing_version: "rgb-letterbox224-v1", calibration_status: "temperature_scaled" };
function pngFixture() {
  const bytes = new Uint8Array(32); bytes.set([137, 80, 78, 71, 13, 10, 26, 10]); bytes.set([73, 72, 68, 82], 12);
  const view = new DataView(bytes.buffer); view.setUint32(16, 64); view.setUint32(20, 64);
  return new File([bytes], "fixture.png", { type: "image/png" });
}
function enterScope() {
  fireEvent.change(screen.getByLabelText("Study UUID"), { target: { value: "11111111-1111-4111-8111-111111111111" } });
  fireEvent.change(screen.getByLabelText("Patient UUID"), { target: { value: "22222222-2222-4222-8222-222222222222" } });
}
beforeEach(() => { vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:synthetic-preview"), revokeObjectURL: vi.fn() })); });
afterEach(() => vi.unstubAllGlobals());
describe("ephemeral research interface", () => {
  it("shows auth error without exposing the response body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("private-error", { status: 401 })));
    render(<VisionTester />); enterScope(); fireEvent.click(screen.getByRole("button", { name: "Check model" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Authentication required");
    expect(screen.queryByText("private-error")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze image" })).toBeDisabled();
  });
  it("shows unavailable model and validates local files", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ experimental: true, available: false, model: null, supported_tasks: [], reason_code: "MODEL_UNAVAILABLE" }))));
    render(<VisionTester />); enterScope(); fireEvent.click(screen.getByRole("button", { name: "Check model" }));
    expect(await screen.findByText("No evaluated food model is available.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Food image"), { target: { files: [new File(["text"], "test.txt", { type: "text/plain" })] } });
    expect(screen.getByRole("alert")).toHaveTextContent("JPEG or PNG"); expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
  it("renders only returned test fixtures with review and revokes the local preview", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ experimental: true, available: true, model, supported_tasks: ["single_label_classification"], reason_code: "MODEL_READY" })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ experimental: true, prediction_id: "44444444-4444-4444-8444-444444444444", status: "review_required", task: "single_label_classification", model, image_quality: { status: "accepted", width: 64, height: 64, warnings: [] }, candidates: [{ canonical_id: "food.test_only", label: "Test-only fixture", score: .9 }], review_required: true, reason_codes: ["HUMAN_REVIEW_REQUIRED"], processing_ms: 1, completed_at: "2026-01-01T00:00:00Z" })));
    vi.stubGlobal("fetch", fetcher); const view = render(<VisionTester />); enterScope();
    fireEvent.click(screen.getByRole("button", { name: "Check model" })); await screen.findByText(/Research classifier available/);
    fireEvent.change(screen.getByLabelText("Food image"), { target: { files: [pngFixture()] } });
    await screen.findByAltText("Selected local food image preview");
    fireEvent.click(screen.getByRole("button", { name: "Analyze image" }));
    expect(await screen.findByText("Test-only fixture")).toBeInTheDocument(); expect(screen.getByText("Human review required")).toBeInTheDocument();
    expect(screen.getByText(/competing single-label hypotheses/)).toBeInTheDocument();
    expect(fetcher.mock.calls[1][1].body).toBeInstanceOf(File);
    view.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:synthetic-preview");
  });
  it("announces loading and keeps raw network errors out of the UI", async () => {
    let reject!: (value: Error) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((_, no) => { reject = no; })));
    render(<VisionTester />); enterScope(); fireEvent.click(screen.getByRole("button", { name: "Check model" }));
    expect(screen.getByRole("status")).toHaveTextContent("Processing");
    await act(async () => reject(new Error("private-internal-path")));
    expect(screen.getByRole("alert")).not.toHaveTextContent("private-internal-path");
  });
});
