import { useCallback, useRef } from "react";
import { toast } from "sonner";
import { useAuth } from "@/lib/stores/auth-store";
import { apiFetch } from "@/lib/api";

interface JobResult {
  status: string;
  progress?: number;
  total?: number;
  progress_json?: {
    processed: number;
    total: number;
    current: string;
  } | null;
  result?: Record<string, unknown>;
  error_message?: string;
}

interface UseJobPollingOptions {
  maxAttempts?: number;
  intervalMs?: number;
  onSuccess?: (result: Record<string, unknown>) => string;
  onProgress?: (
    progress: number,
    total: number,
    details: JobResult["progress_json"],
  ) => string | void;
}

export function useJobPolling(options: UseJobPollingOptions = {}) {
  const { token } = useAuth();
  const { maxAttempts = 60, intervalMs = 2000, onSuccess, onProgress } = options;
  const abortedRef = useRef(false);

  const poll = useCallback(
    async (jobId: string): Promise<Record<string, unknown> | null> => {
      abortedRef.current = false;
      for (let i = 0; i < maxAttempts; i++) {
        if (abortedRef.current) return null;
        await new Promise((r) => setTimeout(r, intervalMs));
        try {
          const job = await apiFetch<JobResult>(`/papers/search/jobs/${jobId}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (job.status === "completed") {
            const msg = onSuccess?.(job.result ?? {});
            toast.success(msg ?? "Done");
            return job.result ?? {};
          }
          if (job.status === "failed") {
            toast.error(job.error_message || "Job failed");
            return null;
          }
          if (job.progress_json?.total && job.progress_json.processed >= 0) {
            const msg = onProgress?.(
              job.progress_json.processed,
              job.progress_json.total,
              job.progress_json,
            );
            if (msg) {
              toast.info(msg, { duration: 1000 });
            }
            continue;
          }
          if (job.progress && job.total && job.progress > 0) {
            const msg = onProgress?.(job.progress, job.total, null);
            toast.info(msg ?? `Processing ${job.progress}/${job.total}...`, {
              duration: 1000,
            });
          }
        } catch {
          // Ignore polling errors, keep trying
        }
      }
      toast.warning("Job is still running. Check back later.");
      return null;
    },
    [token, maxAttempts, intervalMs, onSuccess, onProgress],
  );

  const abort = useCallback(() => {
    abortedRef.current = true;
  }, []);

  return { poll, abort };
}
