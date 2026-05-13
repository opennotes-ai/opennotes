import { createEffect } from "solid-js";
import { notify } from "~/lib/notifications";

export const TERMINAL_JOB_STATUSES = new Set(["done", "partial", "failed"]);

export function titleFor(status: string): string {
  if (status === "done") return "Vibecheck ready";
  if (status === "partial") return "Vibecheck partially ready";
  return "Vibecheck failed";
}

export function bodyFor(status: string): string {
  if (status === "done") return "Your analysis is complete.";
  if (status === "partial") return "Some sections finished, others may be missing.";
  return "We couldn't complete the analysis.";
}

export interface NotifyEffectParams {
  jobStatus: () => string | null;
  jobId: () => string | null;
  notifyEnabled: () => boolean;
}

export function buildNotifyEffect(params: NotifyEffectParams): void {
  let firedForJobId: string | null = null;

  createEffect(() => {
    const status = params.jobStatus();
    const id = params.jobId();
    if (!id || !params.notifyEnabled()) return;
    if (!TERMINAL_JOB_STATUSES.has(status ?? "")) return;
    if (firedForJobId === id) return;
    firedForJobId = id;
    notify(titleFor(status!), { body: bodyFor(status!) });
  });
}
