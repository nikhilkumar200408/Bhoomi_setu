"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import {
  AlertTriangle, CheckCircle2, ClipboardCheck, FileDiff, FileText,
  Plus, RefreshCw, ShieldCheck, Trash2, XCircle,
} from "lucide-react";

type DocumentItem = { id: string; filename: string };
type Evidence = { document_id: string; filename: string; page: number; quote: string };
type Requirement = { id: string; label: string; keywords: string[]; status: string; message: string; evidence: Evidence[] };
type Checklist = { _id: string; name: string; requirements: Requirement[]; document_names: string[]; created_at: string };
type Rule = { _id: string; name: string; description: string; operator: string; expected_value: string; severity: string };
type Review = { _id: string; title: string; description: string; source_type: string; status: string; evidence: Evidence[]; history: { action: string; comment: string; timestamp: string }[] };
type VersionEvidence = { document_id: string; filename: string; page: number; quote: string };
type VersionResult = {
  old_document: { id: string; filename: string };
  new_document: { id: string; filename: string };
  summary: { added: number; removed: number; modified: number };
  added: VersionEvidence[];
  removed: VersionEvidence[];
  modified: { old: VersionEvidence; new: VersionEvidence; change: string }[];
  notice: string;
};
type Overview = { documents: DocumentItem[]; indexed_document_count: number; checklist_count: number; rule_count: number; pending_review_count: number; notice: string };

const statusClasses: Record<string, string> = {
  FOUND: "border-emerald-200 bg-emerald-50 text-emerald-700",
  MISSING: "border-rose-200 bg-rose-50 text-rose-700",
  NEEDS_VERIFICATION: "border-amber-200 bg-amber-50 text-amber-800",
  PENDING: "border-amber-200 bg-amber-50 text-amber-800",
  ACCEPTED: "border-emerald-200 bg-emerald-50 text-emerald-700",
  REJECTED: "border-rose-200 bg-rose-50 text-rose-700",
  CORRECTED: "border-sky-200 bg-sky-50 text-sky-700",
  NEEDS_FURTHER_REVIEW: "border-amber-200 bg-amber-50 text-amber-800",
};

const defaultRequirements = [
  "Signed agreement|signed agreement,executed agreement,contract",
  "Identity document|identity proof,identity card,passport",
  "Address proof|address proof,utility bill,residential address",
  "Payment evidence|payment receipt,transaction receipt,proof of payment",
].join("\n");

export default function CompliancePage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [checklists, setChecklists] = useState<Checklist[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [checklistName, setChecklistName] = useState("Document completeness review");
  const [requirementsText, setRequirementsText] = useState(defaultRequirements);
  const [ruleName, setRuleName] = useState("");
  const [ruleDescription, setRuleDescription] = useState("");
  const [operator, setOperator] = useState("contains");
  const [expectedValue, setExpectedValue] = useState("");
  const [severity, setSeverity] = useState("MEDIUM");
  const [oldId, setOldId] = useState("");
  const [newId, setNewId] = useState("");
  const [comparison, setComparison] = useState<VersionResult | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [correctedValues, setCorrectedValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [o, c, r, v] = await Promise.all([
        api.get<Overview>("/api/compliance/overview"),
        api.get<{ items: Checklist[] }>("/api/compliance/checklists"),
        api.get<{ items: Rule[] }>("/api/compliance/rules"),
        api.get<{ items: Review[] }>("/api/compliance/reviews"),
      ]);
      setOverview(o);
      setChecklists(c.items || []);
      setRules(r.items || []);
      setReviews(v.items || []);
      setSelectedIds((current) => current.length ? current.filter((id) => o.documents.some((d) => d.id === id)) : o.documents.map((d) => d.id));
      setOldId((current) => current || o.documents[0]?.id || "");
      setNewId((current) => current || o.documents[1]?.id || "");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load verification workspace.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const selectedDocuments = useMemo(
    () => overview?.documents.filter((d) => selectedIds.includes(d.id)) || [],
    [overview, selectedIds]
  );

  function toggleDocument(id: string) {
    setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
  }

  async function createChecklist(event: FormEvent) {
    event.preventDefault();
    const requirements = requirementsText.split("\n").map((line) => {
      const [label, rawKeywords] = line.split("|");
      return { label: (label || "").trim(), keywords: (rawKeywords || "").split(",").map((x) => x.trim()).filter(Boolean) };
    }).filter((x) => x.label && x.keywords.length);
    if (!selectedIds.length || !requirements.length) {
      setError("Select indexed documents and add at least one valid requirement.");
      return;
    }
    setBusy("checklist"); setError(""); setNotice("");
    try {
      const result = await api.post<Checklist>("/api/compliance/checklists", {
        name: checklistName, document_ids: selectedIds, requirements,
      });
      setNotice("Checklist created: " + result.requirements.filter((x) => x.status === "FOUND").length + " found, " + result.requirements.filter((x) => x.status === "MISSING").length + " missing, " + result.requirements.filter((x) => x.status === "NEEDS_VERIFICATION").length + " need verification.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Checklist could not be created.");
    } finally { setBusy(""); }
  }

  async function createRule(event: FormEvent) {
    event.preventDefault();
    if (!ruleName.trim()) return;
    setBusy("rule"); setError(""); setNotice("");
    try {
      await api.post("/api/compliance/rules", {
        name: ruleName, description: ruleDescription, operator,
        expected_value: expectedValue, severity,
      });
      setRuleName(""); setRuleDescription(""); setExpectedValue("");
      setNotice("Custom review rule saved.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Rule could not be saved.");
    } finally { setBusy(""); }
  }

  async function runRule(rule: Rule) {
    if (!selectedIds.length) { setError("Select indexed documents first."); return; }
    setBusy("run-" + rule._id); setError(""); setNotice("");
    try {
      const result = await api.post<{ summary: { passed: number; failed: number } }>("/api/compliance/rules/" + rule._id + "/run", { document_ids: selectedIds });
      setNotice(rule.name + ": " + result.summary.passed + " passed, " + result.summary.failed + " failed. Failed checks were added to the human review queue.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Rule execution failed.");
    } finally { setBusy(""); }
  }

  async function deleteRule(ruleId: string) {
    setBusy("delete-" + ruleId);
    try {
      await api.delete("/api/compliance/rules/" + ruleId);
      await load();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not delete rule."); }
    finally { setBusy(""); }
  }

  async function compareVersions(event: FormEvent) {
    event.preventDefault();
    if (!oldId || !newId || oldId === newId) {
      setError("Choose two different indexed documents to compare.");
      return;
    }
    setBusy("compare"); setError(""); setNotice("");
    try {
      setComparison(await api.post<VersionResult>("/api/compliance/versions/compare", {
        old_document_id: oldId, new_document_id: newId,
      }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Version comparison failed.");
    } finally { setBusy(""); }
  }

  async function reviewAction(review: Review, action: "ACCEPT" | "REJECT" | "CORRECT" | "MARK_FOR_REVIEW") {
    const corrected_value = correctedValues[review._id] || "";
    if (action === "CORRECT" && !corrected_value.trim()) {
      setError("Enter the corrected value before choosing Correct.");
      return;
    }
    setBusy("review-" + review._id); setError(""); setNotice("");
    try {
      await api.patch("/api/compliance/reviews/" + review._id, {
        action, comment: reviewNotes[review._id] || "", corrected_value: action === "CORRECT" ? corrected_value : undefined,
      });
      setNotice("Review updated: " + review.title);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Review action failed.");
    } finally { setBusy(""); }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">TrustLens AI · Phase 2</p>
          <h1 className="mt-2 font-serif text-3xl font-semibold text-navy">Verification &amp; Compliance</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-ink/60">Check document completeness, compare versions, run review rules and record human decisions with source evidence.</p>
        </div>
        <button onClick={() => void load()} className="inline-flex items-center gap-2 rounded-card border border-line bg-white px-3 py-2 text-sm text-navy hover:bg-slate-50"><RefreshCw size={14}/> Refresh</button>
      </header>

      {error && <div role="alert" className="rounded-card border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</div>}
      {notice && <div role="status" className="rounded-card border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div>}

      {loading ? <div className="rounded-card border border-line bg-white p-12 text-center text-sm text-ink/50">Loading verification workspace…</div> : <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Indexed documents", overview?.indexed_document_count ?? 0, "Available for evidence checks"],
            ["Saved checklists", overview?.checklist_count ?? 0, "Completeness reviews"],
            ["Custom rules", overview?.rule_count ?? 0, "Reusable review conditions"],
            ["Pending reviews", overview?.pending_review_count ?? 0, "Awaiting human decision"],
          ].map(([label, value, hint]) => <div key={String(label)} className="rounded-card border border-line bg-white p-4"><p className="text-xs text-ink/50">{label}</p><p className="mt-1 text-2xl font-semibold text-navy">{value}</p><p className="mt-1 text-[11px] text-ink/45">{hint}</p></div>)}
        </div>

        <section className="rounded-card border border-line bg-white p-5">
          <div className="flex items-center gap-2"><FileText size={17} className="text-accent"/><h2 className="text-sm font-semibold text-navy">Select source documents</h2></div>
          <p className="mt-1 text-xs text-ink/50">All checks operate only on indexed documents that your account is allowed to access.</p>
          {!overview?.documents.length ? <p className="mt-4 rounded-lg bg-slate-50 p-4 text-sm text-ink/55">No indexed documents found. Upload and index documents in Document AI first.</p> :
            <div className="mt-3 flex flex-wrap gap-2">{overview.documents.map((doc) => <label key={doc.id} className={"flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-xs " + (selectedIds.includes(doc.id) ? "border-accent bg-accent-bg text-navy" : "border-line text-ink/65")}><input type="checkbox" checked={selectedIds.includes(doc.id)} onChange={() => toggleDocument(doc.id)}/>{doc.filename}</label>)}</div>}
          <p className="mt-2 text-[11px] text-ink/45">{selectedDocuments.length} selected</p>
        </section>

        <section className="grid gap-5 xl:grid-cols-2">
          <div className="rounded-card border border-line bg-white p-5">
            <div className="flex items-center gap-2"><ClipboardCheck size={17} className="text-accent"/><h2 className="text-sm font-semibold text-navy">Missing Document &amp; Compliance Checker</h2></div>
            <p className="mt-1 text-xs leading-5 text-ink/50">Define the evidence expected in your file set. Each requirement is marked Found, Missing or Needs Verification, with source-page references where available.</p>
            <form onSubmit={createChecklist} className="mt-4 space-y-3">
              <input value={checklistName} onChange={(e) => setChecklistName(e.target.value)} className="w-full rounded-lg border border-line px-3 py-2 text-sm text-navy" placeholder="Checklist name"/>
              <textarea value={requirementsText} onChange={(e) => setRequirementsText(e.target.value)} rows={6} className="w-full rounded-lg border border-line px-3 py-2 font-mono text-xs leading-5 text-navy" />
              <p className="text-[10px] text-ink/45">One requirement per line: Label|keyword one,keyword two</p>
              <button disabled={busy === "checklist" || !selectedIds.length} className="inline-flex items-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"><Plus size={14}/>{busy === "checklist" ? "Checking…" : "Run completeness check"}</button>
            </form>
            <div className="mt-5 space-y-3">
              {checklists.slice(0, 5).map((checklist) => <article key={checklist._id} className="rounded-lg border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm text-navy">{checklist.name}</strong><span className="text-[10px] text-ink/45">{checklist.document_names?.length || 0} documents</span></div>
                <div className="mt-3 space-y-2">{checklist.requirements.map((req) => <div key={req.id} className="rounded-md bg-slate-50 p-2">
                  <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs font-medium text-navy">{req.label}</span><span className={"rounded-full border px-2 py-0.5 text-[10px] font-semibold " + (statusClasses[req.status] || "")}>{req.status.replaceAll("_", " ")}</span></div>
                  <p className="mt-1 text-[11px] text-ink/55">{req.message}</p>
                  {req.evidence?.slice(0, 2).map((ev, i) => <p key={i} className="mt-1 text-[10px] leading-4 text-ink/45">{ev.filename} · Page {ev.page}: “{ev.quote.slice(0, 180)}”</p>)}
                </div>)}</div>
              </article>)}
              {!checklists.length && <p className="text-xs text-ink/45">No checklists created yet.</p>}
            </div>
          </div>

          <div className="rounded-card border border-line bg-white p-5">
            <div className="flex items-center gap-2"><FileDiff size={17} className="text-accent"/><h2 className="text-sm font-semibold text-navy">Document Version Intelligence</h2></div>
            <p className="mt-1 text-xs leading-5 text-ink/50">Compare two indexed versions and inspect added, removed and modified text with page-level evidence.</p>
            <form onSubmit={compareVersions} className="mt-4 space-y-3">
              <label className="block text-xs font-medium text-ink/60">Older version<select value={oldId} onChange={(e) => setOldId(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-navy"><option value="">Select document</option>{overview?.documents.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}</select></label>
              <label className="block text-xs font-medium text-ink/60">Newer version<select value={newId} onChange={(e) => setNewId(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-navy"><option value="">Select document</option>{overview?.documents.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}</select></label>
              <button disabled={busy === "compare" || !overview?.documents.length} className="rounded-lg bg-navy px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">{busy === "compare" ? "Comparing…" : "Compare versions"}</button>
            </form>
            {comparison && <div className="mt-5 space-y-3">
              <div className="grid grid-cols-3 gap-2">{[["Added", comparison.summary.added, "text-emerald-700"], ["Removed", comparison.summary.removed, "text-rose-700"], ["Modified", comparison.summary.modified, "text-amber-700"]].map(([label, count, color]) => <div key={String(label)} className="rounded-lg bg-slate-50 p-3"><p className="text-[10px] text-ink/45">{label}</p><p className={"text-xl font-semibold " + color}>{count}</p></div>)}</div>
              <div className="max-h-80 space-y-2 overflow-auto">{comparison.modified.map((item, i) => <div key={i} className="rounded-lg border border-amber-200 p-3"><p className="text-[10px] font-semibold text-amber-800">MODIFIED</p><p className="mt-1 text-xs text-rose-700">Old · {item.old.filename} · p.{item.old.page}: {item.old.quote}</p><p className="mt-1 text-xs text-emerald-700">New · {item.new.filename} · p.{item.new.page}: {item.new.quote}</p></div>)}
                {comparison.added.map((item, i) => <div key={"a-" + i} className="rounded-lg border border-emerald-200 p-3"><p className="text-[10px] font-semibold text-emerald-700">ADDED · {item.filename} · p.{item.page}</p><p className="mt-1 text-xs text-ink/70">{item.quote}</p></div>)}
                {comparison.removed.map((item, i) => <div key={"r-" + i} className="rounded-lg border border-rose-200 p-3"><p className="text-[10px] font-semibold text-rose-700">REMOVED · {item.filename} · p.{item.page}</p><p className="mt-1 text-xs text-ink/70">{item.quote}</p></div>)}
              </div>
              <p className="text-[10px] leading-4 text-ink/45">{comparison.notice}</p>
            </div>}
          </div>
        </section>

        <section className="rounded-card border border-line bg-white p-5">
          <div className="flex items-center gap-2"><ShieldCheck size={17} className="text-accent"/><h2 className="text-sm font-semibold text-navy">Custom Review Rules</h2></div>
          <p className="mt-1 text-xs text-ink/50">Save reusable deterministic checks and run them against the selected indexed documents.</p>
          <form onSubmit={createRule} className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <input value={ruleName} onChange={(e) => setRuleName(e.target.value)} placeholder="Rule name" className="rounded-lg border border-line px-3 py-2 text-sm"/>
            <select value={operator} onChange={(e) => setOperator(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm"><option value="contains">Must contain phrase</option><option value="not_contains">Must not contain phrase</option><option value="regex">Must match regex</option><option value="date_present">Date must be present</option><option value="min_pages">Minimum page count</option></select>
            <input value={expectedValue} onChange={(e) => setExpectedValue(e.target.value)} placeholder={operator === "min_pages" ? "Minimum pages" : "Expected text / regex"} className="rounded-lg border border-line px-3 py-2 text-sm"/>
            <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm"><option>LOW</option><option>MEDIUM</option><option>HIGH</option></select>
            <button disabled={busy === "rule"} className="rounded-lg bg-navy px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{busy === "rule" ? "Saving…" : "Save rule"}</button>
            <input value={ruleDescription} onChange={(e) => setRuleDescription(e.target.value)} placeholder="Optional rule explanation" className="rounded-lg border border-line px-3 py-2 text-sm md:col-span-2 xl:col-span-5"/>
          </form>
          <div className="mt-4 divide-y divide-line">{rules.map((rule) => <div key={rule._id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div><strong className="text-sm text-navy">{rule.name}</strong><p className="mt-1 text-xs text-ink/50">{rule.operator} {rule.expected_value} · {rule.severity}{rule.description ? " · " + rule.description : ""}</p></div>
            <div className="flex items-center gap-2"><button onClick={() => void runRule(rule)} disabled={busy === "run-" + rule._id} className="rounded-lg border border-line px-3 py-2 text-xs font-medium text-navy disabled:opacity-50">{busy === "run-" + rule._id ? "Running…" : "Run on selected"}</button><button onClick={() => void deleteRule(rule._id)} disabled={busy === "delete-" + rule._id} className="rounded-lg p-2 text-rose-600 hover:bg-rose-50" aria-label="Delete rule"><Trash2 size={14}/></button></div>
          </div>)}{!rules.length && <p className="py-4 text-xs text-ink/45">No custom rules saved yet.</p>}</div>
        </section>

        <section className="rounded-card border border-line bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="flex items-center gap-2 text-sm font-semibold text-navy"><ClipboardCheck size={17}/> Human Review &amp; Approval</h2><p className="mt-1 text-xs text-ink/50">Record a decision, correction or follow-up. Every action is appended to the review history.</p></div><span className="text-xs text-ink/45">{reviews.filter((r) => r.status === "PENDING" || r.status === "NEEDS_FURTHER_REVIEW").length} awaiting action</span></div>
          <div className="mt-4 space-y-3">{reviews.map((review) => <article key={review._id} className="rounded-lg border border-line p-4">
            <div className="flex flex-wrap items-start justify-between gap-2"><div><strong className="text-sm text-navy">{review.title}</strong><p className="mt-1 text-xs text-ink/50">{review.source_type} · {review.description}</p></div><span className={"rounded-full border px-2 py-1 text-[10px] font-semibold " + (statusClasses[review.status] || "")}>{review.status.replaceAll("_", " ")}</span></div>
            <div className="mt-3 space-y-2">{review.evidence?.map((ev, i) => <div key={i} className="rounded-md bg-slate-50 p-2"><p className="text-[10px] font-semibold text-ink/55">{ev.filename} · Page {ev.page}</p><p className="mt-1 text-xs leading-5 text-ink/70">{ev.quote}</p></div>)}</div>
            {(review.status === "PENDING" || review.status === "NEEDS_FURTHER_REVIEW") && <div className="mt-3 space-y-2"><input value={reviewNotes[review._id] || ""} onChange={(e) => setReviewNotes((s) => ({ ...s, [review._id]: e.target.value }))} placeholder="Reviewer comment (optional)" className="w-full rounded-lg border border-line px-3 py-2 text-xs"/><input value={correctedValues[review._id] || ""} onChange={(e) => setCorrectedValues((s) => ({ ...s, [review._id]: e.target.value }))} placeholder="Corrected value (required only for Correct)" className="w-full rounded-lg border border-line px-3 py-2 text-xs"/><div className="flex flex-wrap gap-2">
              <button onClick={() => void reviewAction(review, "ACCEPT")} className="inline-flex items-center gap-1 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-medium text-white"><CheckCircle2 size={13}/> Accept</button>
              <button onClick={() => void reviewAction(review, "REJECT")} className="inline-flex items-center gap-1 rounded-lg bg-rose-700 px-3 py-2 text-xs font-medium text-white"><XCircle size={13}/> Reject</button>
              <button onClick={() => void reviewAction(review, "CORRECT")} className="rounded-lg border border-line px-3 py-2 text-xs font-medium text-navy">Correct</button>
              <button onClick={() => void reviewAction(review, "MARK_FOR_REVIEW")} className="inline-flex items-center gap-1 rounded-lg border border-amber-200 px-3 py-2 text-xs font-medium text-amber-800"><AlertTriangle size={13}/> Further review</button>
            </div></div>}
            {review.history?.length > 0 && <details className="mt-3"><summary className="cursor-pointer text-xs font-medium text-accent">View audit history ({review.history.length})</summary><div className="mt-2 space-y-1">{review.history.map((h, i) => <p key={i} className="text-[10px] text-ink/55">{h.action} · {h.comment || "No comment"} · {new Date(h.timestamp).toLocaleString()}</p>)}</div></details>}
          </article>)}{!reviews.length && <p className="rounded-lg bg-slate-50 p-6 text-center text-xs text-ink/45">No pending review items. Rule failures and checklist exceptions will appear here.</p>}</div>
        </section>
        <p className="text-[11px] leading-5 text-ink/45">{overview?.notice} Version comparison is text-level only; reviewers must inspect original pages before making legal or compliance decisions.</p>
      </>}
    </div>
  );
}
