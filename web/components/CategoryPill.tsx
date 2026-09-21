import { cn } from "@/lib/utils";
import type { Category } from "@/lib/types";

const STYLES: Record<Category, string> = {
  legitimate:
    "bg-[var(--cat-legitimate-bg)] text-[var(--cat-legitimate-fg)] border-[var(--cat-legitimate-bd)]",
  promotional:
    "bg-[var(--cat-promotional-bg)] text-[var(--cat-promotional-fg)] border-[var(--cat-promotional-bd)]",
  spam: "bg-[var(--cat-spam-bg)] text-[var(--cat-spam-fg)] border-[var(--cat-spam-bd)]",
  phishing:
    "bg-[var(--cat-phishing-bg)] text-[var(--cat-phishing-fg)] border-[var(--cat-phishing-bd)]",
  uncertain:
    "bg-[var(--cat-uncertain-bg)] text-[var(--cat-uncertain-fg)] border-dashed border-[var(--cat-uncertain-bd)]",
  other:
    "bg-[var(--cat-other-bg)] text-[var(--cat-other-fg)] border-[var(--cat-other-bd)]",
};

export function CategoryPill({
  category,
  large = false,
}: {
  category: Category;
  large?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center border uppercase tracking-[0.14em]",
        large ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-[11px]",
        STYLES[category] ?? STYLES.other,
      )}
    >
      {category}
    </span>
  );
}
