export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatCostUsd(usd: number): string {
  if (usd < 1) return `${(usd * 100).toFixed(3)}¢`;
  return `$${usd.toFixed(2)}`;
}

export function formatTokens(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatProb(n: number, label: string): string {
  return `${n.toFixed(2)} ${label}`;
}

export function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
