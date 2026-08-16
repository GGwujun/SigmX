function StateAction({ label, onAction }: { label: string; onAction: () => void }) {
  return <button type="button" className="page-state__action" onClick={onAction}>{label}</button>;
}

export function EmptyState({ title, description, actionLabel, onAction }: { title: string; description: string; actionLabel?: string; onAction?: () => void }) {
  return <div className="page-state"><strong>{title}</strong><p>{description}</p>{actionLabel && onAction && <StateAction label={actionLabel} onAction={onAction} />}</div>;
}

export function ErrorState({ title, description, onRetry }: { title: string; description: string; onRetry?: () => void }) {
  return <div role="alert" className="page-state page-state--error"><strong>{title}</strong><p>{description}</p>{onRetry && <StateAction label="重试" onAction={onRetry} />}</div>;
}
