"use client";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import type { VisionAvailability, VisionResult } from "@t1d/shared-contracts";
import { VisionClientError, analyzeVision, validScope, validateFile, previewDimensions, visionStatus } from "@/lib/vision";

export function VisionTester() {
  const [scope, setScope] = useState({ study: "", patient: "" });
  const [upload, setUpload] = useState<{ file: File; preview: string } | null>(null);
  const [availability, setAvailability] = useState<VisionAvailability | null>(null);
  const [result, setResult] = useState<VisionResult | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const selection = useRef(0);
  const controller = useRef<AbortController | null>(null), input = useRef<HTMLInputElement>(null);
  useEffect(() => () => { if (upload) URL.revokeObjectURL(upload.preview); }, [upload]);
  useEffect(() => () => { selection.current++; controller.current?.abort(); }, []);
  function changeScope(key: "study" | "patient", value: string) {
    setScope({ ...scope, [key]: value }); setAvailability(null); setResult(null); setUpload(null); setError("");
    if (input.current) input.current.value = "";
  }
  async function choose(file?: File) {
    const revision = ++selection.current;
    setUpload(null); setResult(null); setError("");
    if (!file) return;
    try {
      validateFile(file); setBusy(true); await previewDimensions(file);
      if (revision === selection.current) setUpload({ file, preview: URL.createObjectURL(file) });
    } catch (failure) {
      if (revision === selection.current) { setError(failure instanceof VisionClientError ? failure.message : "Image header unavailable."); if (input.current) input.current.value = ""; }
    } finally { if (revision === selection.current) setBusy(false); }
  }
  async function run(kind: "status" | "analysis") {
    const active = new AbortController(); controller.current?.abort(); controller.current = active;
    setBusy(true); setError(""); setResult(null);
    try {
      if (kind === "status") { const value = await visionStatus(scope, active.signal); if (!active.signal.aborted) setAvailability(value); }
      else if (upload) { const value = await analyzeVision(scope, upload.file, active.signal); if (!active.signal.aborted) setResult(value); }
    } catch (failure) {
      if (!active.signal.aborted) { setAvailability(null); setError(failure instanceof VisionClientError ? failure.message : "Vision request failed. Check the service and retry."); }
    } finally { if (!active.signal.aborted) setBusy(false); }
  }
  const field = "mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-60";
  return <section aria-label="Ephemeral vision test" className="mt-8 grid gap-6 md:grid-cols-2">
    <div className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-lg font-semibold">Research scope</h2>
      <p className="mt-3 text-sm leading-6 text-slate-600">Use synthetic or explicitly approved food-only images. Do not upload patient photographs. Authentication, a current grant and consent are required.</p>
      <label className="mt-5 block text-sm font-medium">Study UUID<input className={field} autoComplete="off" value={scope.study} onChange={e => changeScope("study", e.target.value)} disabled={busy} /></label>
      <label className="mt-4 block text-sm font-medium">Patient UUID<input className={field} autoComplete="off" value={scope.patient} onChange={e => changeScope("patient", e.target.value)} disabled={busy} /></label>
      <button className="mt-5 rounded-lg border border-teal-800 px-4 py-2 text-sm font-semibold text-teal-800 disabled:opacity-40" disabled={busy || !validScope(scope)} onClick={() => void run("status")}>Check model</button>
      <label className="mt-6 block text-sm font-medium">Food image<input ref={input} className={field} type="file" accept="image/jpeg,image/png" disabled={busy} onChange={e => void choose(e.target.files?.[0])} /></label>
      <p className="mt-2 text-xs leading-5 text-slate-500">JPEG/PNG · 8 MiB maximum · 16 million decoded pixels · single food classification only. Images are not saved by this application.</p>
      <button className="mt-5 rounded-lg bg-teal-800 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40" disabled={busy || !upload || !availability?.available || !validScope(scope)} onClick={() => void run("analysis")}>Analyze image</button>
      <div aria-live="polite" className="mt-5 text-sm leading-6">
        {busy && <p role="status">Processing research request…</p>}
        {!busy && availability?.available === false && <p role="status">No evaluated food model is available.</p>}
        {!busy && availability?.available && <p role="status">Research classifier available · {availability.model?.version}</p>}
        {error && <p role="alert" className="text-red-800">{error}</p>}
      </div>
    </div>
    <div className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-lg font-semibold">Preview and review</h2>
      {upload ? <Image unoptimized src={upload.preview} alt="Selected local food image preview" width={400} height={300} className="mt-5 max-h-64 w-full rounded-lg bg-slate-50 object-contain" /> : <p className="mt-5 text-sm text-slate-500">Select an approved image for a temporary local preview.</p>}
      {result && <div className="mt-6" aria-label="Research classification result">
        <p className="font-semibold text-amber-900">{result.status === "abstained" ? "Classifier abstained — review required" : "Human review required"}</p>
        <p className="mt-2 text-sm leading-6 text-slate-600">These are competing single-label hypotheses, not separate meal components. Scores do not establish clinical reliability.</p>
        <ol className="mt-4 space-y-2">{result.candidates.map(c => <li key={c.canonical_id} className="flex justify-between gap-4 rounded-lg bg-slate-50 px-3 py-2 text-sm"><span>{c.label}</span><span>{(100 * c.score).toFixed(1)}%</span></li>)}</ol>
        <p className="mt-4 text-xs leading-5 text-slate-500">Model {result.model.version} · taxonomy {result.model.taxonomy_version} · calibration {result.model.calibration_status} · {result.image_quality.status === "warning" ? "Image conversion warning" : "Image decoded; food quality unassessed"}</p>
      </div>}
    </div>
  </section>;
}
