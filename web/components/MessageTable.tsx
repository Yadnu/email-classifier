"use client";

import { CategoryPill } from "@/components/CategoryPill";
import { formatCostUsd, formatMs, formatProb, formatWhen } from "@/lib/format";
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
import { useMemo, useState } from "react";

const columns: ColumnDef<CompactMessage>[] = [
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
  { accessorKey: "sender_domain", header: "sender domain" },
  { accessorKey: "subject", header: "subject" },
];

export function MessageTable({ rows }: { rows: CompactMessage[] }) {
  const router = useRouter();
  const [sorting, setSorting] = useState<SortingState>([
    { id: "classified_at", desc: true },
  ]);
  const data = useMemo(() => rows, [rows]);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

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
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="cursor-pointer hover:bg-[var(--row-hover)]"
              onClick={() => router.push(`/messages/${row.original.message_id}`)}
            >
              {row.getVisibleCells().map((cell, i) => (
                <td key={cell.id} className="border-b border-[var(--line)] px-3 py-2 font-mono text-[13px]">
                  {i === 0 ? (
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
