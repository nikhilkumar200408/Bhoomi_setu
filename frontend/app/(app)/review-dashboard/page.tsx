"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Archive, CheckCircle2, Cloud, CloudOff, Download, FileText, RefreshCw, ShieldAlert } from "lucide-react";
import { api, ApiError, downloadAuthedPost } from "@/lib/api";

type Evidence = { filename: string; page: number; quote: string };
type Requirement = { label: string; status: string; message: string; evidence: Evidence[] };
type Review = { _id: string; title: string; description: string; source_type: string; status: string; evidence: Evidence[] };
type Snapshot = {
  generated_at: string;
  documents: { id: string; filename: string }[];
  summary: {
    indexed_documents: number; indexed_pages: number; pending_reviews: number; further_review: number;
    completed_reviews: number; rule_failures: number; missing_requirements: number;
    needs_verification_requirements: number;
    confidence: { total: number; verified: number; needs_review: number; uncertain: number };
  };
  requirement_counts: Record<string, number>;
  review_counts: Record<string, number>;
  checklists: { _id: string; name: string; requirements: Requirement[] }[];
  reviews: Review[];
  notice: string;
};
type Cache = { saved_at: string; snapshot: Snapshot };
const CACHE_KEY = "trustlens_phase3_review_snapshot_v1";

function readCache(): Cache | null {
  try { const raw = localStorage.getItem(CACHE_KEY); return raw ? JSON.parse(raw) as Cache : null; } catch { return null; }
}
function saveCache(snapshot: Snapshot): string | null {
  try { const saved_at = new Date().toISOString(); localStorage.setItem(CACHE_KEY, JSON.stringify({ saved_at, snapshot })); return saved_at; } catch { return null; }
}
function saveJson(value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = "trustlens-offline-review-snapshot.json"; a.click(); URL.revokeObjectURL(url);
}

export default function ReviewDashboardPage() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [offline, setOffline] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    if (!navigator.onLine) {
      const cached = readCache();
      if (cached) {
        setData(cached.snapshot); setCachedAt(cached.saved_at);
        setSelected(cached.snapshot.documents.map((d) => d.id));
        setNotice("Offline mode: showing previously cached analysis. Live checks and report generation are unavailable.");
      } else setError("No offline snapshot is saved on this device yet. Connect and load the dashboard once.");
      setOffline(true); setLoading(false); return;
    }
    setLoading(true);
    try {
      const result = await api.get<Snapshot>("/api/compliance/phase3/dashboard");
      setData(result);
      setCachedAt(saveCache(result));
      setSelected((current) => current.length ? current.filter((id) => result.documents.some((d) => d.id === id)) : result.documents.map((d) => d.id));
      setOffline(false);
      setNotice("Live review data loaded. A read-only snapshot has been saved locally for offline access.");
    } catch (e) {
      const cached = readCache();
      if (cached) {
        setData(cached.snapshot); setCachedAt(cached.saved_at); setOffline(true);
        setNotice("Backend unavailable. Showing the last locally saved snapshot.");
      } else setError(e instanceof ApiError ? e.message : "Could not load the review dashboard.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const online = () => { setOffline(false); void load(); };
    const offlineEvent = () => {
      setOffline(true);
      const cached = readCache();
      if (cached) { setData(cached.snapshot); setCachedAt(cached.saved_at); setNotice("Connection lost. Switched to the last local snapshot."); }
    };
    window.addEventListener("online", online); window.addEventListener("offline", offlineEvent);
    void load();
    return () => { window.removeEventListener("online", online); window.removeEventListener("offline", offlineEvent); };
  }, [load]);

  const pending = useMemo(() => data?.reviews.filter((r) => ["PENDING", "NEEDS_FURTHER_REVIEW"].includes(r.status)).slice(0, 8) || [], [data]);
  const exceptions = useMemo(() => data?.checklists.flatMap((c) => c.requirements.filter((r) => r.status !== "FOUND").map((r) => ({ checklist: c.name, requirement: r } )).slice(0, 8)) || [], [data]);
  const s = data?.summary;

  async function report() {
    if (!selected.length) { setError("Select at least one indexed document."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      await downloadAuthedPost("/api/compliance/phase3/reports/due-diligence", {
        document_ids: selected, title: "TrustLens AI Due Diligence Report",
      }, "trustlens-due-diligence-report.pdf");
      setNotice("Due diligence PDF generated and downloaded.");
    } catch (e) { setError(e instanceof ApiError ? e.message : "PDF generation failed."); }
    finally { setBusy(false); }
  }

  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">TrustLens AI · Phase 3</p>
        <h1 className="mt-2 font-serif text-3xl font-semibold text-navy">Complete Review Dashboard</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink/60">A consolidated view of compliance exceptions, extraction confidence and human decisions, with an evidence-backed due diligence report.</p>
      </div>
      <div className="flex items-center gap-2">
        <span className={"inline-flex items-center gap-1.5 rounded-full border px-3 py-2 text-xs " + (offline ? "border-amber-200 bg-amber-50 text-amber-800" : "border-emerald-200 bg-emerald-50 text-emerald-700")}>{offline ? <CloudOff size={13}/> : <Cloud size={13}/>} {offline ? "Offline snapshot" : "Live connection"}</span>
        <button onClick={() => void load()} disabled={offline || loading} className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-3 py-2 text-xs text-navy disabled:opacity-40"><RefreshCw size={13}/> Refresh</button>
      </div>
    </header>
    {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</div>}
    {notice && <div role="status" className="rounded-xl border border-line bg-white p-3 text-xs text-ink/65">{notice}</div>}
    {loading ? <div className="rounded-2xl border border-line bg-white p-12 text-center text-sm text-ink/50">Preparing review dashboard…</div> : data && s ? <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Indexed documents", s.indexed_documents, s.indexed_pages + " indexed pages", FileText],
          ["Pending reviews", s.pending_reviews, s.further_review + " marked for further review", Activity],
          ["Compliance exceptions", s.missing_requirements + s.needs_verification_requirements, s.missing_requirements + " missing · " + s.needs_verification_requirements + " need verification", ShieldAlert],
          ["Rule failures", s.rule_failures, s.completed_reviews + " completed decisions", AlertTriangle],
        ].map(([label, value, hint, Icon]) => <div key={String(label)} className="rounded-2xl border border-line bg-white p-4 shadow-sm"><div className="flex items-center justify-between"><p className="text-xs text-ink/55">{label}</p><Icon size={16} className="text-accent"/></div><p className="mt-2 text-3xl font-semibold text-navy">{value as number}</p><p className="mt-1 text-[11px] text-ink/45">{hint}</p></div>)}
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <div className="rounded-2xl border border-line bg-white p-5">
          <h2 className="text-sm font-semibold text-navy">Review pipeline</h2><p className="mt-1 text-xs text-ink/50">Current review decisions and completeness checks</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>{Object.entries(data.review_counts).map(([key, value]) => <div key={key} className="mb-3"><div className="mb-1 flex justify-between text-[11px]"><span className="text-ink/60">{key.replaceAll("_", " ")}</span><strong>{value}</strong></div><div className="h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-accent" style={{ width: Math.min(100, value / Math.max(1, Object.values(data.review_counts).reduce((a, b) => a + b, 0)) * 100) + "%" }}/></div></div>)}</div>
            <div>{Object.entries(data.requirement_counts).map(([key, value]) => <div key={key} className="mb-2 flex justify-between rounded-lg bg-slate-50 px-3 py-2 text-xs"><span className="text-ink/60">{key.replaceAll("_", " ")}</span><strong>{value}</strong></div>)}</div>
          </div>
        </div>
        <div className="rounded-2xl border border-line bg-white p-5">
          <h2 className="text-sm font-semibold text-navy">Extraction confidence</h2><p className="mt-1 text-xs text-ink/50">Text extraction reliability, not legal correctness.</p>
          <p className="mt-4 text-4xl font-semibold text-navy">{s.confidence.total ? Math.round(s.confidence.verified / s.confidence.total * 100) : 0}%</p>
          <p className="text-xs text-ink/45">high extraction signal</p>
          <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-slate-100"><div className="bg-emerald-500" style={{ width: (s.confidence.total ? s.confidence.verified / s.confidence.total * 100 : 0) + "%" }}/><div className="bg-amber-400" style={{ width: (s.confidence.total ? s.confidence.needs_review / s.confidence.total * 100 : 0) + "%" }}/><div className="bg-rose-400" style={{ width: (s.confidence.total ? s.confidence.uncertain / s.confidence.total * 100 : 0) + "%" }}/></div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs"><div><strong className="text-emerald-700">{s.confidence.verified}</strong><p className="text-[10px] text-ink/45">High signal</p></div><div><strong className="text-amber-700">{s.confidence.needs_review}</strong><p className="text-[10px] text-ink/45">Needs review</p></div><div><strong className="text-rose-700">{s.confidence.uncertain}</strong><p className="text-[10px] text-ink/45">Uncertain</p></div></div>
        </div>
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <div className="rounded-2xl border border-line bg-white p-5"><h2 className="text-sm font-semibold text-navy">Priority review queue</h2><div className="mt-3 space-y-2">{pending.map((r) => <article key={r._id} className="rounded-xl border border-line p-3"><div className="flex justify-between gap-2"><strong className="text-xs text-navy">{r.title}</strong><span className="text-[9px] text-amber-800">{r.status.replaceAll("_", " ")}</span></div><p className="mt-1 text-[11px] text-ink/50">{r.source_type} · {r.description}</p>{r.evidence?.slice(0, 1).map((e, i) => <p key={i} className="mt-2 text-[10px] text-ink/50">{e.filename} · p.{e.page}: {e.quote.slice(0, 160)}</p>)}</article>)}{!pending.length && <p className="rounded-lg bg-slate-50 p-4 text-xs text-ink/45">No pending review items.</p>}</div></div>
        <div className="rounded-2xl border border-line bg-white p-5"><h2 className="text-sm font-semibold text-navy">Checklist exceptions</h2><div className="mt-3 space-y-2">{exceptions.map((x, i) => <article key={i} className="rounded-xl border border-line p-3"><div className="flex justify-between gap-2"><strong className="text-xs text-navy">{x.requirement.label}</strong><span className="text-[9px] text-rose-700">{x.requirement.status.replaceAll("_", " ")}</span></div><p className="mt-1 text-[10px] text-ink/50">{x.checklist} · {x.requirement.message}</p>{x.requirement.evidence?.slice(0, 1).map((e, j) => <p key={j} className="mt-1 text-[10px] text-ink/45">{e.filename} · p.{e.page}: {e.quote.slice(0, 140)}</p>)}</article>)}{!exceptions.length && <p className="rounded-lg bg-slate-50 p-4 text-xs text-ink/45">No checklist exceptions.</p>}</div></div>
      </section>
      <section className="rounded-2xl border border-line bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-sm font-semibold text-navy">One-Click Due Diligence Report</h2><p className="mt-1 text-xs text-ink/50">PDF includes document scope, extraction findings, compliance exceptions, human review register and limitations.</p></div><button onClick={() => void report()} disabled={offline || busy || !selected.length} className="inline-flex items-center gap-2 rounded-xl bg-navy px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-40"><Download size={14}/>{busy ? "Generating…" : "Generate PDF report"}</button></div>
        <div className="mt-4 flex flex-wrap gap-2">{data.documents.map((d) => <label key={d.id} className={"flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-xs " + (selected.includes(d.id) ? "border-accent bg-accent-bg text-navy" : "border-line text-ink/60")}><input type="checkbox" checked={selected.includes(d.id)} onChange={() => setSelected((s0) => s0.includes(d.id) ? s0.filter((x) => x !== d.id) : [...s0, d.id])} disabled={offline}/>{d.filename}</label>)}</div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><p className="text-[10px] text-ink/45">{selected.length} selected · PDF generation requires live backend.</p><button onClick={() => saveJson({ saved_at: cachedAt, snapshot: data })} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-[11px] text-navy"><Archive size={13}/> Download offline snapshot</button></div>
      </section>
      <p className="text-[10px] leading-5 text-ink/40">{data.notice} Snapshot saved: {cachedAt ? new Date(cachedAt).toLocaleString() : "not saved"}</p>
    </> : <div className="rounded-2xl border border-line bg-white p-10 text-center text-sm text-ink/50">No review data available.</div>}
  </div>;
}
