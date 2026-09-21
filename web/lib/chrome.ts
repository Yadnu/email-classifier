export type ThemePref = "system" | "light" | "dark";

export const THEME_KEY = "classifier-theme";
export const REDACT_KEY = "classifier-redact";

export function cycleTheme(pref: ThemePref): ThemePref {
  if (pref === "system") return "light";
  if (pref === "light") return "dark";
  return "system";
}

export function resolvedTheme(pref: ThemePref, systemDark: boolean): "light" | "dark" {
  if (pref === "system") return systemDark ? "dark" : "light";
  return pref;
}

export function stepIndex(length: number, current: number, delta: number): number {
  if (length <= 0) return 0;
  return (current + delta + length) % length;
}

export function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

export function formatUpdateStatus(r: {
  ingest_ok: boolean;
  ingested_new: number;
  classified: number;
  unclassified_remaining: number;
}): string {
  const gmail = r.ingest_ok
    ? `${r.ingested_new} new from gmail`
    : "gmail sync failed";
  const waiting =
    r.unclassified_remaining === 0
      ? "none waiting"
      : `${r.unclassified_remaining} waiting`;
  return `${gmail} · ${r.classified} classified · ${waiting}`;
}
