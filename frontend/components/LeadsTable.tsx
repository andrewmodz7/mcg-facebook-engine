"use client";

import { useMemo, useState } from "react";

import type { Lead, Stage } from "../app/api-client";

// Stage pill colors. Keep in sync with the drawer's stage selector.
const STAGE_STYLES: Record<Stage, string> = {
  new: "bg-gray-100 text-gray-700",
  messaged: "bg-blue-100 text-blue-700",
  replied: "bg-yellow-100 text-yellow-800",
  engaged: "bg-green-100 text-green-700",
  dead: "bg-red-100 text-red-700",
};

export function StagePill({ stage }: { stage: Stage }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
        STAGE_STYLES[stage] ?? STAGE_STYLES.new
      }`}
    >
      {stage}
    </span>
  );
}

type SortKey = "score" | "stage" | "group";

function truncate(text: string, n: number): string {
  return text.length > n ? text.slice(0, n) + "…" : text;
}

export default function LeadsTable({
  leads,
  onRowClick,
}: {
  leads: Lead[];
  onRowClick: (id: string) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("score");

  const sorted = useMemo(() => {
    const copy = [...leads];
    switch (sortKey) {
      case "stage":
        return copy.sort((a, b) => a.stage.localeCompare(b.stage));
      case "group":
        return copy.sort((a, b) =>
          (a.group_name ?? "").localeCompare(b.group_name ?? ""),
        );
      case "score":
      default:
        // Highest urgency first (matches the backend default ordering).
        return copy.sort((a, b) => b.urgency_score - a.urgency_score);
    }
  }, [leads, sortKey]);

  if (leads.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        No leads yet. Run a scan to populate the pipeline.
      </p>
    );
  }

  const sortBtn = (key: SortKey, label: string) => (
    <button
      onClick={() => setSortKey(key)}
      className={`rounded px-2 py-1 text-xs font-medium ${
        sortKey === key
          ? "bg-gray-900 text-white"
          : "bg-white text-gray-600 hover:bg-gray-100"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xs text-gray-400">Sort by</span>
        {sortBtn("score", "Score")}
        {sortBtn("stage", "Stage")}
        {sortBtn("group", "Group")}
      </div>

      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              <th className="px-4 py-2.5 w-12">Rank</th>
              <th className="px-4 py-2.5 w-16">Score</th>
              <th className="px-4 py-2.5">Author</th>
              <th className="px-4 py-2.5">Group</th>
              <th className="px-4 py-2.5">Post</th>
              <th className="px-4 py-2.5">Type</th>
              <th className="px-4 py-2.5">Stage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((lead, i) => (
              <tr
                key={lead.id}
                onClick={() => onRowClick(lead.id)}
                className="cursor-pointer hover:bg-gray-50"
              >
                <td className="px-4 py-3 text-gray-400">{i + 1}</td>
                <td className="px-4 py-3">
                  <span className="font-semibold text-gray-900">
                    {lead.urgency_score}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-900">
                  {lead.author_name ?? "—"}
                </td>
                <td className="px-4 py-3 text-gray-600">
                  {lead.group_name ?? "—"}
                </td>
                <td className="px-4 py-3 text-gray-600">
                  {truncate(lead.post_text, 120)}
                </td>
                <td className="px-4 py-3 text-gray-600">{lead.lead_type}</td>
                <td className="px-4 py-3">
                  <StagePill stage={lead.stage} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
