"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  BrainCircuit, CheckCircle2, FileSearch, Loader2, RefreshCw, RotateCcw, UploadCloud,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { LoadingState, ErrorState } from "@/components/ui/States";


type Doc = {
  id: string; filename: string; status: string; docai_status?: string; source_url?: string;
  file_size_bytes?: number; uploaded_at?: string;
};
type DocumentStructure = {
  sections: {
    section_id: string; heading: string | null; text: string;
    page_numbers: number[]; source_spans: { page: number; quote: string }[];
    reconstruction: string;
  }[];
  tables: {
    table_id: string; header: string[]; rows: string[][];
    page_numbers: number[]; continuation_status: string;
  }[];
  page_quality?: {
    page: number; source_type: string;
    metadata: Record<string, any>;
    review_blocks: { text: string; confidence: number; bbox: number[]; reason: string }[];
  }[];
  section_count: number; table_count: number; source_page_count: number;
  warnings: string[];
};
type Job = {
  status: string; pages_total?: number; pages_processed?: number;
  error?: { message?: string }; structure?: DocumentStructure;
};
type ExtractedPage = {
  page: number; text: string; source_type: string;
  extraction_metadata: Record<string, any>;
  layout_blocks: { text: string; confidence?: number; bbox?: number[] }[];
  tables: { header?: string[]; rows?: string[][] }[];
};
type ExtractionResponse = { page_count: number; structure: DocumentStructure; pages: ExtractedPage[] };
type IntelligenceOverview = {
  indexed_document_count: number; page_count: number; entity_count: number; relationship_count: number;
  fields: { id: string; document_id: string; filename: string; page: number; field_type: string;
    label: string; value: string; confidence: number; confidence_basis: string; status: string; quote: string }[];
  visual_review: { document_id: string; filename: string; page: number; signals: string[];
    review_candidates: {text:string;confidence:number}[] }[];
  notice: string;
};
type IntelligenceSearchResult = { document_id: string; filename: string; page: number; score: number; snippet: string; source_type: string };

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
      ? <mark key={index} className="rounded bg-cyan-200 px-1 font-bold text-slate-950 ring-1 ring-cyan-700">{part}</mark>
      : <span key={index}>{part}</span>
  );
}

export default function DocumentAIPage() {
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [indexedIds, setIndexedIds] = useState<string[]>([]);
  const [structures, setStructures] = useState<Record<string, DocumentStructure>>({});
  const [extractedPages, setExtractedPages] = useState<Record<string, ExtractedPage[]>>({});
  const [extractionLoading, setExtractionLoading] = useState<Record<string, boolean>>({});
  const [intelligenceOverview, setIntelligenceOverview] = useState<IntelligenceOverview | null>(null);
  const [intelligenceLoading, setIntelligenceLoading] = useState(false);
  const [intelligenceQuery, setIntelligenceQuery] = useState("");
  const [intelligenceResults, setIntelligenceResults] = useState<IntelligenceSearchResult[]>([]);
  const [intelligenceSearching, setIntelligenceSearching] = useState(false);

  const [reviewOpen, setReviewOpen] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [indexing, setIndexing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [webUrl, setWebUrl] = useState("");
  const [importingWeb, setImportingWeb] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [indexMessage, setIndexMessage] = useState("");
  const [question, setQuestion] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const recognitionRef = useRef<any>(null);
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
          if (job.structure) {
            setStructures((current) => ({ ...current, [id]: job.structure! }));
          }
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


  async function loadExtraction(documentId: string) {
    if (extractedPages[documentId]?.length || extractionLoading[documentId]) return;
    setExtractionLoading((current) => ({ ...current, [documentId]: true }));
    try {
      const result = await api.get<ExtractionResponse>("/api/document-ai/documents/" + documentId + "/extraction");
      setStructures((current) => ({ ...current, [documentId]: result.structure }));
      setExtractedPages((current) => ({ ...current, [documentId]: result.pages || [] }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load extracted pages. Try refreshing or re-indexing the document.");
    } finally {
      setExtractionLoading((current) => ({ ...current, [documentId]: false }));
    }
  }

  async function toggleExtractionReview(documentId: string) {
    const willOpen = !reviewOpen[documentId];
    setReviewOpen((current) => ({ ...current, [documentId]: willOpen }));
    if (willOpen) await loadExtraction(documentId);
  }

  useEffect(() => {
    const ids = selectedDocs.filter((doc) => isIndexed(doc)).map((doc) => doc.id);
    if (!ids.length) {
      setIntelligenceOverview(null);
      setIntelligenceResults([]);
      return;
    }
    let active = true;
    setIntelligenceLoading(true);
    api.get<IntelligenceOverview>("/api/intelligence/overview?document_ids=" + encodeURIComponent(ids.join(",")))
      .then((data) => { if (active) setIntelligenceOverview(data); })
      .catch(() => { if (active) setIntelligenceOverview(null); })
      .finally(() => { if (active) setIntelligenceLoading(false); });
    return () => { active = false; };
  }, [selectedDocs, indexedIds]);

  async function searchIntelligence(event: React.FormEvent) {
    event.preventDefault();
    const ids = selectedDocs.filter((doc) => isIndexed(doc)).map((doc) => doc.id);
    if (!intelligenceQuery.trim() || !ids.length) return;
    setIntelligenceSearching(true);
    try {
      const result = await api.get<{ items: IntelligenceSearchResult[] }>(
        "/api/intelligence/search?q=" + encodeURIComponent(intelligenceQuery.trim()) +
        "&document_ids=" + encodeURIComponent(ids.join(",")) + "&limit=10"
      );
      setIntelligenceResults(result.items || []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Intelligence search failed.");
    } finally {
      setIntelligenceSearching(false);
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

  function toggleVoiceInput() {
    setVoiceError("");

    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setVoiceError("Voice input is not supported in this browser. Try Chrome or Edge.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = language === "hi" ? "hi-IN" : "en-IN";
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event: any) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      if (transcript.trim()) {
        setQuestion((previous) =>
          `${previous}${previous.trim() ? " " : ""}${transcript}`.slice(0, 2000)
        );
      }
    };

    recognition.onerror = (event: any) => {
      setVoiceError(
        event.error === "not-allowed"
          ? "Microphone permission denied. Allow microphone access in browser settings."
          : `Voice input error: ${event.error}`
      );
      setListening(false);
    };

    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;

    try {
      recognition.start();
      setListening(true);
    } catch {
      setVoiceError("Could not start microphone. Please try again.");
      setListening(false);
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
            Upload, index and inspect documents with page-by-page extracted text, reconstructed sections, detected tables and OCR quality review.
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
            <p className="mt-1 text-xs text-ink/50">Upload a file or add a public webpage. Both enter the same extraction, indexing and evidence-search pipeline.</p>
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
              {importingWeb ? <><Loader2 size={14} className="animate-spin" /> Adding source…</> : "Add webpage to pipeline"}
            </Button>
          </div>
          <p className="w-full text-[11px] text-ink/45">Web pages are safely fetched, saved as traceable sources, then processed with the same Index selected documents action. Public HTTPS and administrator allowlisting are required.</p>
        </CardContent>
      </Card>

      <div className="grid gap-5">
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
                    <div key={doc.id} className="space-y-1.5">
                      <label className={`flex cursor-pointer items-start gap-3 rounded-card border p-3 transition-colors ${checked ? "border-accent bg-accent-bg/50" : "border-line hover:bg-slate-50"}`}>
                        <input type="checkbox" checked={checked} onChange={() => toggleDocument(doc.id)} className="mt-1 accent-blue-600" />
                        <span className="min-w-0 flex-1">
                          <span className="block break-words text-sm font-medium text-navy">{doc.filename}</span>
                          <span className="mt-1 flex items-center gap-1.5 text-[11px] text-ink/50">
                            {indexed ? <><CheckCircle2 size={12} className="text-verified" /> Indexed</> : <><FileSearch size={12} /> Ready to index</>}
                          </span>
                        </span>
                      </label>
                      {indexed && (
                        <button type="button" onClick={() => void toggleExtractionReview(doc.id)}
                          disabled={!!extractionLoading[doc.id]}
                          className="ml-8 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold text-accent transition hover:bg-accent-bg disabled:opacity-60">
                          {extractionLoading[doc.id] ? <Loader2 size={12} className="animate-spin" /> : <FileSearch size={12} />}
                          {extractionLoading[doc.id] ? "Loading extracted pages…" : reviewOpen[doc.id] ? "Hide extracted pages" : "View extracted pages"}
                        </button>
                      )}
                    </div>
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

      </div>

      {selectedDocs.some((doc) => structures[doc.id] && reviewOpen[doc.id]) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileSearch size={17} /> Document structure & quality review
            </CardTitle>
            <p className="text-xs text-ink/55">
              Reconstructed sections, detected tables and OCR quality by page.
              Low-confidence text is flagged for human verification, not automatically corrected.
            </p>
          </CardHeader>
          <CardContent className="space-y-5">
            {selectedDocs.filter((doc) => structures[doc.id] && reviewOpen[doc.id]).map((doc) => {
              const structure = structures[doc.id];
              return (
                <div key={doc.id} className="space-y-4 border-b border-line pb-5 last:border-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="break-all text-sm font-semibold text-navy">{doc.filename}</h3>
                    <span className="text-xs text-ink/50">
                      {structure.source_page_count} pages · {structure.section_count} sections · {structure.table_count} tables
                    </span>
                  </div>

                  {structure.page_quality?.length ? (
                    <div className="space-y-2">
                      <h4 className="text-xs font-semibold uppercase tracking-wide text-navy">Page OCR quality</h4>
                      {structure.page_quality.map((page) => {
                        const meta = page.metadata || {};
                        const quality = String(meta.quality_status || "UNKNOWN");
                        const qualityClass =
                          quality === "HIGH" || quality === "TEXT_LAYER_PRESENT"
                            ? "bg-emerald-100 text-emerald-950 ring-emerald-600"
                            : quality === "REVIEW"
                              ? "bg-amber-200 text-amber-950 ring-amber-700"
                              : quality === "LOW" || quality === "EMPTY"
                                ? "bg-rose-200 text-rose-950 ring-rose-700"
                                : "bg-slate-200 text-slate-950 ring-slate-600";
                        return (
                          <div key={page.page} className="rounded-card border border-line p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-sm font-semibold text-navy">Page {page.page}</span>
                              <span className={`rounded px-2 py-1 text-[11px] font-bold ring-1 ${qualityClass}`}>{quality}</span>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-3 text-xs text-ink/60">
                              <span>Source: {page.source_type}</span>
                              <span>Words: {meta.text_word_count ?? "—"}</span>
                              <span>OCR confidence: {typeof meta.ocr_confidence_avg === "number" ? `${Math.round(meta.ocr_confidence_avg * 100)}%` : "Not available"}</span>
                              <span>Tables: {meta.table_count ?? 0}</span>
                            </div>
                            {Array.isArray(meta.warnings) && meta.warnings.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {meta.warnings.map((warning: string, i: number) => (
                                  <span key={i} className="rounded bg-amber-100 px-2 py-1 text-[10px] font-medium text-amber-950">{warning.replaceAll("_", " ")}</span>
                                ))}
                              </div>
                            )}
                            {page.review_blocks?.length > 0 && (
                              <div className="mt-3 rounded-md border border-rose-300 bg-rose-50 p-3">
                                <p className="text-xs font-bold text-rose-950">
                                  {page.review_blocks.length} low-confidence text block(s) — manual review needed
                                </p>
                                {page.review_blocks.map((block, i) => (
                                  <div key={i} className="mt-2 border-t border-rose-200 pt-2">
                                    <p className="break-words text-sm text-rose-950">{block.text || "Unreadable text"}</p>
                                    <p className="mt-1 text-[11px] font-semibold text-rose-800">
                                      Confidence: {Math.round(block.confidence * 100)}% · {block.reason.replaceAll("_", " ")}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-navy">Reconstructed sections</h4>
                    {structure.sections?.length ? structure.sections.map((section) => (
                      <details key={section.section_id} className="rounded-card border border-line p-3">
                        <summary className="cursor-pointer text-sm font-semibold text-navy">
                          {section.heading || "Unheaded text group"}
                          <span className="ml-2 text-[11px] font-normal text-ink/50">
                            Page(s) {section.page_numbers.join(", ")}
                          </span>
                        </summary>
                        <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-ink/80">{section.text}</p>
                        <p className="mt-2 text-[11px] text-ink/45">Grouping: {section.reconstruction.replaceAll("_", " ")}</p>
                        {section.source_spans?.map((span, i) => (
                          <div key={i} className="mt-2 rounded bg-cyan-50 p-2 text-xs text-cyan-950">
                            Source · Page {span.page}: “{span.quote}”
                          </div>
                        ))}
                      </details>
                    )) : <p className="text-xs text-ink/50">No sections were reconstructed.</p>}
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-navy">Detected tables</h4>
                    {structure.tables?.length ? structure.tables.map((table) => (
                      <div key={table.table_id} className="overflow-x-auto rounded-card border border-line">
                        <div className="flex flex-wrap justify-between gap-2 bg-slate-100 p-3 text-xs">
                          <strong className="text-navy">Page(s) {table.page_numbers.join(", ")}</strong>
                          <span className="text-ink/60">{table.continuation_status.replaceAll("_", " ")}</span>
                        </div>
                        <table className="w-full border-collapse text-left text-xs">
                          <thead className="bg-cyan-100 text-cyan-950">
                            <tr>{table.header.map((cell, i) => <th key={i} className="border border-cyan-200 p-2">{cell || "—"}</th>)}</tr>
                          </thead>
                          <tbody>
                            {table.rows.slice(1).map((row, ri) => (
                              <tr key={ri} className="odd:bg-white even:bg-slate-50">
                                {table.header.map((_, ci) => <td key={ci} className="border border-line p-2 text-ink/80">{row[ci] || "—"}</td>)}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )) : <p className="text-xs text-ink/50">No tables detected. Scanned-page OCR table reconstruction is not currently supported.</p>}
                  </div>
                </div>
              );
            })}
            <p className="text-[11px] text-ink/45">
              Note: section grouping is heuristic. OCR confidence measures recognition confidence, not factual correctness.
              Always verify flagged text against the original page.
            </p>
            {selectedDocs.filter((doc) => reviewOpen[doc.id] && extractedPages[doc.id]).map((doc) => (
              <div key={doc.id + "-extracted-pages"} className="space-y-3 border-t border-line pt-4">
                <h3 className="text-sm font-semibold text-navy">Extracted page text · {doc.filename}</h3>
                {extractedPages[doc.id].map((page) => (
                  <details key={page.page} className="rounded-card border border-line bg-slate-50 p-3" open={extractedPages[doc.id].length <= 2}>
                    <summary className="cursor-pointer text-xs font-semibold text-navy">
                      Page {page.page} · {page.source_type} · {page.text.trim().split(/\s+/).filter(Boolean).length} words
                    </summary>
                    <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap break-words font-sans text-xs leading-6 text-ink/80">{page.text || "No text extracted from this page."}</pre>
                  </details>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

    </div>
  );
}
