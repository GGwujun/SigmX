export type DataQuality = "verified" | "degraded" | "error" | "unknown";

const QUALITY_LABEL: Record<DataQuality, string> = {
  verified: "已校验",
  degraded: "数据降级",
  error: "读取失败",
  unknown: "待校验",
};

export function DataStatus({
  source,
  asOf,
  freshness,
  quality,
  message,
  onRetry,
}: {
  source: string;
  asOf: string | null;
  freshness: string;
  quality: DataQuality;
  message?: string;
  onRetry?: () => void;
}) {
  const compactDate = asOf?.match(/^(\d{4})(\d{2})(\d{2})$/);
  const parsed = asOf
    ? new Date(compactDate ? `${compactDate[1]}-${compactDate[2]}-${compactDate[3]}T00:00:00+08:00` : asOf)
    : null;
  const timestamp = parsed && !Number.isNaN(parsed.getTime())
    ? new Intl.DateTimeFormat("zh-CN", compactDate ? { dateStyle: "medium" } : { dateStyle: "medium", timeStyle: "short" }).format(parsed)
    : asOf || "时间未知";
  return (
    <div role="status" className={`data-status data-status--${quality}`}>
      <span className="data-status__quality">{QUALITY_LABEL[quality]}</span>
      <span>{source}</span>
      <span>{freshness}</span>
      <time dateTime={asOf ?? undefined}>{timestamp}</time>
      {message && <span className="data-status__message">{message}</span>}
      {quality === "error" && onRetry && <button type="button" onClick={onRetry}>重试</button>}
    </div>
  );
}
