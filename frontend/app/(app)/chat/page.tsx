"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Bot, Check, ChevronDown, FileText, Loader2, MessageCircle, Plus, Send, ShieldCheck, Sparkles, Trash2, User, X, ExternalLink, BookOpen, Quote, Network, Search, ScanSearch, RefreshCw, Calculator } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import PdfEvidenceViewer from "@/components/PdfEvidenceViewer";
import { LoadingState } from "@/components/ui/States";

type Doc = { id: string; filename: string; file_type?: string; docai_status?: string; status?: string };
type Evidence = { evidence_id: string; filename: string; page_number: number; quote: string; source_url?: string; verification?: { quote_found_in_source?: boolean } };
type Claim = { claim_id: string; text: string; status: string; confidence: number; explanation?: string; correction?: { corrected_text: string; reason: string; corrected_at: string } };
type Conflict = { topic: string; status: string; explanation?: string; evidence: Evidence[] };
type Answer = {
  answer_id?: string; question: string; answer: string; abstained: boolean;
  faithfulness_score: number | null; question_coverage_score?: number;
  claims: Claim[]; evidence: Evidence[]; conflicts: Conflict[];
  missing_evidence?: { description: string }[];
  language_notice?: string | null;
  llm_assistance?: { status: string; draft?: string | null; model?: string | null; notice?: string };
  contextual_follow_up?: boolean;
};
type Message = { id: string; role: "user" | "assistant"; content: string; answer?: Answer; created_at: string };
type Session = { id: string; title: string; document_ids: string[]; updated_at: string; message_count: number; preview?: string };

function renderHighlightedAnswer(content: string, claims: Claim[]) {
  const matches: { start: number; end: number; status: string }[] = [];

  // Highlight only claim text supplied by the evidence analysis, never guessed keywords.
  for (const claim of [...claims].sort((a, b) => b.text.length - a.text.length)) {
    if (!claim.text?.trim()) continue;
    const start = content.toLocaleLowerCase().indexOf(claim.text.trim().toLocaleLowerCase());
    if (start < 0) continue;
    const end = start + claim.text.trim().length;
    if (matches.some(match => start < match.end && end > match.start)) continue;
    matches.push({ start, end, status: claim.status });
  }

  if (!matches.length) return content;
  matches.sort((a, b) => a.start - b.start);

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  matches.forEach((match, index) => {
    if (match.start > cursor) parts.push(content.slice(cursor, match.start));
    const status = match.status.toUpperCase();
    const style = status === "SUPPORTED"
      ? "rounded-[2px] bg-[linear-gradient(transparent_66%,rgba(211,177,103,0.34)_66%)] font-semibold text-[#26364d]"
      : status === "PARTIALLY_SUPPORTED" || status === "INSUFFICIENT_EVIDENCE"
        ? "rounded-[2px] underline decoration-dashed decoration-[#c49a52] decoration-[1.5px] underline-offset-[4px]"
        : status === "CONTRADICTED"
          ? "rounded-[2px] underline decoration-wavy decoration-[#c77b70] decoration-[1.5px] underline-offset-[4px]"
          : "font-medium underline decoration-[#b9c5d5] decoration-[1px] underline-offset-[4px]";
    parts.push(<span key={`claim-${index}`} className={style} title={status.replaceAll("_", " ").toLowerCase()}>{content.slice(match.start, match.end)}</span>);
    cursor = match.end;
  });
  if (cursor < content.length) parts.push(content.slice(cursor));
  return parts;
}

function timeLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ChatPage() {
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const [loading, setLoading] = useState(true);
  const [loadingSession, setLoadingSession] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSources, setShowSources] = useState<Record<string, boolean>>({});
  const [showDocPicker, setShowDocPicker] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const indexedDocs = useMemo(() => documents.filter(d => d.docai_status === "INDEXED"), [documents]);
  const selectedDocs = useMemo(() => indexedDocs.filter(d => selectedIds.includes(d.id)), [indexedDocs, selectedIds]);
  const latestAnswer = useMemo(() => [...messages].reverse().find(message => message.role === "assistant" && message.answer)?.answer, [messages]);
  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null);
  const activeEvidence = latestAnswer?.evidence.find(item => item.evidence_id === activeEvidenceId) || latestAnswer?.evidence[0];

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docs, history] = await Promise.all([
        api.get<Doc[]>("/api/documents"),
        api.get<{ items: Session[] }>("/api/chat/sessions"),
      ]);
      setDocuments(docs);
      setSessions(history.items || []);
      const indexed = docs.filter(d => d.docai_status === "INDEXED").map(d => d.id);
      setSelectedIds(current => current.length ? current.filter(id => indexed.includes(id)) : indexed);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Chat workspace load nahi ho paya.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadWorkspace(); }, [loadWorkspace]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, sending]);

  const openSession = async (id: string) => {
    setLoadingSession(true);
    setError(null);
    try {
      const data = await api.get<{ id: string; document_ids: string[]; messages: Message[] }>(`/api/chat/sessions/${id}`);
      setActiveId(id);
      setMessages(data.messages || []);
      setSelectedIds(data.document_ids || []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Conversation open nahi ho payi.");
    } finally {
      setLoadingSession(false);
    }
  };

  const newChat = () => {
    setActiveId(null);
    setMessages([]);
    setQuestion("");
    setError(null);
    setShowSources({});
    setSelectedIds(indexedDocs.map(d => d.id));
    inputRef.current?.focus();
  };

  const toggleDocument = (id: string) => {
    setSelectedIds(current => current.includes(id) ? current.filter(x => x !== id) : [...current, id]);
  };

  const sendMessage = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = question.trim();
    if (!text || sending) return;
    if (!selectedIds.length) {
      setError("Pehle kam se kam ek indexed document select karo.");
      return;
    }
    setSending(true);
    setError(null);
    const optimistic: Message = {
      id: `pending-${Date.now()}`, role: "user", content: text, created_at: new Date().toISOString(),
    };
    setMessages(current => [...current, optimistic]);
    setQuestion("");
    try {
      const result = await api.post<{ session_id: string; user_message: Message; assistant_message: Message; answer: Answer }>(
        "/api/chat/messages",
        { session_id: activeId, question: text, document_ids: selectedIds, language }
      );
      setActiveId(result.session_id);
      setMessages(current => [...current.filter(m => m.id !== optimistic.id), result.user_message, result.assistant_message]);
      try {
        const history = await api.get<{ items: Session[] }>("/api/chat/sessions");
        setSessions(history.items || []);
      } catch {
        // The answer is already saved; a sidebar refresh failure must not turn
        // a successful send into a retryable/duplicate-looking failure.
      }
    } catch (e) {
      setMessages(current => current.filter(m => m.id !== optimistic.id));
      setQuestion(text);
      setError(e instanceof ApiError ? e.message : "Message send nahi ho paya. Please retry.");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const removeSession = async (id: string) => {
    try {
      await api.delete(`/api/chat/sessions/${id}`);
      setSessions(current => current.filter(s => s.id !== id));
      if (activeId === id) newChat();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Conversation delete nahi ho payi.");
    }
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  };

  if (loading) return <LoadingState label="Loading TrustLens AI Chat…" />;

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] overflow-hidden rounded-2xl border border-line bg-white shadow-card">
      <aside className="hidden w-72 shrink-0 flex-col border-r border-line bg-slate-50/80 md:flex">
        <div className="flex items-center justify-between border-b border-line p-4">
          <div><p className="font-semibold text-navy">Conversations</p><p className="text-xs text-ink/45">Your saved RAG chats</p></div>
          <Button size="sm" onClick={newChat}><Plus size={14}/> New</Button>
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto p-2">
          {sessions.length ? sessions.map(session => (
            <div key={session.id} className={`group flex items-start gap-1 rounded-xl p-2 ${activeId === session.id ? "bg-blue-100/80" : "hover:bg-white"}`}>
              <button onClick={() => void openSession(session.id)} className="min-w-0 flex-1 text-left">
                <p className="truncate text-sm font-medium text-navy">{session.title}</p>
                <p className="mt-1 line-clamp-2 text-xs text-ink/45">{session.preview || "No messages yet"}</p>
                <p className="mt-1 text-[10px] text-ink/35">{session.message_count} messages</p>
              </button>
              <button aria-label="Delete conversation" onClick={() => void removeSession(session.id)} className="rounded p-1 text-ink/30 opacity-0 hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"><Trash2 size={13}/></button>
            </div>
          )) : <p className="p-3 text-xs text-ink/45">No saved conversations yet.</p>}
        </div>
        <div className="border-t border-line p-3 text-[11px] leading-5 text-ink/45">
          <ShieldCheck size={13} className="mr-1 inline text-verified"/> Chats are private to your account.
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-bg text-accent"><Bot size={21}/></div>
            <div><h1 className="font-serif text-lg font-semibold text-navy">TrustLens AI Assistant</h1><p className="text-xs text-ink/45">Evidence-first document conversations</p></div>
          </div>
          <div className="flex items-center gap-2">
            <select value={language} onChange={e => setLanguage(e.target.value as "en" | "hi")} className="rounded-lg border border-line bg-white px-2 py-2 text-xs text-navy" aria-label="Response language">
              <option value="en">English</option><option value="hi">हिन्दी</option>
            </select>
            <div className="flex items-center gap-2">
              <select aria-label="Open recent conversation" value={activeId || ""} onChange={e => e.target.value ? void openSession(e.target.value) : newChat()} className="max-w-36 rounded-lg border border-line bg-white px-2 py-2 text-xs text-navy md:hidden">
                <option value="">Recent chats</option>
                {sessions.map(session => <option key={session.id} value={session.id}>{session.title}</option>)}
              </select>
              <Button size="sm" variant="secondary" onClick={newChat} className="md:hidden"><Plus size={14}/> New chat</Button>
            </div>
          </div>
        </header>

        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3 sm:px-6">
          <button onClick={() => setShowDocPicker(v => !v)} className="flex max-w-full items-center gap-2 rounded-full border border-line bg-slate-50 px-3 py-2 text-xs text-navy hover:bg-slate-100">
            <FileText size={14}/><span className="max-w-[230px] truncate">{selectedDocs.length ? `${selectedDocs.length} indexed document(s) selected` : "Select indexed documents"}</span><ChevronDown size={13}/>
          </button>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-800"><ShieldCheck size={12}/> Evidence-backed answers</span>
          {showDocPicker && <div className="basis-full rounded-xl border border-line bg-white p-3 shadow-sm">
            <div className="mb-2 flex items-center justify-between"><p className="text-xs font-semibold text-navy">Search scope</p><button onClick={() => setShowDocPicker(false)} aria-label="Close document picker"><X size={14}/></button></div>
            {indexedDocs.length ? <div className="grid max-h-48 gap-2 overflow-y-auto sm:grid-cols-2">
              {indexedDocs.map(doc => <label key={doc.id} className="flex cursor-pointer items-center gap-2 rounded-lg bg-slate-50 p-2 text-xs text-ink/75">
                <input type="checkbox" checked={selectedIds.includes(doc.id)} onChange={() => toggleDocument(doc.id)} className="accent-blue-600"/>
                <span className="truncate">{doc.filename}</span><Check size={12} className={selectedIds.includes(doc.id) ? "ml-auto text-emerald-600" : "ml-auto text-transparent"}/>
              </label>)}
            </div> : <p className="text-xs text-ink/45">No indexed documents. Upload and index files in Document AI first.</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              <button onClick={() => setSelectedIds(indexedDocs.map(d => d.id))} className="text-xs text-accent">Select all</button>
              <button onClick={() => setSelectedIds([])} className="text-xs text-ink/50">Clear selection</button>
            </div>
          </div>}
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto bg-[#fbfcfe] px-4 py-5 sm:px-6">
          {loadingSession && <div className="flex justify-center"><Loader2 className="animate-spin text-accent"/></div>}
          {!messages.length && !loadingSession && (
            <div className="mx-auto flex min-h-[380px] max-w-2xl flex-col items-center justify-center text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-bg text-accent"><MessageCircle size={30}/></div>
              <h2 className="font-serif text-2xl font-semibold text-navy">Ask your documents anything.</h2>
              <p className="mt-2 max-w-lg text-sm leading-6 text-ink/55">TrustLens retrieves passages from your selected indexed documents, verifies source quotes and shows where each answer came from. If evidence is missing, it can abstain instead of guessing.</p>
              <div className="mt-6 grid w-full gap-2 text-left sm:grid-cols-2">
                {["Summarize the key obligations in these documents","Find deadlines, amounts or eligibility rules","Compare conflicting clauses across documents","What information is missing from the selected sources?"].map(prompt => <button key={prompt} onClick={() => { setQuestion(prompt); inputRef.current?.focus(); }} className="rounded-xl border border-line bg-white p-3 text-xs text-ink/65 transition hover:border-accent/40 hover:bg-blue-50/50"><Sparkles size={13} className="mb-2 text-accent"/>{prompt}</button>)}
              </div>
            </div>
          )}

          {messages.map(message => (
            <div key={message.id} className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
              {message.role === "assistant" && <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-bg text-accent"><Bot size={17}/></div>}
              <div className={`min-w-0 max-w-[min(92%,780px)] rounded-2xl p-4 ${message.role === "user" ? "bg-[#173B70] text-white" : "border border-line bg-white text-navy shadow-sm"}`}>
                {message.role === "user" ? <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p> : (
                  <div className="space-y-3">
                    <div className="whitespace-pre-wrap break-words text-sm leading-7">{message.answer?.abstained && <span className="mb-2 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-800"><AlertCircle size={12}/> Insufficient evidence</span>}{renderHighlightedAnswer(message.content, message.answer?.claims || [])}</div>
                    {message.answer?.llm_assistance?.draft && <div className="rounded-lg border border-violet-100 bg-violet-50/60 p-3"><p className="mb-1 text-[10px] font-bold uppercase tracking-wide text-violet-700">Optional AI draft · unverified</p><p className="whitespace-pre-wrap text-sm text-violet-950">{message.answer.llm_assistance.draft}</p></div>}
                    {!!message.answer?.evidence?.length && <div className="border-t border-line pt-3">
                      <button onClick={() => setShowSources(current => ({ ...current, [message.id]: !current[message.id] }))} className="flex items-center gap-2 text-xs font-semibold text-accent"><FileText size={13}/> {message.answer.evidence.length} source passage(s)<ChevronDown size={13}/></button>
                      {showSources[message.id] && <div className="mt-3 space-y-2">
                        {message.answer.evidence.map(ev => <div key={ev.evidence_id} className="rounded-lg border border-line bg-slate-50 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span className="font-semibold text-navy">{ev.filename}</span><span className="rounded bg-white px-2 py-1 text-ink/55">Page {ev.page_number}</span></div>
                          <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-ink/75">“{ev.quote}”</p>
                          <p className={`mt-2 text-[10px] ${ev.verification?.quote_found_in_source ? "text-emerald-700" : "text-amber-700"}`}>{ev.verification?.quote_found_in_source ? "Source quote verified" : "Verification status unavailable"}</p>
                          {ev.source_url && <a href={ev.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-[10px] text-accent underline">Open source</a>}
                        </div>)}
                      </div>}
                    </div>}
                    {!!message.answer?.claims?.length && <div className="rounded-lg border border-line bg-slate-50 p-3"><p className="mb-2 text-xs font-semibold text-navy">Claim verification breakdown</p><div className="space-y-2">{message.answer.claims.map(claim => <div key={claim.claim_id} className="flex flex-wrap items-start justify-between gap-2 text-xs"><span className="min-w-0 flex-1 text-ink/70">{claim.text}</span><span className="shrink-0 rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-navy">{claim.status.replaceAll("_"," ")} · {Math.round(claim.confidence*100)}%</span></div>)}</div></div>}
                    {!!message.answer?.answer_id && <AnswerAuditPanel answerId={message.answer.answer_id}/>}
                    {!!message.answer?.answer_id && message.answer.claims.map(claim => <ClaimReviewControl key={claim.claim_id} answerId={message.answer!.answer_id!} claim={claim}/>)}{!!message.answer?.conflicts?.length && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3"><p className="text-xs font-semibold text-amber-900">Potential conflicts detected</p>{message.answer.conflicts.map((c,i) => <p key={i} className="mt-1 text-xs text-amber-900">{c.topic}: {c.explanation || c.status}</p>)}</div>}
                    {message.answer?.missing_evidence?.map((item,i) => <p key={i} className="text-xs text-amber-700">{item.description}</p>)}
                    <div className="flex flex-wrap items-center gap-3 border-t border-line pt-2 text-[10px] text-ink/40">
                      <span>{message.answer?.faithfulness_score == null ? "Faithfulness not scored" : `Evidence grounding: ${Math.round(message.answer.faithfulness_score * 100)}%`}</span>
                      {message.answer?.question_coverage_score != null && <span>Question coverage: {Math.round(message.answer.question_coverage_score * 100)}%</span>}{message.answer?.contextual_follow_up && <span>Conversation context used</span>}
                      <span>{timeLabel(message.created_at)}</span>
                    </div>
                    {message.answer?.language_notice && <p className="text-xs text-amber-700">{message.answer.language_notice}</p>}
                  </div>
                )}
              </div>
              {message.role === "user" && <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-600"><User size={16}/></div>}
            </div>
          ))}
          {sending && <div className="flex items-center gap-2 text-xs text-ink/45"><Loader2 size={14} className="animate-spin"/> Searching and verifying document evidence…</div>}
          <div ref={bottomRef}/>
        </div>

        {error && <div role="alert" className="mx-4 mb-2 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800 sm:mx-6"><AlertCircle size={15} className="mt-0.5 shrink-0"/><span className="flex-1">{error}</span><button onClick={() => setError(null)} aria-label="Dismiss error"><X size={14}/></button></div>}
        <form onSubmit={sendMessage} className="border-t border-line bg-white p-4 sm:px-6">
          <div className="mx-auto flex max-w-4xl items-end gap-2 rounded-2xl border border-line bg-slate-50 p-2 focus-within:border-accent/50 focus-within:ring-2 focus-within:ring-accent/10">
            <textarea ref={inputRef} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={onComposerKeyDown} rows={1} maxLength={2000} placeholder={selectedIds.length ? "Ask a question about your selected documents…" : "Select at least one indexed document to start"} disabled={sending} className="max-h-36 min-h-11 flex-1 resize-y bg-transparent px-2 py-3 text-sm text-navy outline-none placeholder:text-ink/35 disabled:opacity-60"/>
            <Button type="submit" disabled={!question.trim() || sending || !selectedIds.length} className="mb-1"><Send size={15}/><span className="hidden sm:inline">Send</span></Button>
          </div>
          <div className="mx-auto mt-2 flex max-w-4xl flex-wrap items-center justify-between gap-2 text-[10px] text-ink/40"><span>Enter to send · Shift + Enter for new line · Max 2,000 characters</span><span>{selectedIds.length} document(s) in scope · Answers cite source passages</span></div>
        </form>
      </section>

      <aside className="hidden w-[320px] shrink-0 flex-col border-l border-line bg-white xl:flex">
        <div className="border-b border-line px-4 py-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-navy"><BookOpen size={16} className="text-accent"/> Evidence inspector</div>
          <p className="mt-1 text-[11px] leading-5 text-ink/45">Source passages supporting the latest answer.</p>
        </div>
        {latestAnswer ? (
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            <div className="rounded-xl border border-line bg-slate-50 p-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-ink/45">Answer status</p>
              <p className={latestAnswer.abstained ? "mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-amber-700" : "mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700"}>
                <ShieldCheck size={14}/>{latestAnswer.abstained ? "Insufficient evidence" : "Evidence-backed response"}
              </p>
              <p className="mt-2 text-xs text-ink/55">{latestAnswer.evidence.length} source passage(s) · {latestAnswer.claims.length} claims checked</p>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between"><h3 className="text-xs font-semibold text-navy">Retrieved sources</h3><span className="text-[10px] text-ink/40">{latestAnswer.evidence.length} found</span></div>
              {latestAnswer.evidence.length ? (
                <div className="space-y-2">
                  {latestAnswer.evidence.map((item, index) => (
                    <button key={item.evidence_id} onClick={() => setActiveEvidenceId(item.evidence_id)} className={activeEvidence?.evidence_id === item.evidence_id ? "w-full rounded-xl border border-accent/50 bg-blue-50/60 p-3 text-left transition" : "w-full rounded-xl border border-line bg-white p-3 text-left transition hover:bg-slate-50"}>
                      <div className="flex items-start gap-2"><FileText size={15} className="mt-0.5 shrink-0 text-accent"/><span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold text-navy">{item.filename}</span><span className="mt-1 block text-[10px] text-ink/45">Source {index + 1} · Page {item.page_number}</span></span>{item.verification?.quote_found_in_source && <Check size={13} className="shrink-0 text-emerald-600"/>}</div>
                    </button>
                  ))}
                </div>
              ) : <p className="rounded-xl border border-dashed border-line p-3 text-xs text-ink/45">No supporting passages were returned for this answer.</p>}
            </div>
            {activeEvidence && (
              <div className="rounded-xl border border-line p-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-navy"><Quote size={13} className="text-accent"/> Source excerpt</div>
                <p className="mt-3 whitespace-pre-wrap text-xs leading-6 text-ink/75">“{activeEvidence.quote}”</p>
                {(() => {
                  const sourceDoc = documents.find((doc) => doc.filename === activeEvidence.filename);
                  const isPdf = sourceDoc?.file_type === "application/pdf" || activeEvidence.filename.toLowerCase().endsWith(".pdf");
                  return sourceDoc && isPdf ? (
                    <div className="mt-3">
                      <PdfEvidenceViewer documentId={sourceDoc.id} pageNumber={activeEvidence.page_number} quote={activeEvidence.quote}/>
                    </div>
                  ) : null;
                })()}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3"><span className="text-[10px] text-ink/45">{activeEvidence.filename} · Page {activeEvidence.page_number}</span><span className={activeEvidence.verification?.quote_found_in_source ? "text-[10px] font-medium text-emerald-700" : "text-[10px] font-medium text-amber-700"}>{activeEvidence.verification?.quote_found_in_source ? "Quote verified" : "Verification unavailable"}</span></div>
                {activeEvidence.source_url && <a href={activeEvidence.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-accent hover:underline">Open source <ExternalLink size={11}/></a>}
              </div>
            )}
            {!!latestAnswer.conflicts.length && <div className="rounded-xl border border-amber-200 bg-amber-50 p-3"><p className="text-xs font-semibold text-amber-900">Potential conflicts</p>{latestAnswer.conflicts.map((conflict,index)=><p key={index} className="mt-2 text-xs leading-5 text-amber-900">{conflict.topic}: {conflict.explanation || conflict.status}</p>)}</div>}
          </div>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-bg text-accent"><BookOpen size={20}/></div>
            <p className="mt-3 text-sm font-semibold text-navy">Evidence appears here</p>
            <p className="mt-1 text-xs leading-5 text-ink/45">Ask a question to inspect cited passages, source pages and verification details alongside the conversation.</p>
          </div>
        )}
        <div className="border-t border-line p-3 text-[10px] leading-5 text-ink/40"><ShieldCheck size={12} className="mr-1 inline text-verified"/> Only retrieved source evidence is shown here.</div>
      </aside>
    </div>
      <DocumentIntelligencePanel documents={indexedDocs} />
      <FinancialCalculatorPanel />
    </div>
  );
}

function ClaimReviewControl({ answerId, claim }: { answerId: string; claim: Claim }) {
  const [open,setOpen] = useState(false);
  const [corrected,setCorrected] = useState(claim.correction?.corrected_text || claim.text);
  const [reason,setReason] = useState(claim.correction?.reason || "");
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState("");
  async function save() {
    if (corrected.trim().length < 3 || reason.trim().length < 5) return;
    setBusy(true); setNotice("");
    try {
      await api.post(`/api/document-ai/claims/${claim.claim_id}/correct`, {
        corrected_text: corrected.trim(), reason: reason.trim()
      });
      setNotice("Reviewer correction saved. The original source quote remains unchanged.");
      setOpen(false);
    } catch(e) {
      setNotice(e instanceof ApiError ? e.message : "Correction could not be saved. Reviewer permission may be required.");
    } finally { setBusy(false); }
  }
  return <div className="rounded-lg border border-line bg-white p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-[10px] font-semibold uppercase tracking-wide text-ink/45">Claim review</p><p className="mt-1 text-xs text-navy">{claim.correction?.corrected_text || claim.text}</p>{claim.correction && <p className="mt-1 text-[10px] text-amber-700">Previously corrected: {claim.correction.reason}</p>}</div><button onClick={()=>setOpen(v=>!v)} className="rounded-md border border-line px-2 py-1.5 text-[10px] font-semibold text-accent">{open ? "Close" : claim.correction ? "Edit correction" : "Correct claim"}</button></div>
    {open && <div className="mt-3 space-y-2"><label className="block text-[10px] font-medium text-ink/60">Corrected statement<textarea value={corrected} onChange={e=>setCorrected(e.target.value)} rows={2} className="mt-1 w-full rounded-md border border-line p-2 text-xs"/></label><label className="block text-[10px] font-medium text-ink/60">Reason<textarea value={reason} onChange={e=>setReason(e.target.value)} rows={2} className="mt-1 w-full rounded-md border border-line p-2 text-xs"/></label><button onClick={()=>void save()} disabled={busy || corrected.trim().length<3 || reason.trim().length<5} className="rounded-md bg-navy px-3 py-2 text-[10px] font-semibold text-white disabled:opacity-50">{busy ? "Saving…" : "Save reviewer correction"}</button><p className="text-[10px] text-ink/40">Restricted by backend reviewer permissions. The original evidence and quote are preserved.</p></div>}
    {notice && <p className="mt-2 text-[10px] text-ink/60">{notice}</p>}
  </div>;
}

function AnswerAuditPanel({ answerId }: { answerId: string }) {
  const [open,setOpen] = useState(false);
  const [events,setEvents] = useState<Record<string,any>[]>([]);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  async function load() {
    if (open) { setOpen(false); return; }
    setBusy(true); setError("");
    try {
      const result = await api.get<{items: Record<string,any>[]}>(`/api/document-ai/answers/${answerId}/audit`);
      setEvents(result.items || []); setOpen(true);
    } catch(e) { setError(e instanceof ApiError ? e.message : "Audit history is unavailable."); }
    finally { setBusy(false); }
  }
  return <div className="rounded-lg border border-line bg-white p-3">
    <button onClick={()=>void load()} disabled={busy} className="text-xs font-semibold text-accent">{busy ? "Loading audit…" : open ? "Hide answer audit history" : "View answer audit history"}</button>
    {error && <p className="mt-2 text-[10px] text-rose-700">{error}</p>}
    {open && <div className="mt-2 space-y-2">{events.length ? events.map((event,index)=><div key={index} className="border-t border-line pt-2 text-[10px] text-ink/60"><strong className="text-navy">{String(event.action || "Event")}</strong> · {String(event.timestamp || "")}{event.new_value && <p>Updated to: {String(event.new_value)}</p>}{event.metadata?.reason && <p>Reason: {String(event.metadata.reason)}</p>}</div>) : <p className="text-[10px] text-ink/45">No audit events recorded for this answer yet.</p>}</div>}
  </div>;
}

type IntelligenceNode = { id: string; type: string; label: string; document_id?: string };
type IntelligenceEdge = { id: string; source: string; target: string; type: string; document_id?: string; page?: number };
type IntelligenceField = { id: string; filename: string; document_id: string; page: number; field_type: string; label: string; value: string; confidence: number; confidence_basis: string; status: string; quote: string };
type IntelligenceReview = { document_id: string; filename: string; page: number; signals: string[]; review_candidates: { text: string; confidence: number; bbox: number[] }[]; analysis_status: string };
type IntelligenceData = { indexed_document_count: number; page_count: number; entity_count: number; relationship_count: number; nodes: IntelligenceNode[]; edges: IntelligenceEdge[]; fields: IntelligenceField[]; visual_review: IntelligenceReview[]; notice: string };
type IntelligenceSearchResult = { document_id: string; filename: string; page: number; score: number; matched_terms: string[]; snippet: string; source_type: string };

function DocumentIntelligencePanel({ documents }: { documents: Doc[] }) {
  const [data, setData] = useState<IntelligenceData | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<IntelligenceSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [contradictions, setContradictions] = useState<Record<string, any>[]>([]);
  const [amendments, setAmendments] = useState<Record<string, any>[]>([]);
  const [filter, setFilter] = useState("ALL");
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const ids = useMemo(() => documents.map(doc => doc.id), [documents]);

  const load = useCallback(async () => {
    if (!ids.length) { setData(null); return; }
    setLoading(true); setError("");
    try {
      const query = encodeURIComponent(ids.join(","));
      const [response, conflictResponse, amendmentResponse] = await Promise.all([
        api.get<IntelligenceData>("/api/intelligence/overview?document_ids=" + query),
        api.get<{items: Record<string, any>[]}>(`/api/document-ai/contradictions?document_ids=${query}&limit=100`),
        api.get<{items: Record<string, any>[]}>(`/api/document-ai/amendments?document_ids=${query}&limit=100`),
      ]);
      setData(response);
      setContradictions(conflictResponse.items || []);
      setAmendments(amendmentResponse.items || []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Document intelligence could not be loaded.");
    } finally { setLoading(false); }
  }, [ids]);

  useEffect(() => { void load(); }, [load]);

  const runSearch = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim() || !ids.length) return;
    setSearching(true); setError("");
    try {
      const response = await api.get<{ items: IntelligenceSearchResult[] }>(
        "/api/intelligence/search?q=" + encodeURIComponent(query.trim()) + "&document_ids=" + encodeURIComponent(ids.join(",")) + "&limit=20"
      );
      setResults(response.items || []);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Search failed."); }
    finally { setSearching(false); }
  };

  const graphNodes = useMemo(() => {
    const nodes = (data?.nodes || []).slice(0, 32);
    return nodes.map((node, index) => ({
      ...node,
      x: 360 + Math.cos((2 * Math.PI * index) / Math.max(nodes.length, 1)) * 145,
      y: 190 + Math.sin((2 * Math.PI * index) / Math.max(nodes.length, 1)) * 145,
    }));
  }, [data]);
  const positions = useMemo(() => Object.fromEntries(graphNodes.map(node => [node.id, { x: node.x, y: node.y }])), [graphNodes]);
  const visibleFields = (data?.fields || []).filter(field => filter === "ALL" || field.status === filter);
  const selectedNode = data?.nodes.find(node => node.id === activeNode);

  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-white shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-5">
        <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">TrustLens AI intelligence</p><h2 className="mt-1 flex items-center gap-2 font-serif text-xl font-semibold text-navy"><Network size={18}/> Document Intelligence Centre</h2><p className="mt-1 text-xs text-ink/50">Knowledge graph, entity candidates, extraction confidence, visual review and indexed-page search.</p></div>
        <button onClick={() => void load()} disabled={loading || !ids.length} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-navy disabled:opacity-50"><RefreshCw size={13} className={loading ? "animate-spin" : ""}/> Refresh</button>
      </div>
      {!ids.length ? <p className="p-6 text-sm text-ink/50">Upload and index documents in Document AI. Indexed documents will automatically become available here.</p> :
      loading && !data ? <p className="p-6 text-sm text-ink/50">Building intelligence workspace…</p> : <>
        {error && <p className="m-4 rounded-lg bg-rose-50 p-3 text-xs text-rose-800">{error}</p>}
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Indexed documents", data?.indexed_document_count ?? 0],
            ["Source pages", data?.page_count ?? 0],
            ["Entity candidates", data?.entity_count ?? 0],
            ["Relationships", data?.relationship_count ?? 0],
          ].map(([label, value]) => <div key={String(label)} className="rounded-xl bg-slate-50 p-3"><p className="text-[11px] text-ink/50">{label}</p><p className="mt-1 text-2xl font-semibold text-navy">{value}</p></div>)}
        </div>
        <div className="grid gap-4 p-4 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="overflow-hidden rounded-xl border border-line">
            <div className="flex items-center justify-between border-b border-line p-3"><div><h3 className="flex items-center gap-2 text-sm font-semibold text-navy"><Network size={15}/> Relationship Knowledge Graph</h3><p className="text-[11px] text-ink/45">Select a node to inspect its type.</p></div><span className="text-xs text-ink/45">{data?.nodes.length || 0} nodes</span></div>
            {(data?.nodes.length || 0) ? <div className="overflow-x-auto bg-slate-50 p-2">
              <svg viewBox="0 0 720 390" className="h-[330px] min-w-[560px] w-full" role="img" aria-label="Document relationship graph">
                {data?.edges.map(edge => { const a = positions[edge.source], b = positions[edge.target]; return a && b ? <line key={edge.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#cbd5e1" strokeWidth="1.4"/> : null; })}
                {graphNodes.map(node => <g key={node.id} onClick={() => setActiveNode(node.id)} className="cursor-pointer"><circle cx={node.x} cy={node.y} r={activeNode === node.id ? 13 : 10} fill={node.type === "DOCUMENT" ? "#17324d" : node.type === "OWNER" ? "#b58a42" : node.type === "PROPERTY_ID" ? "#0f766e" : "#64748b"} stroke={activeNode === node.id ? "#fbbf24" : "#fff"} strokeWidth="3"/><text x={node.x} y={node.y + 24} textAnchor="middle" fontSize="10" fill="#334155">{node.label.length > 18 ? node.label.slice(0,18) + "…" : node.label}</text></g>)}
              </svg>
            </div> : <p className="p-8 text-center text-xs text-ink/45">No relationship data found yet.</p>}
            {selectedNode && <p className="border-t border-line bg-slate-50 p-3 text-xs"><strong>{selectedNode.label}</strong> · {selectedNode.type.replaceAll("_"," ")} <button onClick={() => setActiveNode(null)} className="float-right text-accent">Clear</button></p>}
          </div>
          <div className="rounded-xl border border-line p-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-navy"><Search size={15}/> Natural Language Document Search</h3>
            <p className="mt-1 text-[11px] text-ink/45">Search indexed source pages by names, survey numbers, dates or clauses.</p>
            <form onSubmit={runSearch} className="mt-3 space-y-2"><textarea value={query} onChange={e => setQuery(e.target.value)} rows={3} placeholder="e.g. Find pages mentioning survey number 42" className="w-full rounded-lg border border-line p-3 text-xs text-navy"/><button disabled={searching || query.trim().length < 2} className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-navy px-3 py-2.5 text-xs font-medium text-white disabled:opacity-50">{searching ? "Searching…" : <><Search size={13}/> Search indexed pages</>}</button></form>
            <p className="mt-2 text-[10px] text-ink/40">Uses BM25 lexical ranking; results are source passages, not legal conclusions.</p>
          </div>
        </div>
        {!!results.length && <div className="space-y-2 border-b border-line px-4 pb-4"><h3 className="text-xs font-semibold text-navy">Search results ({results.length})</h3>{results.map((result,index) => <article key={result.document_id + result.page + index} className="rounded-lg border border-line p-3"><div className="flex justify-between gap-2 text-xs"><strong>{result.filename}</strong><span className="text-ink/45">Page {result.page} · {result.score.toFixed(2)}</span></div><p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-ink/70">{result.snippet}</p></article>)}</div>}
        <div className="grid gap-4 border-t border-line p-4 xl:grid-cols-2">
          <div><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 text-sm font-semibold text-navy"><ShieldCheck size={15}/> AI Confidence & Verification</h3><select value={filter} onChange={e => setFilter(e.target.value)} className="rounded-lg border border-line px-2 py-1.5 text-xs"><option value="ALL">All statuses</option><option value="VERIFIED">Source verified</option><option value="NEEDS_REVIEW">Needs review</option><option value="UNCERTAIN">Uncertain</option></select></div>
            <div className="mb-3 grid grid-cols-3 gap-2">{["VERIFIED","NEEDS_REVIEW","UNCERTAIN"].map(status => <div key={status} className="rounded-lg bg-slate-50 p-2"><p className="text-[10px] text-ink/45">{status.replaceAll("_"," ")}</p><p className="text-lg font-semibold text-navy">{data?.fields.filter(field => field.status === status).length || 0}</p></div>)}</div>
            <div className="max-h-[440px] space-y-2 overflow-y-auto">{visibleFields.slice(0,80).map(field => <article key={field.id} className="rounded-lg border border-line p-3"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-xs text-navy">{field.value}</strong><span className="text-[10px] text-ink/45">{Math.round(field.confidence*100)}% · {field.status}</span></div><p className="mt-1 text-[11px] text-ink/50">{field.label} · {field.filename} · Page {field.page}</p><p className="mt-2 text-xs text-ink/65">“{field.quote}”</p></article>)}</div>
            <p className="mt-2 text-[10px] text-ink/40">Confidence reflects extraction reliability, not legal correctness.</p>
          </div>
          <div><h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-navy"><ScanSearch size={15}/> Handwriting & Stamp Review Candidates</h3><div className="max-h-[520px] space-y-2 overflow-y-auto">{(data?.visual_review || []).map((item,index) => <article key={item.document_id + item.page + index} className="rounded-lg border border-amber-200 bg-amber-50/50 p-3"><div className="flex justify-between gap-2 text-xs"><strong>{item.filename}</strong><span>Page {item.page}</span></div>{item.signals.map((signal,i)=><p key={i} className="mt-1 text-xs text-ink/65">• {signal}</p>)}{item.review_candidates.length > 0 && <p className="mt-2 text-[10px] text-amber-800">{item.review_candidates.length} low-confidence OCR region(s) flagged.</p>}</article>)}{!data?.visual_review.length && <p className="text-xs text-ink/45">No current visual-review candidates.</p>}</div><p className="mt-2 text-[10px] text-ink/40">These are manual-review signals, not signature, handwriting or stamp authentication.</p></div>
        </div>
        <div className="grid gap-4 border-t border-line p-4 xl:grid-cols-2">
          <div><h3 className="mb-2 text-sm font-semibold text-navy">Cross-document contradictions</h3>{contradictions.length ? contradictions.slice(0,30).map((item,index)=><article key={String(item.contradiction_id || index)} className="mb-2 rounded-lg border border-amber-200 bg-amber-50/50 p-3"><p className="text-xs font-semibold text-amber-900">{String(item.topic || "Potential inconsistency")} · {String(item.status || "REVIEW")}</p><p className="mt-1 text-[11px] text-ink/65">{String(item.explanation || "Compare the attached source passages before drawing a conclusion.")}</p>{Array.isArray(item.evidence) && item.evidence.slice(0,3).map((ev:any,i:number)=><p key={i} className="mt-1 text-[10px] text-ink/55">{String(ev.filename || "Source")} · Page {String(ev.page_number || "?")}: “{String(ev.quote || "")}”</p>)}</article>) : <p className="text-xs text-ink/45">No contradiction candidates returned for the selected documents.</p>}</div>
          <div><h3 className="mb-2 text-sm font-semibold text-navy">Document amendment history</h3>{amendments.length ? amendments.slice(0,30).map((item,index)=><article key={String(item.amendment_id || index)} className="mb-2 rounded-lg border border-line p-3"><div className="flex justify-between gap-2 text-xs"><strong className="text-navy">{String(item.topic || "Amendment")}</strong><span className="text-ink/45">{String(item.status || "Review required")}</span></div><p className="mt-1 text-[11px] text-ink/55">Effective from: {String(item.effective_from || "Not established")}</p></article>) : <p className="text-xs text-ink/45">No amendment chain was detected in the selected documents.</p>}</div>
        </div>
        <p className="border-t border-line p-4 text-[10px] leading-5 text-ink/45">{data?.notice}</p>
      </>}
    </section>
  );
}

type CalculationResult = { formula: string; working: string; notice: string; calculation_type: string; result: Record<string, number> };
function FinancialCalculatorPanel() {
  const [kind,setKind] = useState<"simple_interest"|"compound_interest"|"emi">("simple_interest");
  const [principal,setPrincipal] = useState("100000");
  const [rate,setRate] = useState("8");
  const [duration,setDuration] = useState("2");
  const [unit,setUnit] = useState<"years"|"months">("years");
  const [result,setResult] = useState<CalculationResult|null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  async function calculate() {
    setBusy(true); setError("");
    try { setResult(await api.post<CalculationResult>("/api/document-ai/calculate",{calculation_type:kind,principal:Number(principal),annual_rate_percent:Number(rate),duration_value:Number(duration),duration_unit:unit,compounding_frequency:12})); }
    catch(e) { setError(e instanceof ApiError ? e.message : "Calculation failed."); setResult(null); }
    finally { setBusy(false); }
  }
  return <section className="rounded-2xl border border-line bg-white p-5 shadow-card"><h2 className="flex items-center gap-2 font-serif text-lg font-semibold text-navy"><Calculator size={17}/> Financial & Loan Calculator</h2><p className="mt-1 text-xs text-ink/50">Simple interest, compound interest and EMI with transparent working. Values are user-provided, not verified document facts.</p><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
    <label className="text-xs text-ink/60">Calculation<select value={kind} onChange={e=>setKind(e.target.value as typeof kind)} className="mt-1 w-full rounded-lg border border-line p-2 text-sm"><option value="simple_interest">Simple interest</option><option value="compound_interest">Compound interest</option><option value="emi">Loan EMI</option></select></label>
    <label className="text-xs text-ink/60">Principal (₹)<input type="number" min="1" value={principal} onChange={e=>setPrincipal(e.target.value)} className="mt-1 w-full rounded-lg border border-line p-2 text-sm"/></label>
    <label className="text-xs text-ink/60">Annual rate (%)<input type="number" min="0" max="100" step="0.01" value={rate} onChange={e=>setRate(e.target.value)} className="mt-1 w-full rounded-lg border border-line p-2 text-sm"/></label>
    <label className="text-xs text-ink/60">Duration<input type="number" min="0.01" value={duration} onChange={e=>setDuration(e.target.value)} className="mt-1 w-full rounded-lg border border-line p-2 text-sm"/></label>
    <label className="text-xs text-ink/60">Unit<select value={unit} onChange={e=>setUnit(e.target.value as typeof unit)} className="mt-1 w-full rounded-lg border border-line p-2 text-sm"><option value="years">Years</option><option value="months">Months</option></select></label>
  </div><button onClick={()=>void calculate()} disabled={busy || !principal || !rate || !duration} className="mt-3 rounded-lg bg-navy px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy?"Calculating…":"Calculate with working"}</button>{error && <p className="mt-2 text-xs text-rose-700">{error}</p>}{result && <div className="mt-4 rounded-lg bg-slate-50 p-4"><strong className="text-sm text-navy">{result.formula}</strong><p className="mt-2 text-xs leading-5 text-ink/65">{result.working}</p><div className="mt-3 flex flex-wrap gap-4">{Object.entries(result.result).map(([key,value])=><div key={key}><p className="text-[10px] uppercase text-ink/45">{key.replaceAll("_"," ")}</p><p className="text-lg font-semibold text-navy">₹{value.toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})}</p></div>)}</div><p className="mt-2 text-[10px] text-ink/45">{result.notice}</p></div>}</section>;
}

