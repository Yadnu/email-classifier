import type { CompactMessage } from "@/lib/types";

export function rowKey(row: CompactMessage): string {
  return `${row.message_id}:${row.id}`;
}

export function prependUnique(
  list: CompactMessage[],
  incoming: CompactMessage[],
  cap = 80,
): CompactMessage[] {
  const seen = new Set(incoming.map(rowKey));
  return [...incoming, ...list.filter((row) => !seen.has(rowKey(row)))].slice(0, cap);
}

export function drainBuffer(buffer: CompactMessage[]): CompactMessage[] {
  return buffer.splice(0, buffer.length);
}
