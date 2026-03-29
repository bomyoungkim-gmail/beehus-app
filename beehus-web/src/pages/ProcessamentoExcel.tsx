import { useMemo, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getGroupedRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import type {
  ColumnDef,
  ColumnFiltersState,
  ExpandedState,
  FilterFn,
  GroupingState,
  OnChangeFn,
  SortingState,
  Updater,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import * as XLSX from 'xlsx';
import Layout from '../components/Layout';

type RFRow = {
  id: string;
  name: string;
  category: string;
  maturityDate: string;
  rate: string;
  indexer: string;
} & Record<string, string>;

type ColumnVisibilityState = Record<string, boolean>;

function pickFirst(record: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null && value !== '') {
      return value;
    }
  }
  return undefined;
}

function normalizeDate(value: unknown): string {
  if (!value) {
    return '';
  }
  const text = String(value).trim();
  if (!text) {
    return '';
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return text.slice(0, 10);
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return text;
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const day = String(parsed.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function normalizeText(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }
  return String(value).trim();
}

function normalizeCellValue(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim();
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return '';
    }
    return JSON.stringify(value);
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function extractExtraFields(
  record: Record<string, unknown>,
  excludedKeys: string[],
): Record<string, string> {
  const excluded = new Set(excludedKeys);
  const out: Record<string, string> = {};

  for (const [key, value] of Object.entries(record)) {
    if (excluded.has(key)) {
      continue;
    }
    const normalized = normalizeCellValue(value);
    if (normalized !== '') {
      out[key] = normalized;
    }
  }

  return out;
}

async function readExcelRows(file: File): Promise<Record<string, unknown>[]> {
  const raw = await file.arrayBuffer();
  const workbook = XLSX.read(raw, { type: 'array' });
  const firstSheetName = workbook.SheetNames[0];
  if (!firstSheetName) {
    throw new Error(`Planilha sem abas em ${file.name}`);
  }
  const sheet = workbook.Sheets[firstSheetName];
  const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
  return rows;
}

function normalizeHeader(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/[^a-z0-9$ ]/g, '');
}

async function readHoldingRows(file: File): Promise<Record<string, unknown>[]> {
  const raw = await file.arrayBuffer();
  const workbook = XLSX.read(raw, { type: 'array' });
  const firstSheetName = workbook.SheetNames[0];
  if (!firstSheetName) {
    throw new Error(`Planilha sem abas em ${file.name}`);
  }

  const sheet = workbook.Sheets[firstSheetName];
  const matrix = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, defval: '' });

  const requiredHeaders = ['account number', 'name', 'product type', 'market value $'];
  let headerRowIndex = -1;
  let bestScore = 0;

  for (let i = 0; i < matrix.length; i += 1) {
    const row = matrix[i];
    if (!Array.isArray(row) || row.length === 0) {
      continue;
    }
    const normalized = row.map((cell) => normalizeHeader(cell));
    const score = requiredHeaders.reduce(
      (total, header) => total + (normalized.some((cell) => cell.includes(header)) ? 1 : 0),
      0,
    );
    if (score > bestScore) {
      bestScore = score;
      headerRowIndex = i;
    }
  }

  if (headerRowIndex < 0 || bestScore < 3) {
    throw new Error('Nao foi possivel identificar a tabela de holdings no arquivo.');
  }

  const rawHeaders = matrix[headerRowIndex] as unknown[];
  const headers = rawHeaders.map((cell, index) => {
    const value = String(cell ?? '').trim();
    return value || `col_${index + 1}`;
  });

  const rows: Record<string, unknown>[] = [];
  for (let i = headerRowIndex + 1; i < matrix.length; i += 1) {
    const row = matrix[i] as unknown[];
    if (!Array.isArray(row)) {
      continue;
    }
    if (!row.some((cell) => normalizeText(cell) !== '' && normalizeText(cell) !== '-')) {
      continue;
    }

    const out: Record<string, unknown> = {};
    headers.forEach((header, idx) => {
      out[header] = row[idx] ?? '';
    });
    rows.push(out);
  }

  return rows;
}

function mapDeParaCarteirasData(payload: unknown): RFRow[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .filter((item) =>
      Boolean(
        normalizeText(pickFirst(item, ['Carteira', 'carteira'])) ||
          normalizeText(pickFirst(item, ['Conta', 'conta'])) ||
          normalizeText(pickFirst(item, ['WalletID', 'walletid', 'walletId', 'WalletId'])),
      ),
    )
    .map((item, idx) => {
      const carteira = normalizeText(pickFirst(item, ['Carteira', 'carteira']));
      const conta = normalizeText(pickFirst(item, ['Conta', 'conta']));
      const contaFormatoAntigo = normalizeText(
        pickFirst(item, [
          'Conta Formato Antigo',
          'conta formato antigo',
          'ContaFormatoAntigo',
          'contaFormatoAntigo',
        ]),
      );
      const walletId = normalizeText(
        pickFirst(item, ['WalletID', 'walletid', 'walletId', 'WalletId']),
      );
      const extraFields = extractExtraFields(item, [
        'Carteira',
        'carteira',
        'Conta',
        'conta',
        'Conta Formato Antigo',
        'conta formato antigo',
        'ContaFormatoAntigo',
        'contaFormatoAntigo',
        'WalletID',
        'walletid',
        'walletId',
        'WalletId',
      ]);

      return {
        id: walletId || `depara-${idx}`,
        name: carteira,
        category: conta || 'SEM CONTA',
        maturityDate: '',
        rate: '',
        indexer: contaFormatoAntigo,
        carteira,
        conta,
        contaFormatoAntigo,
        walletId,
        ...extraFields,
      };
    });
}

function mapHoldingData(payload: unknown): RFRow[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item, idx) => {
      const accountNumber = normalizeText(pickFirst(item, ['Account Number']));
      const holdingName = normalizeText(pickFirst(item, ['Name']));
      const productType = normalizeText(pickFirst(item, ['Product Type']));
      const asOf = normalizeDate(pickFirst(item, ['As of']));
      const symbol = normalizeText(pickFirst(item, ['Symbol']));
      const cusip = normalizeText(pickFirst(item, ['CUSIP']));
      const marketValue = normalizeText(pickFirst(item, ['Market Value ($)']));
      const dividendPerShare = normalizeText(pickFirst(item, ['Dividend Per Share ($)']));

      const extraFields = extractExtraFields(item, [
        'Account Number',
        'Name',
        'Product Type',
        'As of',
        'Symbol',
        'CUSIP',
        'Market Value ($)',
        'Dividend Per Share ($)',
      ]);

      return {
        id: `holding-${idx}-${accountNumber || holdingName || 'row'}`,
        name: holdingName,
        category: productType || 'SEM TIPO',
        maturityDate: asOf,
        rate: dividendPerShare,
        indexer: accountNumber,
        accountNumber,
        symbol,
        cusip,
        marketValue,
        ...extraFields,
      };
    })
    .filter((row) => Boolean(row.name || row.indexer || row.symbol || row.cusip));
}

const globalContainsFilter: FilterFn<RFRow> = (row, _columnId, filterValue) => {
  const query = String(filterValue ?? '').trim().toLowerCase();
  if (!query) {
    return true;
  }

  const combined = Object.entries(row.original)
    .filter(([key]) => key !== 'id')
    .map(([, value]) => value)
    .join(' ')
    .toLowerCase();

  return combined.includes(query);
};

function collectDatasetKeys(rows: RFRow[]): string[] {
  const keySet = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (key !== 'id') {
        keySet.add(key);
      }
    }
  }
  return Array.from(keySet);
}

function buildColumns(keys: string[], leadingKeys: string[]): ColumnDef<RFRow>[] {
  const leading = leadingKeys.filter((key) => keys.includes(key));
  const remaining = keys
    .filter((key) => !leading.includes(key))
    .sort((a, b) => a.localeCompare(b));

  const ordered = [...leading, ...remaining];
  return ordered.map((key) => ({
    accessorKey: key,
    header: key === 'category'
      ? 'Tipo/Categoria'
      : key === 'name'
      ? 'Nome'
      : key === 'maturityDate'
      ? 'Vencimento'
      : key === 'rate'
      ? 'Taxa'
      : key === 'indexer'
      ? 'Indexador'
      : key,
    enableGrouping: key === 'category',
  }));
}

function buildDefaultVisibility(
  keys: string[],
  defaultVisibleKeys: string[],
): ColumnVisibilityState {
  const defaults = new Set(defaultVisibleKeys);
  const visibility: ColumnVisibilityState = {};
  for (const key of keys) {
    visibility[key] = defaults.has(key);
  }
  return visibility;
}

type RfTableProps = {
  title: string;
  data: RFRow[];
  columns: ColumnDef<RFRow>[];
  globalFilter: string;
  columnFilters: ColumnFiltersState;
  onColumnFiltersChange: OnChangeFn<ColumnFiltersState>;
  grouping: GroupingState;
  onGroupingChange: OnChangeFn<GroupingState>;
  expanded: ExpandedState;
  onExpandedChange: OnChangeFn<ExpandedState>;
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;
  columnVisibility: ColumnVisibilityState;
  onColumnVisibilityChange: OnChangeFn<ColumnVisibilityState>;
  onProcess?: () => void;
  processCount?: number;
  onLeafRowClick?: (row: RFRow) => void;
};

function RfTable({
  title,
  data,
  columns,
  globalFilter,
  columnFilters,
  onColumnFiltersChange,
  grouping,
  onGroupingChange,
  expanded,
  onExpandedChange,
  sorting,
  onSortingChange,
  columnVisibility,
  onColumnVisibilityChange,
  onProcess,
  processCount = 0,
  onLeafRowClick,
}: RfTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showColumnEditor, setShowColumnEditor] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');

  const table = useReactTable({
    data,
    columns,
    state: {
      globalFilter,
      columnFilters,
      grouping,
      expanded,
      sorting,
      columnVisibility,
    },
    onColumnFiltersChange,
    onGroupingChange,
    onExpandedChange,
    onSortingChange,
    onColumnVisibilityChange,
    globalFilterFn: globalContainsFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getGroupedRowModel: getGroupedRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  });

  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 44,
    overscan: 14,
  });

  const items = virtualizer.getVirtualItems();
  const editableColumns = table
    .getAllLeafColumns()
    .filter((column) =>
      column.id.toLowerCase().includes(columnSearch.trim().toLowerCase()),
    );
  const hasOpenOverlay = showColumnEditor;

  return (
    <section
      className={`glass relative rounded-xl border border-white/10 p-4 ${
        hasOpenOverlay ? 'z-[70]' : 'z-0'
      }`}
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowColumnEditor((current) => !current)}
              className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
            >
              Editar colunas
            </button>
            {showColumnEditor && (
              <div className="absolute left-0 top-9 z-[80] w-72 rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl">
                <div className="mb-2 text-xs font-semibold text-slate-300">
                  Colunas detectadas ({table.getAllLeafColumns().length})
                </div>
                <input
                  value={columnSearch}
                  onChange={(event) => setColumnSearch(event.target.value)}
                  placeholder="Buscar campo..."
                  className="mb-2 block w-full rounded border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs text-slate-200 outline-none focus:border-brand-500"
                />
                <div className="mb-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => table.getAllLeafColumns().forEach((column) => column.toggleVisibility(true))}
                    className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800"
                  >
                    Selecionar todos
                  </button>
                  <button
                    type="button"
                    onClick={() => table.getAllLeafColumns().forEach((column) => column.toggleVisibility(false))}
                    className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800"
                  >
                    Limpar
                  </button>
                </div>
                <div className="max-h-72 space-y-2 overflow-auto pr-1">
                  {editableColumns.map((column) => (
                    <label key={column.id} className="flex items-center gap-2 text-xs text-slate-200">
                      <input
                        type="checkbox"
                        checked={column.getIsVisible()}
                        onChange={column.getToggleVisibilityHandler()}
                        className="rounded border-slate-600 bg-slate-950"
                      />
                      <span>
                        {typeof column.columnDef.header === 'string'
                          ? column.columnDef.header
                          : column.id}
                      </span>
                    </label>
                  ))}
                  {editableColumns.length === 0 && (
                    <div className="text-xs text-slate-400">Nenhuma coluna encontrada.</div>
                  )}
                </div>
              </div>
            )}
          </div>
          {onProcess && (
            <>
              <button
                type="button"
                onClick={onProcess}
                disabled={processCount === 0}
                className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Processar
              </button>
              <span className="text-xs text-slate-300">
                {processCount} linha(s) para processamento
              </span>
            </>
          )}
        </div>
        <span className="text-xs text-slate-400">{rows.length} linhas visiveis</span>
      </header>

      <div ref={containerRef} className="h-[68vh] overflow-auto rounded-lg border border-white/10">
        <table className="min-w-[1100px] w-full text-sm text-slate-200">
          <thead className="sticky top-0 z-10 bg-slate-900/95">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-white/10">
                {headerGroup.headers.map((header) => {
                  const filterValue = header.column.getFilterValue();
                  return (
                    <th key={header.id} className="px-3 py-2 text-left align-top">
                      <div className="mb-2">
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          disabled={!header.column.getCanSort()}
                          className="inline-flex items-center gap-1 font-semibold text-slate-100 disabled:cursor-default"
                        >
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                          {{
                            asc: '↑',
                            desc: '↓',
                          }[header.column.getIsSorted() as 'asc' | 'desc'] ?? null}
                        </button>
                      </div>
                      {header.column.getCanFilter() && (
                        <input
                          value={String(filterValue ?? '')}
                          onChange={(event) => header.column.setFilterValue(event.target.value)}
                          placeholder="Filtrar"
                          className="block w-full rounded border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs text-slate-200 outline-none focus:border-brand-500"
                        />
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>

          <tbody style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
            {items.map((virtualRow) => {
              const row = rows[virtualRow.index];
              if (!row) {
                return null;
              }

              const isLeaf = !row.getCanExpand();

              return (
                <tr
                  key={row.id}
                  className={`absolute left-0 top-0 w-full border-b border-white/5 ${
                    isLeaf && onLeafRowClick
                      ? 'cursor-pointer hover:bg-brand-500/10'
                      : 'bg-slate-900/20 hover:bg-slate-800/30'
                  }`}
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                  onClick={() => {
                    if (isLeaf && onLeafRowClick) {
                      onLeafRowClick(row.original);
                    }
                  }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 align-top">
                      {cell.getIsGrouped() ? (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            row.toggleExpanded();
                          }}
                          className="inline-flex items-center gap-2 text-slate-100"
                        >
                          <span>{row.getIsExpanded() ? '▾' : '▸'}</span>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          <span className="text-xs text-slate-400">({row.subRows.length})</span>
                        </button>
                      ) : cell.getIsPlaceholder() ? null : (
                        flexRender(cell.column.columnDef.cell, cell.getContext())
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function applyPrefilter(
  filters: ColumnFiltersState,
  indexer: string,
  maturityDate: string,
): ColumnFiltersState {
  const remaining = filters.filter(
    (entry) => entry.id !== 'indexer' && entry.id !== 'maturityDate',
  );

  if (indexer) {
    remaining.push({ id: 'indexer', value: indexer });
  }
  if (maturityDate) {
    remaining.push({ id: 'maturityDate', value: maturityDate });
  }

  return remaining;
}

export default function ProcessamentoExcel() {
  const [beehusFile, setBeehusFile] = useState<File | null>(null);
  const [xpFile, setXpFile] = useState<File | null>(null);

  const [beehusRows, setBeehusRows] = useState<RFRow[] | null>(null);
  const [xpRows, setXpRows] = useState<RFRow[] | null>(null);

  const [loadingBeehus, setLoadingBeehus] = useState(false);
  const [loadingXP, setLoadingXP] = useState(false);
  const [errorBeehus, setErrorBeehus] = useState<string | null>(null);
  const [errorXP, setErrorXP] = useState<string | null>(null);

  const [globalFilter, setGlobalFilter] = useState('');
  const [leftColumnFilters, setLeftColumnFilters] = useState<ColumnFiltersState>([]);
  const [rightColumnFilters, setRightColumnFilters] = useState<ColumnFiltersState>([]);

  const [leftGrouping, setLeftGrouping] = useState<GroupingState>(['category']);
  const [rightGrouping, setRightGrouping] = useState<GroupingState>(['category']);

  const [leftExpanded, setLeftExpanded] = useState<ExpandedState>(true);
  const [rightExpanded, setRightExpanded] = useState<ExpandedState>(true);
  const [leftSorting, setLeftSorting] = useState<SortingState>([]);
  const [rightSorting, setRightSorting] = useState<SortingState>([]);
  const [leftColumnVisibility, setLeftColumnVisibility] = useState<ColumnVisibilityState>({});
  const [rightColumnVisibility, setRightColumnVisibility] = useState<ColumnVisibilityState>({});

  const [xpPrefilter, setXpPrefilter] = useState<{ indexer: string; maturityDate: string } | null>(null);

  const applyUpdater = <T,>(updater: Updater<T>, current: T): T =>
    typeof updater === 'function' ? (updater as (old: T) => T)(current) : updater;

  const onLeftColumnFiltersChange: OnChangeFn<ColumnFiltersState> = (updater) => {
    setLeftColumnFilters((current) => applyUpdater(updater, current));
  };

  const onRightColumnFiltersChange: OnChangeFn<ColumnFiltersState> = (updater) => {
    setRightColumnFilters((current) => applyUpdater(updater, current));
  };

  const onLeftGroupingChange: OnChangeFn<GroupingState> = (updater) => {
    setLeftGrouping((current) => applyUpdater(updater, current));
  };

  const onRightGroupingChange: OnChangeFn<GroupingState> = (updater) => {
    setRightGrouping((current) => applyUpdater(updater, current));
  };

  const onLeftExpandedChange: OnChangeFn<ExpandedState> = (updater) => {
    setLeftExpanded((current) => applyUpdater(updater, current));
  };

  const onRightExpandedChange: OnChangeFn<ExpandedState> = (updater) => {
    setRightExpanded((current) => applyUpdater(updater, current));
  };

  const onLeftSortingChange: OnChangeFn<SortingState> = (updater) => {
    setLeftSorting((current) => applyUpdater(updater, current));
  };

  const onRightSortingChange: OnChangeFn<SortingState> = (updater) => {
    setRightSorting((current) => applyUpdater(updater, current));
  };

  const onLeftColumnVisibilityChange: OnChangeFn<ColumnVisibilityState> = (updater) => {
    setLeftColumnVisibility((current) => applyUpdater(updater, current));
  };

  const onRightColumnVisibilityChange: OnChangeFn<ColumnVisibilityState> = (updater) => {
    setRightColumnVisibility((current) => applyUpdater(updater, current));
  };

  const hasBothDatasets = useMemo(
    () => Array.isArray(beehusRows) && Array.isArray(xpRows),
    [beehusRows, xpRows],
  );

  const parseBeehusFile = async (file: File) => {
    setLoadingBeehus(true);
    setErrorBeehus(null);
    try {
      const rows = await readExcelRows(file);
      const mapped = mapDeParaCarteirasData(rows);
      const keys = collectDatasetKeys(mapped);
      setBeehusRows(mapped);
      setLeftColumnVisibility(
        buildDefaultVisibility(keys, ['name', 'category', 'walletId', 'contaFormatoAntigo']),
      );
    } catch (error) {
      setBeehusRows(null);
      setErrorBeehus(error instanceof Error ? error.message : 'Falha ao processar De/Para Carteiras');
    } finally {
      setLoadingBeehus(false);
    }
  };

  const parseXPFile = async (file: File) => {
    setLoadingXP(true);
    setErrorXP(null);
    try {
      const rows = await readHoldingRows(file);
      const mapped = mapHoldingData(rows);
      const keys = collectDatasetKeys(mapped);
      setXpRows(mapped);
      setRightColumnVisibility(
        buildDefaultVisibility(keys, [
          'indexer',
          'name',
          'category',
          'symbol',
          'cusip',
          'marketValue',
          'maturityDate',
          'rate',
        ]),
      );
    } catch (error) {
      setXpRows(null);
      setErrorXP(error instanceof Error ? error.message : 'Falha ao processar Posicao Holding');
    } finally {
      setLoadingXP(false);
    }
  };

  const onBeehusUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setBeehusFile(file);
    if (file) {
      await parseBeehusFile(file);
    } else {
      setBeehusRows(null);
    }
  };

  const onXPUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setXpFile(file);
    if (file) {
      await parseXPFile(file);
    } else {
      setXpRows(null);
    }
  };

  const handleBeehusRowClick = (row: RFRow) => {
    const indexer = row.indexer;
    const maturityDate = row.maturityDate;

    setXpPrefilter({ indexer, maturityDate });
    setRightColumnFilters((current) => applyPrefilter(current, indexer, maturityDate));
  };

  const clearXpPrefilter = () => {
    setXpPrefilter(null);
    setRightColumnFilters((current) => applyPrefilter(current, '', ''));
  };

  const beehusColumns = useMemo(
    () =>
      buildColumns(
        collectDatasetKeys(beehusRows ?? []),
        ['name', 'category', 'walletId', 'contaFormatoAntigo', 'maturityDate', 'rate', 'indexer'],
      ),
    [beehusRows],
  );

  const xpColumns = useMemo(
    () =>
      buildColumns(
        collectDatasetKeys(xpRows ?? []),
        ['indexer', 'name', 'category', 'symbol', 'cusip', 'marketValue', 'maturityDate', 'rate'],
      ),
    [xpRows],
  );

  const processPositionsExcel = async () => {
    if (!beehusFile || !xpFile) {
      setErrorXP('Selecione os arquivos De/Para Carteiras e Posicao Holding antes de processar.');
      return;
    }

    try {
      setErrorXP(null);
      const formData = new FormData();
      formData.append('depara_file', beehusFile);
      formData.append('holdings_file', xpFile);

      const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiBase}/processamento-excel/process`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Falha no processamento (${response.status})`);
      }

      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const filenameMatch = disposition.match(/filename=\"?([^"]+)\"?/i);
      const filename = filenameMatch?.[1] || `positions_processado_V6-2-${Date.now()}.xlsx`;

      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setErrorXP(error instanceof Error ? error.message : 'Falha ao processar arquivo.');
    }
  };

  return (
    <Layout>
      <div className="mx-auto max-w-[1800px] space-y-6 p-8">
        <header className="space-y-2">
          <h2 className="text-2xl font-bold text-white">Processamento Excel</h2>
          <p className="text-slate-400">
            Faça upload do De/Para Carteiras (Excel) e da Posicao Holding (Excel) para comparação.
          </p>
        </header>

        <section className="glass rounded-xl border border-white/10 p-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">
                Upload De/Para Carteiras
              </label>
              <input
                type="file"
                accept=".xlsx,.xls,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                onChange={onBeehusUpload}
                className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-brand-500/20 file:px-4 file:py-2 file:font-semibold file:text-brand-200 hover:file:bg-brand-500/30"
              />
              <div className="text-xs text-slate-400">
                {loadingBeehus
                  ? 'Processando planilha De/Para Carteiras...'
                  : beehusFile?.name || 'Nenhum arquivo selecionado'}
              </div>
              {errorBeehus && <div className="text-xs text-red-300">{errorBeehus}</div>}
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">Upload Posicao Holding</label>
              <input
                type="file"
                accept=".xlsx,.xls,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                onChange={onXPUpload}
                className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-brand-500/20 file:px-4 file:py-2 file:font-semibold file:text-brand-200 hover:file:bg-brand-500/30"
              />
              <div className="text-xs text-slate-400">
                {loadingXP ? 'Processando planilha Posicao Holding...' : xpFile?.name || 'Nenhum arquivo selecionado'}
              </div>
              {errorXP && <div className="text-xs text-red-300">{errorXP}</div>}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <input
              value={globalFilter}
              onChange={(event) => setGlobalFilter(event.target.value)}
              placeholder="Busca global sincronizada (carteira, conta, wallet, account number, symbol, cusip...)"
              className="w-full rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-200 outline-none focus:border-brand-500"
            />
            {xpPrefilter && (
              <div className="inline-flex items-center gap-2">
                <span className="inline-flex items-center rounded-full border border-brand-500/40 bg-brand-500/10 px-3 py-2 text-xs text-brand-200">
                  Prefiltro XP: {xpPrefilter.indexer || 'Sem indexador'} +{' '}
                  {xpPrefilter.maturityDate || 'Sem vencimento'}
                </span>
                <button
                  type="button"
                  onClick={clearXpPrefilter}
                  className="rounded-full border border-slate-600 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800"
                >
                  Limpar prefiltro
                </button>
              </div>
            )}
          </div>
        </section>

        {hasBothDatasets ? (
          <section className="grid grid-cols-2 gap-6 max-xl:grid-cols-1">
            <RfTable
              title="De/Para Carteiras"
              data={beehusRows ?? []}
              columns={beehusColumns}
              globalFilter={globalFilter}
              columnFilters={leftColumnFilters}
              onColumnFiltersChange={onLeftColumnFiltersChange}
              grouping={leftGrouping}
              onGroupingChange={onLeftGroupingChange}
              expanded={leftExpanded}
              onExpandedChange={onLeftExpandedChange}
              sorting={leftSorting}
              onSortingChange={onLeftSortingChange}
              columnVisibility={leftColumnVisibility}
              onColumnVisibilityChange={onLeftColumnVisibilityChange}
              onLeafRowClick={handleBeehusRowClick}
            />

            <RfTable
              title="Posicao Holding"
              data={xpRows ?? []}
              columns={xpColumns}
              globalFilter={globalFilter}
              columnFilters={rightColumnFilters}
              onColumnFiltersChange={onRightColumnFiltersChange}
              grouping={rightGrouping}
              onGroupingChange={onRightGroupingChange}
              expanded={rightExpanded}
              onExpandedChange={onRightExpandedChange}
              sorting={rightSorting}
              onSortingChange={onRightSortingChange}
              columnVisibility={rightColumnVisibility}
              onColumnVisibilityChange={onRightColumnVisibilityChange}
              onProcess={processPositionsExcel}
              processCount={xpRows?.length ?? 0}
            />
          </section>
        ) : (
          <section className="glass rounded-xl border border-white/10 p-6 text-sm text-slate-400">
            Faça upload dos arquivos Excel de De/Para Carteiras e Posicao Holding.
          </section>
        )}
      </div>
    </Layout>
  );
}

