"use client";

import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type Row,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Columns3, Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type DataTableColumn<T> = {
  id: string;
  header: string;
  /** Cell renderer. Return a `FinancialValue` for numbers. */
  cell: (row: T) => ReactNode;
  /** Value used for sorting / global search. Defaults to the cell text when omitted. */
  accessor?: (row: T) => string | number | null | undefined;
  /** Right-align numeric columns. */
  align?: "left" | "right" | "center";
  /** Hide on small screens (still available via column toggle on wide screens). */
  hideBelow?: "sm" | "md" | "lg" | "xl";
  /** Initial visibility (default true). */
  defaultVisible?: boolean;
  /** Disable sorting for this column. */
  enableSorting?: boolean;
  /** Fixed width class (e.g. "w-28"). */
  className?: string;
};

export type DataTableProps<T> = {
  rows: T[];
  columns: DataTableColumn<T>[];
  rowKey: (row: T) => string;
  /** Accessible table caption (visually hidden unless `showCaption`). */
  caption: string;
  showCaption?: boolean;
  /** Show the global search box. */
  searchable?: boolean;
  searchPlaceholder?: string;
  /** Page size; 0 disables pagination. */
  pageSize?: number;
  /** Initial sort. */
  initialSort?: { id: string; desc?: boolean };
  /** Row click handler (rows become buttons; selected row is highlighted). */
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  /** Optional toolbar content (filters) rendered between search and column toggle. */
  toolbar?: ReactNode;
  /** Shown when `rows` is empty (after filters). */
  emptyState?: ReactNode;
  /** Compact row height. */
  dense?: boolean;
  className?: string;
  /** Hide the column visibility control. */
  hideColumnToggle?: boolean;
};

const HIDE: Record<NonNullable<DataTableColumn<unknown>["hideBelow"]>, string> = {
  sm: "hidden sm:table-cell",
  md: "hidden md:table-cell",
  lg: "hidden lg:table-cell",
  xl: "hidden xl:table-cell",
};

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join(" ");
  if (typeof node === "object" && "props" in node) {
    const props = (node as { props?: { children?: ReactNode; value?: unknown } }).props;
    if (props?.value !== undefined) return String(props.value ?? "");
    return textOf(props?.children);
  }
  return "";
}

/**
 * Financial data grid on TanStack Table: global search, column sorting,
 * column visibility, pagination, row selection, responsive horizontal scroll,
 * and proper `<th scope="col">` headers. Decimal strings sort numerically.
 */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  caption,
  showCaption = false,
  searchable = true,
  searchPlaceholder = "Search…",
  pageSize = 25,
  initialSort,
  onRowClick,
  selectedKey,
  toolbar,
  emptyState,
  dense = false,
  className,
  hideColumnToggle = false,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSort ? [{ id: initialSort.id, desc: Boolean(initialSort.desc) }] : []);
  const [globalFilter, setGlobalFilter] = useState("");
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(() =>
    Object.fromEntries(columns.filter((c) => c.defaultVisible === false).map((c) => [c.id, false])),
  );

  const columnDefs = useMemo<ColumnDef<T>[]>(
    () =>
      columns.map((col) => ({
        id: col.id,
        header: col.header,
        enableSorting: col.enableSorting !== false,
        accessorFn: (row: T) => {
          const v = col.accessor ? col.accessor(row) : textOf(col.cell(row));
          return v ?? "";
        },
        sortingFn: (a: Row<T>, b: Row<T>, id: string) => {
          const av = a.getValue<string | number>(id);
          const bv = b.getValue<string | number>(id);
          const an = typeof av === "number" ? av : Number(av);
          const bn = typeof bv === "number" ? bv : Number(bv);
          if (Number.isFinite(an) && Number.isFinite(bn) && String(av).trim() !== "" && String(bv).trim() !== "") {
            return an === bn ? 0 : an < bn ? -1 : 1;
          }
          return String(av ?? "").localeCompare(String(bv ?? ""), undefined, { numeric: true, sensitivity: "base" });
        },
        cell: ({ row }) => col.cell(row.original),
        meta: col,
      })),
    [columns],
  );

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    state: { sorting, globalFilter, columnVisibility },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onColumnVisibilityChange: setColumnVisibility,
    globalFilterFn: (row, _columnId, filterValue) => {
      const needle = String(filterValue ?? "").trim().toLowerCase();
      if (!needle) return true;
      return row.getAllCells().some((cell) => String(cell.getValue() ?? "").toLowerCase().includes(needle));
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: pageSize > 0 ? getPaginationRowModel() : undefined,
    initialState: pageSize > 0 ? { pagination: { pageSize } } : undefined,
    autoResetPageIndex: true,
  });

  const pageRows = table.getRowModel().rows;
  const total = table.getFilteredRowModel().rows.length;
  const pagination = table.getState().pagination;
  const showPager = pageSize > 0 && total > pageSize;
  const hasToolbar = searchable || toolbar || !hideColumnToggle;

  return (
    <div className={cn("flex min-w-0 flex-col gap-3", className)}>
      {hasToolbar ? (
        <div className="flex flex-wrap items-center gap-2">
          {searchable ? (
            <div className="relative min-w-[10rem] flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
                placeholder={searchPlaceholder}
                aria-label={`Search ${caption}`}
                className="h-8 rounded-full pl-8 text-xs"
              />
            </div>
          ) : null}
          {toolbar}
          {!hideColumnToggle ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="ml-auto rounded-full" aria-label="Choose visible columns">
                  <Columns3 className="mr-1.5 h-3.5 w-3.5" aria-hidden />
                  Columns
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[11rem]">
                <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {table.getAllLeafColumns().map((column) => (
                  <DropdownMenuCheckboxItem
                    key={column.id}
                    checked={column.getIsVisible()}
                    onCheckedChange={(v) => column.toggleVisibility(Boolean(v))}
                    onSelect={(e) => e.preventDefault()}
                  >
                    {String(column.columnDef.header)}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      ) : null}

      <div className="cn-thin-scroll w-full overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[32rem] caption-bottom text-sm">
          <caption className={cn("px-3 py-2 text-left text-[11px] text-muted-foreground", !showCaption && "sr-only")}>
            {caption}
          </caption>
          <thead className="bg-muted/40">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-border">
                {hg.headers.map((header) => {
                  const meta = header.column.columnDef.meta as DataTableColumn<T> | undefined;
                  const sorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : canSort ? "none" : undefined}
                      className={cn(
                        "h-9 whitespace-nowrap px-3 text-xs font-medium text-muted-foreground",
                        meta?.align === "right" ? "text-right" : meta?.align === "center" ? "text-center" : "text-left",
                        meta?.hideBelow ? HIDE[meta.hideBelow] : undefined,
                        meta?.className,
                      )}
                    >
                      {canSort ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className={cn(
                            "inline-flex items-center gap-1 rounded hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            meta?.align === "right" && "flex-row-reverse",
                          )}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sorted === "asc" ? (
                            <ArrowUp className="h-3 w-3" aria-hidden />
                          ) : sorted === "desc" ? (
                            <ArrowDown className="h-3 w-3" aria-hidden />
                          ) : (
                            <ArrowUpDown className="h-3 w-3 opacity-40" aria-hidden />
                          )}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={table.getVisibleLeafColumns().length} className="px-3 py-8 text-center text-sm text-muted-foreground">
                  {emptyState ?? (globalFilter ? "No rows match this search." : "No rows.")}
                </td>
              </tr>
            ) : (
              pageRows.map((row) => {
                const key = rowKey(row.original);
                const selected = selectedKey != null && selectedKey === key;
                return (
                  <tr
                    key={key}
                    className={cn(
                      "border-b border-border/60 transition-colors last:border-0",
                      onRowClick && "cursor-pointer hover:bg-muted/40 focus-within:bg-muted/40",
                      selected && "bg-brand/10",
                    )}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                    onKeyDown={
                      onRowClick
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              onRowClick(row.original);
                            }
                          }
                        : undefined
                    }
                    tabIndex={onRowClick ? 0 : undefined}
                    aria-selected={onRowClick ? selected : undefined}
                    data-state={selected ? "selected" : undefined}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const meta = cell.column.columnDef.meta as DataTableColumn<T> | undefined;
                      return (
                        <td
                          key={cell.id}
                          className={cn(
                            "whitespace-nowrap px-3 align-middle text-xs",
                            dense ? "py-1.5" : "py-2.5",
                            meta?.align === "right" ? "text-right" : meta?.align === "center" ? "text-center" : "text-left",
                            meta?.hideBelow ? HIDE[meta.hideBelow] : undefined,
                            meta?.className,
                          )}
                        >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span>
          {total === rows.length ? `${total} row${total === 1 ? "" : "s"}` : `${total} of ${rows.length} rows`}
        </span>
        {showPager ? (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 rounded-full px-2"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
            </Button>
            <span className="font-mono">
              {pagination.pageIndex + 1} / {table.getPageCount()}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 rounded-full px-2"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              aria-label="Next page"
            >
              <ChevronRight className="h-3.5 w-3.5" aria-hidden />
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
