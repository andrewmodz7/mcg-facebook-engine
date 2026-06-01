"use client";

import { useEffect, useState } from "react";

import { getCurrentScan, startScan, type ScanRun } from "../app/api-client";

const STAGE_LABELS: Record<string, string> = {
  scraping: "Scraping",
  filtering: "Filtering",
  scoring: "Scoring",
  done: "Done",
};

function Spinner() {
  return (
    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
  );
}

export default function RunScanButton({
  onScanComplete,
}: {
  onScanComplete: () => void;
}) {
  const [scan, setScan] = useState<ScanRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // On mount, pick up an in-flight scan so a page reload resumes the Running UI.
  useEffect(() => {
    getCurrentScan()
      .then(setScan)
      .catch(() => {});
  }, []);

  // Poll every 5s while a scan is running; stop once it finishes.
  useEffect(() => {
    if (scan?.status !== "running") return;
    const id = setInterval(async () => {
      try {
        setScan(await getCurrentScan());
      } catch {
        // transient; keep last known state and retry next tick
      }
    }, 5000);
    return () => clearInterval(id);
  }, [scan?.status]);

  async function handleStart() {
    setError(null);
    setDismissed(false);
    setStarting(true);
    try {
      await startScan();
      setScan(await getCurrentScan());
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 409) {
        // Someone else's scan is already running — show its progress.
        setScan(await getCurrentScan().catch(() => null));
      } else {
        setError(err.message);
      }
    } finally {
      setStarting(false);
    }
  }

  const isRunning = starting || scan?.status === "running";
  const justCompleted = !dismissed && scan?.status === "completed";
  const justFailed = !dismissed && scan?.status === "failed";

  // --- Running -----------------------------------------------------------
  if (isRunning) {
    const stage = scan?.stage ? STAGE_LABELS[scan.stage] ?? scan.stage : "";
    const msg = scan?.progress_message ?? "Starting…";
    return (
      <div className="flex items-center gap-2 rounded-md border border-gray-300 bg-gray-100 px-3 py-1.5 text-sm text-gray-600">
        <Spinner />
        <span className="font-medium text-gray-700">
          {stage ? `${stage}: ` : ""}
        </span>
        <span className="max-w-xs truncate">{msg}</span>
      </div>
    );
  }

  // --- Just completed ----------------------------------------------------
  if (justCompleted) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="rounded-md bg-green-50 px-3 py-1.5 font-medium text-green-700">
          Scan complete — {scan?.leads_created ?? 0} new lead
          {scan?.leads_created === 1 ? "" : "s"}
        </span>
        <button
          onClick={() => {
            onScanComplete();
            setDismissed(true);
          }}
          className="rounded-md bg-gray-900 px-3 py-1.5 font-medium text-white hover:bg-gray-700"
        >
          Refresh leads
        </button>
      </div>
    );
  }

  // --- Just failed -------------------------------------------------------
  if (justFailed) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span
          className="max-w-xs truncate rounded-md bg-red-50 px-3 py-1.5 font-medium text-red-700"
          title={scan?.error_message ?? undefined}
        >
          Scan failed
        </span>
        <button
          onClick={handleStart}
          className="rounded-md bg-gray-900 px-3 py-1.5 font-medium text-white hover:bg-gray-700"
        >
          Retry
        </button>
      </div>
    );
  }

  // --- Idle --------------------------------------------------------------
  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs text-red-600">{error}</span>}
      <button
        onClick={handleStart}
        className="rounded-md bg-gray-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-gray-700"
      >
        Run Scan
      </button>
    </div>
  );
}
