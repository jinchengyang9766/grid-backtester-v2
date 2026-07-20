import { Badge } from "@/components/ui/badge";
import { statusLabel } from "@/lib/backtests/display";

/** Status is stated in words, never conveyed by colour alone. */
export function ResultStatus({ status }: { status: string }) {
  const tone =
    status === "COMPLETED" ? "success" : status === "FAILED" ? "warning" : "info";
  return <Badge tone={tone}>{statusLabel(status)}</Badge>;
}
