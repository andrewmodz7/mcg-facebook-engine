// Typed fetch wrapper for the MCG Lead Engine backend.
//
// Requests use relative URLs (/api/...) and are proxied to the backend by the
// Next.js rewrite (see next.config.mjs). That keeps the browser on a single
// origin, so HTTP Basic Auth is handled natively by the browser and there's no
// CORS surface at all.

export type Stage = "new" | "messaged" | "replied" | "engaged" | "dead";

// A lead row joined with its raw_post + group context. The list and detail
// endpoints return the same shape, so LeadDetail is an alias.
export interface Lead {
  id: string;
  urgency_score: number;
  lead_type: string;
  recommended_action: string;
  angle: string | null;
  reasoning: string | null;
  stage: Stage;
  marcus_notes: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  created_at: string | null;
  updated_at: string | null;
  raw_post_id: string;
  post_text: string;
  post_url: string;
  author_name: string | null;
  author_profile_url: string | null;
  group_name: string | null;
  posted_at: string | null;
  reactions_count: number;
  comments_count: number;
}

export type LeadDetail = Lead;

export interface LeadUpdate {
  stage: Stage;
  marcus_notes: string | null;
  contact_email: string | null;
  contact_phone: string | null;
}

export type ScanStatus = "running" | "completed" | "failed";
export type ScanStage = "scraping" | "filtering" | "scoring" | "done" | null;

export interface ScanRun {
  id: string;
  triggered_by: string;
  status: ScanStatus;
  stage: ScanStage;
  progress_message: string | null;
  groups_total: number;
  groups_completed: number;
  posts_scraped: number;
  posts_filtered: number;
  posts_scored: number;
  leads_created: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    const err = new Error(detail) as Error & { status: number };
    err.status = res.status;
    throw err;
  }

  return res.json() as Promise<T>;
}

export function getLeads(): Promise<Lead[]> {
  return request<Lead[]>("/api/leads");
}

export function getLead(id: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/api/leads/${id}`);
}

export function updateLead(
  id: string,
  patch: Partial<LeadUpdate>,
): Promise<LeadDetail> {
  return request<LeadDetail>(`/api/leads/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function startScan(): Promise<{ scan_run_id: string }> {
  return request<{ scan_run_id: string }>("/api/scans", { method: "POST" });
}

// Returns null when no scan has ever run (backend 404).
export async function getCurrentScan(): Promise<ScanRun | null> {
  try {
    return await request<ScanRun>("/api/scans/current");
  } catch (e) {
    if ((e as { status?: number }).status === 404) return null;
    throw e;
  }
}
