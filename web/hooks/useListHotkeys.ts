"use client";

import { isTypingTarget, stepIndex } from "@/lib/chrome";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export function useListHotkeys({
  count,
  selected,
  setSelected,
  ids,
  searchRef,
}: {
  count: number;
  selected: number;
  setSelected: (n: number) => void;
  ids: string[];
  searchRef?: { current: HTMLInputElement | null };
}) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/" && !isTypingTarget(e.target)) {
        e.preventDefault();
        searchRef?.current?.focus();
        searchRef?.current?.select();
        return;
      }
      if (e.key === "Escape") {
        if (isTypingTarget(e.target)) {
          (e.target as HTMLElement).blur();
          return;
        }
        if (pathname.startsWith("/messages/") && pathname !== "/messages") {
          router.push("/messages");
        }
        return;
      }
      if (isTypingTarget(e.target)) return;
      if (count === 0) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelected(stepIndex(count, selected, 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setSelected(stepIndex(count, selected, -1));
      } else if (e.key === "Enter") {
        const id = ids[selected];
        if (id) {
          e.preventDefault();
          router.push(`/messages/${id}`);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, selected, setSelected, ids, router, searchRef, pathname]);
}
