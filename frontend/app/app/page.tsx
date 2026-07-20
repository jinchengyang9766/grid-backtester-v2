"use client";

/**
 * `/app` is the legacy authenticated home from before `/history` existed
 * (SPEC Section 27 places the landing at `/history`). It is kept only so old
 * links and bookmarks still work, and immediately replaces itself.
 *
 * The redirect runs inside the guard, so it never fires before the session
 * has resolved and it cannot expose anything private on the way through.
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoadingState } from "@/components/ui/loading-state";

export default function LegacyWorkspacePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/history");
  }, [router]);

  return <LoadingState fullPage label="Taking you to your backtest history…" />;
}
