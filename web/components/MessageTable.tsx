"use client";

import { useChrome } from "@/components/ChromeProvider";
import { CategoryPill } from "@/components/CategoryPill";
import { useListHotkeys } from "@/hooks/useListHotkeys";
import { cn } from "@/lib/utils";
import { formatCostUsd, formatMs, formatProb, formatWhen } from "@/lib/format";
import { redactValue } from "@/lib/redact";
import type { CompactMessage } from "@/lib/types";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";

export function MessageTable({
  rows,
  searchRef,
  enableKeys = true,
}: {
  rows: CompactMessage[];
  searchRef?: RefObject<HTMLInputElement | null>;
  enableKeys?: boolean;
}) {
  const { redact } = useChrome();
  const router = useRouter();
  const [selected, setSelected] = useState(0);
  const [sorting, setSorting] = useState<SortingState>([{ id: "classified_at", desc: true }]);
  const data = useMemo(() => rows, [rows]);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  const columns = useMemo<ColumnDef<CompactMessage>[]>(
    () => [
      {
        accessorKey: "classified_at",
        header: "time",
        cell: ({ getValue }) => formatWhen(String(getValue())),
      },
      {
        accessorKey: "category",
        header: "category",
        cell: ({ row }) => <CategoryPill category={row.original.category} />,
      },
      {
        accessorKey: "spam_probability",
        header: "spam %",
        cell: ({ row }) => formatProb(row.original.spam_probability, "prob."),
      },
      {
        accessorKey: "reply_probability",
        header: "reply %",
        cell: ({ row }) => formatProb(row.original.reply_probability, "prob."),
      },
      {
        accessorKey: "category_confidence",
        header: "confidence",
        cell: ({ row }) => formatProb(row.original.category_confidence, "conf."),
      },
      {
        accessorKey: "total_ms",
        header: "latency",
        cell: ({ row }) => formatMs(row.original.total_ms),
      },
      {
        accessorKey: "cost_usd",
        header: "cost",
        cell: ({ row }) => formatCostUsd(row.original.cost_usd),
      },
      {
        accessorKey: "sender_domain",
        header: "sender domain",
        cell: ({ getValue }) => redactValue(String(getValue() || ""), redact),
      },
      {
        accessorKey: "subject",
        header: "subject",
        cell: ({ getValue }) => redactValue(String(getValue() || ""), redact) || "(no subject)",
      },
    ],
    [redact],
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const sorted = table.getRowModel().rows;
  const ids = sorted.map((r) => r.original.message_id);

  useListHotkeys({
    count: enableKeys ? sorted.length : 0,
    selected,
    setSelected,
    ids,
    searchRef,
  });

  useEffect(() => {
    setSelected(0);
  }, [rows]);

  useEffect(() => {
    rowRefs.current[selected]?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  return (
    <div className="overflow-x-auto border border-[var(--line)]">
      <table className="w-full min-w-[64rem] border-collapse text-left text-sm">
        <thead className="bg-[var(--paper-2)] font-mono text-[11px] uppercase tracking-widest text-[var(--muted)]">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th key={header.id} className="border-b border-[var(--line)] px-3 py-2">
                  {header.isPlaceholder ? null : (
                    <button
                      type="button"
                      className="hover:text-[var(--ink)]"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </button>
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={row.id}
              ref={(el) => {
                rowRefs.current[i] = el;
              }}
              aria-selected={i === selected}
              className={cn("cursor-pointer hover:bg-[var(--row-hover)]", i === selected && "row-active")}
              onClick={() => router.push(`/messages/${row.original.message_id}`)}
              onMouseEnter={() => setSelected(i)}
            >
              {row.getVisibleCells().map((cell, ci) => (
                <td key={cell.id} className="border-b border-[var(--line)] px-3 py-2 font-mono text-[13px]">
                  {ci === 0 ? (
                    <Link
                      href={`/messages/${row.original.message_id}`}
                      className="underline-offset-2 hover:underline"
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </Link>
                  ) : (
                    flexRender(cell.column.columnDef.cell, cell.getContext())
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
