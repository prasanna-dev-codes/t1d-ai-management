"use client";

import { useEffect, useState } from "react";
import { getReadiness } from "@/lib/api";

type State = "loading" | "ready" | "error";

export function BackendStatus() {
  const [state, setState] = useState<State>("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getReadiness(controller.signal).then(
      () => { if (!controller.signal.aborted) setState("ready"); },
      () => { if (!controller.signal.aborted) setState("error"); },
    );
    return () => controller.abort();
  }, [attempt]);

  const labels: Record<State, string> = {
    loading: "Checking backend connection…",
    ready: "Backend connected",
    error: "Backend unavailable",
  };
  return (
    <section aria-labelledby="connection-title" className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
      <p className="mb-3 text-xs font-semibold tracking-widest text-slate-500 uppercase">Connection</p>
      <h2 id="connection-title" className="text-xl font-semibold">Research backend</h2>
      <p role="status" aria-live="polite" className="mt-5 flex items-center gap-3 text-sm font-medium">
        <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${state === "ready" ? "bg-teal-600" : state === "error" ? "bg-amber-600" : "bg-slate-400"}`} />
        {labels[state]}
      </p>
      <p className="mt-3 max-w-lg text-sm leading-6 text-slate-600">
        {state === "error" ? "Start the local API and check its configured address, then try again." :
         "This checks the API’s readiness for its enabled capabilities. Optional database services are not connected in this phase."}
      </p>
      <button type="button" disabled={state === "loading"}
        onClick={() => { setState("loading"); setAttempt((value) => value + 1); }}
        className="mt-6 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-700 disabled:cursor-wait disabled:opacity-50">
        {state === "loading" ? "Checking…" : "Check connection"}
      </button>
    </section>
  );
}
