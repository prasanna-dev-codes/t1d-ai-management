import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "T1D AI · Research foundation",
  description: "Local engineering foundation for a research-only T1D AI prototype.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
