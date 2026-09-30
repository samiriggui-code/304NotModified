'use client';

import { ReactNode, useMemo, useState } from 'react';
import {
  ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  PaginationState,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { Download, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardHeading, CardTable, CardTitle, CardToolbar } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

export { DataGridColumnHeader as ColumnHeader } from '@/components/ui/data-grid-column-header';

// Table Metronic (DataGrid) dans une carte : titre, recherche, export CSV, tri, pagination.
export function DataTable<T extends object>({
  title,
  description,
  data,
  columns,
  searchText,
  searchPlaceholder = 'Rechercher…',
  toolbar,
  onRowClick,
  emptyMessage = 'Aucune donnée.',
  isLoading,
  pageSize = 10,
  initialSort = [],
  csv,
  getRowId,
}: {
  title: ReactNode;
  description?: ReactNode;
  data: T[];
  columns: ColumnDef<T>[];
  // Texte sur lequel porte la recherche, pour une ligne.
  searchText?: (row: T) => (string | null | undefined)[];
  searchPlaceholder?: string;
  toolbar?: ReactNode;
  onRowClick?: (row: T) => void;
  emptyMessage?: ReactNode;
  isLoading?: boolean;
  pageSize?: number;
  initialSort?: SortingState;
  csv?: { filename: string; export: (rows: T[]) => void };
  getRowId?: (row: T, index: number) => string;
}) {
  const [query, setQuery] = useState('');
  const [sorting, setSorting] = useState<SortingState>(initialSort);
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize,
  });

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !searchText) return data;
    return data.filter((r) => searchText(r).some((v) => v?.toLowerCase().includes(q)));
  }, [data, query, searchText]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId,
    state: { sorting, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      onRowClick={onRowClick}
      isLoading={isLoading}
      loadingMode="skeleton"
      emptyMessage={emptyMessage}
      tableLayout={{
        headerBackground: true,
        headerSticky: true,
        rowBorder: true,
        cellBorder: false,
      }}
    >
      <Card className="min-w-full">
        <CardHeader className="py-4 flex-wrap gap-3">
          <CardHeading>
            <CardTitle>{title}</CardTitle>
            {description && <div className="text-sm text-muted-foreground font-normal">{description}</div>}
          </CardHeading>
          <CardToolbar className="flex-wrap">
            {searchText && (
              <div className="relative">
                <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
                <Input
                  placeholder={searchPlaceholder}
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setPagination((p) => ({ ...p, pageIndex: 0 }));
                  }}
                  className="ps-9 w-60"
                />
                {query && (
                  <Button
                    mode="icon"
                    variant="ghost"
                    aria-label="Effacer la recherche"
                    className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
                    onClick={() => setQuery('')}
                  >
                    <X />
                  </Button>
                )}
              </div>
            )}
            {toolbar}
            {csv && (
              <Button variant="outline" disabled={!rows.length} onClick={() => csv.export(rows)}>
                <Download /> CSV
              </Button>
            )}
          </CardToolbar>
        </CardHeader>
        <CardTable>
          <ScrollArea>
            <DataGridTable />
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </CardTable>
        {rows.length > pageSize && (
          <CardFooter>
            <DataGridPagination info="{from} à {to} sur {count}" sizesLabel="Afficher" sizesDescription="par page" />
          </CardFooter>
        )}
      </Card>
    </DataGrid>
  );
}
