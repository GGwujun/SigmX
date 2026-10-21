import type { ReactNode } from "react";

export function Panel({ title, description, action, children }: { title: string; description?: string; action?: ReactNode; children: ReactNode }) {
  return <section className="product-panel"><header className="product-panel__header"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</header><div className="product-panel__body">{children}</div></section>;
}
