import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react";

interface PriceUpdate {
  code: string;
  price: number;
  nav: number;
  premium_rate: number;
  amount: number;
  timestamp: string;
}

interface AlertEvent {
  rule_id: string;
  fund_code: string;
  fund_name: string;
  premium_rate: number;
  amount: number;
  price: number;
  nav: number;
  webhook_type: string;
  triggered_at: string;
}

interface SSEContextValue {
  prices: Map<string, PriceUpdate>;
  alerts: AlertEvent[];
  connected: boolean;
  lastUpdate: string | null;
  clearAlerts: () => void;
}

const SSEContext = createContext<SSEContextValue>({
  prices: new Map(),
  alerts: [],
  connected: false,
  lastUpdate: null,
  clearAlerts: () => {},
});

export function useSSE() {
  return useContext(SSEContext);
}

function createEventSource(url: string, token: string | null): EventSource | null {
  try {
    // EventSource doesn't support custom headers, so we pass token as query param
    const fullUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url;
    return new EventSource(fullUrl);
  } catch {
    return null;
  }
}

export function SSEProvider({ children }: { children: ReactNode }) {
  const [prices, setPrices] = useState<Map<string, PriceUpdate>>(new Map());
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const pricesRef = useRef(prices);
  pricesRef.current = prices;

  const clearAlerts = useCallback(() => setAlerts([]), []);

  useEffect(() => {
    const token = localStorage.getItem("vibe_token");

    // Connect to fund-prices stream
    const priceES = createEventSource("/stream/fund-prices", token);
    if (priceES) {
      priceES.addEventListener("connected", () => {
        setConnected(true);
      });

      priceES.addEventListener("fund_prices", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const updates: PriceUpdate[] = Array.isArray(data) ? data : data.data || [data];
          setPrices(prev => {
            const next = new Map(prev);
            for (const u of updates) {
              if (u.code) next.set(u.code, u);
            }
            return next;
          });
          setLastUpdate(new Date().toISOString());
        } catch { /* ignore parse errors */ }
      });

      priceES.addEventListener("error", () => {
        setConnected(false);
      });

      priceES.onerror = () => {
        setConnected(false);
      };
    }

    // Connect to alerts stream
    const alertES = createEventSource("/stream/alerts", token);
    if (alertES) {
      alertES.addEventListener("fund_alerts", (e: MessageEvent) => {
        try {
          const alert: AlertEvent = JSON.parse(e.data);
          setAlerts(prev => [alert, ...prev].slice(0, 50)); // Keep last 50
        } catch { /* ignore */ }
      });
    }

    return () => {
      priceES?.close();
      alertES?.close();
      setConnected(false);
    };
  }, []);

  return (
    <SSEContext.Provider value={{ prices, alerts, connected, lastUpdate, clearAlerts }}>
      {children}
    </SSEContext.Provider>
  );
}
