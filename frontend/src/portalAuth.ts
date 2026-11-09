const STORAGE_KEY = "ragam_portal_unlocked";
const KEY_STORAGE = "ragam_portal_key";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8010";

export function isPortalUnlocked(): boolean {
  return sessionStorage.getItem(STORAGE_KEY) === "1";
}

export function getPortalKey(): string {
  return sessionStorage.getItem(KEY_STORAGE) || "";
}

export function markPortalUnlocked(key: string): void {
  sessionStorage.setItem(STORAGE_KEY, "1");
  sessionStorage.setItem(KEY_STORAGE, key);
}

export function clearPortalUnlock(): void {
  sessionStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(KEY_STORAGE);
}

/** Append portal_key for media tags (img/audio/video) that cannot send headers. */
export function withPortalKey(url: string): string {
  const key = getPortalKey();
  if (!key) return url;
  try {
    const u = new URL(url, typeof window !== "undefined" ? window.location.origin : API_BASE);
    u.searchParams.set("portal_key", key);
    return u.toString();
  } catch {
    const sep = url.includes("?") ? "&" : "?";
    return `${url}${sep}portal_key=${encodeURIComponent(key)}`;
  }
}

export async function unlockPortal(key: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/portal/unlock`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Portal-Key": key },
    body: JSON.stringify({ key }),
  });
  if (!res.ok) {
    throw new Error("Invalid access key");
  }
  markPortalUnlocked(key.trim());
}

/** Install once: attach portal key + credentials to all API fetch calls. */
export function installPortalFetch(): void {
  const original = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const isApi =
      url.startsWith(API_BASE) ||
      url.startsWith("/api/") ||
      url.includes("/api/v1/") ||
      url.endsWith("/ready") ||
      url.includes("/ready?");

    if (!isApi) {
      return original(input, init);
    }

    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
    const key = getPortalKey();
    if (key && !headers.has("X-Portal-Key")) {
      headers.set("X-Portal-Key", key);
    }
    return original(input, {
      ...init,
      headers,
      credentials: init?.credentials ?? "include",
    });
  };
}
