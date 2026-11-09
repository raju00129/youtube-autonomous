import { useRef, useState } from "react";
import { API_BASE, withPortalKey } from "./portalAuth";

type Progress = { percent: number; message: string };

export default function DenoisePage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [downloadPath, setDownloadPath] = useState<string | null>(null);
  const [bust, setBust] = useState(0);

  function reset() {
    setFile(null);
    setBusy(false);
    setError(null);
    setNotice(null);
    setProgress(null);
    setJobId(null);
    setDownloadPath(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function pollJob(id: string) {
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    for (;;) {
      const res = await fetch(`${API_BASE}/api/v1/jobs/${id}`);
      const body = (await res.json()) as {
        detail?: string | { error?: string };
        data?: {
          status?: string;
          progress?: { percent?: number; message?: string };
          result?: { download_path?: string; original_filename?: string };
          error?: string;
        };
      };
      if (!res.ok) {
        const d = body.detail;
        const msg =
          typeof d === "string"
            ? d
            : d && typeof d === "object" && d.error
              ? d.error
              : body.data?.error || "Denoise job failed";
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      const data = body.data;
      const status = (data?.status || "").toLowerCase();
      const pct = data?.progress?.percent ?? 0;
      const message =
        data?.progress?.message ||
        (status === "pending" || status === "queued"
          ? "Queued — waiting for worker…"
          : status === "started"
            ? "Worker started…"
            : "Working…");
      setProgress({ percent: Math.max(0, Math.min(100, pct)), message });
      if (status === "success" || status === "successful") {
        return data?.result;
      }
      if (status === "failure" || status === "failed" || status === "revoked") {
        throw new Error(data?.error || message || "Denoise failed");
      }
      await sleep(2000);
    }
  }

  async function onRemoveNoise() {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setProgress({ percent: 0, message: "Uploading…" });
    setJobId(null);
    setDownloadPath(null);

    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/api/v1/denoise`, { method: "POST", body: form });
      const body = (await res.json().catch(() => ({}))) as {
        detail?: string;
        data?: { job_id?: string; download_path?: string };
      };
      if (!res.ok) {
        const detail = body.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : detail
              ? JSON.stringify(detail)
              : `Upload failed (${res.status})`,
        );
      }
      const id = body.data?.job_id;
      if (!id) throw new Error("No job_id returned");
      setJobId(id);
      setProgress({ percent: 5, message: "Queued — removing audio noise…" });
      const result = await pollJob(id);
      const path = result?.download_path || `/api/v1/denoise/${id}/download`;
      setDownloadPath(path);
      setBust((n) => n + 1);
      setNotice("Noise removed. Picture is unchanged — download and re-upload wherever you need.");
      setProgress({ percent: 100, message: "Done" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Denoise failed");
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  const previewUrl =
    downloadPath && jobId
      ? withPortalKey(`${API_BASE}${downloadPath}${downloadPath.includes("?") ? "&" : "?"}v=${bust}`)
      : null;
  const downloadUrl = downloadPath
    ? withPortalKey(`${API_BASE}${downloadPath}`)
    : null;

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-[0.25em] text-temple/80">Tools</p>
        <h1 className="font-display text-4xl text-ink">Noise remove</h1>
        <p className="text-ink/70">
          Upload one video. Audio noise is stripped; the picture and timing stay as they are. Download
          the cleaned file to use anywhere — independent of Song Studio.
        </p>
      </header>

      {error && (
        <p className="border border-saffron/40 bg-white/50 px-4 py-3 text-saffron">{error}</p>
      )}
      {notice && (
        <p className="border border-temple/30 bg-white/50 px-4 py-3 text-temple">{notice}</p>
      )}

      <section className="space-y-4 border border-ink/10 bg-white/55 p-6">
        <label className="block space-y-2">
          <span className="text-sm text-ink/70">Video file (mp4, mov, mkv, webm)</span>
          <input
            ref={inputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.mkv,.webm,.m4v"
            disabled={busy}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
              setNotice(null);
              setProgress(null);
              setJobId(null);
              setDownloadPath(null);
            }}
            className="block w-full text-sm text-ink/80 file:mr-4 file:border-0 file:bg-temple file:px-4 file:py-2 file:text-white"
          />
        </label>
        {file && (
          <p className="text-sm text-ink/60">
            Selected: {file.name} ({Math.round(file.size / 1024 / 1024)} MB)
          </p>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={!file || busy}
            onClick={() => void onRemoveNoise()}
            className="bg-temple px-5 py-2.5 font-medium text-white disabled:opacity-50"
          >
            {busy ? "Working…" : "Remove noise"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={reset}
            className="border border-ink/20 bg-white px-5 py-2.5 text-ink disabled:opacity-50"
          >
            Clear
          </button>
        </div>

        {progress && (
          <div className="space-y-2">
            <div className="h-2 w-full overflow-hidden bg-ink/10">
              <div
                className="h-full bg-temple transition-all"
                style={{ width: `${progress.percent}%` }}
              />
            </div>
            <p className="text-sm text-ink/70">
              {progress.percent}% — {progress.message}
              {jobId ? ` (${jobId.slice(0, 8)}…)` : ""}
            </p>
          </div>
        )}
      </section>

      {previewUrl && downloadUrl && (
        <section className="space-y-4 border border-ink/10 bg-white/55 p-6">
          <h2 className="font-display text-2xl text-ink">Cleaned video</h2>
          <video
            key={previewUrl}
            src={previewUrl}
            controls
            className="w-full border border-ink/10 bg-black"
          />
          <a
            href={downloadUrl}
            download
            className="inline-block bg-temple px-5 py-2.5 font-medium text-white"
          >
            Download cleaned video
          </a>
        </section>
      )}
    </main>
  );
}
