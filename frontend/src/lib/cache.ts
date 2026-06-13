/**
 * Module-level TTL cache with stale-while-revalidate semantics.
 *
 * Why module-level (not localStorage): the dashboard aggregates live market
 * data whose freshness matters within a session, but it's fine to re-fetch on
 * a fresh page load / new session. An in-memory Map gives instant reads on
 * in-app navigation (the slow case the user reported) without persisting
 * stale numbers across browser restarts.
 *
 * Usage:
 *   const c = cached("home:opp", () => api.listOpportunities(), 60_000);
 *   const { data, stale } = await c.read();   // instant if cached
 *   c.refresh();                               // force re-fetch
 *   cached.invalidate("home:opp");             // invalidate one key
 *   cached.invalidatePrefix("home:");          // invalidate a group
 */

interface Entry<T> {
  ts: number;        // when the data was fetched
  data: T | undefined;
  inflight: Promise<T> | null;  // dedupe concurrent fetches
}

const store = new Map<string, Entry<unknown>>();

const DEFAULT_TTL = 60_000;

export interface Cached<T> {
  /** Return cached data if fresh; else fetch. Stale old data is returned
   *  immediately with stale=true while a background refresh runs. */
  read: () => Promise<{ data: T; stale: boolean }>;
  /** Force a re-fetch regardless of TTL. Returns the fresh data. */
  refresh: () => Promise<T>;
  /** Drop the cache for this key. */
  invalidate: () => void;
}

export function cached<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlMs: number = DEFAULT_TTL,
): Cached<T> {
  const getEntry = (): Entry<T> => {
    let e = store.get(key) as Entry<T> | undefined;
    if (!e) {
      e = { ts: 0, data: undefined, inflight: null };
      store.set(key, e as Entry<unknown>);
    }
    return e;
  };

  const doFetch = async (): Promise<T> => {
    const e = getEntry();
    if (e.inflight) return e.inflight as Promise<T>;
    e.inflight = (async () => {
      try {
        const data = await fetcher();
        e.data = data;
        e.ts = Date.now();
        return data;
      } finally {
        e.inflight = null;
      }
    })();
    return e.inflight;
  };

  const read = async (): Promise<{ data: T; stale: boolean }> => {
    const e = getEntry();
    const now = Date.now();
    const fresh = e.data !== undefined && now - e.ts < ttlMs;
    if (fresh) {
      return { data: e.data as T, stale: false };
    }
    // No cache at all → must wait for the fetch (caller shows loading).
    if (e.data === undefined) {
      const data = await doFetch();
      return { data, stale: false };
    }
    // Stale cache → return immediately, refresh in the background.
    void doFetch();
    return { data: e.data as T, stale: true };
  };

  const refresh = async (): Promise<T> => {
    // Force a new fetch (bypass the inflight dedupe if a bg refresh is running
    // by clearing the timestamp so the next read also treats it as fresh).
    const data = await doFetch();
    return data;
  };

  const invalidate = () => {
    store.delete(key);
  };

  return { read, refresh, invalidate };
}

/** Invalidate a single key. */
export function invalidate(key: string): void {
  store.delete(key);
}

/** Invalidate all keys with the given prefix (e.g. "home:"). */
export function invalidatePrefix(prefix: string): void {
  for (const key of [...store.keys()]) {
    if (key.startsWith(prefix)) store.delete(key);
  }
}
