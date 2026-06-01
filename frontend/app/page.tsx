"use client";

// Pipeline page. Owns the leads list and coordinates refreshes between the
// Run Scan button and the table. Data is fetched client-side because auth is
// HTTP Basic, managed by the browser — a server component would have no
// credentials to forward.

import { useCallback, useEffect, useState } from "react";

import LeadDrawer from "../components/LeadDrawer";
import LeadsTable from "../components/LeadsTable";
import RunScanButton from "../components/RunScanButton";
import { getLeads, type Lead } from "./api-client";

export default function Home() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openLeadId, setOpenLeadId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      setLeads(await getLeads());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <main className="min-h-screen">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <h1 className="text-base font-semibold tracking-tight text-gray-900">
          MCG Lead Engine
        </h1>
        <RunScanButton onScanComplete={reload} />
      </header>

      <div className="px-6 py-6">
        {error && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Failed to load leads: {error}
          </div>
        )}
        {loading ? (
          <p className="text-sm text-gray-500">Loading leads…</p>
        ) : (
          <LeadsTable leads={leads} onRowClick={(id) => setOpenLeadId(id)} />
        )}
      </div>

      <LeadDrawer
        leadId={openLeadId}
        onClose={() => setOpenLeadId(null)}
        onUpdated={reload}
      />
    </main>
  );
}
