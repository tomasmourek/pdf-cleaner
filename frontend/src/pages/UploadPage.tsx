/**
 * Hlavní stránka — PDF / foto upload, OCR progress, výsledky, handoff do CSV.
 */
import { useState, useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import toast from "react-hot-toast";
import { useQuery } from "@tanstack/react-query";
import { pdfApi } from "../services/api";

type JobStatus = "idle" | "uploading" | "processing" | "done" | "error";

interface ExtractedField {
  value: string | number | null;
  confidence: number;
}

interface ExtractedData {
  document_type?: ExtractedField;
  vendor_name?: ExtractedField;
  document_number?: ExtractedField;
  document_date?: ExtractedField;
  total_amount?: ExtractedField;
  currency?: ExtractedField;
  items?: Array<Record<string, ExtractedField>>;
}

export default function UploadPage() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus>("idle");

  const { data: job } = useQuery({
    queryKey: ["pdf-job", jobId],
    queryFn: () => pdfApi.getJob(jobId!).then((r) => r.data),
    enabled: !!jobId && (status === "processing" || status === "uploading"),
    refetchInterval: 2500,
  });

  useEffect(() => {
    if (!job) return;
    if (job.status === "done") setStatus("done");
    if (job.status === "error") {
      setStatus("error");
      toast.error(`Chyba: ${job.error_message}`);
    }
  }, [job]);

  const onDrop = useCallback(async (accepted: File[]) => {
    const file = accepted[0];
    if (!file) return;
    setStatus("uploading");
    setJobId(null);
    try {
      const res = await pdfApi.upload(file);
      setJobId(res.data.job_id);
      setStatus("processing");
      toast.success("PDF nahráno — spouštím OCR…");
    } catch (err: any) {
      setStatus("error");
      toast.error(err.response?.data?.detail ?? "Nahrání selhalo.");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
      "image/webp": [".webp"],
      "image/tiff": [".tif", ".tiff"],
    },
    maxFiles: 1,
    maxSize: 100 * 1024 * 1024, // 100MB
    disabled: status === "uploading" || status === "processing",
  });

  const handleHandoff = async () => {
    if (!jobId) return;
    try {
      const res = await pdfApi.handoff(jobId);
      const csvUrl = `https://upravcsv.eu/csv/import/${res.data.token}`;
      window.open(csvUrl, "_blank");
      toast.success("Otevírám upravcsv.eu…");
    } catch {
      toast.error("Handoff selhal — zkuste znovu.");
    }
  };

  const extracted: ExtractedData = job?.extracted_data ?? {};
  const confidence = job?.extraction_confidence;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">Analyzovat PDF</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          PDF, foto faktury nebo dodacího listu — extrakce dat pomocí AI
        </p>
      </div>

      {/* Drop zone */}
      {(status === "idle" || status === "error") && (
        <div
          {...getRootProps()}
          className={`rounded-xl border-2 border-dashed p-14 text-center cursor-pointer transition-colors ${
            isDragActive
              ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
              : "border-[var(--color-border)] hover:border-[var(--color-primary)] hover:bg-[var(--color-surface-alt)]"
          }`}
        >
          <input {...getInputProps()} />
          <div className="text-5xl mb-4">📄</div>
          <p className="text-[var(--color-text-primary)] font-medium text-lg">
            {isDragActive ? "Pusťte PDF nebo foto…" : "Přetáhněte PDF nebo foto"}
          </p>
          <p className="text-sm text-[var(--color-text-secondary)] mt-2">
            PDF, JPG, PNG, WEBP, TIFF · Max 100 MB
          </p>
        </div>
      )}

      {/* Progress */}
      {(status === "uploading" || status === "processing") && (
        <div className="bg-[var(--color-surface)] rounded-xl shadow-[var(--shadow-card)] p-8 text-center">
          <div className="text-5xl mb-4 animate-spin">⚙️</div>
          <p className="font-semibold text-lg">
            {status === "uploading" ? "Nahrávám…" : "Analyzuji dokument…"}
          </p>
          {job?.ocr_method && (
            <p className="text-sm text-[var(--color-text-secondary)] mt-2">
              OCR metoda: {job.ocr_method} · Čitelnost: {job.readability_score?.toFixed(0)}%
            </p>
          )}
          <p className="text-xs text-[var(--color-text-secondary)] mt-3">
            PDF zpracování trvá obvykle 10–30 sekund
          </p>
        </div>
      )}

      {/* Result */}
      {status === "done" && job && (
        <div className="flex flex-col gap-4">
          {/* Header */}
          <div className="bg-[var(--color-surface)] rounded-xl shadow-[var(--shadow-card)] p-5 flex items-center justify-between gap-4">
            <div>
              <p className="font-semibold text-green-600">✅ Extrakce dokončena</p>
              <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
                OCR: {job.ocr_method} · Čitelnost: {job.readability_score?.toFixed(0)}%
                {confidence != null && ` · Jistota AI: ${(confidence * 100).toFixed(0)}%`}
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={handleHandoff} className="btn btn-primary">
                📤 Exportovat do CSV
              </button>
              <button onClick={() => { setStatus("idle"); setJobId(null); }} className="btn btn-secondary">
                Nový dokument
              </button>
            </div>
          </div>

          {/* Extracted fields */}
          {Object.keys(extracted).length > 0 && (
            <div className="bg-[var(--color-surface)] rounded-xl shadow-[var(--shadow-card)] p-5">
              <h2 className="font-semibold mb-4">Extrahovaná data</h2>
              <dl className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(
                  [
                    ["Typ dokumentu", extracted.document_type],
                    ["Dodavatel", extracted.vendor_name],
                    ["Číslo dokladu", extracted.document_number],
                    ["Datum", extracted.document_date],
                    ["Celková částka", extracted.total_amount],
                    ["Měna", extracted.currency],
                  ] as [string, ExtractedField | undefined][]
                )
                  .filter(([, f]) => f?.value != null)
                  .map(([label, field]) => (
                    <div key={label} className="flex flex-col bg-[var(--color-surface-alt)] rounded-lg p-3">
                      <dt className="text-xs text-[var(--color-text-secondary)] font-medium">{label}</dt>
                      <dd className="text-sm font-semibold mt-1">{String(field!.value)}</dd>
                      <dd className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                        Jistota: {((field!.confidence ?? 0) * 100).toFixed(0)}%
                      </dd>
                    </div>
                  ))}
              </dl>
            </div>
          )}

          {/* Line items */}
          {extracted.items && extracted.items.length > 0 && (
            <div className="bg-[var(--color-surface)] rounded-xl shadow-[var(--shadow-card)] overflow-hidden">
              <div className="px-5 py-3 border-b border-[var(--color-border)]">
                <h2 className="font-semibold">Položky ({extracted.items.length})</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-[var(--color-surface-alt)]">
                      {["Kat. číslo", "Popis", "Množství", "Cena bez DPH", "DPH", "Celkem"].map((h) => (
                        <th key={h} className="px-4 py-2 text-left text-xs font-medium text-[var(--color-text-secondary)]">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {extracted.items.map((item, i) => (
                      <tr key={i} className="border-t border-[var(--color-border)] hover:bg-[var(--color-surface-alt)]">
                        <td className="px-4 py-2">{String(item.part_number?.value ?? "")}</td>
                        <td className="px-4 py-2">{String(item.description?.value ?? "")}</td>
                        <td className="px-4 py-2">{String(item.quantity?.value ?? "")}</td>
                        <td className="px-4 py-2">{String(item.unit_price_excl_vat?.value ?? "")}</td>
                        <td className="px-4 py-2">{String(item.vat_rate?.value ?? "")}</td>
                        <td className="px-4 py-2 font-medium">{String(item.total_price_incl_vat?.value ?? "")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
