import Link from "next/link";
import { BackendStatus } from "@/components/backend-status";

export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 sm:px-10">
      <a href="#main" className="sr-only focus:not-sr-only focus:mt-4">Skip to content</a>
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 py-7">
        <Link href="/" aria-label="T1D AI home" className="text-lg font-bold tracking-tight">T1D<span className="ml-1 text-teal-700">AI</span></Link>
        <span className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800">Research prototype</span>
      </header>
      <main id="main" className="flex-1 py-14 sm:py-20">
        <p className="mb-4 text-xs font-semibold tracking-widest text-teal-700 uppercase">Phase 01 / Engineering foundation</p>
        <h1 className="max-w-3xl text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">A foundation for<br className="hidden sm:block" /> careful research.</h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600">T1D AI is an academic Type 1 diabetes research project. This local workspace establishes the application shell and backend connection.</p>
        <Link href="/vision" className="mt-6 inline-block text-sm font-semibold text-teal-800 underline">Open food vision research interface</Link>
        <div className="mt-10 grid gap-6 md:grid-cols-2">
          <BackendStatus />
          <section aria-labelledby="scope-title" className="rounded-2xl bg-slate-900 p-6 text-white sm:p-8">
            <p className="mb-3 text-xs font-semibold tracking-widest text-teal-300 uppercase">Current scope</p>
            <h2 id="scope-title" className="text-xl font-semibold">Infrastructure first</h2>
            <p className="mt-5 text-sm leading-6 text-slate-300">Meal analysis, metabolic memory and glucose forecasting are planned for later phases. No patient records or clinical outputs are available here.</p>
            <p className="mt-5 border-t border-slate-700 pt-5 text-sm leading-6 text-slate-300">This prototype is not a clinically validated medical device and provides no medical advice or treatment instructions.</p>
          </section>
        </div>
      </main>
      <footer className="border-t border-slate-200 py-6 text-xs leading-5 text-slate-500">T1D AI · Academic research and engineering prototype · Local development</footer>
    </div>
  );
}
