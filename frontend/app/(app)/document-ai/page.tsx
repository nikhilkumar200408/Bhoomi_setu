"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  AlertTriangle, BrainCircuit, Calculator, CheckCircle2, FileSearch, GitBranch,
  Loader2, RefreshCw, RotateCcw, Send, ShieldCheck, Sparkles, UploadCloud,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { LoadingState, ErrorState } from "@/components/ui/States";

type Doc = {
  id: string; filename: string; status: string; docai_status?: string; source_url?: string;
  file_size_bytes?: number; uploaded_at?: string;
};
type Job = { status: string; pages_total?: number; pages_processed?: number; error?: { message?: string } };
type Evidence = {
  evidence_id: string; filename: string; page_number: number; quote: string; source_url?: string;
  relation?: string; verification?: { quote_found_in_source?: boolean };
};
type Claim = {
  claim_id: string; text: string; status: string; confidence: number;
  explanation?: string; requires_human_review?: boolean;
  correction?: { corrected_text: string; reason: string; corrected_at: string };
};
type AuditEvent = { action: string; old_value?: string; new_value?: string; metadata?: Record<string, unknown>; timestamp: string; user_id?: string };
type Conflict = {
  contradiction_id?: string; topic: string; status: string; type?: string;
  evidence: Evidence[]; explanation?: string;
};
type Answer = {
  answer_id?: string; answer: string; abstained: boolean; faithfulness_score: number | null; question_coverage_score?: number;
  faithfulness_method?: string; claims: Claim[]; evidence: Evidence[]; language_notice?: string | null;
  conflicts: Conflict[]; missing_evidence?: { description: string }[];
  llm_assistance?: { status: string; draft?: string | null; model?: string | null; notice?: string };
};
type PageResult<T> = { items: T[]; next_cursor?: string | null };
type CalculationResult = { formula: string; working: string; notice: string; calculation_type: string; result: Record<string, number> };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function highlightImportantText(value: string) {
  const pattern = /(interest rate|processing fee|overdue charges?|repayment|maturity|effective date|penalty|eligibility|sanction|ब्याज दर|प्रसंस्करण शुल्क|विलंब शुल्क|पुनर्भुगतान|परिपक्वता|प्रभावी तिथि|दंड|पात्रता|₹\s?[\d,]+|\b\d+(?:\.\d+)?\s?%|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b)/gi;
  const matcher = new RegExp(pattern.source, "i");
  return value.split(pattern).map((part, index) =>
    matcher.test(part)
      ? <mark key={index} className="rounded bg-amber-100 px-1 text-amber-950">{part}</mark>
      : <span key={index}>{part}</span>
  );
}

export default function DocumentAIPage() {
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [indexedIds, setIndexedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [indexing, setIndexing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [webUrl, setWebUrl] = useState("");
  const [importingWeb, setImportingWeb] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [indexMessage, setIndexMessage] = useState("");
  const [question, setQuestion] = useState("");
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const [calculationType, setCalculationType] = useState<"simple_interest" | "compound_interest" | "emi">("simple_interest");
  const [principal, setPrincipal] = useState("100000");
  const [annualRate, setAnnualRate] = useState("8");
  const [duration, setDuration] = useState("2");
  const [durationUnit, setDurationUnit] = useState<"years" | "months">("years");
  const [calculation, setCalculation] = useState<CalculationResult | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [amendments, setAmendments] = useState<Record<string, unknown>[]>([]);
  const [editingClaimId, setEditingClaimId] = useState<string | null>(null);
  const [correctionText, setCorrectionText] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditOpen, setAuditOpen] = useState(false);

  async function loadDocuments() {
    setError(null);
    try {
      const data = await api.get<Doc[]>("/api/documents");
      setDocuments(data);
      setIndexedIds((current) => Array.from(new Set([...current, ...data.filter((doc) => doc.docai_status === "INDEXED").map((doc) => doc.id)])));
      setSelected((current) => current.filter((id) => data.some((doc) => doc.id === id)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadDocuments(); }, []);
  useEffect(() => {
    folderInputRef.current?.setAttribute("webkitdirectory", "");
    folderInputRef.current?.setAttribute("directory", "");
  }, []);

  async function refreshWorkspace() {
    setRefreshing(true);
    try {
      await loadDocuments();
      const ids = selected;
      if (ids.length) {
        const query = encodeURIComponent(ids.join(","));
        const [c, a] = await Promise.all([
          api.get<PageResult<Conflict>>(`/api/document-ai/contradictions?document_ids=${query}&limit=100`),
          api.get<PageResult<Record<string, unknown>>>(`/api/document-ai/amendments?document_ids=${query}&limit=100`),
        ]);
        setConflicts(c.items || []);
        setAmendments(a.items || []);
      } else {
        setConflicts([]);
        setAmendments([]);
      }
      if (answer?.answer_id) {
        const latest = await api.get<Answer>(`/api/document-ai/answers/${answer.answer_id}`);
        setAnswer(latest);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Workspace refresh failed.");
    } finally {
      setRefreshing(false);
    }
  }

  const selectedDocs = useMemo(
    () => documents.filter((doc) => selected.includes(doc.id)),
    [documents, selected]
  );
  const isIndexed = (doc: Doc) => doc.docai_status === "INDEXED" || indexedIds.includes(doc.id);
  const indexedCount = selectedDocs.filter(isIndexed).length;

  async function importWebpage() {
    if (!webUrl.trim()) return;
    setImportingWeb(true);
    setError(null);
    try {
      const result = await api.post<{ id: string; filename: string; source_url: string; message: string }>("/api/document-ai/sources/webpage/import", { url: webUrl.trim() });
      await loadDocuments();
      setSelected((current) => Array.from(new Set([...current, result.id])));
      setWebUrl("");
      setIndexMessage(result.message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Webpage import failed. Check the URL and administrator allowlist.");
    } finally {
      setImportingWeb(false);
    }
  }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length) return;
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    setUploading(true);
    setError(null);
    try {
      const result = await api.post<{ items: Doc[]; errors?: { filename: string; message: string }[] }>("/api/document-ai/documents/upload", form);
      await loadDocuments();
      if (result.errors?.length) setError(result.errors.map((item) => `${item.filename}: ${item.message}`).join("; "));
      setSelected((current) => Array.from(new Set([...current, ...result.items.map((doc) => doc.id)])));
      setIndexMessage(`${result.items.length} document(s) uploaded. Select all or index the uploaded files.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Document upload failed.");
    } finally {
      setUploading(false);
    }
  }

  function toggleDocument(id: string) {
    setSelected((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
    setAnswer(null);
    setConflicts([]);
    setAmendments([]);
  }

  // Reset only the active Document AI workspace. Uploaded files and indexed
  // source pages remain in the account and can be selected again later.
  function resetWorkspace() {
    setSelected([]);
    setQuestion("");
    setLanguage("en");
    setAnswer(null);
    setConflicts([]);
    setAmendments([]);
    setError(null);
    setIndexMessage("");
    setCalculation(null);
    setWebUrl("");
    setEditingClaimId(null);
    setCorrectionText("");
    setCorrectionReason("");
    setAuditEvents([]);
    setAuditOpen(false);
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
        if (doc && isIndexed(doc)) continue;
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

  async function runCalculation() {
    setCalculating(true);
    setError(null);
    try {
      const result = await api.post<CalculationResult>("/api/document-ai/calculate", {
        calculation_type: calculationType,
        principal: Number(principal),
        annual_rate_percent: Number(annualRate),
        duration_value: Number(duration),
        duration_unit: durationUnit,
        compounding_frequency: 12,
      });
      setCalculation(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Calculation failed. Check the entered values.");
      setCalculation(null);
    } finally {
      setCalculating(false);
    }
  }

  async function saveClaimCorrection(claimId: string) {
    if (!correctionText.trim() || correctionText.trim().length < 3 || correctionReason.trim().length < 5 || !answer?.answer_id) return;
    try {
      const result = await api.post<{ correction: Claim["correction"] }>(`/api/document-ai/claims/${claimId}/correct`, {
        corrected_text: correctionText.trim(), reason: correctionReason.trim(),
      });
      setAnswer((current) => current ? {
        ...current,
        claims: current.claims.map((claim) => claim.claim_id === claimId ? { ...claim, correction: result.correction } : claim),
      } : current);
      setEditingClaimId(null);
      setCorrectionText("");
      setCorrectionReason("");
      const history = await api.get<{ items: AuditEvent[] }>(`/api/document-ai/answers/${answer.answer_id}/audit`);
      setAuditEvents(history.items || []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Claim correction failed. Reviewer access may be required.");
    }
  }

  async function loadAnswerAudit() {
    if (!answer?.answer_id) return;
    try {
      const history = await api.get<{ items: AuditEvent[] }>(`/api/document-ai/answers/${answer.answer_id}/audit`);
      setAuditEvents(history.items || []);
      setAuditOpen(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load audit history.");
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
        question: question.trim(), document_ids: selected, language,
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
        <div className="flex items-center gap-2">
          <Button type="button" variant="secondary" onClick={resetWorkspace}
            disabled={asking || indexing || uploading || importingWeb || refreshing}>
            <RotateCcw size={14} /> Reset workspace
          </Button>
          <Button variant="secondary" onClick={refreshWorkspace} disabled={indexing || asking || uploading || refreshing}>
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} /> {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      {error && <ErrorState message={error} />}

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div>
            <p className="text-sm font-semibold text-navy">Add documents to this workspace</p>
            <p className="mt-1 text-xs text-ink/50">Upload PDFs or scanned JPG/PNG files directly. This does not run the legacy land-record digitization workflow.</p>
          </div>
          <label className={`inline-flex cursor-pointer items-center gap-2 rounded-card bg-accent px-4 py-2.5 text-sm font-medium text-white ${uploading ? "pointer-events-none opacity-60" : "hover:opacity-90"}`}>
            {uploading ? <Loader2 size={15} className="animate-spin" /> : <UploadCloud size={15} />}
            {uploading ? "Uploading…" : "Upload documents"}
            <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" className="hidden" disabled={uploading} onChange={(event) => { void uploadFiles(event.target.files); event.currentTarget.value = ""; }} />
          </label>
          <Button type="button" variant="secondary" onClick={() => folderInputRef.current?.click()} disabled={uploading}>
            <FileSearch size={14} /> Choose folder
          </Button>
          <input ref={folderInputRef} type="file" multiple accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
            className="hidden" disabled={uploading}
            onChange={(event) => { void uploadFiles(event.target.files); event.currentTarget.value = ""; }} />
          <div className="flex w-full flex-wrap gap-2 border-t border-line pt-3">
            <input type="url" value={webUrl} onChange={(event) => setWebUrl(event.target.value)}
              placeholder="https://public-website.example/page"
              className="min-w-[220px] flex-1 rounded-card border border-line bg-white px-3 py-2 text-sm text-navy"
              disabled={importingWeb} />
            <Button type="button" variant="secondary" onClick={() => void importWebpage()} disabled={importingWeb || !webUrl.trim()}>
              {importingWeb ? <><Loader2 size={14} className="animate-spin" /> Importing…</> : "Import webpage"}
            </Button>
          </div>
          <p className="w-full text-[11px] text-ink/45">Public HTTPS pages only. The host must be administrator-allowlisted; robots.txt and network safety checks are enforced.</p>
        </CardContent>
      </Card>

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
                  const indexed = isIndexed(doc);
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
              <button type="button" className="font-medium text-accent hover:underline" onClick={() => setSelected(selected.length === documents.length ? [] : documents.map((doc) => doc.id))} disabled={!documents.length || indexing}>{selected.length === documents.length ? "Clear selection" : "Select all documents"}</button>
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
                <div className="flex flex-wrap items-center gap-2">
                  <label htmlFor="answer-language" className="text-xs text-ink/55">Answer language</label>
                  <select id="answer-language" value={language} onChange={(event) => setLanguage(event.target.value as "en" | "hi")}
                    className="rounded-card border border-line bg-white px-2 py-1.5 text-xs text-navy">
                    <option value="en">English</option>
                    <option value="hi">हिन्दी (Hindi)</option>
                  </select>
                  <span className="text-xs text-ink/45">Up to 2,000 characters</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button type="submit" disabled={!question.trim() || !selected.length || indexedCount !== selected.length || asking}>
                    {asking ? <><Loader2 size={14} className="animate-spin" /> Searching evidence…</> : <><Send size={14} /> Ask documents</>}
                  </Button>
                </div>
              </div>
              {selected.length > 0 && indexedCount !== selected.length && (
                <p className="text-xs text-review">Index all selected documents before asking a question.</p>
              )}
            </form>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-5">
        <Card><CardContent className="py-4"><p className="text-xs text-ink/50">Documents</p><p className="mt-1 text-2xl font-semibold text-navy">{documents.length}</p><p className="text-xs text-ink/45">{documents.filter(isIndexed).length} indexed</p></CardContent></Card>
        <Card><CardContent className="py-4"><p className="text-xs text-ink/50">Claims checked</p><p className="mt-1 text-2xl font-semibold text-navy">{answer?.claims.length ?? 0}</p><p className="text-xs text-ink/45">{answer?.claims.filter(c => c.status === "SUPPORTED").length ?? 0} fully supported</p></CardContent></Card>
        <Card><CardContent className="py-4"><p className="text-xs text-ink/50">Contradictions</p><p className="mt-1 text-2xl font-semibold text-navy">{conflicts.length}</p><p className="text-xs text-ink/45">Across current selection</p></CardContent></Card>
        <Card><CardContent className="py-4"><p className="text-xs text-ink/50">Faithfulness score</p><p className="mt-1 text-2xl font-semibold text-navy">{answer?.faithfulness_score == null ? "—" : `${Math.round(answer.faithfulness_score * 100)}%`}</p><p className="text-xs text-ink/45">Claims grounded in verified source quotes / all claims</p></CardContent></Card>
        <Card><CardContent className="py-4"><p className="text-xs text-ink/50">Question coverage</p><p className="mt-1 text-2xl font-semibold text-navy">{answer?.question_coverage_score == null ? "—" : `${Math.round(answer.question_coverage_score * 100)}%`}</p><p className="text-xs text-ink/45">Question terms found in returned evidence</p></CardContent></Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Calculator size={17} /> Financial calculator</CardTitle>
          <p className="text-xs text-ink/50">Calculate simple interest, compound interest or EMI with visible working. Inputs are supplied by you, not extracted or verified from documents.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <label className="space-y-1 text-xs text-ink/60">Calculation
              <select value={calculationType} onChange={(e) => setCalculationType(e.target.value as typeof calculationType)} className="w-full rounded-card border border-line bg-white p-2 text-sm text-navy">
                <option value="simple_interest">Simple interest</option><option value="compound_interest">Compound interest</option><option value="emi">Loan EMI</option>
              </select>
            </label>
            <label className="space-y-1 text-xs text-ink/60">Principal (₹)<input type="number" min="1" value={principal} onChange={(e) => setPrincipal(e.target.value)} className="w-full rounded-card border border-line bg-white p-2 text-sm text-navy" /></label>
            <label className="space-y-1 text-xs text-ink/60">Annual rate (%)<input type="number" min="0" max="100" step="0.01" value={annualRate} onChange={(e) => setAnnualRate(e.target.value)} className="w-full rounded-card border border-line bg-white p-2 text-sm text-navy" /></label>
            <label className="space-y-1 text-xs text-ink/60">Duration<input type="number" min="0.01" value={duration} onChange={(e) => setDuration(e.target.value)} className="w-full rounded-card border border-line bg-white p-2 text-sm text-navy" /></label>
            <label className="space-y-1 text-xs text-ink/60">Duration unit
              <select value={durationUnit} onChange={(e) => setDurationUnit(e.target.value as "years" | "months")} className="w-full rounded-card border border-line bg-white p-2 text-sm text-navy"><option value="years">Years</option><option value="months">Months</option></select>
            </label>
          </div>
          <Button type="button" onClick={runCalculation} disabled={calculating || !principal || !annualRate || !duration}>{calculating ? <><Loader2 size={14} className="animate-spin" /> Calculating…</> : "Calculate with working"}</Button>
          {calculation && <div className="rounded-card border border-line bg-slate-50 p-4">
            <p className="text-sm font-semibold text-navy">{calculation.formula}</p><p className="mt-2 text-sm text-ink/75">{calculation.working}</p>
            <div className="mt-3 flex flex-wrap gap-4">{Object.entries(calculation.result).map(([key, value]) => <div key={key}><p className="text-[11px] uppercase tracking-wide text-ink/45">{key.replaceAll("_", " ")}</p><p className="text-lg font-semibold text-navy">₹{value.toLocaleString("en-IN", {minimumFractionDigits:2, maximumFractionDigits:2})}</p></div>)}</div>
            <p className="mt-2 text-xs text-ink/50">{calculation.notice}</p>
          </div>}
        </CardContent>
      </Card>
      <div className="grid gap-5 xl:grid-cols-2">
        <Card><CardHeader><CardTitle>Document indexing status</CardTitle></CardHeader><CardContent>
          <div className="h-64 w-full"><ResponsiveContainer width="100%" height="100%"><BarChart data={[
            {name:"Indexed",count:documents.filter(isIndexed).length},
            {name:"Pending",count:documents.filter(d => !isIndexed(d)).length},
          ]}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
            <Bar dataKey="count" fill="#2563eb" radius={[6,6,0,0]} /></BarChart></ResponsiveContainer></div>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Answer quality breakdown</CardTitle></CardHeader><CardContent>
          <div className="mb-3 flex items-center justify-between text-sm"><span className="text-ink/60">Faithfulness · verified source grounding</span>
            <strong className="text-navy">{answer?.faithfulness_score == null ? "Not calculated" : `${Math.round(answer.faithfulness_score * 100)}%`}</strong></div>
          <div className="mb-2 flex items-center justify-between text-xs"><span className="text-ink/60">Question-term coverage · retrieval coverage</span>
            <strong className="text-navy">{answer?.question_coverage_score == null ? "—" : `${Math.round(answer.question_coverage_score * 100)}%`}</strong></div>
          <div className="mb-4 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-amber-500 transition-all"
            style={{width:`${Math.max(0,Math.min(100,(answer?.question_coverage_score ?? 0)*100))}%`}} /></div>
          <div className="h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-verified transition-all"
            style={{width:`${Math.max(0,Math.min(100,(answer?.faithfulness_score ?? 0)*100))}%`}} /></div>
          <div className="mt-5 h-44 w-full"><ResponsiveContainer width="100%" height="100%"><BarChart data={[
            {name:"Supported",count:answer?.claims.filter(c=>c.status==="SUPPORTED").length ?? 0},
            {name:"Partial",count:answer?.claims.filter(c=>c.status==="PARTIALLY_SUPPORTED").length ?? 0},
            {name:"Review",count:answer?.claims.filter(c=>c.status!=="SUPPORTED" && c.status!=="PARTIALLY_SUPPORTED").length ?? 0},
          ]}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
            <Bar dataKey="count" fill="#0f766e" radius={[6,6,0,0]} /></BarChart></ResponsiveContainer></div>
          <p className="text-xs text-ink/45">Faithfulness measures supported claims with verified quotes. Question-term coverage shows how much of the question appeared in retrieved evidence; 100% faithfulness does not mean every part of a question was answered.</p>
        </CardContent></Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Claim status distribution</CardTitle></CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={[
                    {name:"Supported", value:answer?.claims.filter(c=>c.status==="SUPPORTED").length ?? 0},
                    {name:"Partial", value:answer?.claims.filter(c=>c.status==="PARTIALLY_SUPPORTED").length ?? 0},
                    {name:"Contradicted / review", value:answer?.claims.filter(c=>c.status!=="SUPPORTED" && c.status!=="PARTIALLY_SUPPORTED").length ?? 0},
                  ].filter(x=>x.value>0)} dataKey="value" nameKey="name" outerRadius={88} label>
                    <Cell fill="#0f766e" /><Cell fill="#d97706" /><Cell fill="#dc2626" />
                  </Pie>
                  <Tooltip /><Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {!answer && <p className="text-xs text-ink/45">Ask a question to populate claim status analytics.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Evidence by source document</CardTitle></CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={Object.entries((answer?.evidence ?? []).reduce<Record<string, number>>((acc, item) => {
                  acc[item.filename] = (acc[item.filename] || 0) + 1; return acc;
                }, {})).map(([name,count])=>({name:name.length>18 ? name.slice(0,18)+"…" : name,count}))}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
                  <Bar dataKey="count" fill="#7c3aed" radius={[6,6,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            {!answer && <p className="text-xs text-ink/45">Ask a question to see which documents supplied evidence.</p>}
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
              <p className="whitespace-pre-wrap text-sm leading-7 text-navy">{highlightImportantText(answer.answer)}</p>
              {answer.language_notice && <p className="rounded-card bg-amber-50 p-2 text-xs text-amber-800">{answer.language_notice}</p>}
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
                <div className="flex flex-wrap gap-4 text-xs text-ink/55">
                  <span className="flex items-center gap-1.5"><ShieldCheck size={14} /> Faithfulness: {answer.faithfulness_score === null ? "N/A" : `${Math.round(answer.faithfulness_score * 100)}%`}</span>
                  <span>{answer.claims.length} claims checked</span>
                  <span>{answer.evidence.length} source passages</span>
                </div>
                <Button type="button" variant="secondary" onClick={loadAnswerAudit}>View audit history</Button>
              </div>
              {auditOpen && (
                <div className="rounded-card border border-line bg-slate-50 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <strong className="text-xs text-navy">Audit history</strong>
                    <button type="button" className="text-xs text-accent" onClick={() => setAuditOpen(false)}>Close</button>
                  </div>
                  {auditEvents.length ? auditEvents.map((event, index) => (
                    <div key={index} className="border-t border-line py-2 text-xs">
                      <strong>{event.action}</strong> · {new Date(event.timestamp).toLocaleString()}
                      {event.new_value && <p className="mt-1 text-ink/60">Updated to: {event.new_value}</p>}
                      {String(event.metadata?.reason ?? "").length > 0 && <p className="text-ink/60">Reason: {String(event.metadata?.reason)}</p>}
                    </div>
                  )) : <p className="text-xs text-ink/50">No review or correction events recorded for this answer.</p>}
                </div>
              )}
            </CardContent>
          </Card>

          {answer.llm_assistance && (
            <Card>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-navy"><Sparkles size={15} /> LLM-generated evidence summary</div>
                <p className="text-xs text-ink/55">Status: {answer.llm_assistance.status} · Model: {answer.llm_assistance.model || "Not enabled"}</p>
                {answer.llm_assistance.draft && (
                  <div className="rounded-card border border-review/30 bg-review-bg/40 p-3">
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-review">LLM summary draft — verify against the cited source passages</p>
                    <p className="line-clamp-2 text-sm text-navy">{answer.llm_assistance.draft.split(/[.!?।]\s/)[0].trim().slice(0, 180)}{answer.llm_assistance.draft.split(/[.!?।]\s/)[0].trim().length > 180 ? "…" : ""}</p>
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
                    <p className="mt-2 rounded-md bg-amber-50 px-2 py-2 text-sm leading-6 text-amber-950">“{highlightImportantText(item.quote)}”</p>
                    {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-[11px] text-accent underline">Open original webpage</a>}
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
                    <p className="mt-2 text-sm text-ink/75">{highlightImportantText(claim.correction?.corrected_text || claim.text)}</p>
                    {claim.correction && <p className="mt-1 text-xs font-medium text-amber-700">Reviewer-corrected · {claim.correction.reason}</p>}
                    {claim.explanation && <p className="mt-1 text-xs text-ink/50">{claim.explanation}</p>}
                    {editingClaimId === claim.claim_id ? (
                      <div className="mt-3 space-y-2 rounded-card bg-slate-50 p-3">
                        <label className="block text-xs font-medium text-navy">Corrected statement
                          <textarea value={correctionText} onChange={(event) => setCorrectionText(event.target.value)} rows={3} className="mt-1 w-full rounded-card border border-line bg-white p-2 text-sm" />
                        </label>
                        <label className="block text-xs font-medium text-navy">Reason for correction
                          <textarea value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} rows={2} className="mt-1 w-full rounded-card border border-line bg-white p-2 text-sm" />
                        </label>
                        <div className="flex gap-2">
                          <Button type="button" size="sm" onClick={() => void saveClaimCorrection(claim.claim_id)} disabled={correctionText.trim().length < 3 || correctionReason.trim().length < 5}>Save correction</Button>
                          <Button type="button" size="sm" variant="secondary" onClick={() => setEditingClaimId(null)}>Cancel</Button>
                        </div>
                        <p className="text-[11px] text-ink/45">Revenue Officer only. Original claim and source citation remain unchanged.</p>
                      </div>
                    ) : (
                      <button type="button" className="mt-2 text-xs font-semibold text-accent hover:underline" onClick={() => {
                        setEditingClaimId(claim.claim_id);
                        setCorrectionText(claim.correction?.corrected_text || claim.text);
                        setCorrectionReason(claim.correction?.reason || "");
                      }}>{claim.correction ? "Edit correction" : "Edit / correct defect"}</button>
                    )}
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
