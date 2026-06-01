"use client";

import { useEffect, useRef, useState } from "react";

import {
  getLead,
  updateLead,
  type LeadDetail,
  type Stage,
} from "../app/api-client";
import { StagePill } from "./LeadsTable";

const STAGES: Stage[] = ["new", "messaged", "replied", "engaged", "dead"];

export default function LeadDrawer({
  leadId,
  onClose,
  onUpdated,
}: {
  leadId: string | null;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const notesTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load the lead whenever the open id changes.
  useEffect(() => {
    if (!leadId) {
      setLead(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getLead(leadId)
      .then((d) => {
        if (cancelled) return;
        setLead(d);
        setNotes(d.marcus_notes ?? "");
        setEmail(d.contact_email ?? "");
        setPhone(d.contact_phone ?? "");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [leadId]);

  // Close on Escape.
  useEffect(() => {
    if (!leadId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [leadId, onClose]);

  if (!leadId) return null;

  async function patch(fields: Parameters<typeof updateLead>[1]) {
    if (!leadId) return;
    setSaving(true);
    try {
      const updated = await updateLead(leadId, fields);
      setLead(updated);
      onUpdated();
    } finally {
      setSaving(false);
    }
  }

  function onStageChange(stage: Stage) {
    if (lead) setLead({ ...lead, stage });
    void patch({ stage });
  }

  // Debounced notes save: 800ms after the last keystroke, and again on blur.
  function onNotesChange(value: string) {
    setNotes(value);
    if (notesTimer.current) clearTimeout(notesTimer.current);
    notesTimer.current = setTimeout(() => void patch({ marcus_notes: value }), 800);
  }

  function flushNotes() {
    if (notesTimer.current) clearTimeout(notesTimer.current);
    void patch({ marcus_notes: notes });
  }

  return (
    <div
      className="fixed inset-0 z-20 flex justify-end bg-black/30"
      onClick={onClose}
    >
      <aside
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-3">
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">
              {saving ? "Saving…" : "Lead detail"}
            </span>
            {lead && <StagePill stage={lead.stage} />}
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {loading || !lead ? (
          <div className="px-6 py-6 text-sm text-gray-500">Loading…</div>
        ) : (
          <div className="flex flex-col gap-6 px-6 py-5">
            {/* Header: author + group + score */}
            <div>
              <div className="flex items-baseline justify-between">
                <h2 className="text-lg font-semibold text-gray-900">
                  {lead.author_name ?? "Unknown author"}
                </h2>
                <span className="text-sm text-gray-500">
                  Score{" "}
                  <span className="text-base font-semibold text-gray-900">
                    {lead.urgency_score}
                  </span>{" "}
                  · {lead.lead_type}
                </span>
              </div>
              <p className="text-sm text-gray-500">{lead.group_name ?? "—"}</p>
              <div className="mt-2 flex gap-3 text-sm">
                {lead.author_profile_url && (
                  <a
                    href={lead.author_profile_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    Facebook profile ↗
                  </a>
                )}
                <a
                  href={lead.post_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  Open post on Facebook ↗
                </a>
              </div>
            </div>

            {/* Angle — the headline content */}
            <div className="rounded-lg border border-gray-900/10 bg-gray-900/[0.03] p-4">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Angle — how to open the conversation
              </h3>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-900">
                {lead.angle || "—"}
              </p>
            </div>

            {/* Reasoning — secondary */}
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                Why this score
              </h3>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-600">
                {lead.reasoning || "—"}
              </p>
            </div>

            {/* Full post text */}
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
                Full post
              </h3>
              <p className="whitespace-pre-wrap rounded-md border border-gray-200 bg-gray-50 p-3 text-sm leading-relaxed text-gray-800">
                {lead.post_text}
              </p>
            </div>

            {/* Stage selector */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-400">
                Stage
              </label>
              <select
                value={lead.stage}
                onChange={(e) => onStageChange(e.target.value as Stage)}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm capitalize focus:border-gray-900 focus:outline-none"
              >
                {STAGES.map((s) => (
                  <option key={s} value={s} className="capitalize">
                    {s}
                  </option>
                ))}
              </select>
            </div>

            {/* Notes */}
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-400">
                Notes
              </label>
              <textarea
                value={notes}
                onChange={(e) => onNotesChange(e.target.value)}
                onBlur={flushNotes}
                rows={4}
                placeholder="Marcus's notes on this lead…"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
              />
            </div>

            {/* Contact fields */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">
                  Contact email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onBlur={() => patch({ contact_email: email || null })}
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-gray-900 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-400">
                  Contact phone
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  onBlur={() => patch({ contact_phone: phone || null })}
                  className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-gray-900 focus:outline-none"
                />
              </div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
