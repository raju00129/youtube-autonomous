import { FormEvent, ReactNode, useState } from "react";
import { isPortalUnlocked, unlockPortal } from "./portalAuth";

export function PortalGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(() => isPortalUnlocked());
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (unlocked) {
    return <>{children}</>;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await unlockPortal(key);
      setUnlocked(true);
    } catch {
      setError("Wrong key — try again");
      setKey("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <form
        onSubmit={(e) => void onSubmit(e)}
        className="w-full max-w-sm space-y-6 border border-ink/10 bg-white/70 p-8 shadow-sm backdrop-blur"
      >
        <div className="space-y-2 text-center">
          <p className="font-display text-3xl font-semibold text-ink">Ragam</p>
          <p className="text-sm text-ink/65">Enter the access key to open the studio</p>
        </div>
        <label className="block space-y-2">
          <span className="text-xs uppercase tracking-[0.2em] text-ink/50">Access key</span>
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            autoFocus
            value={key}
            onChange={(e) => setKey(e.target.value)}
            className="w-full border border-ink/20 bg-white px-4 py-3 text-center text-lg tracking-[0.35em] text-ink outline-none focus:border-temple"
            placeholder="••••"
          />
        </label>
        {error && <p className="text-center text-sm text-saffron">{error}</p>}
        <button
          type="submit"
          disabled={busy || !key.trim()}
          className="w-full bg-temple px-4 py-3 font-medium text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Checking…" : "Enter studio"}
        </button>
      </form>
    </div>
  );
}
