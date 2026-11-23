"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Bot, Check, ChevronDown, FileText, Loader2, MessageCircle, Plus, Send, ShieldCheck, Sparkles, Trash2, User, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { LoadingState } from "@/components/ui/States";

type Doc = { id: string; filename: string; docai_status?: string; status?: string };
type Evidence = { evidence_id: string; filename: string; page_number: number; quote: string; source_url?: string; verification?: { quote_found_in_source?: boolean } };
type Claim = { claim_id: string; text: string; status: string; confidence: number; explanation?: string };
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
                    <div className="whitespace-pre-wrap break-words text-sm leading-7">{message.answer?.abstained && <span className="mb-2 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-800"><AlertCircle size={12}/> Insufficient evidence</span>}{message.content}</div>
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
                    {!!message.answer?.conflicts?.length && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3"><p className="text-xs font-semibold text-amber-900">Potential conflicts detected</p>{message.answer.conflicts.map((c,i) => <p key={i} className="mt-1 text-xs text-amber-900">{c.topic}: {c.explanation || c.status}</p>)}</div>}
                    {message.answer?.missing_evidence?.map((item,i) => <p key={i} className="text-xs text-amber-700">{item.description}</p>)}
                    <div className="flex flex-wrap items-center gap-3 border-t border-line pt-2 text-[10px] text-ink/40">
                      <span>{message.answer?.faithfulness_score == null ? "Faithfulness not scored" : `Evidence grounding: ${Math.round(message.answer.faithfulness_score * 100)}%`}</span>
                      {message.answer?.contextual_follow_up && <span>Conversation context used</span>}
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
    </div>
  );
}
