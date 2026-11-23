"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, Loader2, ZoomIn, ZoomOut } from "lucide-react";
import { fetchAuthedBlobUrl } from "@/lib/api";

type PdfEvidenceViewerProps = {
  documentId: string;
  pageNumber: number;
  quote: string;
};

export default function PdfEvidenceViewer({ documentId, pageNumber, quote }: PdfEvidenceViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [matchFound, setMatchFound] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchAuthedBlobUrl(`/api/documents/${documentId}/file`)
      .then((url) => {
        if (cancelled) URL.revokeObjectURL(url);
        else {
          objectUrl = url;
          setBlobUrl(url);
        }
      })
      .catch(() => {
        if (!cancelled) setError("The original PDF could not be loaded.");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId]);

  useEffect(() => {
    let cancelled = false;
    async function renderPage() {
      if (!blobUrl || !canvasRef.current) return;
      setLoading(true);
      setMatchFound(false);
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const pdf = await pdfjs.getDocument(blobUrl).promise;
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.35 * zoom });
        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("Canvas rendering is unavailable.");
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        await page.render({ canvasContext: context, viewport }).promise;
        const textContent = await page.getTextContent();
        const items = textContent.items.filter((item) => "str" in item && "transform" in item);
        const normalize = (value: string) => value.toLocaleLowerCase().replace(/\s+/g, " ").trim();
        const pageText = items.map((item) => item.str).join(" ");
        const normalizedPage = normalize(pageText);
        const normalizedQuote = normalize(quote);
        const found = normalizedQuote.length > 0 && normalizedPage.includes(normalizedQuote);
        if (!cancelled) setMatchFound(found);
        if (found) {
          const start = normalizedPage.indexOf(normalizedQuote);
          const end = start + normalizedQuote.length;
          let cursor = 0;
          context.save();
          context.fillStyle = "rgba(241, 196, 92, 0.38)";
          context.strokeStyle = "rgba(181, 132, 37, 0.78)";
          context.lineWidth = 1.2;
          for (const item of items) {
            const itemText = normalize(item.str);
            const itemStart = cursor;
            const itemEnd = itemStart + itemText.length;
            cursor = itemEnd + 1;
            if (!itemText || itemEnd <= start || itemStart >= end) continue;
            const transform = pdfjs.Util.transform(viewport.transform, item.transform);
            const height = Math.max(7, Math.hypot(transform[2], transform[3]));
            const x = transform[4];
            const y = transform[5] - height;
            const width = Math.max(3, item.width * viewport.scale);
            context.fillRect(x - 1, y, width + 2, height + 2);
            context.strokeRect(x - 1, y, width + 2, height + 2);
          }
          context.restore();
        }
      } catch {
        if (!cancelled) setError("This PDF page could not be rendered. Try opening the original document.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void renderPage();
    return () => { cancelled = true; };
  }, [blobUrl, pageNumber, quote, zoom]);

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-slate-100">
      <div className="flex items-center justify-between border-b border-line bg-white px-3 py-2">
        <div className="text-xs font-semibold text-navy">Source page · {pageNumber}</div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setZoom((value) => Math.max(0.7, value - 0.15))} className="rounded-md p-1.5 text-ink/60 hover:bg-slate-100" aria-label="Zoom out"><ZoomOut size={14}/></button>
          <button type="button" onClick={() => setZoom((value) => Math.min(2, value + 0.15))} className="rounded-md p-1.5 text-ink/60 hover:bg-slate-100" aria-label="Zoom in"><ZoomIn size={14}/></button>
        </div>
      </div>
      {error ? <div className="flex items-center gap-2 p-4 text-xs text-rose-700"><AlertCircle size={14}/>{error}</div> : (
        <div className="relative max-h-[560px] overflow-auto p-3">
          {loading && <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/70 text-xs text-ink/55"><Loader2 size={15} className="mr-2 animate-spin"/> Rendering cited page…</div>}
          <canvas ref={canvasRef} className="mx-auto h-auto max-w-full bg-white shadow-sm"/>
        </div>
      )}
      {!loading && !error && <div className="border-t border-line bg-white px-3 py-2 text-[11px] text-ink/55">
        {matchFound ? "Cited passage highlighted on the original PDF page." : "The exact quote was not found in the PDF text layer; page shown without a guessed highlight."}
      </div>}
    </div>
  );
}
