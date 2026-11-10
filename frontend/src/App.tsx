import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import DenoisePage from "./DenoisePage";
import { API_BASE, withPortalKey } from "./portalAuth";

type ReadyResponse = {
  status: string;
  database: boolean;
  redis: boolean;
  providers: Record<string, boolean>;
};

type ProvidersResponse = {
  data: {
    readiness: Record<string, boolean>;
    music_model: string;
    music_provider?: string;
    video_model: string;
    video_defaults: {
      duration: number;
      resolution: string;
      aspect_ratio: string;
      via?: string;
    };
    llm_model: string;
    image_model?: string;
    notes?: Record<string, string>;
  };
};

type Readiness = {
  checks: { key: string; label: string; ok: boolean }[];
  reviewable: boolean;
  publishable: boolean;
  can_set_time: boolean;
  missing: string[];
  queue_bucket: string;
};

type Song = {
  id: string;
  title: string;
  deity?: string | null;
  stage: string;
  style_prompt?: string | null;
  music_genre?: string | null;
  vocal_preference?: string | null;
  publish_at?: string | null;
  youtube_title?: string | null;
  youtube_description?: string | null;
  youtube_tags?: string | null;
  youtube_playlist_id?: string | null;
  youtube_playlist_title?: string | null;
  youtube_url?: string | null;
  youtube_video_id?: string | null;
  shorts_playlist_id?: string | null;
  shorts_playlist_title?: string | null;
  readiness?: Readiness;
  lyrics?: {
    id: string;
    version: number;
    body: string;
    approved: boolean;
  } | null;
  music?: {
    id: string;
    provider: string;
    status: string;
    original_filename?: string | null;
    download_path: string;
  } | null;
  shorts?: {
    id: string;
    slot_index: number;
    title?: string | null;
    hook?: string | null;
    description?: string | null;
    stage: string;
    clip_path?: string | null;
    clip_url?: string | null;
    final_clip_path?: string | null;
    final_url?: string | null;
    youtube_video_id?: string | null;
    youtube_url?: string | null;
    audio_start_sec?: number | null;
    audio_end_sec?: number | null;
  }[];
  visual?: {
    prompt?: string | null;
    clip_path?: string | null;
    clip_url?: string | null;
    resolution?: string;
    shorts_from_same_clip?: boolean;
  };
  final?: {
    path?: string | null;
    url?: string | null;
    ready?: boolean;
  };
  thumbnail?: {
    path?: string | null;
    requires_channel_logo?: boolean;
    requires_deity_image?: boolean;
  };
  notes?: string | null;
  pipeline?: {
    next_step?: string;
    detail?: string;
    publish_at?: string | null;
    prep_at?: string | null;
    prep_lead_minutes?: number;
    video_provider?: string;
    has_final?: boolean;
    published?: boolean;
  };
};

type YtPlaylist = { id: string; title: string };

const PROVIDER_LABELS: Record<string, string> = {
  gemini_lyrics: "Gemini lyrics",
  kling_thumbnails: "Kling thumbnails",
  suno_manual_upload: "Suno manual upload",
  mureka_music: "Mureka (optional API)",
  kling_video_720p: "Kling 4.0 video (720p)",
  youtube_oauth: "YouTube OAuth",
};

function toLocalInputValue(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type SunoPack = {
  title: string;
  style: string;
  lyrics: string;
  lyrics_approved: boolean;
  copy_all: string;
  instructions: string[];
};

function Dashboard() {
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [providers, setProviders] = useState<ProvidersResponse["data"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [readyRes, providerRes] = await Promise.all([
          fetch(`${API_BASE}/ready`),
          fetch(`${API_BASE}/api/v1/system/providers`),
        ]);
        if (!readyRes.ok || !providerRes.ok) {
          throw new Error("Backend not reachable");
        }
        setReady((await readyRes.json()) as ReadyResponse);
        const body = (await providerRes.json()) as ProvidersResponse;
        setProviders(body.data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load status");
      }
    }
    void load();
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-10 px-6 py-12">
      <header className="space-y-3">
        <p className="text-sm uppercase tracking-[0.25em] text-temple/80">Studio</p>
        <h1 className="font-display text-5xl font-semibold text-ink md:text-6xl">
          Ragam Spiritual
        </h1>
        <p className="max-w-2xl text-lg text-ink/75">
          Prepare Telugu lyrics here, generate in your Suno Pro app, upload the MP3 — we continue
          from there.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/ready"
            className="inline-block bg-temple px-5 py-2.5 font-medium text-white transition hover:opacity-90"
          >
            Ready queue
          </Link>
          <Link
            to="/schedule"
            className="inline-block border border-ink/20 bg-white px-5 py-2.5 font-medium text-ink"
          >
            Week schedule
          </Link>
          <Link to="/songs" className="inline-block px-5 py-2.5 font-medium text-temple">
            Song Studio
          </Link>
          <Link to="/branding" className="inline-block px-5 py-2.5 font-medium text-temple">
            Logo
          </Link>
        </div>
      </header>

      {error && (
        <p className="border border-saffron/40 bg-white/50 px-4 py-3 text-saffron">
          {error}. Is the API running at {API_BASE}?
        </p>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        <StatusCard label="API / infra" value={ready?.status ?? "…"} ok={ready?.status === "ready"} />
        <StatusCard label="PostgreSQL" value={ready?.database ? "up" : "down"} ok={!!ready?.database} />
        <StatusCard label="Redis" value={ready?.redis ? "up" : "down"} ok={!!ready?.redis} />
      </section>

      {providers && (
        <section className="space-y-4 border border-ink/10 bg-white/55 p-6 backdrop-blur">
          <h2 className="font-display text-2xl text-ink">Provider readiness</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {Object.entries(providers.readiness).map(([key, ok]) => (
              <li key={key} className="flex items-center justify-between border-b border-ink/5 py-2">
                <span className="font-medium">{PROVIDER_LABELS[key] ?? key}</span>
                <span className={ok ? "text-temple" : "text-saffron"}>{ok ? "configured" : "missing"}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-ink/70">
            Music: <strong>manual Suno upload</strong> (Pro). Video: Gemini Omni{" "}
            <strong>{providers.video_defaults?.resolution ?? "720p"}</strong> — one clip, Shorts cut
            from it (no second generation).
          </p>
        </section>
      )}
    </main>
  );
}

function StatusCard({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="border border-ink/10 bg-white/55 p-5 backdrop-blur">
      <p className="text-sm uppercase tracking-wide text-ink/55">{label}</p>
      <p className={`mt-2 font-display text-3xl ${ok ? "text-temple" : "text-saffron"}`}>{value}</p>
    </div>
  );
}

function SongList() {
  const navigate = useNavigate();
  const [songs, setSongs] = useState<Song[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [deity, setDeity] = useState("");
  const [topic, setTopic] = useState("");
  const [lyrics, setLyrics] = useState(
    "[Pallavi]\n\n[Anupallavi]\n\n[Pallavi]\n\n[Slokam]\n\n[Pallavi]\n\n[Charanam 1]\n\n[Pallavi]\n\n[Charanam 2]\n\n[Pallavi]\n",
  );
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/v1/songs`);
    if (!res.ok) throw new Error("Failed to load songs");
    const body = (await res.json()) as { data: Song[] };
    setSongs(body.data);
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [load]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/songs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          deity: deity || null,
          lyrics,
          notes: topic || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = (await res.json()) as { data: Song };
      setTitle("");
      setDeity("");
      setTopic("");
      await load();
      navigate(`/songs/${body.data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function onGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/songs/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title || null,
          deity: deity || null,
          topic: topic || null,
          vocal_preference: "m",
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = (await res.json()) as { data: Song };
      setTitle("");
      setDeity("");
      setTopic("");
      await load();
      navigate(`/songs/${body.data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generate failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-12">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-[0.25em] text-temple/80">Song Studio</p>
        <h1 className="font-display text-4xl text-ink">Lyrics → Suno → Upload</h1>
        <p className="max-w-2xl text-ink/70">
          Write lyrics here, copy the Suno pack, generate on suno.com with your Pro plan, then
          upload the MP3 back.
        </p>
      </header>

      {error && <p className="border border-saffron/40 bg-white/50 px-4 py-3 text-saffron">{error}</p>}

      <form onSubmit={onCreate} className="grid gap-4 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">New song</h2>
        <p className="text-sm text-ink/65">
          Prefer <strong>Generate with Gemini</strong> — deep Telugu lyrics + Suno style. Or paste
          lyrics manually and Create.
        </p>
        <label className="grid gap-1 text-sm">
          Title (optional for Generate — agent can invent)
          <input
            className="border border-ink/15 bg-white/80 px-3 py-2"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
          />
        </label>
        <label className="grid gap-1 text-sm">
          Deity (optional)
          <input
            className="border border-ink/15 bg-white/80 px-3 py-2"
            value={deity}
            onChange={(e) => setDeity(e.target.value)}
            maxLength={120}
            placeholder="e.g. Sri Rama, Sri Vishnu, Durga, Shiva"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Topic / mood (for Generate)
          <textarea
            className="min-h-20 border border-ink/15 bg-white/80 px-3 py-2 text-sm"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Friday morning temple aarti, peaceful gratitude"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Lyrics (manual path)
          <textarea
            className="min-h-40 border border-ink/15 bg-white/80 px-3 py-2 font-mono text-sm"
            value={lyrics}
            onChange={(e) => setLyrics(e.target.value)}
          />
        </label>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={generating || busy}
            onClick={() => void onGenerate()}
            className="bg-temple px-5 py-2.5 font-medium text-white disabled:opacity-50"
          >
            {generating ? "Generating with Gemini…" : "Generate with Gemini"}
          </button>
          <button
            type="submit"
            disabled={busy || generating || !title.trim() || !lyrics.trim()}
            className="border border-ink/20 bg-white px-5 py-2.5 font-medium text-ink disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create manually"}
          </button>
        </div>
      </form>

      <section className="space-y-3">
        <h2 className="font-display text-2xl">Projects</h2>
        {songs.length === 0 ? (
          <p className="text-ink/60">No songs yet.</p>
        ) : (
          <ul className="divide-y divide-ink/10 border border-ink/10 bg-white/55">
            {songs.map((s) => (
              <li key={s.id}>
                <Link
                  to={`/songs/${s.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-white/80"
                >
                  <span className="font-medium text-ink">{s.title}</span>
                  <span className="text-sm text-ink/55">{s.stage}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function SongDetail() {
  const { songId } = useParams();
  const [song, setSong] = useState<Song | null>(null);
  const [pack, setPack] = useState<SunoPack | null>(null);
  const [title, setTitle] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [style, setStyle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [visualProgress, setVisualProgress] = useState<{
    percent: number;
    message: string;
  } | null>(null);
  const [regenTopic, setRegenTopic] = useState("");
  const [playlists, setPlaylists] = useState<YtPlaylist[]>([]);
  const [playlistPick, setPlaylistPick] = useState("");
  const [playlistHint, setPlaylistHint] = useState<string | null>(null);
  const [publishLocal, setPublishLocal] = useState("");

  const pollVisualJob = useCallback(async (jobId: string) => {
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    for (;;) {
      const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`);
      const body = (await res.json()) as {
        detail?: string | { error?: string };
        data?: {
          status?: string;
          progress?: { percent?: number; message?: string };
          result?: { note?: string };
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
              : body.data?.error || (await res.text()) || "Visual job failed";
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
      setVisualProgress({ percent: Math.max(0, Math.min(100, pct)), message });
      if (status === "success" || status === "successful") {
        return data?.result;
      }
      if (status === "failure" || status === "failed" || status === "revoked") {
        throw new Error(data?.error || message || "Visual generation failed");
      }
      await sleep(2000);
    }
  }, []);

  const load = useCallback(async () => {
    if (!songId) return;
    const [songRes, packRes] = await Promise.all([
      fetch(`${API_BASE}/api/v1/songs/${songId}`),
      fetch(`${API_BASE}/api/v1/songs/${songId}/suno-pack`),
    ]);
    if (!songRes.ok) throw new Error("Song not found");
    const songBody = (await songRes.json()) as { data: Song };
    setSong(songBody.data);
    setTitle(songBody.data.title ?? "");
    setLyrics(songBody.data.lyrics?.body ?? "");
    setStyle(songBody.data.style_prompt ?? "");
    setPublishLocal(toLocalInputValue(songBody.data.publish_at));
    if (songBody.data.youtube_playlist_id) {
      setPlaylistPick(songBody.data.youtube_playlist_id);
    }
    if (packRes.ok) {
      const packBody = (await packRes.json()) as { data: SunoPack };
      setPack(packBody.data);
    } else {
      setPack(null);
    }
  }, [songId]);

  const loadPlaylists = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/playlists`);
      if (!res.ok) {
        setPlaylistHint(await res.text());
        setPlaylists([]);
        return;
      }
      const body = (await res.json()) as {
        data?: { playlists?: YtPlaylist[]; hint?: string };
      };
      setPlaylists(body.data?.playlists ?? []);
      setPlaylistHint(body.data?.hint ?? null);
    } catch (err) {
      setPlaylistHint(err instanceof Error ? err.message : "Could not load playlists");
    }
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [load]);

  useEffect(() => {
    void loadPlaylists();
  }, [loadPlaylists]);

  // Auto-refresh while background Gemini lyrics are writing
  useEffect(() => {
    if (song?.stage !== "generating_lyrics") return;
    const t = window.setInterval(() => {
      void load().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(t);
  }, [song?.stage, load]);

  async function saveManualEdits(approve: boolean) {
    if (!songId) return;
    const trimmedTitle = title.trim();
    const trimmedLyrics = lyrics.trim();
    if (!trimmedTitle) {
      setError("Title is required.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const lyricsChanged = trimmedLyrics !== (song?.lyrics?.body ?? "").trim();
      const styleChanged = style !== (song?.style_prompt ?? "");
      const titleChanged = trimmedTitle !== (song?.title ?? "");

      if (trimmedLyrics && (lyricsChanged || approve || styleChanged || titleChanged)) {
        const res = await fetch(`${API_BASE}/api/v1/songs/${songId}/lyrics`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            body: lyrics,
            approve,
            title: trimmedTitle,
            style_prompt: style,
          }),
        });
        if (!res.ok) throw new Error(await res.text());
      } else if (titleChanged || styleChanged) {
        const res = await fetch(`${API_BASE}/api/v1/songs/${songId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...(titleChanged ? { title: trimmedTitle } : {}),
            ...(styleChanged ? { style_prompt: style } : {}),
          }),
        });
        if (!res.ok) throw new Error(await res.text());
      } else if (approve && song?.lyrics) {
        const res = await fetch(`${API_BASE}/api/v1/songs/${songId}/lyrics/approve`, {
          method: "POST",
        });
        if (!res.ok) throw new Error(await res.text());
      } else {
        setNotice("Nothing to save — title, style, and lyrics are unchanged.");
        return;
      }

      setNotice(
        approve
          ? "Title, style & lyrics saved and approved — copy Suno pack and generate."
          : "Title, style & lyrics saved.",
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function copyPack() {
    if (!pack) return;
    await navigator.clipboard.writeText(pack.copy_all);
    setNotice("Suno pack copied to clipboard.");
  }

  async function copyField(label: string, text: string) {
    const value = text.trim();
    if (!value) {
      setNotice(`${label} is empty — nothing to copy.`);
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setNotice(`${label} copied.`);
    } catch {
      setError(`Could not copy ${label.toLowerCase()}.`);
    }
  }

  async function regenerateLyrics() {
    if (!songId) return;
    setBusy(true);
    setError(null);
    setNotice("Gemini is writing lyrics — usually 1–3 minutes. Keep this tab open…");
    try {
      const res = await fetch(`${API_BASE}/api/v1/songs/${songId}/lyrics/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: regenTopic || song?.notes || null,
          deity: song?.deity || null,
          title: title.trim() || song?.title || null,
          vocal_preference: song?.vocal_preference || "m",
          music_genre: song?.music_genre || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = (await res.json()) as { data: Song };
      setSong(body.data);
      setTitle(body.data.title ?? "");
      setLyrics(body.data.lyrics?.body ?? "");
      setStyle(body.data.style_prompt ?? "");
      setNotice(
        `New draft v${body.data.lyrics?.version ?? "?"} — title, lyrics & style updated. Review and save/approve.`,
      );
      try {
        await load();
      } catch {
        // Song already updated in UI; pack refresh is optional
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Regenerate failed");
      setNotice(null);
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(file: File | null) {
    if (!file || !songId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/api/v1/songs/${songId}/music/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      setNotice("Audio uploaded — stage is music_ready. Next: visuals / render.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  if (!song) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-12">
        <p className="text-ink/60">{error ?? "Loading…"}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-8 px-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link to="/songs" className="text-sm text-temple hover:underline">
            ← All songs
          </Link>
          <h1 className="mt-2 font-display text-4xl text-ink">{title || song.title}</h1>
          <p className="text-ink/60">
            Stage: <span className="font-medium text-ink">{song.stage}</span>
            {song.deity ? ` · ${song.deity}` : ""}
          </p>
          {song.stage === "generating_lyrics" && (
            <p className="mt-2 text-sm text-temple">
              Gemini is writing lyrics in the background — refresh in a minute (you can create
              other songs meanwhile).
            </p>
          )}
        </div>
      </div>

      {error && <p className="border border-saffron/40 bg-white/50 px-4 py-3 text-saffron">{error}</p>}
      {notice && <p className="border border-temple/30 bg-white/50 px-4 py-3 text-temple">{notice}</p>}

      <section className="grid gap-4 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">1. Title, lyrics & style</h2>
        <p className="text-sm text-ink/60">
          Edit manually anytime — Save keeps your title (won&apos;t replace it with Pallavi).
          Regenerate still drafts a fresh Gemini version you can tweak.
        </p>
        <label className="grid gap-1 text-sm">
          Title
          <input
            className="border border-ink/15 bg-white/80 px-3 py-2 text-base"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Song title (Telugu or English)"
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="flex items-center justify-between gap-2">
            <span>Style prompt (Suno) — auto-includes Telugu pronunciation / clear-diction tags</span>
            <button
              type="button"
              title="Copy style"
              aria-label="Copy style"
              disabled={!style.trim()}
              onClick={(e) => {
                e.preventDefault();
                void copyField("Style", style);
              }}
              className="shrink-0 border border-ink/15 bg-white px-2 py-0.5 text-xs text-ink/70 hover:border-temple/40 hover:text-temple disabled:opacity-40"
            >
              ⧉ Copy
            </button>
          </span>
          <textarea
            className="min-h-20 border border-ink/15 bg-white/80 px-3 py-2 text-sm"
            value={style}
            onChange={(e) => setStyle(e.target.value)}
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="flex items-center justify-between gap-2">
            <span>Lyrics</span>
            <button
              type="button"
              title="Copy lyrics"
              aria-label="Copy lyrics"
              disabled={!lyrics.trim()}
              onClick={(e) => {
                e.preventDefault();
                void copyField("Lyrics", lyrics);
              }}
              className="shrink-0 border border-ink/15 bg-white px-2 py-0.5 text-xs text-ink/70 hover:border-temple/40 hover:text-temple disabled:opacity-40"
            >
              ⧉ Copy
            </button>
          </span>
          <textarea
            className="min-h-56 border border-ink/15 bg-white/80 px-3 py-2 font-mono text-sm"
            value={lyrics}
            onChange={(e) => setLyrics(e.target.value)}
          />
        </label>
        <label className="grid gap-1 text-sm">
          Regen topic hint (optional)
          <input
            className="border border-ink/15 bg-white/80 px-3 py-2"
            value={regenTopic}
            onChange={(e) => setRegenTopic(e.target.value)}
            placeholder="Adjust mood / focus for Gemini regenerate"
          />
        </label>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => void regenerateLyrics()}
            className="bg-ink px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            {busy ? "Generating… (1–3 min)" : "Regenerate with Gemini"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void saveManualEdits(false)}
            className="border border-ink/20 bg-white px-4 py-2 text-ink disabled:opacity-50"
          >
            Save title / style / lyrics
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void saveManualEdits(true)}
            className="bg-temple px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            Save & approve
          </button>
        </div>
        {song.lyrics && (
          <p className="text-sm text-ink/55">
            Version {song.lyrics.version}
            {song.lyrics.approved ? " · approved" : " · draft"}
          </p>
        )}
      </section>

      <section className="grid gap-4 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">2. Generate in Suno (your Pro)</h2>
        {pack ? (
          <>
            <ol className="list-decimal space-y-1 pl-5 text-sm text-ink/75">
              {pack.instructions.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <pre className="max-h-64 overflow-auto border border-ink/10 bg-ink/5 p-4 text-xs whitespace-pre-wrap">
              {pack.copy_all}
            </pre>
            <button
              type="button"
              onClick={() => void copyPack()}
              className="justify-self-start bg-ink px-4 py-2 font-medium text-white"
            >
              Copy Suno pack
            </button>
          </>
        ) : (
          <p className="text-ink/60">Save lyrics first to build the Suno pack.</p>
        )}
      </section>

      <section className="grid gap-4 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">3. Upload finished audio</h2>
        <input
          type="file"
          accept="audio/*,audio/webm,video/webm,.mp3,.wav,.m4a,.ogg,.webm"
          disabled={busy}
          onChange={(e) => void onUpload(e.target.files?.[0] ?? null)}
        />
        {song.music && (
          <div className="space-y-2 text-sm text-ink/75">
            <p>
              Uploaded: <strong>{song.music.original_filename}</strong> ({song.music.status})
            </p>
            <audio controls src={withPortalKey(`${API_BASE}${song.music.download_path}`)} className="w-full" />
          </div>
        )}
      </section>

      <section className="grid gap-3 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">4. Visual (16:9 + Shorts 9:16)</h2>
        <p className="text-sm text-ink/65">
          Prefer uploading a finished video when you already have a better clip — kept as-is
          (no scale/crop). Or generate one silent <strong>16:9</strong> clip (Gemini first, Kling if
          quota exhausted); AI Shorts use <strong>9:16 center-crop</strong> &lt;30s. On a schedule,
          auto-prep skips generation when a clip is already present.
        </p>
        {song.visual?.clip_url ? (
          <video
            controls
            src={withPortalKey(`${API_BASE}${song.visual.clip_url}?v=${encodeURIComponent(song.visual.clip_path || "")}`)}
            className="max-w-lg border border-ink/10"
          />
        ) : (
          <p className="text-sm text-saffron">No visual clip yet — upload one or generate below.</p>
        )}
        {visualProgress && (
          <div className="max-w-lg space-y-2" aria-live="polite">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-ink/80">{visualProgress.message}</span>
              <span className="shrink-0 font-medium tabular-nums text-ink">
                {visualProgress.percent}%
              </span>
            </div>
            <div className="h-2.5 w-full overflow-hidden bg-ink/10">
              <div
                className="h-full bg-temple transition-[width] duration-500 ease-out"
                style={{ width: `${visualProgress.percent}%` }}
              />
            </div>
            <p className="text-xs text-ink/55">
              Kling can take several minutes. Keep this tab open — the bar updates as the job runs.
            </p>
          </div>
        )}
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 border-2 border-temple bg-temple/10 px-4 py-4">
            <p className="text-base font-semibold text-ink">Upload your own video (skip AI)</p>
            <p className="text-xs text-ink/60">
              Use a finished clip (mp4 / mov / webm). Kept exactly as uploaded — no scale, crop,
              watermark trim, or re-encode. Shorts are a time-slice only. No Gemini/Kling.
            </p>
            <label className="inline-flex w-fit cursor-pointer items-center gap-2 bg-temple px-5 py-2.5 text-sm font-semibold text-white has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50">
              {busy ? "Uploading…" : "Choose video file…"}
              <input
                type="file"
                accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm,.m4v"
                disabled={busy}
                className="sr-only"
                onChange={(e) =>
                  void (async () => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (!file) return;
                    setBusy(true);
                    setError(null);
                    setNotice("Uploading video — keeping as-is…");
                    setVisualProgress(null);
                    try {
                      const form = new FormData();
                      form.append("file", file);
                      const res = await fetch(
                        `${API_BASE}/api/v1/songs/${song.id}/visuals/upload`,
                        { method: "POST", body: form },
                      );
                      if (!res.ok) throw new Error(await res.text());
                      const body = (await res.json()) as { data?: { note?: string } };
                      setNotice(body.data?.note ?? "Video uploaded — stage is video_ready.");
                      await load();
                    } catch (err) {
                      setError(err instanceof Error ? err.message : "Video upload failed");
                      setNotice(null);
                    } finally {
                      setBusy(false);
                    }
                  })()
                }
              />
            </label>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void (async () => {
                setBusy(true);
                setError(null);
                setNotice(null);
                setVisualProgress({ percent: 1, message: "Starting visual job…" });
                try {
                  const res = await fetch(`${API_BASE}/api/v1/songs/${song.id}/visuals/generate`, {
                    method: "POST",
                  });
                  if (!res.ok) throw new Error(await res.text());
                  const body = (await res.json()) as { data?: { job_id?: string; note?: string } };
                  const jobId = body.data?.job_id;
                  if (!jobId) throw new Error("No job_id returned from visuals/generate");
                  const result = await pollVisualJob(jobId);
                  setVisualProgress({ percent: 100, message: "Visual + Shorts ready" });
                  setNotice(
                    (result && typeof result === "object" && "note" in result
                      ? String((result as { note?: string }).note)
                      : null) ?? "Visual + Shorts ready.",
                  );
                  await load();
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Visual generate failed");
                  setVisualProgress(null);
                } finally {
                  setBusy(false);
                }
              })()
            }
            className="w-fit border border-ink/20 bg-white px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {visualProgress && busy
              ? `Generating… ${visualProgress.percent}%`
              : "Or generate with AI (16:9 + Shorts)"}
          </button>
        </div>
      </section>

      <section className="grid gap-3 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">5. Thumbnail</h2>
        <p className="text-sm text-ink/65">
          Prefer uploading a finished ChatGPT / design thumb, or generate with AI (Gemini → Kling
          fallback). Manual upload is used as-is for YouTube publish.
        </p>
        {song.thumbnail?.path ? (
          <img
            key={song.thumbnail.path}
            src={withPortalKey(`${API_BASE}/api/v1/songs/${song.id}/thumbnail?v=${encodeURIComponent(song.thumbnail.path)}`)}
            alt="YouTube thumbnail preview"
            className="max-w-lg border border-ink/10"
          />
        ) : (
          <p className="text-sm text-saffron">No thumbnail yet — upload one or generate below.</p>
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="flex flex-col gap-2 rounded border-2 border-temple/40 bg-temple/5 px-4 py-3">
            <p className="text-sm font-semibold text-ink">Upload finished thumbnail (ChatGPT / design)</p>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
              disabled={busy}
              className="block w-full max-w-md text-sm text-ink file:mr-3 file:cursor-pointer file:border-0 file:bg-temple file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white disabled:opacity-50"
              onChange={(e) =>
                void (async () => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  setBusy(true);
                  setError(null);
                  setNotice("Uploading thumbnail…");
                  try {
                    const form = new FormData();
                    form.append("file", file);
                    const res = await fetch(
                      `${API_BASE}/api/v1/songs/${song.id}/thumbnail/upload`,
                      { method: "POST", body: form },
                    );
                    if (!res.ok) throw new Error(await res.text());
                    const body = (await res.json()) as { data?: { note?: string } };
                    setNotice(body.data?.note ?? "Thumbnail uploaded.");
                    await load();
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Thumbnail upload failed");
                    setNotice(null);
                  } finally {
                    setBusy(false);
                  }
                })()
              }
            />
          </div>
          <button
            type="button"
            disabled={busy || !song.lyrics}
            onClick={() =>
              void (async () => {
                setBusy(true);
                setError(null);
                setNotice("Generating AI thumbnail — keep this tab open (20–90s)…");
                try {
                  const res = await fetch(
                    `${API_BASE}/api/v1/songs/${song.id}/thumbnail/generate`,
                    { method: "POST" },
                  );
                  if (!res.ok) throw new Error(await res.text());
                  const body = (await res.json()) as {
                    data?: { engine?: string; note?: string; overlay_title?: string };
                  };
                  setNotice(
                    body.data?.note ??
                      `Thumbnail ready (${body.data?.engine ?? "ai"})${
                        body.data?.overlay_title ? ` — title: ${body.data.overlay_title}` : ""
                      }`,
                  );
                  await load();
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Thumbnail failed");
                  setNotice(null);
                } finally {
                  setBusy(false);
                }
              })()
            }
            className="border border-ink/20 bg-white px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {busy ? "Generating…" : "Generate with AI"}
          </button>
        </div>
      </section>

      <section className="grid gap-3 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">6. YouTube playlist</h2>
        <p className="text-sm text-ink/65">
          Auto-pick by deity, or choose manually from your channel list. Shorts use the same
          playlist as the main video.
        </p>
        <p className="text-sm">
          Selected:{" "}
          <strong>
            {song.youtube_playlist_title ?? "— none yet —"}
            {song.youtube_playlist_id ? "" : " (needs selection)"}
          </strong>
        </p>
        <p className="text-sm">
          Token expired / 401?{" "}
          <a
            className="font-medium text-temple underline"
            href={withPortalKey(`${API_BASE}/api/v1/youtube/auth`)}
            target="_blank"
            rel="noreferrer"
          >
            Reconnect YouTube OAuth
          </a>
          {" "}then hit Refresh list.
        </p>
        {playlistHint && !playlists.length && (
          <p className="text-sm text-saffron">{playlistHint}</p>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid min-w-[16rem] flex-1 gap-1 text-sm">
            Channel playlists
            <select
              className="border border-ink/15 bg-white/80 px-3 py-2"
              value={playlistPick}
              onChange={(e) => setPlaylistPick(e.target.value)}
            >
              <option value="">— select playlist —</option>
              {playlists.map((pl) => (
                <option key={pl.id} value={pl.id}>
                  {pl.title}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy || !playlistPick}
            onClick={() =>
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  const chosen = playlists.find((p) => p.id === playlistPick);
                  const res = await fetch(`${API_BASE}/api/v1/playlists/songs/${song.id}/assign`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      auto: false,
                      both: true,
                      playlist_id: playlistPick,
                      playlist_title: chosen?.title ?? null,
                    }),
                  });
                  if (!res.ok) throw new Error(await res.text());
                  setNotice(`Playlist set: ${chosen?.title ?? playlistPick}`);
                  await load();
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Manual playlist failed");
                } finally {
                  setBusy(false);
                }
              })()
            }
            className="border border-ink/20 bg-white px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Use selected
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void (async () => {
                setBusy(true);
                setError(null);
                try {
                  await loadPlaylists();
                  const res = await fetch(`${API_BASE}/api/v1/playlists/songs/${song.id}/assign`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ auto: true, both: true }),
                  });
                  if (!res.ok) throw new Error(await res.text());
                  const body = (await res.json()) as {
                    data?: { needs_manual?: boolean; song?: { youtube_playlist_title?: string } };
                  };
                  if (body.data?.needs_manual) {
                    setNotice(
                      "Auto-pick found no match — choose a playlist from the list and click Use selected.",
                    );
                  } else {
                    setNotice(
                      `Auto-picked: ${body.data?.song?.youtube_playlist_title ?? "playlist"}`,
                    );
                  }
                  await load();
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Playlist match failed");
                } finally {
                  setBusy(false);
                }
              })()
            }
            className="border border-ink/20 bg-white px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Auto-pick
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void loadPlaylists()}
            className="border border-ink/20 bg-white px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Refresh list
          </button>
        </div>
      </section>

      <section className="grid gap-3 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">7. Final mix (audio + video) — preview before publish</h2>
        <p className="text-sm text-ink/65">
          Long-form: full Suno audio under the 16:9 visual. Shorts: each 9:16 clip gets audio from the{" "}
          <strong>middle of a different Charanam</strong> (Short 1 ← Charanam 1, Short 2 ← Charanam 2),
          not the same opening. Remixed under 30s. Preview before publish.
        </p>
        <button
          type="button"
          disabled={busy || !song.music || !song.visual?.clip_url}
          onClick={() =>
            void (async () => {
              setBusy(true);
              setError(null);
              setNotice("Mixing audio + video — usually under a minute…");
              try {
                const res = await fetch(`${API_BASE}/api/v1/songs/${song.id}/final/mix`, {
                  method: "POST",
                });
                if (!res.ok) throw new Error(await res.text());
                const body = (await res.json()) as { data?: { note?: string } };
                setNotice(body.data?.note ?? "Final mix ready — preview below.");
                await load();
              } catch (err) {
                setError(err instanceof Error ? err.message : "Final mix failed");
                setNotice(null);
              } finally {
                setBusy(false);
              }
            })()
          }
          className="justify-self-start border border-ink/20 bg-white px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {busy ? "Mixing…" : "Mix audio + video"}
        </button>
        {song.final?.url ? (
          <div className="grid gap-3">
            <p className="text-sm font-medium">Long-form (16:9) with audio</p>
            <video
              key={song.final.path || song.final.url}
              controls
              src={withPortalKey(`${API_BASE}${song.final.url}?v=${encodeURIComponent(song.final.path || "")}`)}
              className="max-w-2xl border border-ink/10"
            />
            <div className="grid gap-3 sm:grid-cols-2">
              {song.shorts
                ?.filter((s) => s.final_url)
                .map((s) => (
                  <div key={s.id} className="grid gap-1">
                    <p className="text-sm font-medium">
                      Short {s.slot_index} — Charanam {s.slot_index} mid-cut (9:16)
                      {typeof s.audio_start_sec === "number" &&
                      typeof s.audio_end_sec === "number"
                        ? ` · audio ${Math.round(s.audio_start_sec)}s–${Math.round(s.audio_end_sec)}s`
                        : ""}
                    </p>
                    <video
                      key={s.final_clip_path || s.final_url}
                      controls
                      src={withPortalKey(`${API_BASE}${s.final_url}?v=${encodeURIComponent(s.final_clip_path || "")}`)}
                      className="max-h-80 border border-ink/10"
                    />
                  </div>
                ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-saffron">
            No final mix yet — upload audio + generate visual, then Mix audio + video.
          </p>
        )}
      </section>

      <section className="grid gap-3 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">8. Publish anytime</h2>
        <p className="text-sm text-ink/65">
          Requires final mix + playlist. One Short goes live with the main video (Short 2 paused).
          If you set a time and do nothing, auto video+mix runs ~1h before publish, then uploads
          at the scheduled time.
        </p>
        {song.pipeline && (
          <div className="border border-temple/30 bg-temple/5 px-4 py-3 text-sm text-ink/80">
            <p className="font-medium text-ink">Auto pipeline</p>
            <p>{song.pipeline.detail}</p>
            {song.pipeline.prep_at && (
              <p className="mt-1 text-xs text-ink/55">
                Prep window opens {new Date(song.pipeline.prep_at).toLocaleString()} · provider{" "}
                {song.pipeline.video_provider || "auto"}
              </p>
            )}
          </div>
        )}
        {song.readiness && (
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {song.readiness.checks.map((c) => (
              <li key={c.key} className={c.ok ? "text-temple" : "text-saffron"}>
                {c.ok ? "✓" : "○"} {c.label}
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-sm">
            Publish at (any time) — saves when you pick
            <input
              type="datetime-local"
              className="border border-ink/15 bg-white/80 px-3 py-2"
              value={publishLocal}
              onChange={(e) => {
                const v = e.target.value;
                setPublishLocal(v); // keep picker on chosen value (don't snap back)
                if (!v) return;
                void (async () => {
                  const res = await fetch(`${API_BASE}/api/v1/publish/songs/${song.id}/schedule`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      publish_at: new Date(v).toISOString(),
                      publish_now: false,
                    }),
                  });
                  if (!res.ok) {
                    setError(await res.text());
                    return;
                  }
                  setNotice("Publish time updated.");
                  setSong((prev) =>
                    prev ? { ...prev, publish_at: new Date(v).toISOString() } : prev,
                  );
                })();
              }}
            />
          </label>
          <button
            type="button"
            disabled={busy || !song.readiness?.publishable}
            title={
              song.readiness?.publishable
                ? "Upload long-form + Shorts to YouTube now"
                : `Missing: ${(song.readiness?.missing || []).join(", ") || "final mix / playlist"}`
            }
            onClick={() =>
              void (async () => {
                setBusy(true);
                setError(null);
                setNotice(
                  "Uploading to YouTube (long-form + Shorts) — keep this tab open, usually 1–5 min…",
                );
                try {
                  const res = await fetch(`${API_BASE}/api/v1/publish/songs/${song.id}/schedule`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ publish_now: true }),
                  });
                  const body = (await res.json().catch(() => ({}))) as {
                    detail?: unknown;
                    data?: {
                      message?: string;
                      youtube_url?: string;
                      upload?: { shorts?: { url?: string; slot_index?: number }[] };
                    };
                  };
                  if (!res.ok) {
                    const d = body.detail;
                    throw new Error(
                      typeof d === "string"
                        ? d
                        : d
                          ? JSON.stringify(d)
                          : "Publish now failed",
                    );
                  }
                  const ytUrl = body.data?.youtube_url;
                  const shortLinks = (body.data?.upload?.shorts || [])
                    .filter((s) => s.url)
                    .map((s) => `Short ${s.slot_index}: ${s.url}`)
                    .join(" · ");
                  setNotice(
                    [
                      body.data?.message || "Published to YouTube.",
                      ytUrl ? `Long-form: ${ytUrl}` : null,
                      shortLinks || null,
                    ]
                      .filter(Boolean)
                      .join(" "),
                  );
                  await load();
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Publish now failed");
                  setNotice(null);
                } finally {
                  setBusy(false);
                }
              })()
            }
            className="bg-temple px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            {busy ? "Publishing to YouTube…" : song.youtube_url ? "Re-publish / open links" : "Publish now"}
          </button>
          {song.youtube_url && (
            <a
              href={song.youtube_url}
              target="_blank"
              rel="noreferrer"
              className="px-4 py-2 text-sm text-temple underline"
            >
              Open long-form
            </a>
          )}
          <Link to="/ready" className="px-4 py-2 text-sm text-temple underline">
            Open Ready queue
          </Link>
        </div>
        {(song.youtube_url || song.shorts?.some((s) => s.youtube_url)) && (
          <div className="grid gap-2 border border-ink/10 bg-white/70 p-4 text-sm">
            <p className="font-medium text-ink">Uploaded to YouTube</p>
            {song.youtube_url && (
              <p>
                Long-form:{" "}
                <a href={song.youtube_url} target="_blank" rel="noreferrer" className="text-temple underline">
                  {song.youtube_url}
                </a>
              </p>
            )}
            {(song.shorts || [])
              .filter((s) => s.youtube_url)
              .map((s) => (
                <p key={s.id}>
                  Short {s.slot_index}:{" "}
                  <a href={s.youtube_url!} target="_blank" rel="noreferrer" className="text-temple underline">
                    {s.youtube_url}
                  </a>
                  {song.youtube_url && (
                    <>
                      {" "}
                      → related{" "}
                      <a
                        href={song.youtube_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-temple underline"
                      >
                        full song
                      </a>
                    </>
                  )}
                </p>
              ))}
            {!song.shorts?.some((s) => s.youtube_url) && song.youtube_url && (
              <p className="text-saffron">
                Shorts links missing in UI data — refresh the page. If still empty, click Publish now
                again (already-uploaded Shorts are reused).
              </p>
            )}
            {song.youtube_url && song.shorts?.some((s) => s.youtube_url) && (
              <p className="text-xs text-ink/55">
                Each Short description links to the long-form. For the in-player Related video chip,
                open YouTube Studio → Short → Related video → pick this long-form (API cannot set that
                chip).
              </p>
            )}
          </div>
        )}
      </section>

      <section className="grid gap-3 border border-ink/10 bg-white/55 p-6">
        <h2 className="font-display text-2xl">9. YouTube package (auto from latest lyrics)</h2>
        <p className="text-sm text-ink/65">
          Regenerates every time you create/regenerate/approve lyrics or rebuild the thumbnail —
          Narasimha-style Telugu + English discovery copy.
        </p>
        <div className="grid gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-ink/50">Title</p>
          <p className="border border-ink/10 bg-white/80 p-3 text-sm font-medium">
            {song.youtube_title || song.title || "— regenerate lyrics to fill —"}
          </p>
          <p className="text-xs font-medium uppercase tracking-wide text-ink/50">Description</p>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap border border-ink/10 bg-white/80 p-3 text-xs leading-relaxed">
            {song.youtube_description || "— regenerate lyrics to fill —"}
          </pre>
          {song.youtube_tags && (
            <>
              <p className="text-xs font-medium uppercase tracking-wide text-ink/50">Tags</p>
              <p className="border border-ink/10 bg-white/80 p-3 text-xs text-ink/70">{song.youtube_tags}</p>
            </>
          )}
        </div>
      </section>

      {(song.shorts?.length ?? 0) > 0 && (
        <section className="grid gap-3 border border-ink/10 bg-white/55 p-6">
          <h2 className="font-display text-2xl">10. Short — cut from main clip</h2>
          <p className="text-sm text-ink/65">
            Portrait 9:16 center-crop from the main 16:9 clip (ffmpeg). One Short for now;
            Short 2 is paused.
          </p>
          <ul className="space-y-3">
            {song.shorts!.filter((s) => s.slot_index <= 1).map((s) => (
              <li key={s.id} className="border border-ink/10 bg-white/70 p-3 text-sm">
                <p className="font-medium">
                  Short {s.slot_index}: {s.title}
                </p>
                <p className="text-ink/70">{s.hook}</p>
                <p className="mt-1 text-ink/50">stage: {s.stage}</p>
                {s.clip_url && (
                  <video
                    controls
                    src={withPortalKey(`${API_BASE}${s.clip_url}`)}
                    className="mt-2 max-h-64 border border-ink/10"
                  />
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

type ScheduleSlot = {
  id: string;
  slot_date: string;
  weekday: string;
  daypart?: string;
  daypart_label?: string;
  publish_at?: string | null;
  title_hint?: string | null;
  status: string;
  published?: boolean;
  song_id?: string | null;
  song_title?: string | null;
  song_stage?: string | null;
  youtube_url?: string | null;
  youtube_video_id?: string | null;
  auto_deity?: string | null;
  auto_mood?: string | null;
  suggestion?: {
    deity: string;
    month_mood: string;
    festive_hint: string;
    shorts_plan?: string;
  };
};

type ScheduleDay = { date: string; slots: ScheduleSlot[] };

function mondayLocalISO(d = new Date()): string {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const day = x.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  x.setDate(x.getDate() + diff);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}`;
}

function addDaysISO(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const x = new Date(y, m - 1, d + days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}`;
}

function WeekSchedule() {
  const [weekStart, setWeekStart] = useState(() => mondayLocalISO());
  const [days, setDays] = useState<ScheduleDay[]>([]);
  const [planNote, setPlanNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    const ensure = await fetch(`${API_BASE}/api/v1/schedule/weeks/ensure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ week_start: weekStart }),
    });
    if (!ensure.ok) throw new Error(await ensure.text());
    const body = (await ensure.json()) as {
      data: { days?: ScheduleDay[]; slots: ScheduleSlot[]; plan?: { note?: string; shorts_per_day?: number } };
    };
    setPlanNote(
      body.data.plan?.note ??
        "Each day: morning song + evening song; each song → 2 Shorts from same audio/video (4 Shorts/day).",
    );
    if (body.data.days?.length) {
      setDays(body.data.days);
    } else {
      const grouped = new Map<string, ScheduleSlot[]>();
      for (const s of body.data.slots) {
        const list = grouped.get(s.slot_date) ?? [];
        list.push(s);
        grouped.set(s.slot_date, list);
      }
      setDays([...grouped.entries()].map(([date, slots]) => ({ date, slots })));
    }
  }, [weekStart]);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [load]);

  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const weekEnd = addDaysISO(weekStart, 6);

  async function saveHint(slotId: string, title_hint: string) {
    await fetch(`${API_BASE}/api/v1/schedule/slots/${slotId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title_hint }),
    });
  }

  async function savePublishAt(slotId: string, localValue: string) {
    if (!localValue) return;
    setError(null);
    setSaveNotice(null);
    const res = await fetch(`${API_BASE}/api/v1/schedule/slots/${slotId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        publish_at: new Date(localValue).toISOString(),
      }),
    });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    const chosenDay = localValue.slice(0, 10);
    const chosenWeek = mondayLocalISO(new Date(`${chosenDay}T12:00:00`));
    setSaveNotice(`Publish time saved for ${chosenDay}.`);
    if (chosenWeek !== weekStart) {
      // Jump the week picker so the slot stays visible after a date change
      setWeekStart(chosenWeek);
      return;
    }
    await load();
  }

  async function materialize(slotId: string) {
    setBusyIds((prev) => ({ ...prev, [slotId]: true }));
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/schedule/slots/${slotId}/materialize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ generate_lyrics: true, approve_lyrics: false }),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = (await res.json()) as {
        data: { song_id: string; note?: string; lyrics_pending?: boolean };
      };
      setSaveNotice(
        body.data.note ||
          (body.data.lyrics_pending
            ? "Song created — lyrics generating in background. You can create another now."
            : "Song created."),
      );
      await load();
      // Stay on schedule so parallel creates keep working (Open song from the slot card).
    } catch (err) {
      setError(err instanceof Error ? err.message : "Materialize failed");
    } finally {
      setBusyIds((prev) => {
        const next = { ...prev };
        delete next[slotId];
        return next;
      });
    }
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-8 px-6 py-12">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-[0.25em] text-temple/80">Weekly plan</p>
        <h1 className="font-display text-4xl text-ink">2 songs / day · 4 Shorts</h1>
        <p className="max-w-2xl text-ink/70">{planNote}</p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-sm">
          Week (pick any day in that week)
          <input
            type="date"
            className="border border-ink/15 bg-white/80 px-3 py-2"
            value={weekStart}
            onChange={(e) => setWeekStart(mondayLocalISO(new Date(`${e.target.value}T12:00:00`)))}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="border border-ink/20 bg-white px-3 py-2 text-sm"
            onClick={() => setWeekStart(addDaysISO(weekStart, -7))}
          >
            ← Prev week
          </button>
          <button
            type="button"
            className="border border-ink/20 bg-white px-3 py-2 text-sm"
            onClick={() => setWeekStart(mondayLocalISO())}
          >
            This week
          </button>
          <button
            type="button"
            className="border border-ink/20 bg-white px-3 py-2 text-sm"
            onClick={() => setWeekStart(addDaysISO(weekStart, 7))}
          >
            Next week →
          </button>
        </div>
        <p className="w-full text-sm text-ink/65">
          Showing week <strong>{weekStart}</strong> → <strong>{weekEnd}</strong> (Mon–Sun). Use Next
          week to see later dates (e.g. 2 Nov).
        </p>
      </div>

      {error && <p className="border border-saffron/40 bg-white/50 px-4 py-3 text-saffron">{error}</p>}
      {saveNotice && (
        <p className="border border-temple/30 bg-white/50 px-4 py-3 text-temple">{saveNotice}</p>
      )}

      <ul className="space-y-6">
        {days.map((day) => {
          const weekday = day.slots[0]?.weekday ?? day.date;
          return (
            <li key={day.date} className="border border-ink/10 bg-white/55 p-4">
              <h2 className="font-display text-2xl text-ink">
                {weekday} · {day.date}
              </h2>
              <p className="mb-4 text-sm text-ink/55">
                Mood: {day.slots[0]?.auto_mood ?? "—"} · Morning & evening use different deities
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                {day.slots.map((slot) => (
                  <div
                    key={slot.id}
                    className={`relative grid gap-2 border p-3 ${
                      slot.published
                        ? "border-temple/40 bg-temple/5"
                        : "border-ink/10 bg-white/80"
                    }`}
                  >
                    {slot.published && (
                      <div className="pointer-events-none absolute right-2 top-2 rotate-[-8deg] border-2 border-temple px-2 py-0.5 font-display text-xs font-bold tracking-wider text-temple opacity-90">
                        PUBLISHED
                      </div>
                    )}
                    <p className="font-medium text-ink pr-20">
                      {slot.daypart_label ?? slot.daypart ?? "slot"} ·{" "}
                      {slot.auto_deity ?? slot.suggestion?.deity ?? "—"} · 1 song → 2 Shorts
                    </p>
                    {slot.song_title && (
                      <p className="text-sm text-ink/70 line-clamp-2">{slot.song_title}</p>
                    )}
                    <input
                      className="w-full border border-ink/15 bg-white px-3 py-2 text-sm"
                      defaultValue={slot.title_hint ?? ""}
                      placeholder={`${slot.daypart ?? "slot"} title hint`}
                      onBlur={(e) => void saveHint(slot.id, e.target.value)}
                      disabled={!!slot.published}
                    />
                    <label className="grid gap-1 text-xs text-ink/60">
                      Publish time (anytime) — saves when you pick
                      <input
                        key={`${slot.id}-${slot.publish_at ?? "empty"}`}
                        type="datetime-local"
                        className="border border-ink/15 bg-white px-2 py-1.5 text-sm"
                        defaultValue={toLocalInputValue(slot.publish_at)}
                        disabled={!!slot.published}
                        onChange={(e) => {
                          if (!e.target.value) return;
                          void savePublishAt(slot.id, e.target.value);
                        }}
                      />
                    </label>
                    <p className="text-xs text-ink/50">
                      {slot.published ? "published" : slot.status}
                      {slot.song_stage ? ` · song: ${slot.song_stage}` : ""}
                    </p>
                    {slot.published && slot.youtube_url ? (
                      <a
                        href={slot.youtube_url}
                        target="_blank"
                        rel="noreferrer"
                        className="bg-temple px-3 py-2 text-center text-sm font-medium text-white"
                      >
                        Watch on YouTube
                      </a>
                    ) : slot.song_id ? (
                      <Link
                        to={`/songs/${slot.song_id}`}
                        className="bg-temple px-3 py-2 text-center text-sm font-medium text-white"
                      >
                        Open song
                        {slot.song_stage === "generating_lyrics" || slot.status === "song_created"
                          ? " (lyrics may still be writing)"
                          : ""}
                      </Link>
                    ) : (
                      <button
                        type="button"
                        disabled={!!busyIds[slot.id]}
                        onClick={() => void materialize(slot.id)}
                        className="bg-ink px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                      >
                        {busyIds[slot.id] ? "Starting…" : "Create song + 2 Shorts"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </main>
  );
}

type QueueSong = {
  id: string;
  title: string;
  deity?: string | null;
  stage: string;
  publish_at?: string | null;
  youtube_playlist_title?: string | null;
  shorts_playlist_title?: string | null;
  music_file?: string | null;
  shorts_count: number;
  readiness: Readiness;
  studio_path: string;
  pipeline?: {
    next_step?: string;
    detail?: string;
    prep_at?: string | null;
  };
};

function ReadyQueue() {
  const [buckets, setBuckets] = useState<Record<string, QueueSong[]>>({});
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/v1/publish/queue`);
    if (!res.ok) throw new Error(await res.text());
    const body = (await res.json()) as {
      data: {
        buckets: Record<string, QueueSong[]>;
        counts: Record<string, number>;
        note: string;
      };
    };
    setBuckets(body.data.buckets);
    setCounts(body.data.counts);
    setNote(body.data.note);
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [load]);

  async function schedule(songId: string, opts: { publish_now?: boolean; publish_at?: string }) {
    setBusyId(songId);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/publish/songs/${songId}/schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(opts),
      });
      const body = (await res.json().catch(() => ({}))) as {
        detail?: unknown;
        data?: { message?: string; youtube_url?: string };
      };
      if (!res.ok) {
        const d = body.detail;
        throw new Error(typeof d === "string" ? d : d ? JSON.stringify(d) : await res.text());
      }
      if (opts.publish_now) {
        setNote(body.data?.message || body.data?.youtube_url || "Published to YouTube.");
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Schedule failed");
    } finally {
      setBusyId(null);
    }
  }

  const sections: { key: string; title: string; blurb: string }[] = [
    {
      key: "ready_for_review",
      title: "Ready for review",
      blurb: "Lyrics + audio ready — publish now, or set a time (auto video+mix ~1h before, then auto-upload).",
    },
    {
      key: "queued",
      title: "Queued / scheduled",
      blurb: "Waiting for schedule. Auto prep ~1h before publish_at; auto YouTube at publish_at.",
    },
    {
      key: "in_progress",
      title: "Still in progress",
      blurb: "Missing lyrics or audio — finish in Song Studio first.",
    },
    {
      key: "published",
      title: "Published",
      blurb: "Live on YouTube (or marked published).",
    },
  ];

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-8 px-6 py-12">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-[0.25em] text-temple/80">Publish desk</p>
        <h1 className="font-display text-4xl text-ink">Ready queue</h1>
        <p className="max-w-2xl text-ink/70">{note}</p>
        <p className="text-sm text-ink/55">
          Review {counts.ready_for_review ?? 0} · Queued {counts.queued ?? 0} · In progress{" "}
          {counts.in_progress ?? 0}
        </p>
      </header>

      {error && <p className="border border-saffron/40 bg-white/50 px-4 py-3 text-saffron">{error}</p>}

      {sections.map((sec) => {
        const items = buckets[sec.key] ?? [];
        return (
          <section key={sec.key} className="space-y-3 border border-ink/10 bg-white/55 p-5">
            <h2 className="font-display text-2xl text-ink">
              {sec.title}{" "}
              <span className="text-base font-sans text-ink/50">({items.length})</span>
            </h2>
            <p className="text-sm text-ink/60">{sec.blurb}</p>
            {items.length === 0 ? (
              <p className="text-sm text-ink/40">None</p>
            ) : (
              <ul className="space-y-4">
                {items.map((song) => (
                  <li
                    key={song.id}
                    className="grid gap-3 border border-ink/10 bg-white/80 p-4 md:grid-cols-[1fr_auto]"
                  >
                    <div className="space-y-2">
                      <p className="font-display text-xl text-ink">{song.title}</p>
                      <p className="text-sm text-ink/60">
                        {song.deity ?? "—"} · {song.stage}
                        {song.music_file ? ` · ${song.music_file}` : ""}
                        {` · ${song.shorts_count} Shorts`}
                      </p>
                      {song.youtube_playlist_title && (
                        <p className="text-xs text-ink/50">
                          Playlist (main + Shorts): {song.youtube_playlist_title}
                        </p>
                      )}
                      {song.pipeline?.detail && (
                        <p className="text-xs text-temple/90">{song.pipeline.detail}</p>
                      )}
                      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
                        {song.readiness.checks.map((c) => (
                          <li key={c.key} className={c.ok ? "text-temple" : "text-saffron"}>
                            {c.ok ? "✓" : "○"} {c.label}
                          </li>
                        ))}
                      </ul>
                      <Link to={song.studio_path} className="text-sm text-temple underline">
                        Open in Song Studio
                      </Link>
                    </div>
                    <div className="flex flex-col gap-2">
                      <label className="grid gap-1 text-xs">
                        Any publish time — saves when you pick
                        <input
                          key={`${song.id}-${song.publish_at ?? "empty"}`}
                          type="datetime-local"
                          className="border border-ink/15 px-2 py-1.5 text-sm"
                          defaultValue={toLocalInputValue(song.publish_at)}
                          disabled={busyId === song.id}
                          onChange={(e) => {
                            if (!e.target.value) return;
                            void schedule(song.id, {
                              publish_at: new Date(e.target.value).toISOString(),
                            });
                          }}
                        />
                      </label>
                      <button
                        type="button"
                        disabled={!song.readiness.publishable || busyId === song.id}
                        title={
                          song.readiness.publishable
                            ? "Upload long-form + Shorts to YouTube"
                            : `Need final mix + playlist. Missing: ${song.readiness.missing.join(", ")}`
                        }
                        onClick={() => void schedule(song.id, { publish_now: true })}
                        className="bg-temple px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                      >
                        {busyId === song.id ? "Publishing to YouTube…" : "Publish now"}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </main>
  );
}

function BrandingPage() {
  const [hasLogo, setHasLogo] = useState(false);
  const [filename, setFilename] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [bust, setBust] = useState(0);

  const load = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/v1/branding`);
    if (!res.ok) throw new Error("Failed to load branding");
    const body = (await res.json()) as {
      data: { has_logo: boolean; logo_original_filename?: string | null };
    };
    setHasLogo(body.data.has_logo);
    setFilename(body.data.logo_original_filename ?? null);
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [load]);

  async function onUpload(file: File | null) {
    if (!file) return;
    setError(null);
    setNotice(null);
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/v1/branding/logo`, { method: "POST", body: form });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    setNotice("Channel logo saved — thumbnails will include it with deity + title.");
    setBust((n) => n + 1);
    await load();
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-[0.25em] text-temple/80">Branding</p>
        <h1 className="font-display text-4xl text-ink">Channel logo</h1>
        <p className="text-ink/70">
          Every thumbnail: deity image + Telugu title + this logo. Upload once; reused for all
          songs.
        </p>
      </header>
      {error && <p className="border border-saffron/40 bg-white/50 px-4 py-3 text-saffron">{error}</p>}
      {notice && <p className="border border-temple/30 bg-white/50 px-4 py-3 text-temple">{notice}</p>}
      <input
        type="file"
        accept="image/png,image/jpeg,image/webp,.svg"
        onChange={(e) => void onUpload(e.target.files?.[0] ?? null)}
      />
      {hasLogo && (
        <div className="space-y-2">
          <p className="text-sm text-ink/60">Current: {filename}</p>
          <img
            src={withPortalKey(`${API_BASE}/api/v1/branding/logo?v=${bust}`)}
            alt="Channel logo"
            className="max-h-40 border border-ink/10 bg-white p-3"
          />
        </div>
      )}
    </main>
  );
}

export default function App() {
  return (
    <div>
      <nav className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-6 py-4">
        <Link to="/" className="font-display text-xl font-semibold text-ink">
          Ragam
        </Link>
        <div className="flex flex-wrap gap-4 text-sm">
          <Link to="/ready" className="text-ink/70 hover:text-ink">
            Ready queue
          </Link>
          <Link to="/schedule" className="text-ink/70 hover:text-ink">
            Week schedule
          </Link>
          <Link to="/songs" className="text-ink/70 hover:text-ink">
            Song Studio
          </Link>
          <Link to="/branding" className="text-ink/70 hover:text-ink">
            Logo
          </Link>
          <Link to="/denoise" className="text-ink/70 hover:text-ink">
            Noise remove
          </Link>
        </div>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/ready" element={<ReadyQueue />} />
        <Route path="/schedule" element={<WeekSchedule />} />
        <Route path="/songs" element={<SongList />} />
        <Route path="/songs/:songId" element={<SongDetail />} />
        <Route path="/branding" element={<BrandingPage />} />
        <Route path="/denoise" element={<DenoisePage />} />
      </Routes>
    </div>
  );
}
