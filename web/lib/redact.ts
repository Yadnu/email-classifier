export const REDACT_STATE_KEYS = new Set([
  "subject",
  "sender_address",
  "sender_display_name",
  "sender_domain",
  "reply_to_address",
  "reply_to_domain",
  "body_excerpt",
]);

export function mask(value: string): string {
  if (!value) return value;
  return "█".repeat(Math.min(16, Math.max(6, Math.min(value.length, 16))));
}

export function redactValue(value: string, on: boolean): string {
  return on ? mask(value) : value;
}

export function redactState(
  state: Record<string, unknown>,
  on: boolean,
): Record<string, unknown> {
  if (!on) return state;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(state)) {
    if (REDACT_STATE_KEYS.has(key) && typeof value === "string") {
      out[key] = mask(value);
    } else {
      out[key] = value;
    }
  }
  return out;
}
