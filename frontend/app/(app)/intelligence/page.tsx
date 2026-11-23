"use client";

import { useEffect, useMemo, useState } from "react";
import { Search, Network, ShieldCheck, ScanSearch, FileText, AlertTriangle, RefreshCw } from "lucide-react";
import { api, ApiError } from "@/lib/api";

type Node = { id: string; type: string; label: string; document_id?: string };
type Edge = { id: string; source: string; target: string; type: string; document_id?: string; page?: number };
type Field = { id: string; filename: string; document_id: string; page: number; field_type: string; label: string; value: string; confidence: number; confidence_basis: string; status: string; quote: string };
type Review = { document_id: string; filename: string; page: number; signals: string[]; review_candidates: { text: string; confidence: number; bbox: number[] }[]; analysis_status: string };
type Overview = { indexed_document_count: number; page_count: number; entity_count: number; relationship_count: number; nodes: Node[]; edges: Edge[]; fields: Field[]; visual_review: Review[]; notice: string };
type SearchResult = { document_id: string; filename: string; page: number; score: number; matched_terms: string[]; snippet: string; source_type: string };

const statusStyle: Record<string, string> = {
  VERIFIED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  NEEDS_REVIEW: "bg-amber-50 text-amber-800 border-amber-200",
  UNCERTAIN: "bg-rose-50 text-rose-700 border-rose-200",
};

export default function IntelligencePage() {
  const [data, setData] = useState<Overview | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [activeNode, setActiveNode] = useState<string | null>(null);

  async function load() {
    setLoading(true); setError("");
    try { setData(await api.get<Overview>("/api/intelligence/overview")); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load intelligence workspace."); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function runSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setSearching(true); setError("");
    try { const response = await api.get<{ items: SearchResult[] }>(`/api/intelligence/search?q=${encodeURIComponent(query.trim())}&limit=20`); setResults(response.items || []); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Search failed."); }
    finally { setSearching(false); }
  }

  const visibleFields = useMemo(() => (data?.fields || []).filter(f => filter === "ALL" || f.status === filter), [data, filter]);
  const visibleNodes = data?.nodes || [];
  const graphNodes = useMemo(() => {
    const nodes = visibleNodes.slice(0, 32);
    const centerX = 360, centerY = 190, radius = 145;
    return nodes.map((node, i) => ({ ...node, x: centerX + Math.cos((2 * Math.PI * i) / Math.max(nodes.length, 1)) * radius, y: centerY + Math.sin((2 * Math.PI * i) / Math.max(nodes.length, 1)) * radius }));
  }, [visibleNodes]);
  const graphPositions = useMemo(() => Object.fromEntries(graphNodes.map(n => [n.id, { x: n.x, y: n.y }])), [graphNodes]);
  const selectedNode = visibleNodes.find(n => n.id === activeNode);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">TrustLens AI · Phase 1</p><h1 className="mt-2 font-serif text-3xl font-semibold text-navy">Document Intelligence</h1><p className="mt-2 max-w-2xl text-sm text-ink/60">Explore connected entities, inspect extraction confidence, review uncertain scanned regions and search across indexed source pages.</p></div>
        <button onClick={load} className="inline-flex items-center gap-2 rounded-card border border-line bg-white px-3 py-2 text-sm text-navy hover:bg-slate-50"><RefreshCw size={14}/> Refresh</button>
      </div>
      {error && <div className="rounded-card border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</div>}
      {loading ? <div className="rounded-card border border-line bg-white p-10 text-center text-sm text-ink/50">Building your intelligence workspace…</div> : <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Indexed documents", data?.indexed_document_count ?? 0, "Files available for analysis"],
            ["Source pages", data?.page_count ?? 0, "Indexed pages inspected"],
            ["Entity candidates", data?.entity_count ?? 0, "People, property IDs, dates, references"],
            ["Relationships", data?.relationship_count ?? 0, "Document mentions and co-occurrences"],
          ].map(([label, value, hint]) => <div key={String(label)} className="rounded-card border border-line bg-white p-4"><p className="text-xs text-ink/50">{label}</p><p className="mt-1 text-2xl font-semibold text-navy">{value}</p><p className="mt-1 text-[11px] text-ink/45">{hint}</p></div>)}
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
          <section className="overflow-hidden rounded-card border border-line bg-white">
            <div className="flex items-center justify-between border-b border-line px-5 py-4"><div><h2 className="flex items-center gap-2 text-sm font-semibold text-navy"><Network size={16}/> Relationship Knowledge Graph</h2><p className="mt-1 text-xs text-ink/50">Select a node to inspect its type and source links.</p></div><span className="text-xs text-ink/45">{visibleNodes.length} nodes</span></div>
            {visibleNodes.length ? <div className="overflow-x-auto bg-[#f8fafc] p-2">
              <svg viewBox="0 0 720 390" className="h-[360px] min-w-[600px] w-full" role="img" aria-label="Document relationship graph">
                {data?.edges.map(edge => { const a = graphPositions[edge.source], b = graphPositions[edge.target]; return a && b ? <line key={edge.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#cbd5e1" strokeWidth="1.5"/> : null; })}
                {graphNodes.map(node => { const active = activeNode === node.id; const fill = node.type === "DOCUMENT" ? "#17324d" : node.type === "OWNER" ? "#b58a42" : node.type === "PROPERTY_ID" ? "#0f766e" : "#64748b"; return <g key={node.id} onClick={() => setActiveNode(node.id)} className="cursor-pointer"><circle cx={node.x} cy={node.y} r={active ? 13 : 10} fill={fill} stroke={active ? "#fbbf24" : "#fff"} strokeWidth={active ? 4 : 2}/><text x={node.x} y={node.y + 25} textAnchor="middle" fontSize="10" fill="#334155">{node.label.length > 18 ? node.label.slice(0, 18) + "…" : node.label}</text></g>; })}
              </svg>
            </div> : <div className="p-10 text-center"><Network className="mx-auto text-ink/25" size={30}/><p className="mt-3 text-sm font-medium text-navy">No graph data yet</p><p className="mt-1 text-xs text-ink/50">Upload and index documents to extract relationship candidates.</p></div>}
            <div className="flex flex-wrap gap-4 border-t border-line px-5 py-3 text-[11px] text-ink/60"><span>● Documents</span><span className="text-[#b58a42]">● Owner candidates</span><span className="text-teal-700">● Property IDs</span><span>● Dates / references</span></div>
            {selectedNode && <div className="border-t border-line bg-slate-50 px-5 py-3 text-xs"><strong className="text-navy">{selectedNode.label}</strong><span className="ml-2 text-ink/50">{selectedNode.type.replaceAll("_", " ")}</span><button onClick={() => setActiveNode(null)} className="float-right text-ink/50">Clear</button></div>}
          </section>

          <section className="rounded-card border border-line bg-white p-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-navy"><Search size={16}/> Natural Language Document Search</h2>
            <p className="mt-1 text-xs text-ink/50">Search names, survey numbers, dates, clauses or describe the information you need.</p>
            <form onSubmit={runSearch} className="mt-4 space-y-2"><textarea value={query} onChange={e => setQuery(e.target.value)} rows={3} placeholder="e.g. Find all documents mentioning owner Rajesh Kumar" className="w-full rounded-card border border-line bg-white p-3 text-sm text-navy outline-none focus:border-accent"/><button disabled={searching || query.trim().length < 2} className="inline-flex w-full items-center justify-center gap-2 rounded-card bg-navy px-3 py-2.5 text-sm font-medium text-white disabled:opacity-50">{searching ? "Searching…" : <><Search size={14}/> Search indexed documents</>}</button></form>
            <p className="mt-3 text-[11px] text-ink/45">Retrieval uses BM25 lexical ranking. Semantic interpretation and cross-language translation are not claimed by this search endpoint.</p>
          </section>
        </div>

        {results.length > 0 && <section className="rounded-card border border-line bg-white p-5"><h2 className="text-sm font-semibold text-navy">Search results <span className="ml-1 text-ink/40">({results.length})</span></h2><div className="mt-3 space-y-3">{results.map((r, i) => <article key={r.document_id + r.page + i} className="rounded-card border border-line p-3"><div className="flex flex-wrap justify-between gap-2"><strong className="text-sm text-navy">{r.filename}</strong><span className="text-xs text-ink/45">Page {r.page} · score {r.score.toFixed(2)}</span></div><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink/75">{r.snippet}</p><div className="mt-2 flex flex-wrap gap-1">{r.matched_terms.map(term => <span key={term} className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-600">{term}</span>)}</div></article>)}</div></section>}

        <section className="rounded-card border border-line bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="flex items-center gap-2 text-sm font-semibold text-navy"><ShieldCheck size={16}/> AI Confidence & Verification</h2><p className="mt-1 text-xs text-ink/50">Confidence describes extraction reliability, not whether a legal statement is true.</p></div><select value={filter} onChange={e => setFilter(e.target.value)} className="rounded-card border border-line bg-white px-3 py-2 text-xs text-navy"><option value="ALL">All statuses</option><option value="VERIFIED">Source verified</option><option value="NEEDS_REVIEW">Needs review</option><option value="UNCERTAIN">Uncertain</option></select></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3"><div className="rounded-card bg-emerald-50 p-3"><p className="text-xs text-emerald-700">Source verified</p><p className="mt-1 text-xl font-semibold text-emerald-900">{data?.fields.filter(f => f.status === "VERIFIED").length ?? 0}</p></div><div className="rounded-card bg-amber-50 p-3"><p className="text-xs text-amber-700">Needs review</p><p className="mt-1 text-xl font-semibold text-amber-900">{data?.fields.filter(f => f.status === "NEEDS_REVIEW").length ?? 0}</p></div><div className="rounded-card bg-rose-50 p-3"><p className="text-xs text-rose-700">Uncertain</p><p className="mt-1 text-xl font-semibold text-rose-900">{data?.fields.filter(f => f.status === "UNCERTAIN").length ?? 0}</p></div></div>
          <div className="mt-4 space-y-2">{visibleFields.slice(0, 80).map(field => <div key={field.id} className="grid gap-2 rounded-card border border-line p-3 sm:grid-cols-[1fr_auto]"><div><div className="flex flex-wrap items-center gap-2"><strong className="text-sm text-navy">{field.value}</strong><span className="text-[10px] text-ink/45">{field.label}</span><span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusStyle[field.status] || statusStyle.UNCERTAIN}`}>{field.status.replaceAll("_", " ")}</span></div><p className="mt-1 text-xs text-ink/55">{field.filename} · Page {field.page} · {field.confidence_basis}</p><p className="mt-2 text-xs leading-5 text-ink/70">“{field.quote}”</p></div><div className="min-w-24 text-right"><p className="text-xl font-semibold text-navy">{Math.round(field.confidence * 100)}%</p><p className="text-[10px] text-ink/45">Extraction signal</p></div></div>)}</div>
          {!visibleFields.length && <p className="py-8 text-center text-xs text-ink/45">No extracted fields match this status. Index documents to populate the review list.</p>}
        </section>

        <section className="rounded-card border border-line bg-white p-5"><h2 className="flex items-center gap-2 text-sm font-semibold text-navy"><ScanSearch size={16}/> Handwriting & Stamp Review Candidates</h2><p className="mt-1 text-xs text-ink/50">Flags pages for manual visual inspection using OCR confidence and extracted wording.</p><div className="mt-4 grid gap-3 md:grid-cols-2">{data?.visual_review.map((item, i) => <article key={item.document_id + item.page + i} className="rounded-card border border-amber-200 bg-amber-50/50 p-3"><div className="flex items-center justify-between gap-2"><strong className="text-sm text-navy">{item.filename}</strong><span className="text-xs text-ink/50">Page {item.page}</span></div><ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-ink/70">{item.signals.map((s, j) => <li key={j}>{s}</li>)}</ul>{item.review_candidates.length > 0 && <p className="mt-2 text-[11px] text-amber-800">{item.review_candidates.length} low-confidence OCR region(s) · coordinates available</p>}</article>)}</div>{!data?.visual_review.length && <p className="py-6 text-center text-xs text-ink/45">No current review candidates. This does not confirm that all signatures or stamps are authentic.</p>}</section>
        <p className="text-[11px] leading-5 text-ink/45">{data?.notice} Handwriting recognition and stamp/seal authenticity require a dedicated visual model and are not inferred from text-only OCR.</p>
      </>}
    </div>
  );
}
