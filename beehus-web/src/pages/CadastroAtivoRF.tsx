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
import Layout from '../components/Layout';

type RFRow = {
  id: string;
  name: string;
  category: string;
  maturityDate: string;
  rate: string;
  indexer: string;
  ticker: string;
  ctipseliccode: string;
};

type XPFixedIncomeRecord = Record<string, unknown>;

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

function normalizeCategory(value: unknown): string {
  const text = normalizeText(value);
  return text ? text.toUpperCase() : 'SEM CATEGORIA';
}

function normalizeRate(value: unknown, percentValue?: unknown): string {
  if (typeof value === 'number') {
    return `${value.toFixed(2)}%`;
  }
  if (value) {
    return normalizeText(value);
  }
  if (typeof percentValue === 'number') {
    return `${percentValue.toFixed(2)}%`;
  }
  return '';
}

async function readJsonFile(file: File): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      try {
        const text = String(reader.result ?? '');
        resolve(JSON.parse(text));
      } catch (error) {
        reject(new Error(`JSON invalido em ${file.name}`));
      }
    };

    reader.onerror = () => {
      reject(new Error(`Falha ao ler o arquivo ${file.name}`));
    };

    reader.readAsText(file);
  });
}

function mapBeehusData(payload: unknown): RFRow[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item, idx) => {
      const name = normalizeText(pickFirst(item, ['beehusName', 'name', 'asset', 'ticker', 'mainId']));
      const category = normalizeCategory(pickFirst(item, ['type', 'category', 'marketType']));
      const maturityDate = normalizeDate(
        pickFirst(item, ['maturityDate', 'dueDate', 'expirationDate', 'due_date']),
      );
      const indexer = normalizeText(pickFirst(item, ['indexer', 'indexDsc', 'strategy']));
      const rate = normalizeRate(item['yield'], item['indexerPercentual']);

      return {
        id: `beehus-${idx}-${name || 'ativo'}`,
        name,
        category,
        maturityDate,
        rate,
        indexer,
        ticker: normalizeText(pickFirst(item, ['ticker', 'mainId'])),
        ctipseliccode: '',
      };
    });
}

function flattenXPData(payload: unknown): XPFixedIncomeRecord[] {
  const maybeRecords = Array.isArray(payload)
    ? payload
    : (payload as { data?: unknown })?.data;

  if (!Array.isArray(maybeRecords)) {
    return [];
  }

  const flat: XPFixedIncomeRecord[] = [];
  for (const entry of maybeRecords) {
    if (!entry || typeof entry !== 'object') {
      continue;
    }

    const record = entry as Record<string, unknown>;
    const assets = record['assets'];
    if (!assets || typeof assets !== 'object') {
      continue;
    }

    const fixedIncome = (assets as Record<string, unknown>)['fixedIncome'];
    if (!Array.isArray(fixedIncome)) {
      continue;
    }

    for (const fi of fixedIncome) {
      if (!fi || typeof fi !== 'object') {
        continue;
      }

      flat.push({
        ...(fi as Record<string, unknown>),
        customerCode: record['customerCode'],
        clientId: record['clientId'],
      });
    }
  }

  return flat;
}

function mapXPData(payload: unknown): RFRow[] {
  const flat = flattenXPData(payload);

  return flat.map((item, idx) => {
    const name = normalizeText(pickFirst(item, ['asset', 'name', 'ticker', 'assetId', 'cetipSelicCode']));
    const category = normalizeCategory(pickFirst(item, ['marketType', 'type', 'category']));
    const maturityDate = normalizeDate(pickFirst(item, ['dueDate', 'maturityDate', 'expirationDate']));
    const indexer = normalizeText(pickFirst(item, ['indexDsc', 'indexer', 'strategy']));
    const rate = normalizeRate(item['rate'], item['percentage']);

    return {
      id: `xp-${idx}-${name || 'ativo'}`,
      name,
      category,
      maturityDate,
      rate,
      indexer,
      ticker: '',
      ctipseliccode: normalizeText(pickFirst(item, ['cetipSelicCode', 'ctipseliccode'])),
    };
  });
}

const globalContainsFilter: FilterFn<RFRow> = (row, _columnId, filterValue) => {
  const query = String(filterValue ?? '').trim().toLowerCase();
  if (!query) {
    return true;
  }

  const combined = [
    row.original.name,
    row.original.category,
    row.original.maturityDate,
    row.original.rate,
    row.original.indexer,
    row.original.ticker,
    row.original.ctipseliccode,
  ]
    .join(' ')
    .toLowerCase();

  return combined.includes(query);
};

const baseColumns: ColumnDef<RFRow>[] = [
  {
    accessorKey: 'name',
    header: 'Nome',
    enableGrouping: false,
  },
  {
    accessorKey: 'category',
    header: 'Tipo/Categoria',
    enableGrouping: true,
  },
  {
    accessorKey: 'maturityDate',
    header: 'Vencimento',
    enableGrouping: false,
  },
  {
    accessorKey: 'rate',
    header: 'Taxa',
    enableGrouping: false,
  },
  {
    accessorKey: 'indexer',
    header: 'Indexador',
    enableGrouping: false,
  },
];

const beehusColumns: ColumnDef<RFRow>[] = [
  {
    accessorKey: 'ticker',
    header: 'Ticker',
    enableGrouping: false,
  },
  ...baseColumns,
];

const xpColumns: ColumnDef<RFRow>[] = [
  {
    accessorKey: 'ctipseliccode',
    header: 'ctipseliccode',
    enableGrouping: false,
  },
  ...baseColumns,
];

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
  onLeafRowClick,
}: RfTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const table = useReactTable({
    data,
    columns,
    state: {
      globalFilter,
      columnFilters,
      grouping,
      expanded,
      sorting,
    },
    onColumnFiltersChange,
    onGroupingChange,
    onExpandedChange,
    onSortingChange,
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

  return (
    <section className="glass rounded-xl border border-white/10 p-4">
      <header className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
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

export default function CadastroAtivoRF() {
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

  const hasBothDatasets = useMemo(
    () => Array.isArray(beehusRows) && Array.isArray(xpRows),
    [beehusRows, xpRows],
  );

  const parseBeehusFile = async (file: File) => {
    setLoadingBeehus(true);
    setErrorBeehus(null);
    try {
      const json = await readJsonFile(file);
      setBeehusRows(mapBeehusData(json));
    } catch (error) {
      setBeehusRows(null);
      setErrorBeehus(error instanceof Error ? error.message : 'Falha ao processar Beehus');
    } finally {
      setLoadingBeehus(false);
    }
  };

  const parseXPFile = async (file: File) => {
    setLoadingXP(true);
    setErrorXP(null);
    try {
      const json = await readJsonFile(file);
      setXpRows(mapXPData(json));
    } catch (error) {
      setXpRows(null);
      setErrorXP(error instanceof Error ? error.message : 'Falha ao processar XP');
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

  return (
    <Layout>
      <div className="mx-auto max-w-[1800px] space-y-6 p-8">
        <header className="space-y-2">
          <h2 className="text-2xl font-bold text-white">Cadastro Ativo RF</h2>
          <p className="text-slate-400">
            Compare os ativos de Renda Fixa entre a base Beehus e a base XP com upload local de JSON.
          </p>
        </header>

        <section className="glass rounded-xl border border-white/10 p-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">
                Upload Base Beehus (Bonds)
              </label>
              <input
                type="file"
                accept=".json,application/json"
                onChange={onBeehusUpload}
                className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-brand-500/20 file:px-4 file:py-2 file:font-semibold file:text-brand-200 hover:file:bg-brand-500/30"
              />
              <div className="text-xs text-slate-400">
                {loadingBeehus
                  ? 'Processando arquivo Beehus...'
                  : beehusFile?.name || 'Nenhum arquivo selecionado'}
              </div>
              {errorBeehus && <div className="text-xs text-red-300">{errorBeehus}</div>}
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">Upload Base Nova XP</label>
              <input
                type="file"
                accept=".json,application/json"
                onChange={onXPUpload}
                className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-brand-500/20 file:px-4 file:py-2 file:font-semibold file:text-brand-200 hover:file:bg-brand-500/30"
              />
              <div className="text-xs text-slate-400">
                {loadingXP ? 'Processando arquivo XP...' : xpFile?.name || 'Nenhum arquivo selecionado'}
              </div>
              {errorXP && <div className="text-xs text-red-300">{errorXP}</div>}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <input
              value={globalFilter}
              onChange={(event) => setGlobalFilter(event.target.value)}
              placeholder="Busca global sincronizada (nome, taxa, indexador, vencimento...)"
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
              title="Base Beehus (Bonds)"
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
              onLeafRowClick={handleBeehusRowClick}
            />

            <RfTable
              title="Base Nova XP"
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
            />
          </section>
        ) : (
          <section className="glass rounded-xl border border-white/10 p-6 text-sm text-slate-400">
            Faça upload dos dois arquivos JSON e aguarde o parsing para visualizar as tabelas comparativas.
          </section>
        )}
      </div>
    </Layout>
  );
}
