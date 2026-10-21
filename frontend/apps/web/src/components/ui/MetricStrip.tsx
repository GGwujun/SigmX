type MetricDirection = "up" | "down" | "flat";

export function MetricStrip({ items }: { items: Array<{ label: string; value: string; change?: string; direction?: MetricDirection }> }) {
  return <dl className="metric-strip">{items.map(item => <div key={item.label} className="metric-strip__item"><dt>{item.label}</dt><dd>{item.value}</dd>{item.change && <span aria-label={`${item.direction === "up" ? "上涨" : item.direction === "down" ? "下跌" : "持平"} ${item.change}`} className={`metric-strip__change metric-strip__change--${item.direction ?? "flat"}`}>{item.direction === "up" ? "↑" : item.direction === "down" ? "↓" : "→"} {item.change}</span>}</div>)}</dl>;
}
