"use client";

import { apiPost } from "@/lib/api";
import { REDACT_KEY, THEME_KEY, cycleTheme, type ThemePref } from "@/lib/chrome";
import type { UpdateResult } from "@/lib/types";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { mutate } from "swr";

type Chrome = {
  theme: ThemePref;
  redact: boolean;
  setRedact: (on: boolean) => void;
  cycle: () => void;
  updating: boolean;
  updateError: string | null;
  lastUpdate: UpdateResult | null;
  refreshEpoch: number;
  updateMailbox: () => Promise<void>;
};

const ChromeContext = createContext<Chrome | null>(null);

function readTheme(): ThemePref {
  if (typeof window === "undefined") return "system";
  const raw = window.localStorage.getItem(THEME_KEY);
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

function applyTheme(pref: ThemePref) {
  document.documentElement.dataset.theme = pref;
}

export function ChromeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemePref>("system");
  const [redact, setRedactState] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<UpdateResult | null>(null);
  const [refreshEpoch, setRefreshEpoch] = useState(0);
  const busyRef = useRef(false);

  useEffect(() => {
    const t = readTheme();
    setTheme(t);
    applyTheme(t);
    setRedactState(window.localStorage.getItem(REDACT_KEY) === "1");
  }, []);

  const setRedact = (on: boolean) => {
    setRedactState(on);
    window.localStorage.setItem(REDACT_KEY, on ? "1" : "0");
  };

  const cycle = () => {
    const next = cycleTheme(theme);
    setTheme(next);
    applyTheme(next);
    window.localStorage.setItem(THEME_KEY, next);
  };

  const updateMailbox = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setUpdating(true);
    setUpdateError(null);
    try {
      const result = await apiPost<UpdateResult>("/api/update", { classify_limit: 20 });
      setLastUpdate(result);
      await mutate((key) => typeof key === "string" && key.startsWith("/api/"));
      setRefreshEpoch((n) => n + 1);
    } catch (err) {
      setUpdateError(err instanceof Error ? err.message : "update failed");
    } finally {
      busyRef.current = false;
      setUpdating(false);
    }
  }, []);

  const value = useMemo(
    () => ({
      theme,
      redact,
      setRedact,
      cycle,
      updating,
      updateError,
      lastUpdate,
      refreshEpoch,
      updateMailbox,
    }),
    [theme, redact, updating, updateError, lastUpdate, refreshEpoch, updateMailbox],
  );

  return <ChromeContext.Provider value={value}>{children}</ChromeContext.Provider>;
}

export function useChrome(): Chrome {
  const ctx = useContext(ChromeContext);
  if (!ctx) {
    throw new Error("useChrome must be used under ChromeProvider");
  }
  return ctx;
}
