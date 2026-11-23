"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, BrainCircuit, CheckCircle2, FileSearch, GitBranch,
  Loader2, RefreshCw, Send, ShieldCheck, Sparkles,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { LoadingState, ErrorState } from "@/components/ui/States";

type Doc = {
  id: string; filename: string; status: string; docai_status?: string;
  file_size_bytes?: number; uploaded_at?: string;
};
type Job = { status: string; pages_total?: number; pages_processed?: number; error?: { message?: string } };
type Evidence = {
  evidence_id: string; filename: string; page_number: number; quote: string;
  relation?: string; verification?: { quote_found_in_source?: boolean };
};
type Claim = {
  claim_id: string; text: string; status: string; confidence: number;
  explanation?: string; requires_human_review?: boolean;
};
type Conflict = {
  contradiction_id?: string; topic: string; status: string; type?: string;
  evidence: Evidence[]; explanation?: string;
};
type Answer = {
  answer: string; abstained: boolean; faithfulness_score: number | null;
  faithfulness_method?: string; claims: Claim[]; evidence: Evidence[];
  conflicts: Conflict[]; missing_evidence?: { description: string }[];
  llm_assistance?: { status: string; draft?: string | null; model?: string | null; notice?: string };
};
type PageResult<T> = { items: T[]; next_cursor?: string | null };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default function DocumentAIPage() {
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [indexedIds, setIndexedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [indexing, setIndexing] = useState(false);
  const [indexMessage, setIndexMessage] = useState("");
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [amendments, setAmendments] = useState<Record<string, unknown>[]>([]);

  async function loadDocuments() {
    setError(null);
    try {
      const data = await api.get<Doc[]>("/api/documents");
      setDocuments(data);
      setSelected((current) => current.filter((id) => data.some((doc) => doc.id === id)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadDocuments(); }, []);

  const selectedDocs = useMemo(
    () => documents.filter((doc) => selected.includes(doc.id)),
    [documents, selected]
  );
  const indexedCount = selectedDocs.filter((doc) => indexedIds.includes(doc.id)).length;

  function toggleDocument(id: string) {
    setSelected((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
    setAnswer(null);
    setConflicts([]);
    setAmendments([]);
  }

  async function indexSelected() {
    if (!selected.length) return;
    setIndexing(true);
    setError(null);
    setIndexMessage("Starting document indexing…");
    try {
      for (let i = 0; i < selected.length; i++) {
        const id = selected[i];
        const doc = documents.find((item) => item.id === id);
        if (indexedIds.includes(id)) continue;
        setIndexMessage(`Indexing ${i + 1} of ${selected.length}: ${doc?.filename ?? "document"}`);
        const started = await api.post<{ indexing_job_id: string }>(`/api/document-ai/documents/${id}/index`, {});
        let completed = false;
        for (let attempt = 0; attempt < 90; attempt++) {
          await sleep(2000);
          const job = await api.get<Job>(`/api/document-ai/indexing-jobs/${started.indexing_job_id}`);
          if (job.status === "COMPLETED") { completed = true; break; }
          if (job.status === "FAILED") throw new Error(job.error?.message || "Document indexing failed.");
        }
        if (!completed) throw new Error(`Indexing timed out for ${doc?.filename ?? "document"}.`);
        setIndexedIds((current) => current.includes(id) ? current : [...current, id]);
      }
      setIndexMessage("All selected documents are indexed and ready for evidence search.");
      await loadDocuments();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Indexing failed.");
    } finally {
      setIndexing(false);
    }
  }

  async function askQuestion(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim() || !selected.length) return;
    setAsking(true);
    setError(null);
    setAnswer(null);
    try {
      const result = await api.post<Answer>("/api/document-ai/qa/ask", {
        question: question.trim(), document_ids: selected, language: "en",
        include_superseded_documents: true, max_evidence_per_claim: 5,
      });
      setAnswer(result);
      const ids = selected.join(",");
      const [c, a] = await Promise.all([
        api.get<PageResult<Conflict>>(`/api/document-ai/contradictions?document_ids=${encodeURIComponent(ids)}&limit=100`),
        api.get<PageResult<Record<string, unknown>>>(`/api/document-ai/amendments?document_ids=${encodeURIComponent(ids)}&limit=100`),
      ]);
      setConflicts(c.items || result.conflicts || []);
      setAmendments(a.items || []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The question could not be answered.");
    } finally {
      setAsking(false);
    }
  }

  if (loading) return <LoadingState label="Loading Document AI workspace…" />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-[0.16em]">
            <BrainCircuit size={15} /> Evidence intelligence
          </div>
          <h1 className="mt-2 font-serif text-2xl text-navy">Document AI</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink/55">
            Ask questions across contracts, banking policies, insurance terms, circulars and other dense documents.
            Answers stay tied to page-level source evidence.
          </p>
        </div>
        <Button variant="secondary" onClick={loadDocuments} disabled={indexing || asking}>
          <RefreshCw size={14} /> Refresh
        </Button>
      </div>

      {error && <ErrorState message={error} />}

      <div className="grid gap-5 xl:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.5fr)]">
        <Card>
          <CardHeader>
            <CardTitle>1. Select source documents</CardTitle>
            <p className="text-xs text-ink/50">Choose one or more PDFs already uploaded to your account.</p>
          </CardHeader>
          <CardContent className="space-y-3">
            {documents.length === 0 ? (
              <p className="rounded-card bg-slate-50 p-4 text-sm text-ink/55">No documents found. Upload documents first, then return here.</p>
            ) : (
              <div className="max-h-[390px] space-y-2 overflow-y-auto">
                {documents.map((doc) => {
                  const checked = selected.includes(doc.id);
                  const indexed = indexedIds.includes(doc.id);
                  return (
                    <label key={doc.id} className={`flex cursor-pointer items-start gap-3 rounded-card border p-3 transition-colors ${checked ? "border-accent bg-accent-bg/50" : "border-line hover:bg-slate-50"}`}>
                      <input type="checkbox" checked={checked} onChange={() => toggleDocument(doc.id)} className="mt-1 accent-blue-600" />
                      <span className="min-w-0 flex-1">
                        <span className="block break-words text-sm font-medium text-navy">{doc.filename}</span>
                        <span className="mt-1 flex items-center gap-1.5 text-[11px] text-ink/50">
                          {indexed ? <><CheckCircle2 size={12} className="text-verified" /> Indexed</> : <><FileSearch size={12} /> Ready to index</>}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
            <div className="flex items-center justify-between border-t border-line pt-3 text-xs text-ink/50">
              <span>{selected.length} selected · {indexedCount} indexed</span>
              <span>Multi-document search</span>
            </div>
            <Button className="w-full" onClick={indexSelected} disabled={!selected.length || indexing || indexedCount === selected.length}>
              {indexing ? <><Loader2 size={14} className="animate-spin" /> Indexing…</> : <><FileSearch size={14} /> Index selected documents</>}
            </Button>
            {indexMessage && <p className="text-xs text-ink/55">{indexMessage}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>2. Ask with evidence</CardTitle>
            <p className="text-xs text-ink/50">Only indexed documents can be queried. Unsupported questions are not guessed.</p>
          </CardHeader>
          <CardContent>
            <form onSubmit={askQuestion} className="space-y-3">
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={4}
                maxLength={2000}
                placeholder="Example: What is the applicable interest rate and when does the agreement expire?"
                className="w-full resize-y rounded-card border border-line bg-white p-3 text-sm text-navy outline-none focus:border-accent focus:ring-2 focus:ring-accent/10"
              />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-xs text-ink/45">Up to 2,000 characters · English query</span>
                <Button type="submit" disabled={!question.trim() || !selected.length || indexedCount !== selected.length || asking}>
                  {asking ? <><Loader2 size={14} className="animate-spin" /> Searching evidence…</> : <><Send size={14} /> Ask documents</>}
                </Button>
              </div>
              {selected.length > 0 && indexedCount !== selected.length && (
                <p className="text-xs text-review">Index all selected documents before asking a question.</p>
              )}
            </form>
          </CardContent>
        </Card>
      </div>

      {answer && (
        <div className="space-y-5">
          <Card>
            <CardHeader className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle>Verified answer</CardTitle>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${answer.abstained ? "bg-review-bg text-review" : "bg-verified-bg text-verified"}`}>
                {answer.abstained ? "Insufficient evidence" : "Source-backed response"}
              </span>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="whitespace-pre-wrap text-sm leading-7 text-navy">{answer.answer}</p>
              <div className="flex flex-wrap gap-4 border-t border-line pt-3 text-xs text-ink/55">
                <span className="flex items-center gap-1.5"><ShieldCheck size={14} /> Faithfulness: {answer.faithfulness_score === null ? "N/A" : `${Math.round(answer.faithfulness_score * 100)}%`}</span>
                <span>{answer.claims.length} claims checked</span>
                <span>{answer.evidence.length} source passages</span>
              </div>
            </CardContent>
          </Card>

          {answer.llm_assistance && (
            <Card>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-navy"><Sparkles size={15} /> Local model assistance</div>
                <p className="text-xs text-ink/55">Status: {answer.llm_assistance.status} · Model: {answer.llm_assistance.model || "Not enabled"}</p>
                {answer.llm_assistance.draft && (
                  <div className="rounded-card border border-review/30 bg-review-bg/40 p-3">
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-review">Unverified Llama draft — not authoritative</p>
                    <p className="whitespace-pre-wrap text-sm text-navy">{answer.llm_assistance.draft}</p>
                    <p className="mt-2 text-xs text-ink/55">{answer.llm_assistance.notice}</p>
                  </div>
                )}
                {!answer.llm_assistance.draft && <p className="text-xs text-ink/50">{answer.llm_assistance.notice || "The evidence-backed answer remains authoritative; model drafting was skipped or disabled."}</p>}
              </CardContent>
            </Card>
          )}

          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Evidence & citations</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {answer.evidence.map((item) => (
                  <div key={item.evidence_id} className="rounded-card border border-line p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-semibold text-navy">{item.filename}</span>
                      <span className="text-ink/50">Page {item.page_number}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-ink/75">“{item.quote}”</p>
                    <p className="mt-2 flex items-center gap-1 text-[11px] text-verified">
                      <CheckCircle2 size={12} /> {item.verification?.quote_found_in_source ? "Quote verified against source page" : "Source quote attached"}
                    </p>
                  </div>
                ))}
                {answer.evidence.length === 0 && <p className="text-sm text-ink/50">No supporting passages were found.</p>}
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Claims & conflict review</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {answer.claims.map((claim) => (
                  <div key={claim.claim_id} className="rounded-card border border-line p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-navy">{claim.status.replaceAll("_", " ")}</span>
                      <span className="text-xs text-ink/45">{Math.round(claim.confidence * 100)}% term coverage</span>
                    </div>
                    <p className="mt-2 text-sm text-ink/75">{claim.text}</p>
                    {claim.explanation && <p className="mt-1 text-xs text-ink/50">{claim.explanation}</p>}
                  </div>
                ))}
                {conflicts.map((conflict, index) => (
                  <div key={conflict.contradiction_id || index} className="rounded-card border border-risk/30 bg-risk-bg/40 p-3">
                    <p className="flex items-center gap-2 text-xs font-semibold text-risk"><AlertTriangle size={13} /> {conflict.topic} · {conflict.status}</p>
                    {conflict.evidence?.map((item, i) => (
                      <p key={item.evidence_id || i} className="mt-2 text-xs leading-5 text-ink/70">
                        <strong>{item.filename}, p.{item.page_number}:</strong> “{item.quote}”
                      </p>
                    ))}
                  </div>
                ))}
                {answer.claims.length === 0 && conflicts.length === 0 && <p className="text-sm text-ink/50">No verified claims or detected conflicts to display.</p>}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle><span className="inline-flex items-center gap-2"><GitBranch size={16} /> Amendment history</span></CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {amendments.length ? amendments.map((item, index) => (
                <div key={String(item.amendment_id || index)} className="rounded-card border border-line p-3 text-sm">
                  <div className="flex flex-wrap justify-between gap-2">
                    <strong className="text-navy">{String(item.topic || "Amendment")}</strong>
                    <span className="text-xs text-ink/50">{String(item.status || "Review required")}</span>
                  </div>
                  <p className="mt-1 text-xs text-ink/55">Effective from: {String(item.effective_from || "Not established")}</p>
                </div>
              )) : <p className="text-sm text-ink/50">No amendment chain was detected in the selected documents.</p>}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
