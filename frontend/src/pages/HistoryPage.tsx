/**
 * Historie analyzovaných PDF dokumentů.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { pdfApi } from "../services/api";

function formatDate(iso: string) {
  return new Intl.DateTimeFormat("cs-CZ", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

const STATUS_LABEL: Record<string, string> = {
  done: "✅ Hotovo", processing: "⚙️ Zpracovává se",
  pending: "⏳ Čeká", error: "❌ Chyba",
};

const OCR_LABEL: Record<string, string> = {
  native: "Nativní text", tesseract: "Tesseract OCR",
  google_vision: "Google Vision", claude_vision: "Claude Vision",
};

export default function HistoryPage() {
  const [page, setPage] = useState(1);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["pdf-history", page],
    queryFn: () => pdfApi.getHistory(page).then((r) => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => pdfApi.deleteHistory(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["pdf-history"] }); toast.success("Záznam smazán."); },
    onError: () => toast.error("Smazání selhalo."),
  });

  const handleHandoff = async (docId: string) => {
    try {
      const res = await pdfApi.handoff(docId);
      window.open(`https://upravcsv.eu/csv/import/${res.data.token}`, "_blank");
      toast.success("Otevírám upravcsv.eu…");
    } catch {
      toast.error("Handoff selhal.");
    }
  };

  if (isLoading) return (
    <div className="flex flex-col gap-3">
      {[...Array(4)].map((_, i) => <div key={i} className="skeleton h-20 rounded-xl" />)}
    </div>
  );

  const docs = data?.documents ?? [];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">Historie analýz</h1>

      {docs.length === 0 ? (
        <div className="text-center py-16 text-[var(--color-text-secondary)]">
          <div className="text-5xl mb-3">📄</div>
          <p className="font-medium">Žádné analyzované dokumenty</p>
          <p className="text-sm mt-1">Nahrajte první PDF na hlavní stránce.</p>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            {docs.map((doc: any) => (
              <div key={doc.id} className="bg-[var(--color-surface)] rounded-xl shadow-[var(--shadow-card)] p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-medium text-sm truncate">{doc.original_filename}</p>
                    <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                      {formatDate(doc.created_at)} · {STATUS_LABEL[doc.status] ?? doc.status}
                      {doc.ocr_method && ` · ${OCR_LABEL[doc.ocr_method] ?? doc.ocr_method}`}
                      {doc.readability_score != null && ` · Čitelnost: ${doc.readability_score.toFixed(0)}%`}
                    </p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    {doc.status === "done" && (
                      <button onClick={() => handleHandoff(doc.id)} className="btn btn-primary text-sm">
                        📤 Do CSV
                      </button>
                    )}
                    <button
                      onClick={() => { if (confirm("Smazat tento záznam?")) deleteMutation.mutate(doc.id); }}
                      className="btn btn-secondary text-sm text-red-600 hover:bg-red-50"
                    >
                      Smazat
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {(data?.has_next || page > 1) && (
            <div className="flex items-center justify-center gap-3">
              <button onClick={() => setPage((p) => p - 1)} disabled={page === 1} className="btn btn-secondary">← Předchozí</button>
              <span className="text-sm text-[var(--color-text-secondary)]">Strana {page}</span>
              <button onClick={() => setPage((p) => p + 1)} disabled={!data?.has_next} className="btn btn-secondary">Další →</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
