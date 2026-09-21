export function percentiles(values: number[]): Record<50 | 95 | 99, number> {
  if (!values.length) return { 50: 0, 95: 0, 99: 0 };
  const sorted = [...values].sort((a, b) => a - b);
  const at = (p: number) => {
    const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
    return sorted[idx];
  };
  return { 50: at(50), 95: at(95), 99: at(99) };
}
