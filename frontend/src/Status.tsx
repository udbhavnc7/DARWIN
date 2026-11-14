const tones: Record<string, string> = {
  connected: 'good', completed: 'good', passed: 'good', ready: 'good',
  failed: 'bad', offline: 'bad', rejected: 'bad', missing: 'bad',
  running: 'active', queued: 'active', promoted: 'active',
  cancelled: 'warn', requires_review: 'warn', optional_missing: 'neutral',
};

export function Status({value, label}: {value: string; label?: string}) {
  return <span className={`status-chip ${tones[value] ?? 'neutral'}`}>
    <span className="status-dot" aria-hidden="true"/>
    {label ?? value.replaceAll('_', ' ')}
  </span>;
}
