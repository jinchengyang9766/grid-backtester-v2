import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth/auth-context";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Grid Backtester",
    template: "%s · Grid Backtester",
  },
  description:
    "Research and educational grid-strategy backtesting for daily price data.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        {/* One provider at the root: a single GET /api/auth/me per page load. */}
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
