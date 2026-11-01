import Link from "next/link";
import { VisionTester } from "@/components/vision-tester";
export default function VisionPage() {
  return <main className="mx-auto min-h-screen max-w-5xl px-6 py-10 sm:px-10">
    <Link href="/" className="text-sm text-teal-800 underline">T1D AI home</Link>
    <p className="mt-10 text-xs font-semibold tracking-widest text-teal-700 uppercase">Phase 03 · Research interface</p>
    <h1 className="mt-3 text-3xl font-semibold tracking-tight">Food vision testing</h1>
    <p className="mt-4 max-w-3xl leading-7 text-slate-600">Experimental classification with human review. No evaluated model is currently supplied. Detection and segmentation are unavailable.</p>
    <VisionTester />
    <p className="mt-10 border-t border-slate-200 pt-6 text-sm text-slate-600">This prototype is not a clinically validated medical device. It provides no medical advice, nutrient estimates or treatment instructions.</p>
  </main>;
}
