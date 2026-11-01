import type { VisionAvailability, VisionResult } from "@t1d/shared-contracts";
import { apiBaseUrl } from "./api";

export class VisionClientError extends Error {}
export type VisionScope = { study: string; patient: string };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function validScope(scope: VisionScope): boolean { return uuid.test(scope.study) && uuid.test(scope.patient); }
export function validateFile(file: File): void {
  if (!["image/jpeg", "image/png"].includes(file.type)) throw new VisionClientError("Choose a JPEG or PNG image.");
  if (file.size === 0 || file.size > 8388608) throw new VisionClientError("Choose a non-empty image of at most 8 MiB.");
}
function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new VisionClientError("Unexpected vision response.");
  return value as Record<string, unknown>;
}
function model(value: unknown): void {
  const m = object(value);
  if (typeof m.model_id !== "string" || !uuid.test(m.model_id) ||
      ![m.version, m.taxonomy_version, m.dataset_version].every(v => typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(v)) ||
      m.preprocessing_version !== "rgb-letterbox224-v1" || !["temperature_scaled", "uncalibrated"].includes(String(m.calibration_status))) throw new VisionClientError("Unexpected vision response.");
}
async function request(scope: VisionScope, path: string, signal: AbortSignal, file?: File): Promise<unknown> {
  if (!validScope(scope)) throw new VisionClientError("Enter valid study and patient UUIDs.");
  if (file) validateFile(file);
  const response = await fetch(`${apiBaseUrl()}/api/v1/patients/${scope.patient}/vision/${path}`, {
    method: file ? "POST" : "GET", cache: "no-store", credentials: "omit",
    headers: { "X-Study-ID": scope.study, ...(file ? { "Content-Type": file.type } : {}) },
    body: file, signal: AbortSignal.any([signal, AbortSignal.timeout(20000)]),
  });
  // Never display an untrusted server error body, file name or internal exception.
  if (response.status === 401) throw new VisionClientError("Authentication required. This prototype has no configured sign-in provider.");
  if (response.status === 404) throw new VisionClientError("This research scope is unavailable.");
  if (!response.ok) throw new VisionClientError(response.status >= 500 ? "Vision service unavailable. Check model status and retry." : "Image request rejected. Check the image format and limits.");
  return response.json();
}
export async function visionStatus(scope: VisionScope, signal: AbortSignal): Promise<VisionAvailability> {
  const v = object(await request(scope, "model", signal));
  if (v.experimental !== true || !Array.isArray(v.supported_tasks)) throw new VisionClientError("Unexpected vision response.");
  if (v.available === false && v.model === null && v.reason_code === "MODEL_UNAVAILABLE" && v.supported_tasks.length === 0) return v as VisionAvailability;
  if (v.available === true && v.reason_code === "MODEL_READY" && v.supported_tasks.length === 1 && v.supported_tasks[0] === "single_label_classification") {
    model(v.model); return v as VisionAvailability;
  }
  throw new VisionClientError("Unexpected vision response.");
}
export async function analyzeVision(scope: VisionScope, file: File, signal: AbortSignal): Promise<VisionResult> {
  const v = object(await request(scope, "analyses?task=single_label_classification", signal, file)); model(v.model);
  const quality = object(v.image_quality);
  const reasons = ["HUMAN_REVIEW_REQUIRED", "LOW_CONFIDENCE", "AMBIGUOUS_CLASS"];
  if (v.experimental !== true || v.review_required !== true || v.task !== "single_label_classification" ||
      !["review_required", "abstained"].includes(String(v.status)) || typeof v.prediction_id !== "string" || !uuid.test(v.prediction_id) ||
      typeof v.completed_at !== "string" || !Number.isFinite(Date.parse(v.completed_at)) || typeof v.processing_ms !== "number" || !Number.isFinite(v.processing_ms) || v.processing_ms < 0 ||
      !["accepted", "warning"].includes(String(quality.status)) || ![quality.width, quality.height].every(x => typeof x === "number" && Number.isInteger(x) && x >= 32 && x <= 8192) ||
      !Array.isArray(v.candidates) || v.candidates.length < 1 || v.candidates.length > 5 ||
      !Array.isArray(v.reason_codes) || v.reason_codes.length === 0 || !v.reason_codes.every(r => reasons.includes(r))) throw new VisionClientError("Unexpected vision response.");
  let previous = 1, total = 0; const identities = new Set<string>();
  for (const value of v.candidates) {
    const c = object(value);
    if (typeof c.canonical_id !== "string" || !/^food\.[a-z][a-z0-9_]*$/.test(c.canonical_id) || identities.has(c.canonical_id) ||
        typeof c.label !== "string" || c.label.length < 1 || c.label.length > 128 || /[\/\\\x00-\x1f\x7f]/.test(c.label) ||
        typeof c.score !== "number" || !Number.isFinite(c.score) || c.score < 0 || c.score > previous) throw new VisionClientError("Unexpected vision response.");
    previous = c.score; total += c.score; identities.add(c.canonical_id);
  }
  if (total > 1.000001) throw new VisionClientError("Unexpected vision response.");
  return v as VisionResult;
}

/** Inspect at most 256 KiB before browser decoding. Server decoding remains authoritative. */
export async function previewDimensions(file: File): Promise<{ width: number; height: number }> {
  validateFile(file);
  const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === "string" || reader.result === null ? reject(new VisionClientError("Image header unavailable.")) : resolve(reader.result);
    reader.onerror = reader.onabort = () => reject(new VisionClientError("Image header unavailable."));
    reader.readAsArrayBuffer(file.slice(0, 256 * 1024));
  });
  const bytes = new Uint8Array(buffer), view = new DataView(buffer);
  let width = 0, height = 0;
  if (file.type === "image/png") {
    const signature = [137, 80, 78, 71, 13, 10, 26, 10];
    if (bytes.length < 24 || !signature.every((v, i) => bytes[i] === v) ||
        ![73, 72, 68, 82].every((v, i) => bytes[i + 12] === v)) throw new VisionClientError("Invalid image header.");
    width = view.getUint32(16); height = view.getUint32(20);
  } else {
    if (bytes.length < 4 || bytes[0] !== 255 || bytes[1] !== 216) throw new VisionClientError("Invalid image header.");
    const frames = new Set([192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207]);
    let offset = 2;
    while (offset + 3 < bytes.length) {
      if (bytes[offset++] !== 255) break;
      while (bytes[offset] === 255) offset++;
      const marker = bytes[offset++];
      if (marker === 217 || marker === 218) break;
      if (marker === 1 || (marker >= 208 && marker <= 215)) continue;
      if (offset + 2 > bytes.length) break;
      const size = view.getUint16(offset);
      if (size < 2 || offset + size > bytes.length) break;
      if (frames.has(marker)) {
        if (size < 8) break;
        height = view.getUint16(offset + 3); width = view.getUint16(offset + 5); break;
      }
      offset += size;
    }
  }
  if (width < 32 || height < 32 || width > 8192 || height > 8192 || width * height > 16000000)
    throw new VisionClientError("Image dimensions must be 32–8192 per side and at most 16 million pixels; oversized or unsupported headers cannot be previewed.");
  return { width, height };
}
